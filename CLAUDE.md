# Expense Tracker — Project Context for Claude
# Always read this file at the start of every session.
# Update TODO.md after completing each task.

## Project overview
Personal expense tracking web app. Multi-tenant — multiple households share one deployment.
Stack: FastAPI + Jinja2 + Supabase (Postgres) + Render.com.
Repo: https://github.com/pog4333/expense-tracker (public)

## Critical rules — never break these
1. **service_role bypasses RLS** — every DB query MUST `.eq("household_id", hid)`. No exceptions.
2. **household_id must be in session cookie** — missing = infinite /login redirect loop.
3. **Balance triggers in DB** — inserting/deleting transactions auto-adjusts balances. Never manually update balances except via /accounts/{id}/adjust endpoint.
4. **Salary** — `is_salary=True` triggers `process_salary_deposit()` RPC which splits across buckets.
5. **Credit cards** — swiping debits bucket immediately. Paying bill = transfer type `cc_payment`.
6. **Refunds** — confirmed refund MUST credit both account AND original bucket_id from the expense.
7. **Merchant trigger** — uses `ON CONFLICT (name, household_id)`. NEVER `ON CONFLICT (name)`.
8. **category_id** — always `category_id if category_id else None`. Never pass empty string.
9. **Views → RPC functions** — v_current_month, v_pending_refunds, v_savings_goals, v_budget_limit_status, v_subscriptions, v_monthly_by_category, v_year_over_year are now RPC functions taking p_household_id. Don't query them as views.

## Tech stack
- Python 3.11, FastAPI, Uvicorn
- Jinja2 templates + plain HTML/CSS/JS (no React, no Node)
- Supabase (Postgres) — use LEGACY JWT keys (eyJ...), NOT new sb_publishable_ format
- itsdangerous signed session cookies
- Render.com free tier — sleeps after 15min, ~30s cold start
- PYTHON_VERSION=3.11.9 set as env var on Render

## File structure
```
expenses track/              ← Windows project root (space in name!)
  run.py / requirements.txt / Procfile / render.yaml / .python-version
  CLAUDE.md / TODO.md        ← always update these
  .gitignore / .env.example  ← never commit .env
  app/
    main.py                  ← registers all 9 routers
    config.py / database.py / auth.py
    routers/
      auth_routes.py         ← /login /logout /forgot-password /reset-password
      dashboard.py           ← / — uses RPC functions only
      transactions.py        ← /transactions/ — split, income, filters
      accounts.py            ← /accounts/
      adjustments.py         ← /accounts/{id}/adjust
      reports.py             ← /reports/
      backup.py              ← /backup/
      help.py                ← /help/
      categories.py          ← /categories/ — add/edit/delete + inline JSON endpoint
    templates/
      base.html              ← sidebar nav
      login / forgot_password / reset_password
      dashboard.html
      accounts/index.html
      transactions/ list, add, edit, transfer, split
      categories/index.html
      reports/ index, audit
      backup/index.html
      help/index.html
      errors/ 404, 500
    static/ manifest.json, sw.js
  sql/
    schema.sql / views.sql / functions.sql
    migration_01-04 / add_new_household.sql
    balance_adjustment.sql / fix_views_household.sql
```

## RPC functions (all need p_household_id except get_balance_check)
- get_balance_check() — uses my_household_id() helper internally
- process_salary_deposit(p_transaction_id, p_amount)
- get_spending_forecast(p_months_back)
- get_current_month(p_household_id)
- get_pending_refunds(p_household_id)
- get_budget_limit_status(p_household_id)
- get_savings_goals(p_household_id)
- get_subscriptions(p_household_id)
- get_monthly_by_category(p_household_id)
- get_year_over_year(p_household_id)
- import_from_csv(p_batch_id, p_imported_by, p_accounts, p_buckets, p_transactions)

## Production
- URL: https://expense-tracker-t2yw.onrender.com
- Supabase: rltddhbjghvdepdotrks.supabase.co
- Render env vars: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, SECRET_KEY
- SMTP/VAPID not yet configured

## Households
- aaaaaaaa-0000-0000-0000-000000000001 → Our Home (user + wife)
- 5e329244-926d-409f-a1cd-196efd014489 → Loveless-Granot (friend)

## Adding a new household
1. Supabase Auth → create user → copy UUID
2. Run add_new_household.sql with their name
3. INSERT into profiles (id, display_name, household_id)
4. User logs out and back in
5. If email limit hit → set password via SQL:
   update auth.users set encrypted_password = crypt('TempPass', gen_salt('bf')) where email = '...';

## Common mistakes to avoid
- Never rely on RLS — always filter by household_id in Python
- Never pass "" as category_id — use None
- Never ON CONFLICT (name) on merchants — must be (name, household_id)
- Never import pywin32/py-vapid/pywebpush in requirements.txt
- Never set secure=False on cookies in production (HTTPS on Render)
- Don't call v_* views that are now RPC functions
- When editing accounts.py savings goals: RPC returns .data, template expects plain list

## Session / auth flow
1. User POSTs /login → Python calls Supabase auth
2. Python fetches profile to get household_id
3. household_id stored in signed cookie via itsdangerous
4. login_required decorator checks cookie + household_id
5. Missing household_id → redirect to /login (not infinite loop because /login checks cookie validity)

## Transaction split logic (transactions.py)
- Single bucket: simple insert with type=expense/income
- Multiple buckets: inserts parent (type=split) + children (type=expense/income with split_parent_id)
- Salary: single insert with is_salary=True, then calls process_salary_deposit() RPC
- Manual income allocation: uses same split mechanism with tx_type=income

## See TODO.md for all completed and pending work.

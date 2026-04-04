# Expense Tracker — Project Context for Claude

## How to use this file
Paste this file at the start of any new conversation to get full context instantly.
Keep it updated as the project evolves — add bugs fixed, decisions made, and pending work.

## Project overview
Personal expense tracking web app. Multi-tenant — multiple households share one deployment.
Built: FastAPI + Jinja2 + Supabase (Postgres) + Render.com hosting.

## Tech stack
- Python 3.11, FastAPI, Uvicorn
- Jinja2 templates + plain HTML/CSS/JS (no React, no Node)
- Supabase (Postgres) — service_role key used server-side
- itsdangerous for signed session cookies
- Render.com free tier (sleeps after 15min, ~30s cold start)
- GitHub: private repo (user can share access)

## Critical architecture rules — ALWAYS follow these
1. **service_role bypasses RLS** — every query MUST include `.eq("household_id", hid)`. Never rely on RLS policies for data isolation.
2. **household_id must be in session cookie** — missing = infinite redirect loop to /login.
3. **Balance triggers in DB** — inserting/deleting transactions auto-adjusts account + bucket balances via Postgres triggers. Never manually update balances except via /accounts/{id}/adjust.
4. **Salary = special income** — `is_salary=True` checkbox triggers `process_salary_deposit()` RPC which splits amount across buckets per allocation_rules for that household.
5. **Credit cards** — swiping debits bucket immediately. Paying the bill = transfer type `cc_payment`.
6. **Refunds** — two stages: pending → confirmed. Confirmed refund MUST credit both account AND original bucket_id.
7. **Adjustments** — manual balance overrides require confirmation + reason, logged as `adjustment` type transaction.
8. **Merchant memory trigger** — uses `ON CONFLICT (name, household_id)` — the composite unique index. NOT `ON CONFLICT (name)` (that was the old single-tenant index, now removed).
9. **category_id is optional** — use `category_id if category_id else None` when inserting transactions. Never pass empty string.

## File structure
```
expenses track/          ← Windows project root (space in folder name)
  run.py                 ← uvicorn entry point
  requirements.txt       ← no pywin32, no py-vapid, no pywebpush
  Procfile               ← uvicorn app.main:app --host 0.0.0.0 --port $PORT
  render.yaml
  .python-version        ← 3.11.9
  .gitignore / .env.example
  CLAUDE.md              ← this file
  app/
    main.py              ← registers: auth_routes, dashboard, transactions, accounts,
                            adjustments, reports, backup, help, categories
    config.py / database.py / auth.py
    routers/
      auth_routes.py     ← /login /logout /forgot-password /reset-password
      dashboard.py       ← / — uses RPC functions, not views
      transactions.py    ← /transactions/
      accounts.py        ← /accounts/
      adjustments.py     ← /accounts/{id}/adjust, /accounts/buckets/{id}/adjust
      reports.py         ← /reports/ — uses RPC functions, not views
      backup.py          ← /backup/
      help.py            ← /help/
      categories.py      ← /categories/ (add/edit/delete)
    templates/
      base.html          ← sidebar: Dashboard, Transactions, Transfer,
                            Accounts & Buckets, Categories, Reports, Audit Log,
                            Backup & Restore, Help
      login.html / forgot_password.html / reset_password.html
      dashboard.html
      accounts/index.html
      transactions/ list, add, edit, transfer, split
      categories/index.html
      reports/ index, audit
      backup/index.html
      help/index.html
      errors/ 404, 500
    static/
      manifest.json / sw.js  ← PWA
  sql/
    schema.sql / views.sql / functions.sql
    migration_01 through 04
    add_new_household.sql
    balance_adjustment.sql
    fix_views_household.sql  ← converts views to RPC functions with p_household_id
```

## Database — key tables
profiles (id=auth.uid, household_id), households, accounts, buckets,
savings_goals, allocation_rules, categories, merchants, transactions,
budget_limits, import_batches, audit_log

## Transaction types (enum)
expense, income, transfer, split, adjustment

## Transfer subtypes: account, bucket, cc_payment
## Refund status: pending, confirmed

## RPC functions (all require household filtering)
- get_balance_check() — no param, uses my_household_id() helper
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

## Production info
- Render URL: https://expense-tracker-t2yw.onrender.com
- Supabase: rltddhbjghvdepdotrks.supabase.co
- Use LEGACY JWT keys in Render env vars (not new sb_publishable_ format)
- Render env: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, SECRET_KEY
- SMTP and VAPID not yet configured

## Households
- aaaaaaaa-0000-0000-0000-000000000001 → "Our Home" (user + wife)
- 5e329244-926d-409f-a1cd-196efd014489 → "Loveless-Granot" (friend)

## Adding a new household (manual process)
1. Supabase Auth → create user (set password directly via SQL if email limit hit)
2. Run add_new_household.sql with their household name
3. INSERT into profiles (id, display_name, household_id)
4. User logs out and back in

## Known bugs fixed
- [x] Infinite redirect loop — session cookie must include household_id
- [x] secure=True needed on Render (HTTPS)
- [x] Merchant memory trigger ON CONFLICT must use (name, household_id) composite index
- [x] category_id must be None not "" when inserting transactions
- [x] v_merchant_suggestions must catch exceptions (Cloudflare 1101 error)
- [x] Views replaced with RPC functions for household isolation (service_role bypasses RLS)
- [x] Allocation rules form shows all active buckets, not just ones with existing rules
- [x] Refund confirm credits bucket AND account

## Pending work (do these in order)
- [ ] Run fix_views_household.sql in Supabase (fixes data isolation between households)
- [ ] Categories need household_id seeded for Loveless-Granot household
- [ ] Split transaction between multiple buckets on the ADD form (not just after saving)
- [ ] Weekly email backup (SMTP not configured — Gmail app password needed)
- [ ] Push notifications (VAPID keys not configured)
- [ ] Offline PWA queue sync
- [ ] Admin page for managing users/households without SQL

## Common mistakes to avoid
- Never use .execute() on a view query without .eq("household_id", hid)
- Never pass empty string as category_id — use None
- Never use ON CONFLICT (name) on merchants — must be (name, household_id)
- Never import pywin32, py-vapid, pywebpush in requirements.txt (Windows-only or Rust deps)
- Never set secure=False on cookies in production
- Never use `v_current_month`, `v_pending_refunds`, `v_savings_goals` as views — they're now RPC functions

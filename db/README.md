# Expense Tracker — Database Setup

## Run order (Supabase SQL Editor)

Run these files **in order** — each one depends on the previous:

1. `schema.sql` — tables, indexes, RLS policies, seed data
2. `views.sql`  — query views for dashboard & reports
3. `functions.sql` — triggers, business logic, CSV import

Paste each file's contents into Supabase → SQL Editor → Run.

---

## Supabase project setup

1. Go to https://supabase.com → New project
2. Name: `expense-tracker`, pick a region close to you
3. Save your database password somewhere safe
4. Wait ~2 min for provisioning

### Create your two users

Authentication → Users → Invite user (do this twice, once per person)

### Get your API credentials

Settings → API — copy these for the Python backend:

| Variable              | Where to find it          |
|-----------------------|---------------------------|
| `SUPABASE_URL`        | Project URL               |
| `SUPABASE_ANON_KEY`   | anon / public key         |
| `SUPABASE_SERVICE_KEY`| service_role key (secret) |

---

## What each file does

### schema.sql
- 14 tables covering every feature in the spec
- `import_batch_id` column on transactions tracks which CSV restore created each row
- `initial_balance` on accounts — set once, never changes, used to verify history
- Audit trigger on transactions fires automatically on every insert/update/delete

### views.sql
- `v_transactions` — full detail join (used by transaction list)
- `v_monthly_by_category` / `v_monthly_by_bucket` — reports
- `v_current_month` — dashboard snapshot
- `v_daily_spending` — last 90 days for daily/weekly charts
- `v_pending_refunds` — refunds waiting to be confirmed
- `v_subscriptions` — auto-detected recurring charges
- `v_year_over_year` — YoY comparison
- `v_savings_goals` — goal progress with % complete
- `v_budget_limit_status` — budget warnings

### functions.sql
- **Balance triggers** — every insert/update/delete on transactions automatically adjusts account and bucket balances. You never manually update balances.
- **Salary allocation** — `process_salary_deposit()` splits income across buckets per your allocation rules
- **Merchant memory** — trigger auto-updates the merchants table on every new expense
- **Forecasting** — `get_spending_forecast(n_months)` returns average monthly spend per category
- **Balance check** — `get_balance_check()` verifies accounts total = buckets total; warns if not
- **Allocation validation** — `validate_allocation_rules()` ensures percentages sum to 100
- **CSV import** — `import_from_csv()` does atomic all-or-nothing restore; on any error the entire import rolls back and the `import_batches` table records what went wrong

---

## Key design decisions

**Credit cards**: Swiping a card debits your bucket immediately (money is allocated). The account balance only drops when you pay the credit card bill — that's a transfer from your bank account to the card account.

**Refunds**: A refund starts as `pending` on the original expense row. When the money actually arrives, Python creates a new `income` transaction and sets the original to `confirmed`. Reports exclude pending refunds from spending totals.

**Exact balance match warning**: `get_balance_check()` compares sum of all account balances vs sum of all bucket balances. The Python backend calls this after every transaction and shows a warning banner if they diverge.

**CSV restore is atomic**: If any row in the CSV fails validation, the entire import rolls back — your database is never left in a partial state. The `import_batches` table records every attempt with success/failure detail.

**Audit log**: Populated automatically by database trigger — no Python code needed. Accessible via `select * from audit_log order by changed_at desc`.

# Expense Tracker — TODO

## Status key
- [x] Done
- [~] Partially done / needs testing
- [ ] Not started

---

## Completed features

### Database
- [x] Schema v2 — all tables with household_id
- [x] Multi-tenant migration (4 SQL files)
- [x] Balance triggers (insert/update/delete auto-adjusts balances)
- [x] Salary allocation RPC
- [x] Merchant memory trigger (ON CONFLICT name, household_id)
- [x] Forecast function
- [x] Balance check function
- [x] Audit log trigger
- [x] Views converted to RPC functions for household isolation
- [x] fix_views_household.sql applied

### Auth
- [x] Login / logout with signed session cookies
- [x] household_id stored in session cookie
- [x] Forgot password flow
- [x] Reset password page
- [x] Redirect loop fix (checks household_id before redirecting)
- [x] secure=True for HTTPS on Render

### Accounts & Buckets
- [x] Add / rename / deactivate / reactivate / delete accounts
- [x] Add / rename / deactivate / reactivate / delete buckets
- [x] Initial balance setup
- [x] Manual balance adjustment (with reason + audit trail)
- [x] Salary allocation rules (all active buckets shown)
- [x] Savings goals

### Transactions
- [x] Add expense (single bucket)
- [x] Add income (single bucket)
- [x] Add salary (auto-allocates)
- [x] Split transaction across multiple buckets (on add form)
- [x] Manual income allocation across buckets
- [x] Edit transaction
- [x] Delete transaction
- [x] Refund — pending + confirmed (credits both account and original bucket)
- [x] Transfer — account, bucket, cc_payment
- [x] Transaction list with filters (account / bucket / category / type)
- [x] Merchant autocomplete with graceful error handling

### Categories
- [x] Categories page (list, add, rename, delete)
- [x] Inline "Add category" button on transaction form
- [x] Two-level (parent + subcategory)

### Reports
- [x] Monthly by category
- [x] Year-over-year
- [x] Subscription detection
- [x] Spending forecast
- [x] CSV export (zip with transactions + accounts + buckets)
- [x] Audit log page

### Backup & Restore
- [x] Export zip (transactions, accounts, buckets CSVs)
- [x] Import from zip (all-or-nothing atomic restore)
- [x] Import history log

### Multi-tenant
- [x] household_id on all tables
- [x] All queries filter by household_id explicitly (service_role bypasses RLS)
- [x] Household isolation verified

### Help
- [x] Interactive help page (9 steps)

### Infrastructure
- [x] PWA manifest + service worker
- [x] Deployed on Render.com
- [x] GitHub repo: https://github.com/pog4333/expense-tracker

---

## In progress / needs testing

- [~] Categories 500 error fix — template folder was missing, now added
- [~] Transaction split between buckets — built, needs real-world test
- [~] Inline category add on transaction form — built, needs test

---

## Pending features

### High priority
- [ ] Weekly email backup (needs Gmail app password in .env + Render env vars)
  - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, BACKUP_EMAIL_TO
  - Use APScheduler (already in requirements) to run weekly
- [ ] Fix get_savings_goals call in accounts.py — currently returns `.data` but template expects list directly

### Medium priority
- [ ] Push notifications (browser) — needs VAPID keys generated + configured
- [ ] Offline PWA queue — transactions entered offline should sync when back online
- [ ] Admin page — add/manage users and households without SQL

### Nice to have
- [ ] Keep-alive ping to prevent Render free tier sleep
- [ ] Dark/light theme toggle
- [ ] Mobile quick-add shortcut (floating + button on dashboard)
- [ ] Budget limit alerts (warn when approaching monthly limit)
- [ ] Subscription auto-detection notifications

---

## Known bugs to watch for
- Merchant memory trigger must use ON CONFLICT (name, household_id) — NOT (name)
- category_id must be None not "" when inserting — use `category_id if category_id else None`
- Never use v_current_month, v_pending_refunds, v_savings_goals as views — they are now RPC functions
- service_role key bypasses ALL RLS — always filter by household_id in Python queries
- Savings goals in accounts page: check if .data is needed or not after get_savings_goals RPC call

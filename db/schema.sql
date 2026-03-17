-- ============================================================
-- Expense Tracker — Schema v2
-- Run in Supabase SQL Editor
-- ============================================================

create extension if not exists "pgcrypto";


-- ============================================================
-- USERS
-- ============================================================
create table public.profiles (
    id           uuid primary key references auth.users(id) on delete cascade,
    display_name text not null,
    created_at   timestamptz default now()
);


-- ============================================================
-- FINANCIAL ACCOUNTS
-- ============================================================
create type account_type as enum ('checking', 'savings', 'credit_card', 'debit_card');

create table public.accounts (
    id                uuid primary key default gen_random_uuid(),
    name              text not null,
    type              account_type not null,
    balance           numeric(12,2) default 0,
    initial_balance   numeric(12,2) default 0,
    credit_limit      numeric(12,2),
    linked_account_id uuid references public.accounts(id) on delete set null,
    is_active         boolean default true,
    created_at        timestamptz default now()
);


-- ============================================================
-- BUDGET BUCKETS
-- ============================================================
create table public.buckets (
    id           uuid primary key default gen_random_uuid(),
    name         text not null,
    balance      numeric(12,2) default 0,
    sort_order   int default 0,
    is_active    boolean default true,
    created_at   timestamptz default now()
);


-- ============================================================
-- SAVINGS GOALS
-- ============================================================
create table public.savings_goals (
    id            uuid primary key default gen_random_uuid(),
    bucket_id     uuid not null references public.buckets(id) on delete cascade,
    name          text not null,
    target_amount numeric(12,2) not null,
    target_date   date,
    is_achieved   boolean default false,
    created_at    timestamptz default now()
);


-- ============================================================
-- SALARY ALLOCATION RULES
-- ============================================================
create table public.allocation_rules (
    id          uuid primary key default gen_random_uuid(),
    bucket_id   uuid not null references public.buckets(id) on delete cascade,
    percentage  numeric(5,2) not null,
    updated_at  timestamptz default now()
);


-- ============================================================
-- CATEGORIES (two-level, self-referential)
-- ============================================================
create table public.categories (
    id         uuid primary key default gen_random_uuid(),
    name       text not null,
    parent_id  uuid references public.categories(id) on delete cascade,
    sort_order int default 0,
    created_at timestamptz default now()
);


-- ============================================================
-- MERCHANT MEMORY
-- ============================================================
create table public.merchants (
    id                  uuid primary key default gen_random_uuid(),
    name                text not null unique,
    default_category_id uuid references public.categories(id) on delete set null,
    default_bucket_id   uuid references public.buckets(id) on delete set null,
    default_account_id  uuid references public.accounts(id) on delete set null,
    last_used           timestamptz default now(),
    use_count           int default 1
);


-- ============================================================
-- TRANSACTIONS
-- ============================================================
create type transaction_type   as enum ('expense', 'income', 'transfer', 'split');
create type refund_status_type as enum ('pending', 'confirmed');
create type transfer_type      as enum ('account', 'bucket', 'cc_payment');

create table public.transactions (
    id              uuid primary key default gen_random_uuid(),
    type            transaction_type not null default 'expense',
    date            date not null,
    merchant_name   text not null,
    amount          numeric(12,2) not null check (amount > 0),
    note            text,
    entered_by      uuid references public.profiles(id),
    is_salary       boolean default false,
    -- expense / income
    account_id      uuid references public.accounts(id),
    bucket_id       uuid references public.buckets(id),
    category_id     uuid references public.categories(id),
    -- refund
    refund_status   refund_status_type,
    refund_of_id    uuid references public.transactions(id) on delete set null,
    -- split
    split_parent_id uuid references public.transactions(id) on delete cascade,
    -- transfer
    transfer_type   transfer_type,
    from_account_id uuid references public.accounts(id),
    to_account_id   uuid references public.accounts(id),
    from_bucket_id  uuid references public.buckets(id),
    to_bucket_id    uuid references public.buckets(id),
    -- import tracking
    import_batch_id uuid,                     -- set when loaded from CSV backup
    created_at      timestamptz default now(),
    updated_at      timestamptz default now()
);


-- ============================================================
-- IMPORT BATCHES
-- Tracks every CSV import attempt for auditability.
-- ============================================================
create table public.import_batches (
    id              uuid primary key default gen_random_uuid(),
    imported_by     uuid references public.profiles(id),
    filename        text,
    status          text not null default 'pending',  -- pending, success, rolled_back
    total_rows      int default 0,
    imported_rows   int default 0,
    error_detail    text,                             -- populated on failure
    started_at      timestamptz default now(),
    completed_at    timestamptz
);


-- ============================================================
-- BUDGET LIMITS
-- ============================================================
create table public.budget_limits (
    id            uuid primary key default gen_random_uuid(),
    category_id   uuid not null references public.categories(id) on delete cascade,
    monthly_limit numeric(12,2) not null,
    is_active     boolean default true,
    updated_at    timestamptz default now(),
    unique(category_id)
);


-- ============================================================
-- OFFLINE QUEUE (PWA sync)
-- ============================================================
create table public.offline_queue (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references public.profiles(id),
    action     text not null,
    payload    jsonb not null,
    queued_at  timestamptz default now(),
    synced_at  timestamptz,
    sync_error text,
    is_synced  boolean default false
);


-- ============================================================
-- AUDIT LOG
-- ============================================================
create table public.audit_log (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid references public.profiles(id),
    action     text not null,
    table_name text not null,
    record_id  uuid not null,
    old_data   jsonb,
    new_data   jsonb,
    changed_at timestamptz default now()
);


-- ============================================================
-- NOTIFICATIONS
-- ============================================================
create table public.notification_log (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid references public.profiles(id),
    type       text not null,
    title      text not null,
    body       text,
    is_read    boolean default false,
    created_at timestamptz default now()
);


-- ============================================================
-- PUSH SUBSCRIPTIONS
-- ============================================================
create table public.push_subscriptions (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references public.profiles(id),
    endpoint   text not null unique,
    p256dh     text not null,
    auth       text not null,
    created_at timestamptz default now()
);


-- ============================================================
-- INDEXES
-- ============================================================
create index idx_tx_date           on public.transactions(date desc);
create index idx_tx_type           on public.transactions(type);
create index idx_tx_account        on public.transactions(account_id);
create index idx_tx_bucket         on public.transactions(bucket_id);
create index idx_tx_category       on public.transactions(category_id);
create index idx_tx_merchant       on public.transactions(merchant_name);
create index idx_tx_refund         on public.transactions(refund_status) where refund_status is not null;
create index idx_tx_split          on public.transactions(split_parent_id) where split_parent_id is not null;
create index idx_tx_import_batch   on public.transactions(import_batch_id) where import_batch_id is not null;
create index idx_audit_record      on public.audit_log(record_id, table_name);
create index idx_audit_time        on public.audit_log(changed_at desc);
create index idx_offline_unsynced  on public.offline_queue(user_id) where is_synced = false;
create index idx_notif_unread      on public.notification_log(user_id) where is_read = false;


-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
do $$ declare t text; begin
    for t in select unnest(array[
        'profiles','accounts','buckets','savings_goals','allocation_rules',
        'categories','merchants','transactions','import_batches','budget_limits',
        'offline_queue','audit_log','notification_log','push_subscriptions'
    ]) loop
        execute format('alter table public.%I enable row level security', t);
        execute format(
            'create policy "auth_full_access" on public.%I for all using (auth.role() = ''authenticated'')', t
        );
    end loop;
end $$;


-- ============================================================
-- AUDIT TRIGGER
-- ============================================================
create or replace function public.log_transaction_audit()
returns trigger language plpgsql security definer as $$
begin
    insert into public.audit_log(user_id, action, table_name, record_id, old_data, new_data)
    values (
        coalesce(
            case when TG_OP != 'DELETE' then NEW.entered_by end,
            OLD.entered_by
        ),
        TG_OP, TG_TABLE_NAME,
        coalesce(
            case when TG_OP != 'DELETE' then NEW.id end,
            OLD.id
        ),
        case when TG_OP = 'INSERT' then null else to_jsonb(OLD) end,
        case when TG_OP = 'DELETE' then null else to_jsonb(NEW) end
    );
    return coalesce(NEW, OLD);
end;
$$;

create trigger trg_audit_transactions
    after insert or update or delete on public.transactions
    for each row execute function public.log_transaction_audit();


-- ============================================================
-- SEED: categories
-- ============================================================
insert into public.categories (id, name, parent_id, sort_order) values
    ('11111111-0000-0000-0000-000000000001', 'Food',           null, 1),
    ('11111111-0000-0000-0000-000000000002', 'Housing',        null, 2),
    ('11111111-0000-0000-0000-000000000003', 'Transportation', null, 3),
    ('11111111-0000-0000-0000-000000000004', 'Health',         null, 4),
    ('11111111-0000-0000-0000-000000000005', 'Entertainment',  null, 5),
    ('11111111-0000-0000-0000-000000000006', 'Shopping',       null, 6),
    ('11111111-0000-0000-0000-000000000007', 'Personal',       null, 7),
    ('11111111-0000-0000-0001-000000000001', 'Groceries',        '11111111-0000-0000-0000-000000000001', 1),
    ('11111111-0000-0000-0001-000000000002', 'Restaurants',      '11111111-0000-0000-0000-000000000001', 2),
    ('11111111-0000-0000-0001-000000000003', 'Coffee',           '11111111-0000-0000-0000-000000000001', 3),
    ('11111111-0000-0000-0001-000000000004', 'Takeout',          '11111111-0000-0000-0000-000000000001', 4),
    ('11111111-0000-0000-0002-000000000001', 'Rent/Mortgage',    '11111111-0000-0000-0000-000000000002', 1),
    ('11111111-0000-0000-0002-000000000002', 'Utilities',        '11111111-0000-0000-0000-000000000002', 2),
    ('11111111-0000-0000-0002-000000000003', 'Repairs',          '11111111-0000-0000-0000-000000000002', 3),
    ('11111111-0000-0000-0002-000000000004', 'Insurance',        '11111111-0000-0000-0000-000000000002', 4),
    ('11111111-0000-0000-0003-000000000001', 'Gas',              '11111111-0000-0000-0000-000000000003', 1),
    ('11111111-0000-0000-0003-000000000002', 'Parking',          '11111111-0000-0000-0000-000000000003', 2),
    ('11111111-0000-0000-0003-000000000003', 'Uber/Lyft',        '11111111-0000-0000-0000-000000000003', 3),
    ('11111111-0000-0000-0003-000000000004', 'Car maintenance',  '11111111-0000-0000-0000-000000000003', 4),
    ('11111111-0000-0000-0004-000000000001', 'Doctor',           '11111111-0000-0000-0000-000000000004', 1),
    ('11111111-0000-0000-0004-000000000002', 'Pharmacy',         '11111111-0000-0000-0000-000000000004', 2),
    ('11111111-0000-0000-0004-000000000003', 'Gym',              '11111111-0000-0000-0000-000000000004', 3),
    ('11111111-0000-0000-0005-000000000001', 'Subscriptions',    '11111111-0000-0000-0000-000000000005', 1),
    ('11111111-0000-0000-0005-000000000002', 'Movies',           '11111111-0000-0000-0000-000000000005', 2),
    ('11111111-0000-0000-0005-000000000003', 'Travel',           '11111111-0000-0000-0000-000000000005', 3),
    ('11111111-0000-0000-0006-000000000001', 'Clothing',         '11111111-0000-0000-0000-000000000006', 1),
    ('11111111-0000-0000-0006-000000000002', 'Electronics',      '11111111-0000-0000-0000-000000000006', 2),
    ('11111111-0000-0000-0006-000000000003', 'Household',        '11111111-0000-0000-0000-000000000006', 3),
    ('11111111-0000-0000-0007-000000000001', 'Charity',          '11111111-0000-0000-0000-000000000007', 1),
    ('11111111-0000-0000-0007-000000000002', 'Gifts',            '11111111-0000-0000-0000-000000000007', 2),
    ('11111111-0000-0000-0007-000000000003', 'Education',        '11111111-0000-0000-0000-000000000007', 3);


-- ============================================================
-- SEED: buckets
-- ============================================================
insert into public.buckets (id, name, balance, sort_order) values
    ('22222222-0000-0000-0000-000000000001', 'Essential Expenses', 0, 1),
    ('22222222-0000-0000-0000-000000000002', 'Short Term Savings',  0, 2),
    ('22222222-0000-0000-0000-000000000003', 'Long Term Savings',   0, 3),
    ('22222222-0000-0000-0000-000000000004', 'Fun',                 0, 4),
    ('22222222-0000-0000-0000-000000000005', 'Charity',             0, 5),
    ('22222222-0000-0000-0000-000000000006', 'Investments',         0, 6);


-- ============================================================
-- SEED: allocation rules (must sum to 100)
-- ============================================================
insert into public.allocation_rules (bucket_id, percentage) values
    ('22222222-0000-0000-0000-000000000001', 40.00),
    ('22222222-0000-0000-0000-000000000002', 20.00),
    ('22222222-0000-0000-0000-000000000003', 20.00),
    ('22222222-0000-0000-0000-000000000004', 15.00),
    ('22222222-0000-0000-0000-000000000005',  5.00);

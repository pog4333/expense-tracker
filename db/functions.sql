-- ============================================================
-- Functions & Triggers — run after schema.sql and views.sql
-- ============================================================


-- ============================================================
-- TRIGGER: apply balance changes on transaction insert
-- ============================================================
create or replace function public.apply_transaction_to_balances()
returns trigger language plpgsql security definer as $$
begin
    if NEW.type = 'expense' then
        update public.accounts set balance = balance - NEW.amount where id = NEW.account_id;
        update public.buckets  set balance = balance - NEW.amount where id = NEW.bucket_id;

    elsif NEW.type = 'income' and NEW.is_salary = false then
        update public.accounts set balance = balance + NEW.amount where id = NEW.account_id;

    elsif NEW.type = 'transfer' then
        case NEW.transfer_type
            when 'account', 'cc_payment' then
                update public.accounts set balance = balance - NEW.amount where id = NEW.from_account_id;
                update public.accounts set balance = balance + NEW.amount where id = NEW.to_account_id;
            when 'bucket' then
                update public.buckets set balance = balance - NEW.amount where id = NEW.from_bucket_id;
                update public.buckets set balance = balance + NEW.amount where id = NEW.to_bucket_id;
        end case;
    end if;
    return NEW;
end;
$$;

create trigger trg_apply_transaction
    after insert on public.transactions
    for each row execute function public.apply_transaction_to_balances();


-- ============================================================
-- TRIGGER: reverse balance changes on transaction delete
-- ============================================================
create or replace function public.reverse_transaction_from_balances()
returns trigger language plpgsql security definer as $$
declare rule record; alloc_amount numeric;
begin
    if OLD.type = 'expense' then
        update public.accounts set balance = balance + OLD.amount where id = OLD.account_id;
        update public.buckets  set balance = balance + OLD.amount where id = OLD.bucket_id;

    elsif OLD.type = 'income' and OLD.is_salary = false then
        update public.accounts set balance = balance - OLD.amount where id = OLD.account_id;

    elsif OLD.type = 'income' and OLD.is_salary = true then
        -- reverse bucket allocation
        for rule in select bucket_id, percentage from public.allocation_rules loop
            alloc_amount := round(OLD.amount * rule.percentage / 100.0, 2);
            update public.buckets set balance = balance - alloc_amount where id = rule.bucket_id;
        end loop;
        update public.accounts set balance = balance - OLD.amount where id = OLD.account_id;

    elsif OLD.type = 'transfer' then
        case OLD.transfer_type
            when 'account', 'cc_payment' then
                update public.accounts set balance = balance + OLD.amount where id = OLD.from_account_id;
                update public.accounts set balance = balance - OLD.amount where id = OLD.to_account_id;
            when 'bucket' then
                update public.buckets set balance = balance + OLD.amount where id = OLD.from_bucket_id;
                update public.buckets set balance = balance - OLD.amount where id = OLD.to_bucket_id;
        end case;
    end if;
    return OLD;
end;
$$;

create trigger trg_reverse_transaction
    after delete on public.transactions
    for each row execute function public.reverse_transaction_from_balances();


-- ============================================================
-- TRIGGER: handle transaction UPDATE (reverse old, apply new)
-- ============================================================
create or replace function public.reapply_transaction_balances()
returns trigger language plpgsql security definer as $$
begin
    -- Reverse OLD row
    perform public.reverse_transaction_from_balances_direct(OLD);
    -- Apply NEW row
    perform public.apply_transaction_to_balances_direct(NEW);
    return NEW;
end;
$$;

-- Helper: apply a transaction row directly (used by update trigger)
create or replace function public.apply_transaction_to_balances_direct(t public.transactions)
returns void language plpgsql security definer as $$
declare rule record; alloc_amount numeric;
begin
    if t.type = 'expense' then
        update public.accounts set balance = balance - t.amount where id = t.account_id;
        update public.buckets  set balance = balance - t.amount where id = t.bucket_id;
    elsif t.type = 'income' and t.is_salary = false then
        update public.accounts set balance = balance + t.amount where id = t.account_id;
    elsif t.type = 'income' and t.is_salary = true then
        update public.accounts set balance = balance + t.amount where id = t.account_id;
        for rule in select bucket_id, percentage from public.allocation_rules loop
            alloc_amount := round(t.amount * rule.percentage / 100.0, 2);
            update public.buckets set balance = balance + alloc_amount where id = rule.bucket_id;
        end loop;
    elsif t.type = 'transfer' then
        case t.transfer_type
            when 'account', 'cc_payment' then
                update public.accounts set balance = balance - t.amount where id = t.from_account_id;
                update public.accounts set balance = balance + t.amount where id = t.to_account_id;
            when 'bucket' then
                update public.buckets set balance = balance - t.amount where id = t.from_bucket_id;
                update public.buckets set balance = balance + t.amount where id = t.to_bucket_id;
        end case;
    end if;
end;
$$;

-- Helper: reverse a transaction row directly (used by update trigger)
create or replace function public.reverse_transaction_from_balances_direct(t public.transactions)
returns void language plpgsql security definer as $$
declare rule record; alloc_amount numeric;
begin
    if t.type = 'expense' then
        update public.accounts set balance = balance + t.amount where id = t.account_id;
        update public.buckets  set balance = balance + t.amount where id = t.bucket_id;
    elsif t.type = 'income' and t.is_salary = false then
        update public.accounts set balance = balance - t.amount where id = t.account_id;
    elsif t.type = 'income' and t.is_salary = true then
        update public.accounts set balance = balance - t.amount where id = t.account_id;
        for rule in select bucket_id, percentage from public.allocation_rules loop
            alloc_amount := round(t.amount * rule.percentage / 100.0, 2);
            update public.buckets set balance = balance - alloc_amount where id = rule.bucket_id;
        end loop;
    elsif t.type = 'transfer' then
        case t.transfer_type
            when 'account', 'cc_payment' then
                update public.accounts set balance = balance + t.amount where id = t.from_account_id;
                update public.accounts set balance = balance - t.amount where id = t.to_account_id;
            when 'bucket' then
                update public.buckets set balance = balance + t.amount where id = t.from_bucket_id;
                update public.buckets set balance = balance - t.amount where id = t.to_bucket_id;
        end case;
    end if;
end;
$$;

create trigger trg_reapply_transaction
    after update on public.transactions
    for each row
    when (OLD.amount is distinct from NEW.amount
       or OLD.type is distinct from NEW.type
       or OLD.account_id is distinct from NEW.account_id
       or OLD.bucket_id  is distinct from NEW.bucket_id)
    execute function public.reapply_transaction_balances();


-- ============================================================
-- FUNCTION: process_salary_deposit
-- Call this from Python after inserting a salary transaction.
-- ============================================================
create or replace function public.process_salary_deposit(
    p_transaction_id uuid,
    p_amount         numeric
) returns void language plpgsql security definer as $$
declare rule record; alloc_amount numeric;
begin
    for rule in select bucket_id, percentage from public.allocation_rules loop
        alloc_amount := round(p_amount * rule.percentage / 100.0, 2);
        update public.buckets set balance = balance + alloc_amount where id = rule.bucket_id;
    end loop;
end;
$$;


-- ============================================================
-- TRIGGER: merchant memory auto-update on new expense
-- ============================================================
create or replace function public.update_merchant_memory()
returns trigger language plpgsql security definer as $$
begin
    insert into public.merchants(name, default_category_id, default_bucket_id, default_account_id, last_used, use_count)
    values (NEW.merchant_name, NEW.category_id, NEW.bucket_id, NEW.account_id, now(), 1)
    on conflict (name) do update set
        default_category_id = NEW.category_id,
        default_bucket_id   = NEW.bucket_id,
        default_account_id  = NEW.account_id,
        last_used           = now(),
        use_count           = merchants.use_count + 1;
    return NEW;
end;
$$;

create trigger trg_merchant_memory
    after insert on public.transactions
    for each row
    when (NEW.type = 'expense')
    execute function public.update_merchant_memory();


-- ============================================================
-- FUNCTION: get_spending_forecast
-- Returns average monthly spend per category over last N months.
-- Usage: select * from get_spending_forecast(6);
-- ============================================================
create or replace function public.get_spending_forecast(p_months_back int default 6)
returns table (
    category_id           uuid,
    category_name         text,
    parent_category_name  text,
    avg_monthly_spend     numeric,
    is_likely_recurring   boolean
) language plpgsql security definer as $$
begin
    return query
    with monthly as (
        select
            t.category_id,
            date_trunc('month', t.date) as month,
            sum(t.amount)               as monthly_total
        from public.transactions t
        where t.type = 'expense'
          and t.date >= date_trunc('month', current_date) - (p_months_back || ' months')::interval
          and t.date  < date_trunc('month', current_date)
        group by t.category_id, date_trunc('month', t.date)
    ),
    summary as (
        select
            m.category_id,
            avg(m.monthly_total)                                            as avg_spend,
            (count(distinct m.month)::numeric / p_months_back) >= 0.8      as recurring
        from monthly m
        group by m.category_id
    )
    select
        s.category_id,
        c.name                 as category_name,
        p.name                 as parent_category_name,
        round(s.avg_spend, 2)  as avg_monthly_spend,
        s.recurring            as is_likely_recurring
    from summary s
    join public.categories c on c.id = s.category_id
    left join public.categories p on p.id = c.parent_id
    order by s.avg_spend desc;
end;
$$;


-- ============================================================
-- FUNCTION: validate_allocation_rules
-- Returns an error if allocation percentages don't sum to 100.
-- Call before saving allocation changes.
-- ============================================================
create or replace function public.validate_allocation_rules()
returns table(is_valid boolean, total_pct numeric, message text)
language plpgsql security definer as $$
declare total numeric;
begin
    select coalesce(sum(percentage), 0) into total from public.allocation_rules;
    return query select
        total = 100,
        total,
        case when total = 100 then 'OK'
             else format('Allocations sum to %s%% — must be exactly 100%%', total)
        end;
end;
$$;


-- ============================================================
-- FUNCTION: get_balance_check
-- Returns warning if sum(account balances) != sum(bucket balances).
-- Run anytime to verify financial integrity.
-- ============================================================
create or replace function public.get_balance_check()
returns table(
    account_total  numeric,
    bucket_total   numeric,
    difference     numeric,
    is_balanced    boolean,
    message        text
) language plpgsql security definer as $$
declare
    acc_total numeric;
    bkt_total numeric;
begin
    select coalesce(sum(balance), 0) into acc_total from public.accounts where is_active = true;
    select coalesce(sum(balance), 0) into bkt_total from public.buckets  where is_active = true;
    return query select
        acc_total,
        bkt_total,
        acc_total - bkt_total,
        acc_total = bkt_total,
        case when acc_total = bkt_total then 'Balanced'
             else format('OUT OF BALANCE: accounts=%s, buckets=%s, diff=%s',
                         acc_total, bkt_total, acc_total - bkt_total)
        end;
end;
$$;


-- ============================================================
-- FUNCTION: import_from_csv
-- Atomic all-or-nothing import of accounts, buckets, transactions
-- from a parsed CSV payload (called from Python).
--
-- p_batch_id    : uuid created by Python before calling this
-- p_accounts    : jsonb array of account rows
-- p_buckets     : jsonb array of bucket rows
-- p_transactions: jsonb array of transaction rows
--
-- On ANY error the entire function rolls back (runs in a
-- transaction — Python must call it inside BEGIN/COMMIT).
-- ============================================================
create or replace function public.import_from_csv(
    p_batch_id      uuid,
    p_imported_by   uuid,
    p_accounts      jsonb,
    p_buckets       jsonb,
    p_transactions  jsonb
) returns jsonb language plpgsql security definer as $$
declare
    acc      jsonb;
    bkt      jsonb;
    tx       jsonb;
    acc_count int := 0;
    bkt_count int := 0;
    tx_count  int := 0;
    result    jsonb;
begin
    -- Mark batch as in-progress
    update public.import_batches
    set status = 'importing', total_rows = jsonb_array_length(p_transactions)
    where id = p_batch_id;

    -- ---- ACCOUNTS ----
    for acc in select * from jsonb_array_elements(p_accounts) loop
        insert into public.accounts(id, name, type, balance, initial_balance, credit_limit, is_active, created_at)
        values (
            (acc->>'id')::uuid,
            acc->>'name',
            (acc->>'type')::account_type,
            (acc->>'balance')::numeric,
            (acc->>'initial_balance')::numeric,
            nullif(acc->>'credit_limit', '')::numeric,
            coalesce((acc->>'is_active')::boolean, true),
            coalesce((acc->>'created_at')::timestamptz, now())
        )
        on conflict (id) do update set
            name            = excluded.name,
            type            = excluded.type,
            balance         = excluded.balance,
            initial_balance = excluded.initial_balance,
            credit_limit    = excluded.credit_limit,
            is_active       = excluded.is_active;
        acc_count := acc_count + 1;
    end loop;

    -- ---- BUCKETS ----
    for bkt in select * from jsonb_array_elements(p_buckets) loop
        insert into public.buckets(id, name, balance, sort_order, is_active, created_at)
        values (
            (bkt->>'id')::uuid,
            bkt->>'name',
            (bkt->>'balance')::numeric,
            coalesce((bkt->>'sort_order')::int, 0),
            coalesce((bkt->>'is_active')::boolean, true),
            coalesce((bkt->>'created_at')::timestamptz, now())
        )
        on conflict (id) do update set
            name       = excluded.name,
            balance    = excluded.balance,
            sort_order = excluded.sort_order,
            is_active  = excluded.is_active;
        bkt_count := bkt_count + 1;
    end loop;

    -- ---- TRANSACTIONS ----
    -- Disable balance triggers during import (balances come from the CSV directly)
    alter table public.transactions disable trigger trg_apply_transaction;
    alter table public.transactions disable trigger trg_reverse_transaction;
    alter table public.transactions disable trigger trg_reapply_transaction;

    for tx in select * from jsonb_array_elements(p_transactions) loop
        insert into public.transactions(
            id, type, date, merchant_name, amount, note, is_salary,
            account_id, bucket_id, category_id,
            refund_status, refund_of_id, split_parent_id,
            transfer_type, from_account_id, to_account_id,
            from_bucket_id, to_bucket_id,
            entered_by, import_batch_id, created_at, updated_at
        ) values (
            (tx->>'id')::uuid,
            (tx->>'type')::transaction_type,
            (tx->>'date')::date,
            tx->>'merchant_name',
            (tx->>'amount')::numeric,
            tx->>'note',
            coalesce((tx->>'is_salary')::boolean, false),
            nullif(tx->>'account_id',       '')::uuid,
            nullif(tx->>'bucket_id',        '')::uuid,
            nullif(tx->>'category_id',      '')::uuid,
            nullif(tx->>'refund_status',    '')::refund_status_type,
            nullif(tx->>'refund_of_id',     '')::uuid,
            nullif(tx->>'split_parent_id',  '')::uuid,
            nullif(tx->>'transfer_type',    '')::transfer_type,
            nullif(tx->>'from_account_id',  '')::uuid,
            nullif(tx->>'to_account_id',    '')::uuid,
            nullif(tx->>'from_bucket_id',   '')::uuid,
            nullif(tx->>'to_bucket_id',     '')::uuid,
            p_imported_by,
            p_batch_id,
            coalesce((tx->>'created_at')::timestamptz, now()),
            coalesce((tx->>'updated_at')::timestamptz, now())
        )
        on conflict (id) do update set
            type          = excluded.type,
            date          = excluded.date,
            merchant_name = excluded.merchant_name,
            amount        = excluded.amount,
            note          = excluded.note,
            updated_at    = now();
        tx_count := tx_count + 1;
    end loop;

    -- Re-enable triggers
    alter table public.transactions enable trigger trg_apply_transaction;
    alter table public.transactions enable trigger trg_reverse_transaction;
    alter table public.transactions enable trigger trg_reapply_transaction;

    -- Mark batch complete
    update public.import_batches set
        status        = 'success',
        imported_rows = tx_count,
        completed_at  = now()
    where id = p_batch_id;

    result := jsonb_build_object(
        'success',      true,
        'accounts',     acc_count,
        'buckets',      bkt_count,
        'transactions', tx_count
    );
    return result;

exception when others then
    -- Re-enable triggers even on failure
    alter table public.transactions enable trigger trg_apply_transaction;
    alter table public.transactions enable trigger trg_reverse_transaction;
    alter table public.transactions enable trigger trg_reapply_transaction;

    update public.import_batches set
        status       = 'rolled_back',
        error_detail = sqlerrm,
        completed_at = now()
    where id = p_batch_id;

    raise;  -- re-raise so Python sees the error and rolls back the outer transaction
end;
$$;

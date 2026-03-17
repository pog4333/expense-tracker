-- ============================================================
-- Views — run after schema.sql
-- ============================================================


-- Full transaction detail
create or replace view public.v_transactions as
select
    t.id, t.type, t.date, t.merchant_name, t.amount, t.note,
    t.is_salary, t.refund_status, t.refund_of_id, t.split_parent_id,
    t.transfer_type, t.import_batch_id, t.created_at, t.updated_at,
    a.id   as account_id,         a.name as account_name,   a.type as account_type,
    b.id   as bucket_id,          b.name as bucket_name,
    c.id   as category_id,        c.name as category_name,
    p.id   as parent_category_id, p.name as parent_category_name,
    fa.name as from_account_name, ta2.name as to_account_name,
    fb.name as from_bucket_name,  tb.name  as to_bucket_name,
    pr.id  as entered_by_id,      pr.display_name as entered_by_name
from public.transactions t
left join public.accounts   a   on a.id   = t.account_id
left join public.buckets    b   on b.id   = t.bucket_id
left join public.categories c   on c.id   = t.category_id
left join public.categories p   on p.id   = c.parent_id
left join public.accounts   fa  on fa.id  = t.from_account_id
left join public.accounts   ta2 on ta2.id = t.to_account_id
left join public.buckets    fb  on fb.id  = t.from_bucket_id
left join public.buckets    tb  on tb.id  = t.to_bucket_id
left join public.profiles   pr  on pr.id  = t.entered_by;


-- Monthly spending by category
create or replace view public.v_monthly_by_category as
select
    date_trunc('month', t.date)::date as month,
    p.id   as parent_category_id,  p.name as parent_category_name,
    c.id   as category_id,         c.name as category_name,
    sum(t.amount) as total_spent,  count(*) as transaction_count
from public.transactions t
join public.categories c on c.id = t.category_id
join public.categories p on p.id = c.parent_id
where t.type = 'expense'
  and t.refund_status is distinct from 'pending'
group by 1,2,3,4,5;


-- Monthly spending by bucket
create or replace view public.v_monthly_by_bucket as
select
    date_trunc('month', t.date)::date as month,
    b.id as bucket_id, b.name as bucket_name,
    sum(t.amount) as total_spent, count(*) as transaction_count
from public.transactions t
join public.buckets b on b.id = t.bucket_id
where t.type = 'expense'
group by 1,2,3;


-- Current month dashboard snapshot
create or replace view public.v_current_month as
select
    b.id as bucket_id, b.name as bucket_name, b.balance as bucket_balance,
    coalesce(s.spent, 0) as spent_this_month
from public.buckets b
left join (
    select bucket_id, sum(amount) as spent
    from public.transactions
    where type = 'expense'
      and date_trunc('month', date) = date_trunc('month', current_date)
    group by bucket_id
) s on s.bucket_id = b.id
where b.is_active = true
order by b.sort_order;


-- Daily spending (last 90 days)
create or replace view public.v_daily_spending as
select
    t.date,
    sum(t.amount) as total_spent,
    count(*)      as transaction_count
from public.transactions t
where t.type = 'expense'
  and t.date >= current_date - interval '90 days'
group by t.date
order by t.date desc;


-- Merchant auto-fill suggestions
create or replace view public.v_merchant_suggestions as
select
    m.id, m.name, m.use_count, m.last_used,
    m.default_category_id,   c.name  as category_name,
    p.id as parent_category_id,       p.name  as parent_category_name,
    m.default_bucket_id,      bk.name as bucket_name,
    m.default_account_id,     ac.name as account_name
from public.merchants m
left join public.categories c  on c.id  = m.default_category_id
left join public.categories p  on p.id  = c.parent_id
left join public.buckets    bk on bk.id = m.default_bucket_id
left join public.accounts   ac on ac.id = m.default_account_id
order by m.use_count desc, m.last_used desc;


-- Budget limit status (current month)
create or replace view public.v_budget_limit_status as
select
    bl.id as limit_id,
    c.id  as category_id,   c.name as category_name,
    p.name as parent_category_name,
    bl.monthly_limit,
    coalesce(s.spent, 0)                                   as spent_this_month,
    bl.monthly_limit - coalesce(s.spent, 0)                as remaining,
    round(coalesce(s.spent,0) / bl.monthly_limit * 100, 1) as pct_used
from public.budget_limits bl
join  public.categories c on c.id = bl.category_id
left join public.categories p on p.id = c.parent_id
left join (
    select category_id, sum(amount) as spent
    from public.transactions
    where type = 'expense'
      and date_trunc('month', date) = date_trunc('month', current_date)
    group by category_id
) s on s.category_id = bl.category_id
where bl.is_active = true;


-- Pending refunds
create or replace view public.v_pending_refunds as
select
    t.id, t.date, t.merchant_name, t.amount, t.note,
    t.account_id, a.name as account_name,
    t.category_id, c.name as category_name,
    pr.display_name as entered_by_name,
    t.created_at,
    (current_date - t.date) as days_waiting
from public.transactions t
left join public.accounts   a  on a.id  = t.account_id
left join public.categories c  on c.id  = t.category_id
left join public.profiles   pr on pr.id = t.entered_by
where t.refund_status = 'pending'
order by t.date asc;


-- Subscription detection
create or replace view public.v_subscriptions as
select
    merchant_name,
    count(*)                    as occurrences,
    min(amount)                 as min_amount,
    max(amount)                 as max_amount,
    round(avg(amount), 2)       as avg_amount,
    min(date)                   as first_seen,
    max(date)                   as last_seen,
    (count(*) >= 3 and (max(amount) - min(amount)) / nullif(avg(amount),0) < 0.05) as likely_subscription
from public.transactions
where type = 'expense'
group by merchant_name
having count(*) >= 3
order by likely_subscription desc, occurrences desc;


-- Year-over-year comparison
create or replace view public.v_year_over_year as
select
    extract(year  from date)::int as year,
    extract(month from date)::int as month,
    to_char(date, 'Mon')          as month_name,
    sum(amount)                   as total_spent,
    count(*)                      as transaction_count
from public.transactions
where type = 'expense'
group by 1,2,3
order by 1,2;


-- Savings goals progress
create or replace view public.v_savings_goals as
select
    sg.id, sg.name, sg.target_amount, sg.target_date, sg.is_achieved,
    b.id as bucket_id, b.name as bucket_name, b.balance as bucket_balance,
    least(b.balance, sg.target_amount)                                     as saved_amount,
    greatest(sg.target_amount - b.balance, 0)                              as remaining_amount,
    round(least(b.balance, sg.target_amount) / sg.target_amount * 100, 1) as pct_complete
from public.savings_goals sg
join public.buckets b on b.id = sg.bucket_id
order by sg.is_achieved, sg.target_date nulls last;

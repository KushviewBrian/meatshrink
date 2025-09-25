-- 3) Reporting views and materialized views

create or replace view v_shrink_events as
select
  se.id, se.store_id, se.entered_by, se.date_time, se.event_type,
  se.weight_lbs, se.unit_cost, se.unit_price,
  (se.weight_lbs * se.unit_cost) as shrink_cost,
  (se.weight_lbs * se.unit_price) as retail_value,
  p.category, p.cut_name, p.product_type, p.grade_spec,
  u.email as entered_by_email, se.notes
from shrink_events se
join products p on p.id = se.product_id
join app_users u on u.id = se.entered_by;

-- MVs
create materialized view if not exists mv_shrink_daily_store as
select store_id,
       date_trunc('day', date_time) as day,
       sum(weight_lbs) as total_weight_lbs,
       sum(weight_lbs*unit_cost) as total_shrink_cost
from shrink_events
group by 1,2;
create index if not exists idx_mv_store_day on mv_shrink_daily_store(store_id, day desc);

create materialized view if not exists mv_shrink_daily_store_category as
select store_id,
       date_trunc('day', date_time) as day,
       category,
       sum(weight_lbs*unit_cost) as shrink_cost
from v_shrink_events
group by 1,2,3;
create index if not exists idx_mv_store_day_cat on mv_shrink_daily_store_category(store_id, day desc, category);

-- RPC function for refreshing materialized views (admin only)
create or replace function refresh_materialized_views()
returns text
language plpgsql
security definer
as $$
begin
  -- Only allow admin users to execute this function
  if (auth.jwt() ->> 'role') != 'admin' then
    raise exception 'Access denied: admin role required';
  end if;
  
  -- Refresh materialized views
  refresh materialized view concurrently mv_shrink_daily_store;
  refresh materialized view concurrently mv_shrink_daily_store_category;
  
  return 'Materialized views refreshed successfully';
end;
$$;

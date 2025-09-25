-- 2) RLS + Policies

alter table app_users           enable row level security;
alter table products            enable row level security;
alter table shrink_events       enable row level security;
alter table shrink_corrections  enable row level security;

-- app_users
drop policy if exists app_users_select on app_users;
create policy app_users_select on app_users
for select using (
  id = auth.uid()
  or (store_id = (auth.jwt() ->> 'store_id')::int and (auth.jwt() ->> 'role') in ('manager','admin','auditor'))
);

drop policy if exists app_users_admin_write on app_users;
create policy app_users_admin_write on app_users
for all using ((auth.jwt() ->> 'role') = 'admin')
with check ((auth.jwt() ->> 'role') = 'admin');

-- products
drop policy if exists products_select on products;
create policy products_select on products for select using (true);

drop policy if exists products_write on products;
create policy products_write on products
for all using ((auth.jwt() ->> 'role') in ('manager','admin'))
with check ((auth.jwt() ->> 'role') in ('manager','admin'));

-- shrink_events
drop policy if exists se_select on shrink_events;
create policy se_select on shrink_events
for select using (
  store_id = (auth.jwt() ->> 'store_id')::int
  or (auth.jwt() ->> 'role') in ('auditor','admin')
);

drop policy if exists se_insert on shrink_events;
create policy se_insert on shrink_events
for insert with check (
  store_id = (auth.jwt() ->> 'store_id')::int
  and (auth.jwt() ->> 'role') in ('associate','lead','manager','admin')
);

drop policy if exists se_update on shrink_events;
create policy se_update on shrink_events
for update using (
  store_id = (auth.jwt() ->> 'store_id')::int
  and (auth.jwt() ->> 'role') in ('lead','manager','admin')
  and (now() - created_at) <= interval '7 days'
)
with check ( store_id = (auth.jwt() ->> 'store_id')::int );

drop policy if exists se_delete on shrink_events;
create policy se_delete on shrink_events
for delete using (
  store_id = (auth.jwt() ->> 'store_id')::int
  and (auth.jwt() ->> 'role') in ('manager','admin')
);

-- shrink_corrections
drop policy if exists sc_select on shrink_corrections;
create policy sc_select on shrink_corrections
for select using (
  exists (select 1 from shrink_events se
          where se.id = shrink_corrections.original_id
          and (se.store_id = (auth.jwt() ->> 'store_id')::int
               or (auth.jwt() ->> 'role') in ('auditor','admin')))
);

drop policy if exists sc_insert on shrink_corrections;
create policy sc_insert on shrink_corrections
for insert with check ( (auth.jwt() ->> 'role') in ('lead','manager','admin') );

-- Storage policy for exports bucket
-- Note: Apply this policy in Supabase Storage settings UI, or via SQL if RLS is enabled on storage.objects
-- This allows authenticated users to download files via signed URLs only
/*
create policy "Authenticated downloads via signed URLs" on storage.objects
for select using (
  bucket_id = 'exports' 
  and auth.role() = 'authenticated'
);

create policy "Admin/Manager uploads to exports" on storage.objects
for insert with check (
  bucket_id = 'exports' 
  and (auth.jwt() ->> 'role') in ('manager','admin','lead','associate')
);
*/

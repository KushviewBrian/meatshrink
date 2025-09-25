-- 4) Audit triggers

create or replace function audit_if_changed() returns trigger as $$
begin
  if tg_op = 'INSERT' then
    insert into audit_log(table_name,row_id,action,by_user,after)
    values (tg_table_name, new.id::text, 'INSERT', auth.uid(), to_jsonb(new));
    return new;
  elsif tg_op = 'UPDATE' then
    insert into audit_log(table_name,row_id,action,by_user,before,after)
    values (tg_table_name, new.id::text, 'UPDATE', auth.uid(), to_jsonb(old), to_jsonb(new));
    return new;
  elsif tg_op = 'DELETE' then
    insert into audit_log(table_name,row_id,action,by_user,before)
    values (tg_table_name, old.id::text, 'DELETE', auth.uid(), to_jsonb(old));
    return old;
  end if;
end; $$ language plpgsql security definer;

drop trigger if exists trg_audit_products on products;
create trigger trg_audit_products after insert or update or delete on products
for each row execute function audit_if_changed();

drop trigger if exists trg_audit_shrink_events on shrink_events;
create trigger trg_audit_shrink_events after insert or update or delete on shrink_events
for each row execute function audit_if_changed();

drop trigger if exists trg_audit_app_users on app_users;
create trigger trg_audit_app_users after insert or update or delete on app_users
for each row execute function audit_if_changed();

-- 1) Core Tables

create table if not exists app_users (
  id         uuid primary key,          -- equals auth.uid()
  email      text unique not null,
  role       text not null,
  store_id   int not null,
  is_active  boolean not null default true,
  created_at timestamptz not null default now(),
  constraint app_users_role_chk check (exists (
    select 1 from app_enums e where e.namespace='role' and e.value=role
  ))
);

create table if not exists products (
  id            bigserial primary key,
  upc_sku       text,
  category      text not null,
  cut_name      text not null,
  product_type  text not null,
  grade_spec    text,
  is_active     boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint products_cat_chk check (exists (select 1 from app_enums e where e.namespace='category' and e.value=category)),
  constraint products_type_chk check (exists (select 1 from app_enums e where e.namespace='product_type' and e.value=product_type))
);
create unique index if not exists ux_products_cat_cut_type on products(category, cut_name, product_type);

create table if not exists shrink_events (
  id            bigserial primary key,
  product_id    bigint not null references products(id),
  store_id      int not null,
  entered_by    uuid not null references app_users(id),
  date_time     timestamptz not null,
  event_type    text not null,
  weight_lbs    numeric(10,3) not null check (weight_lbs > 0),
  unit_cost     numeric(10,4) not null check (unit_cost >= 0),
  unit_price    numeric(10,4) not null check (unit_price >= 0),
  notes         text,
  created_at    timestamptz not null default now(),
  constraint shrink_events_type_chk check (exists (select 1 from app_enums e where e.namespace='event_type' and e.value=event_type))
);
create index if not exists idx_se_store_time on shrink_events(store_id, date_time desc);
create index if not exists idx_se_product on shrink_events(product_id);
create index if not exists idx_se_event_type on shrink_events(event_type);

create table if not exists shrink_corrections (
  id            bigserial primary key,
  original_id   bigint not null references shrink_events(id),
  corrected_by  uuid not null references app_users(id),
  reason        text not null,
  created_at    timestamptz not null default now()
);

-- Audit log
create table if not exists audit_log (
  id         bigserial primary key,
  table_name text not null,
  row_id     text not null,
  action     text not null check (action in ('INSERT','UPDATE','DELETE')),
  by_user    uuid,
  at         timestamptz not null default now(),
  before     jsonb,
  after      jsonb
);
create index if not exists idx_audit_at on audit_log(at desc);

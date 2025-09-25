
# 0) Non-Negotiables

* **Security**: Supabase Auth + Postgres **Row-Level Security (RLS)**; HTTPS; 2FA on; principle of least privilege; full audit trail.
* **Stability**: managed Postgres; immutable facts (no destructive edits); correction workflow; automated backups + restore drill.
* **Speed**: indexed filters; materialized views for reports; server-side filtering; cached dimensions; P95 query < 300 ms at 100k rows.

---

# 1) Architecture

* **UI**: Streamlit (Python 3.11+).
* **Auth & DB**: Supabase (Postgres 15, Auth, Storage).
* **Charts**: Plotly (interactive in-app), Matplotlib (PDF/PNG exports).
* **Exports**: CSV + XLSX to Supabase Storage, downloadable via signed URLs.
* **Hosting**: Streamlit Cloud / Render / Fly.io (HTTPS on).
* **Secrets**: via environment variables only.

**Flow:** User logs in → JWT includes `sub` (user id), `role`, `store_id` → all queries hit Postgres with RLS enforcing access → UI renders only permitted data.

---

# 2) Data Model (DDL, constraints, indexes)

## 2.1 Enumerations (CHECKs)

```sql
-- Units locked to pounds for launch
-- Roles
-- Event types (reason codes)
-- Product types (processing/merchandising)
```

```sql
-- No Postgres ENUMs to ease evolution; use CHECKs.
CREATE TABLE app_enums (
  namespace text NOT NULL,          -- 'role','event_type','product_type','category'
  value     text NOT NULL,
  PRIMARY KEY (namespace, value)
);

INSERT INTO app_enums(namespace, value) VALUES
('role','associate'), ('role','lead'), ('role','manager'), ('role','auditor'), ('role','admin'),
('event_type','Spoilage'),('event_type','Trim/Waste'),('event_type','Theft'),('event_type','Damage'),
('event_type','Markdown'),('event_type','Rework'),('event_type','Return'),
('product_type','Raw'),('product_type','Ground'),('product_type','Marinated'),
('product_type','Value-Added'),('product_type','Ready-to-Cook'),('product_type','Ready-to-Eat');
```

## 2.2 Users (mirror of Supabase auth users with roles)

```sql
CREATE TABLE app_users (
  id         uuid PRIMARY KEY,                 -- equals auth.uid()
  email      text UNIQUE NOT NULL,
  role       text NOT NULL,                    -- must exist in app_enums('role')
  store_id   int  NOT NULL,
  is_active  boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Guarantee valid role
ALTER TABLE app_users
  ADD CONSTRAINT app_users_role_fk
  FOREIGN KEY (role, role) REFERENCES app_enums(value, namespace)
  DEFERRABLE INITIALLY DEFERRED; -- (value,namespace) = (role,'role')
```

## 2.3 Products (catalog with taxonomy)

```sql
CREATE TABLE products (
  id            bigserial PRIMARY KEY,
  upc_sku       text,
  category      text NOT NULL,     -- must exist in app_enums('category'); see §7
  cut_name      text NOT NULL,
  product_type  text NOT NULL,     -- app_enums('product_type')
  grade_spec    text,              -- e.g., USDA Choice, Organic
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_products_cat_cut_type
  ON products (category, cut_name, product_type);

-- FK-like checks via app_enums; flexibility retained.
```

## 2.4 Shrink Events (immutable business facts)

```sql
CREATE TABLE shrink_events (
  id            bigserial PRIMARY KEY,
  product_id    bigint NOT NULL REFERENCES products(id),
  store_id      int    NOT NULL,
  entered_by    uuid   NOT NULL REFERENCES app_users(id),
  date_time     timestamptz NOT NULL,                 -- store UTC; display local
  event_type    text   NOT NULL,                      -- app_enums('event_type')
  weight_lbs    numeric(10,3) NOT NULL CHECK (weight_lbs > 0),
  unit_cost     numeric(10,4) NOT NULL CHECK (unit_cost >= 0),   -- cost snapshot
  unit_price    numeric(10,4) NOT NULL CHECK (unit_price >= 0),  -- optional retail
  notes         text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_se_store_time   ON shrink_events (store_id, date_time DESC);
CREATE INDEX idx_se_product      ON shrink_events (product_id);
CREATE INDEX idx_se_event_type   ON shrink_events (event_type);
```

## 2.5 Corrections (append-only)

```sql
CREATE TABLE shrink_corrections (
  id            bigserial PRIMARY KEY,
  original_id   bigint NOT NULL REFERENCES shrink_events(id),
  corrected_by  uuid   NOT NULL REFERENCES app_users(id),
  reason        text   NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
```

## 2.6 Audit Log (trigger-driven)

```sql
CREATE TABLE audit_log (
  id         bigserial PRIMARY KEY,
  table_name text NOT NULL,
  row_id     text NOT NULL,
  action     text NOT NULL CHECK (action IN ('INSERT','UPDATE','DELETE')),
  by_user    uuid,
  at         timestamptz NOT NULL DEFAULT now(),
  before     jsonb,
  after      jsonb
);
CREATE INDEX idx_audit_at ON audit_log (at DESC);
```

---

# 3) Security (RLS, auth, triggers, policies)

## 3.1 Enable RLS

```sql
ALTER TABLE app_users      ENABLE ROW LEVEL SECURITY;
ALTER TABLE products       ENABLE ROW LEVEL SECURITY;
ALTER TABLE shrink_events  ENABLE ROW LEVEL SECURITY;
ALTER TABLE shrink_corrections ENABLE ROW LEVEL SECURITY;
```

## 3.2 RLS Policies

**app_users**

```sql
-- Self read or same-store read for manager/admin/auditor
CREATE POLICY app_users_select ON app_users
FOR SELECT USING (
  id = auth.uid()
  OR (store_id = (auth.jwt() ->> 'store_id')::int
      AND (auth.jwt() ->> 'role') IN ('manager','admin','auditor'))
);

-- Admin can modify user rows (no one else)
CREATE POLICY app_users_admin_write ON app_users
FOR ALL USING ((auth.jwt() ->> 'role') = 'admin')
WITH CHECK ((auth.jwt() ->> 'role') = 'admin');
```

**products** (read for all roles; write restricted)

```sql
-- Everyone signed in can read catalog
CREATE POLICY products_select ON products
FOR SELECT USING (true);

-- Only manager/admin can write
CREATE POLICY products_write ON products
FOR ALL USING ((auth.jwt() ->> 'role') IN ('manager','admin'))
WITH CHECK ((auth.jwt() ->> 'role') IN ('manager','admin'));
```

**shrink_events** (store scope; role gates)

```sql
-- SELECT: same store OR auditor/admin
CREATE POLICY se_select ON shrink_events
FOR SELECT USING (
  store_id = (auth.jwt() ->> 'store_id')::int
  OR (auth.jwt() ->> 'role') IN ('auditor','admin')
);

-- INSERT: associate+ within same store
CREATE POLICY se_insert ON shrink_events
FOR INSERT WITH CHECK (
  store_id = (auth.jwt() ->> 'store_id')::int
  AND (auth.jwt() ->> 'role') IN ('associate','lead','manager','admin')
);

-- UPDATE: lead/manager/admin same store; restrict to 7 days by CHECK
CREATE POLICY se_update ON shrink_events
FOR UPDATE USING (
  store_id = (auth.jwt() ->> 'store_id')::int
  AND (auth.jwt() ->> 'role') IN ('lead','manager','admin')
  AND (now() - created_at) <= interval '7 days'
)
WITH CHECK (
  store_id = (auth.jwt() ->> 'store_id')::int
);

-- DELETE: manager/admin same store
CREATE POLICY se_delete ON shrink_events
FOR DELETE USING (
  store_id = (auth.jwt() ->> 'store_id')::int
  AND (auth.jwt() ->> 'role') IN ('manager','admin')
);
```

**shrink_corrections** (append-only; read scoped)

```sql
CREATE POLICY sc_select ON shrink_corrections
FOR SELECT USING (
  EXISTS (SELECT 1 FROM shrink_events se
          WHERE se.id = shrink_corrections.original_id
            AND (se.store_id = (auth.jwt() ->> 'store_id')::int
                 OR (auth.jwt() ->> 'role') IN ('auditor','admin')))
);

CREATE POLICY sc_insert ON shrink_corrections
FOR INSERT WITH CHECK (
  (auth.jwt() ->> 'role') IN ('lead','manager','admin')
);
```

## 3.3 Auth Settings (Supabase Console)

* **Email/password** enabled; **email verification ON**.
* **TOTP 2FA ON** (required).
* **Session expiry 8h**, refresh tokens enabled.
* JWT includes custom claims: `role`, `store_id` (via edge function or admin set on signup; mirror in `app_users`).

## 3.4 Audit Triggers (authoritative trail)

```sql
CREATE OR REPLACE FUNCTION audit_if_changed() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO audit_log(table_name,row_id,action,by_user,after)
    VALUES (TG_TABLE_NAME, NEW.id::text, 'INSERT', auth.uid(), to_jsonb(NEW));
    RETURN NEW;
  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO audit_log(table_name,row_id,action,by_user,before,after)
    VALUES (TG_TABLE_NAME, NEW.id::text, 'UPDATE', auth.uid(), to_jsonb(OLD), to_jsonb(NEW));
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    INSERT INTO audit_log(table_name,row_id,action,by_user,before)
    VALUES (TG_TABLE_NAME, OLD.id::text, 'DELETE', auth.uid(), to_jsonb(OLD));
    RETURN OLD;
  END IF;
END; $$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_audit_products
AFTER INSERT OR UPDATE OR DELETE ON products
FOR EACH ROW EXECUTE FUNCTION audit_if_changed();

CREATE TRIGGER trg_audit_shrink_events
AFTER INSERT OR UPDATE OR DELETE ON shrink_events
FOR EACH ROW EXECUTE FUNCTION audit_if_changed();

CREATE TRIGGER trg_audit_app_users
AFTER INSERT OR UPDATE OR DELETE ON app_users
FOR EACH ROW EXECUTE FUNCTION audit_if_changed();
```

---

# 4) Reporting Layer (views, MVs, indices)

## 4.1 Canonical view (joins product taxonomy)

```sql
CREATE OR REPLACE VIEW v_shrink_events AS
SELECT
  se.id, se.store_id, se.entered_by, se.date_time, se.event_type,
  se.weight_lbs, se.unit_cost, se.unit_price,
  (se.weight_lbs * se.unit_cost) AS shrink_cost,
  (se.weight_lbs * se.unit_price) AS retail_value,
  p.category, p.cut_name, p.product_type, p.grade_spec
FROM shrink_events se
JOIN products p ON p.id = se.product_id;
```

## 4.2 Materialized views (performance)

```sql
-- Daily store summary
CREATE MATERIALIZED VIEW mv_shrink_daily_store AS
SELECT store_id,
       date_trunc('day', date_time) AS day,
       SUM(weight_lbs)         AS total_weight_lbs,
       SUM(weight_lbs*unit_cost) AS total_shrink_cost
FROM shrink_events
GROUP BY 1,2;

CREATE INDEX idx_mv_store_day ON mv_shrink_daily_store(store_id, day DESC);

-- Category breakdown per day/store
CREATE MATERIALIZED VIEW mv_shrink_daily_store_category AS
SELECT store_id,
       date_trunc('day', date_time) AS day,
       category,
       SUM(weight_lbs*unit_cost) AS shrink_cost
FROM v_shrink_events
GROUP BY 1,2,3;
CREATE INDEX idx_mv_store_day_cat ON mv_shrink_daily_store_category(store_id, day DESC, category);
```

**Refresh policy:** nightly at 02:30 local store time (UTC cron) and on-demand via Admin page button:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_shrink_daily_store;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_shrink_daily_store_category;
```

---

# 5) Streamlit Application (pages, components, validation)

## 5.1 Project layout

```
/app
  /pages
    01_Record_Shrink.py
    02_Reports.py
    03_Exports.py
    04_Catalog.py
    05_Admin_Audit.py
  /lib
    auth.py       # Supabase login, session
    supa.py       # Supabase client factory
    db.py         # typed queries, server-side validation
    charts.py     # Plotly builders
    exports.py    # CSV/XLSX writers, storage uploads
    validators.py # strict field checks, weight bands
  /seed
    products_seed.csv   # full taxonomy (see §7)
  .streamlit/config.toml
```

## 5.2 Global UX rules

* **Keyboard-first entry**: focus → Product → Event Type → Weight → Cost → [Enter] submits.
* **All times stored UTC**, display in store’s timezone (config per store).
* **Units**: **pounds only** at launch; numeric fields with 3 decimals for weight, 4 for prices.
* **Autosave** never; explicit submit; clear success toast.
* **Role-aware UI**: hide forbidden buttons; DB still enforces permissions.
* **Error feedback**: friendly message + dev detail in logs.

## 5.3 Page: Record Shrink

**Fields & constraints**

* **Product**: searchable select bound to `products.id` (shows “Category • Cut • Type”). Required.
* **Event Type**: required; values from `app_enums(event_type)`.
* **Weight (lbs)**: numeric > 0; three decimals max; per-category **weight bands** warning (see §8).
* **Unit Cost**: numeric ≥ 0; prefilled from product default (optional product_costs table later).
* **Unit Price**: numeric ≥ 0; optional; default 0 if unknown.
* **Date/Time**: default now(); allow override (UTC stored).
* **Notes**: optional text.

**On submit**

* Client validates; build payload; set `store_id` and `entered_by` from session.
* Insert into `shrink_events`; RLS enforces scope; show success.
* Reset form; show **Recent Events (today)** table with last 50 rows.

**Correction flow**

* Button “Create Correction” (lead+): opens modal with `reason` (required); creates `shrink_corrections` row; original remains unchanged.

## 5.4 Page: Reports

**Filter panel**

* Date range presets (Today, Last 7 days, Month to date, Custom).
* Category (multi), Cut (dependent multi), Product Type (multi), Event Type (multi).
* Store (auditor/admin only).
* Toggle: **Measure = Cost / Weight / Retail Value**.

**Visuals**

* **Bar**: Shrink Cost by Category (descending).
* **Pareto**: Top 20 products by Shrink Cost + cumulative line.
* **Line**: Daily trend (Cost/Weight), aggregated by day.
* **Donut**: Event type mix (share of cost).
* **Table**: All filtered rows (paginated), WYSIWYG with exports.

**Behavior**

* All filters apply server-side via SQL WHERE.
* Limits: max 10k rows for table; charts aggregate before plotting.

## 5.5 Page: Exports

* **Download current result**: CSV + XLSX of the **filtered** dataset.
* **Scheduled exports**: define preset (filters + frequency), stored as JSON; a Supabase cron/edge function writes to Storage daily 03:00 local.
* **File naming**:
  `shrink_<storeid>_<YYYYMMDD>_<report_name>.{csv|xlsx}`
* **Columns** (fixed): `id, store_id, date_time_iso, category, cut_name, product_type, event_type, weight_lbs, unit_cost, unit_price, shrink_cost, retail_value, entered_by_email, notes`

## 5.6 Page: Catalog

* Add Product (manager/admin): category, cut_name, product_type, upc_sku (opt), grade_spec (opt), is_active.
* Bulk import: upload `products_seed.csv` or store-specific CSV; dedupe via `(category,cut_name,product_type)`.
* Deactivate instead of delete if referenced.

## 5.7 Page: Admin & Audit

* Users table: email, role, store_id, is_active; role/store updates (admin only).
* Audit viewer: filters by table, action, date range, user; shows JSON diff (before/after).
* Buttons: “Refresh Materialized Views” (admin), “Run backup verification” (opens runbook link).

---

# 6) Validation Rules (strict)

* **Weight**: `0 < weight_lbs ≤ 500` (hard ceiling); soft bands by category:

  * Poultry: warn if `> 20 lbs`
  * Beef primal (Brisket, Chuck Roast, etc.): warn if `< 2 lbs` or `> 120 lbs`
  * Ground items: warn if `> 60 lbs` per event
* **Unit Cost/Price**: `0 ≤ value ≤ 999.9999`; warn if price < cost (unless event_type = Markdown/Rework).
* **Date/Time**: no future > 24h; warn on backdated > 30 days (manager override).
* **Event Type**: required; must exist in `app_enums`.
* **Product active**: must be `is_active = true` to select; otherwise show disabled.

---

# 7) Full Meat Taxonomy (seed catalog)

Load these into `app_enums('category')` and `products_seed.csv`. (All items `product_type=Raw` unless noted; keep `Ground`, `Marinated`, `Value-Added`, `Ready-to-Cook`, `Ready-to-Eat` where specified.)

**Categories**
Beef, Pork, Poultry, Lamb/Goat, Veal, Seafood, Deli/Smoked, Value-Added

**Beef**

* Ribeye, New York Strip, Tenderloin, Top Sirloin, Chuck Roast, Chuck Eye, Brisket (Flat, Point), Short Ribs (English, Flanken), Back Ribs, Tri-Tip, Flank, Skirt (Inside, Outside), Hanger, Top Round, Eye of Round, Bottom Round, Sirloin Tip, Stew Meat, Stir Fry Strips, Beef Shank (Osso Buco), Oxtail, Marrow Bones, Suet, Brisket Deckle (Trim), **Ground Beef** (80/20, 85/15, 90/10, 93/7) → `product_type=Ground`, **Marinated Steaks** (various) → `product_type=Marinated`

**Pork**

* Pork Loin (Whole, Center Cut, Chops), Pork Tenderloin, Shoulder/Boston Butt (Bone-in, Boneless), Picnic Shoulder, Pork Belly (Skin-on/Off), Spare Ribs, St. Louis Ribs, Baby Back Ribs, Country-Style Ribs, Fresh Ham, Smoked Ham → `Deli/Smoked`, Pork Shank, Pork Hocks, Pork Neck Bones, Pork Fatback, Leaf Lard, **Ground Pork** → `Ground`, **Marinated Pork Chops** → `Marinated`

**Poultry**

* Chicken Whole Fryer, Split Fryer, Bone-in Breast, Boneless Skinless Breast, Tenders, Bone-in Thighs, Boneless Thighs, Drumsticks, Whole Wings, Party Wings, Leg Quarters, Backs/Necks, **Ground Chicken** → `Ground`, Turkey Whole, Turkey Breast, Turkey Thighs, Turkey Drumsticks, **Ground Turkey** (85/15, 93/7) → `Ground`, Duck (Whole, Breast), Cornish Hen

**Lamb/Goat**

* Leg (Whole, Boneless), Shoulder (Bone-in, Boneless), Rack, Loin Chops, Rib Chops, Shank, Stew, **Ground Lamb** → `Ground`, Goat Leg, Goat Shoulder, Goat Stew, **Ground Goat** → `Ground`

**Veal**

* Veal Cutlets, Veal Chop, Veal Shoulder, Veal Shank (Osso Buco), Veal Stew, Veal Breast, **Ground Veal** → `Ground`

**Seafood** (fresh, common retail cuts)

* Salmon Fillet (Atlantic, Coho, Sockeye), Salmon Portions, Cod Fillet, Haddock Fillet, Tilapia Fillet, Catfish Fillet, Halibut Steak, Mahi Mahi, Tuna Loin/Steaks, Swordfish Steaks, Shrimp (16/20, 21/25, 26/30, 31/40), Scallops (U10, 10/20), Calamari, Crab (clusters, meat), Mussels, Clams

**Deli/Smoked**

* Bacon (Thick, Applewood, Maple, Peppered), Smoked Sausage (Pork, Beef, Polska Kielbasa, Andouille), Sliced Turkey Breast (RTE), Sliced Ham (RTE), Sliced Roast Beef (RTE), Bologna, Salami, Hot Dogs/Franks, Smoked Brisket (RTE)

  * `product_type=Ready-to-Eat` for sliced meats; many are `Deli/Smoked` category but keep type consistent.

**Value-Added / Ready-to-Cook**

* Marinated Chicken Breast (Lemon Pepper, Teriyaki, BBQ), Chicken Kebabs (Breast/Thigh w/ Veg), Stuffed Chicken Breast (Broccoli Cheddar, Cordon Bleu), House Sausage (Italian Mild/Hot, Bratwurst, Breakfast) → `product_type=Value-Added` (raw; for **RTE** cooked sausage use `Ready-to-Eat`)
* Marinated Pork Chops (Garlic Herb), Stuffed Pork Chops (Apple, Dressing), Pork Kebabs
* Beef Kebabs, Marinated Flank/Skirt, Meatloaf Mix (Beef/Pork/Veal)
* Pre-formed Burgers (Beef 80/20, Turkey, Chicken) → `Ready-to-Cook`

> This list is **immediately usable** for seeding; extend per store recipes/SKUs.

---

# 8) Reason Codes & Business Rules

**Event Types** (hardcoded in `app_enums`):

* Spoilage (date/odor/temperature)
* Trim/Waste (fat, bone, silverskin; use for fabrication loss)
* Theft (unknown loss)
* Damage (dropped, broken vacuum, package leak)
* Markdown (sell-down; treat as shrink **separate** or include in shrink wall—configurable)
* Rework (e.g., ribeye ends → kebabs; cost remains in system; monitor flows)
* Return (customer return to meat dept; treat per store policy)

**Default math**

* **Shrink Cost** = `weight_lbs * unit_cost`
* **Retail Value** = `weight_lbs * unit_price`
* **Trend**: aggregate by day with UTC→local display only

---

# 9) Exports (contract)

* **Formats**: CSV (UTF-8, `,` delimiter), XLSX.
* **Headers** (fixed order):
  `id,store_id,date_time_iso,category,cut_name,product_type,event_type,weight_lbs,unit_cost,unit_price,shrink_cost,retail_value,entered_by_email,notes`
* **Date format**: ISO-8601 UTC (`2025-09-24T17:03:21Z`).
* **Decimal precision**: weight 3, prices/cost 4, totals 2.
* **Retention**: files kept 90 days in Supabase Storage bucket `exports/`.
* **Access**: signed URL expiring in 15 minutes.

---

# 10) Performance Targets & Techniques

* **Indexes**: as defined; verify via `EXPLAIN ANALYZE` for key queries.
* **Materialization**: daily summaries pre-aggregated; refresh nightly + on-demand.
* **Server-side WHERE**: all filters applied in SQL, never client-side on >10k rows.
* **Caching**: products catalog cached in Streamlit for 10 minutes.
* **Pagination**: tables page by 200 rows; CSV export uses server-side streaming.

---

# 11) Observability & Ops

* **Logging**: application logs for inserts/exports; DB audit_log for data changes.
* **Metrics (lightweight)**: events/day, active users/day, report latency (client-side captured).
* **Backups**: Supabase automated daily; monthly **restore drill** to staging project documented.
* **Runbooks**:

  * Lost password (Supabase reset).
  * Role change (Admin page + PR in `app_users` with audit).
  * Store split/merge (script updates `store_id` with audit).
  * Data correction (Correction entry; never overwrite).

---

# 12) Security Hardening

* HTTPS enforced; HSTS at proxy.
* 2FA (TOTP) required for all users.
* Sessions 8h; idle timeout 30m client-side (autologout).
* Secrets never in repo; rotate on departures.
* RLS is **source of truth**; UI hides controls but never trusts itself.
* Rate-limit login attempts (Supabase policy) + lockout after 10 tries.
* Export endpoints require explicit scope check + audit log entry.

---

# 13) Testing & Acceptance

## 13.1 Unit

* Validators: weight bands, price/ cost logic, date bounds.
* Query builders: ensure correct WHERE clauses per filter set.

## 13.2 Integration (with RLS on)

* For each role (associate, lead, manager, auditor, admin):

  * **Can login**
  * **Can (or cannot) INSERT** per policy
  * **Cannot SELECT** other store’s data (except auditor/admin)
  * **Cannot DELETE** unless manager/admin
  * **UPDATE** allowed for lead+ within 7 days only

## 13.3 Performance

* Seed 100k `shrink_events` spanning 365 days.
* **P95**: daily trend query < 300 ms; category bar < 300 ms.
* Page TTFI < 4 s on median laptop + retail Wi-Fi.

## 13.4 UAT checklist (must pass)

* Record Shrink in ≤ 5 clicks; Enter submits; form resets with toast.
* Filters produce identical totals in charts and export file.
* Corrections produce linked row; original unchanged.
* Audit viewer shows create/update/delete with who/when/diff.
* Export naming/timestamps correct; signed URL works.
* Materialized views refresh button updates today’s dashboard.

**Definition of Done** is passing all the above.

---

# 14) Deployment & CI/CD

* **Branches**: `main` (prod), `staging`.
* **CI**: ruff (lint), mypy (type), pytest (unit/integration), SQL lints, `.sql` apply dry-run.
* **CD**: auto deploy staging on merge; manual promote to prod via tag.
* **Config**: `.env` for `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE` (admin ops only in admin scripts).

---

# 15) Page-by-Page Field IDs (for consistency)

* Product select: `fld_product_id`
* Event type: `fld_event_type`
* Weight (lbs): `fld_weight_lbs`
* Unit cost: `fld_unit_cost`
* Unit price: `fld_unit_price`
* Date/time: `fld_datetime`
* Notes: `fld_notes`
* Submit button: `btn_submit_event`
* Correction reason: `fld_correction_reason`

Filters:

* `f_date_from`, `f_date_to`, `f_category[]`, `f_cut[]`, `f_product_type[]`, `f_event_type[]`, `f_store_id`

---

# 16) Role Matrix (authorizations)

| Action                                   | Associate | Lead | Manager | Auditor | Admin |
| ---------------------------------------- | :-------: | :--: | :-----: | :-----: | :---: |
| View own store data                      |     ✓     |   ✓  |    ✓    |    ✓*   |   ✓   |
| View all stores                          |           |      |         |    ✓    |   ✓   |
| Create shrink event                      |     ✓     |   ✓  |    ✓    |         |   ✓   |
| Update shrink event (≤7d)                |           |   ✓  |    ✓    |         |   ✓   |
| Delete shrink event                      |           |      |    ✓    |         |   ✓   |
| Create correction                        |           |   ✓  |    ✓    |         |   ✓   |
| Manage products                          |           |      |    ✓    |         |   ✓   |
| Manage users/roles                       |           |      |         |         |   ✓   |
| Refresh MVs                              |           |      |    ✓    |         |   ✓   |
| * Auditor can view all stores read-only. |           |      |         |         |       |

---

# 17) Roadmap (post-launch, optional)

* POS/ERP ingestion (receipts, sales) to compute formal shrink %.
* Scale-label barcode parsing (embedded weight).
* Label printing for Rework/Markdown.
* Yield sessions (input primal → outputs; variance vs targets).
* SSO/SAML (Okta/Azure AD) if corporate needs.

---

# 18) Delivery Package (what the $20k+ includes)

* Supabase SQL (all tables, indexes, RLS, triggers, MVs, seed catalog).
* Streamlit codebase (5 pages + libs as specified).
* Admin handbook (user lifecycle, backups, restores, role changes).
* QA suite & acceptance checklist.
* One-click staging → prod promotion docs.

---
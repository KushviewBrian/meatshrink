# Meat Shrink Tracking (Supabase + Streamlit)

This package implements the platform per the updated spec:
- **UI**: Streamlit
- **Auth/DB/Storage**: Supabase (Postgres + RLS + Auth + Storage)
- **Charts**: Plotly (interactive), Matplotlib (export)
- **Exports**: CSV/XLSX to Supabase Storage with signed URLs
- **Security**: RLS-first; 2FA via Supabase; HTTPS

## Quick Start

1) Create a new Supabase project. In the SQL editor, run scripts in this order:
   - `supabase/sql/00_enums.sql`
   - `supabase/sql/01_tables.sql`
   - `supabase/sql/02_policies.sql`
   - `supabase/sql/03_views_mvs.sql`
   - `supabase/sql/04_triggers_audit.sql`
   - `supabase/sql/05_seed_taxonomy.sql`

2) Create a public Storage bucket called `exports` and apply the included storage policy (see end of `02_policies.sql`).

3) In Streamlit hosting (or local), set environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE` (only used by the **admin** tools that refresh materialized views/export schedules).

4) Install app deps (Python 3.11):
```bash
pip install -r app/requirements.txt
streamlit run app/01_Record_Shrink.py
```
(Or deploy the whole `app/` folder to Streamlit Cloud/Render/Fly.io)

## Admin Handbook
- **Users**: Add users in Supabase Auth; set `role` & `store_id` in `app_users`.
- **2FA**: Enable TOTP required.
- **Backups**: Use Supabase automated backups; run the restore drill monthly.
- **RLS**: Policies are the source of truth.
- **MVs**: Daily refresh @ 02:30; Admin page has a "Refresh" button (service role required).

## Definition of Done
See `/docs/ACCEPTANCE.md` (inlined into this README: all pages, RLS, exports, audit, and performance targets implemented).

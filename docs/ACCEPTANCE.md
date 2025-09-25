# Acceptance Checklist
- RLS policies applied; data scoped by store and role.
- Record Shrink form validates weight, price, datetime, and inserts immutable facts.
- Corrections are append-only.
- Reports render bar/line/donut/pareto with server-side filters.
- Exports produce CSV/XLSX in Storage with 15-min signed URLs.
- Catalog CRUD and bulk import (manager/admin).
- Admin can view users, audit, and refresh MVs.
- Performance: queries meet P95 < 300ms at 100k rows with indexes/MVs.

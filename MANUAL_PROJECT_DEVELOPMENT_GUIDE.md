# SL Carborundum Planning Center — Manual Software Development Guide

## 1. What this project really is

This is not an Excel automation script. It is a small Manufacturing Planning / PPC application with:

1. Source and revision management
2. Master-data management
3. Work-order and WIP transactions
4. Production status history
5. Firing-capacity and kiln scheduling
6. Physical loading / furniture constraints
7. Daily section scheduling
8. KPI calculation and evidence
9. QR / mobile shop-floor tracking
10. Audit trail, permissions and reports

If you can build this manually, you have learned the structure used by much larger MES/PPC/ERP systems.

---

## 2. Recommended architecture

Use five layers. Do not put everything into one Streamlit page.

```text
Browser / Mobile
       |
       v
UI Layer
(Streamlit / React / FastAPI)
       |
       v
Application Services
(KPI service, WIP service, Firing Planner service)
       |
       v
Domain / Planning Engine
(rules, capacity, scheduling, validation)
       |
       +------------------+
       |                  |
       v                  v
PostgreSQL             File/Object Storage
(master + transactions) (original Excel, photos, PDFs, exports)
       |
       v
Audit / Source Registry
```

### Rule

UI asks the service for data.

The service calls the database.

The planning engine calculates.

The database stores the result.

The UI should never contain the real business rule.

---

# 3. Data model

Start with these core entities.

## A. Master tables

### `customer`
- `customer_id` PK
- `customer_code`
- `customer_name`
- `active`

### `part_master`
- `part_id` PK
- `part_code`
- `specification`
- `category`
- `shape`
- `unit`
- `weight_kg_per_pc`
- `length_mm`
- `width_mm`
- `height_mm`
- `diameter_mm`
- `hole_mm`
- `active`

### `routing`
- `routing_id` PK
- `part_id` FK
- `sequence_no`
- `section`
- `standard_process`
- `standard_days`
- `active`

Example:

```text
P001
  10 Preparation
  20 Mixing
  30 Forming
  40 Firing
  50 Grinding
  60 Packing
```

### `resource`
- `resource_id` PK
- `resource_code`
- `resource_type`
- `section`
- `capacity_unit`
- `capacity_value`
- `active`

### `kiln`
- `kiln_id` PK
- `kiln_code`
- `kiln_type`
- `program`
- `physical_kg`
- `gross_volume_m3`
- `length_mm`
- `width_mm`
- `height_mm`
- `cycle_days`
- `active`

### `kiln_furniture`
- `furniture_id` PK
- `kiln_id` FK
- `furniture_type`
- `length_mm`
- `width_mm`
- `height_mm`
- `quantity`
- `stack_rule`
- `active`

### `calendar`
- `calendar_date` PK
- `is_working_day`
- `shift_hours`
- `holiday_name`

---

# 4. Transaction tables

## `sales_order`

```text
sales_order_id PK
customer_id FK
order_no
order_line_no
part_id FK
order_qty
requested_date
initial_due_date
revised_due_date
revision_no
status
created_at
```

Never overwrite the initial due date.

---

## `work_order`

```text
wo_id PK
wo_no UNIQUE
sales_order_id FK
part_id FK
order_qty
issue_date
due_date
priority
status
created_at
updated_at
```

---

## `wo_process`

One WO has many process records.

```text
wo_process_id PK
wo_id FK
section
sequence_no
planned_qty
actual_qty
status
planned_start
planned_finish
actual_start
actual_finish
```

Important:

**A section can be closed without closing the whole WO.**

---

## `wip_event`

Never overwrite physical history.

```text
event_id PK
tracking_id
wo_id nullable
part_id nullable
section
status
quantity
unit
location_id
photo_id nullable
operator_id
event_time
server_time
source
```

---

## `wip_location`

```text
location_id PK
building
section
machine
rack
bin
description
```

---

# 5. Firing planner data structure

The firing planner should not directly plan from raw Excel.

Use this pipeline:

```text
Plan 2026
    |
    v
Normalized WO table
    |
    v
Process remaining quantity
    |
    v
Firing-ready calculation
    |
    v
Program classification
    |
    v
Compatible kiln candidates
    |
    v
Capacity screening
    |
    v
Physical/furniture packing
    |
    v
Load schedule
    |
    v
Validation
    |
    v
Operator output
```

## Normalized firing order

Use one row per WO:

```text
WO
Customer
Part
Category
Program
Order Qty
Firing Target Qty
Firing Actual Qty
Remaining Firing Qty
Firing Ready Qty
Due Date
Priority
Weight kg/pc
Footprint X
Footprint Y
Piece Height
Geometry
Readiness
Earliest Firing Date
```

---

# 6. Firing calculation

The most important rule is:

```text
Priority 1 = due-date protection
Priority 2 = physical feasibility
Priority 3 = capacity utilization
Priority 4 = workload balance
```

Do not reverse these.

A planner must never fill a kiln to 95% by moving an urgent WO behind a future WO.

---

## 6.1 Candidate generation

For each working day:

```python
open_wos = remaining_qty > 0

candidates = open_wos
candidates = sort(
    due_date,
    priority,
    earliest_firing_date
)

for wo in candidates:
    compatible_kilns = find_compatible_kilns(wo)
```

---

# 7. Kiln selection

For each candidate kiln calculate:

```text
weight_utilization
estimated_volume_utilization
height_utilization
furniture_feasibility
cycle_finish_date
delivery_risk
```

Example score:

```text
score =
    due_date_score
  + physical_fit_score
  + volume_utilization_score
  + weight_utilization_score
  + workload_balance_score
```

But due-date protection must have a much larger weight than utilization.

---

# 8. Avoiding very small loads

A good planner needs a **load decision gate**.

Example:

```text
Occupancy >= 80%
    -> RELEASE

Occupancy 60–80%
    -> REVIEW / COMBINE

Occupancy < 60%
    -> WAIT / RIGHT-SIZE
```

Exceptions:

```text
Overdue
Due-risk
Approved urgent/test work
Physical/weight constraint
Special kiln rule
```

These should be visible as exceptions.

Do not silently force a small load just to make every calendar day look full.

---

# 9. Avoiding empty planning days

An empty day should have a reason.

Use a daily capacity status table:

```text
Date
Working day
Available kilns
Available capacity
Open demand
Ready demand
Due-risk demand
Planned loads
Unused capacity
Reason for unused capacity
Recommended action
```

Example:

```text
29-Oct
Working day
6 compatible kilns
4 available
2 due-risk WOs
1 load
1 unused kiln
Reason: second compatible WO cannot physically fit
Action: wait/combine
```

This is much better than simply showing a blank Gantt day.

---

# 10. KPI database

Use evidence-based KPI records.

## `kpi_definition`

```text
kpi_code PK
name
thai_name
owner_role
target
weight
formula
definition_version
effective_from
effective_to
```

## `kpi_measurement`

```text
measurement_id PK
kpi_code FK
month
numerator
denominator
actual_percent
evidence_id
notes
recorded_by
recorded_at
definition_version
```

## `source_evidence`

```text
evidence_id PK
filename
sheet
revision
sha256
import_time
source_path
uploaded_by
```

---

# 11. October 2026 Planning KPI evidence implemented

The revised software recognizes:

### KPI-PL-07
On-time material readiness confirmation

October source:

`October_in out.xlsx`

```text
Target = 448
Actual = 448
Result = 100%
Target = 95%
```

### KPI-PL-08
On-time work-order distribution and acknowledgement

October source:

`October_in out.xlsx`

```text
Target = 286
Actual = 286
Result = 100%
Target = 98%
```

Blank and zero-target days are treated as **N/A**, not KPI failures.

### October closed-job file

`October-2026_job closure.xlsx`

Total closed-job activity:

```text
250 items
```

This is stored as operational evidence only. The software does not invent a KPI target from this workbook.

---

# 12. Why blank days must not become zero

Suppose:

```text
1 Oct Target = 12
2 Oct Target = 16
3 Oct Target = blank
4 Oct Target = blank
```

Correct:

```text
1 Oct -> scored
2 Oct -> scored
3 Oct -> N/A
4 Oct -> N/A
```

Incorrect:

```text
1 Oct -> scored
2 Oct -> scored
3 Oct -> 0%
4 Oct -> 0%
```

Otherwise holidays / no-demand days artificially reduce KPI.

---

# 13. Source management

Every imported workbook should have:

```text
source_id
original_filename
stored_filename
revision_no
sha256
imported_at
uploaded_by
sheet
source_period
status
```

When the same file is uploaded twice:

```text
same SHA-256
    -> do not duplicate records
```

When a new revision arrives:

```text
revision 1
revision 2
revision 3
```

Keep all revisions.

---

# 14. QR / WIP architecture

A QR code should identify a stable record.

Do NOT encode:

```text
http://192.168.1.50:8000/...
```

Prefer:

```text
WO:WO2026100001
```

or:

```text
TRACK:TMP-20261029-000123
```

The application resolves that ID.

This means the factory IP can change without changing every QR label.

---

# 15. Audit event model

Never update:

```text
quantity = 100 -> quantity = 80
```

without history.

Instead:

```text
event 1: 100 pcs
event 2: correction -20 pcs
```

Then the system can explain why the current quantity is 80.

---

# 16. Performance design

For thousands of WOs:

### Do not

```python
for every page:
    read_excel("Plan 2026.xlsx")
```

### Do

```text
Excel
  -> import once
  -> normalized database
  -> indexed SQL query
```

Use indexes:

```sql
CREATE INDEX ix_wo_due_date
ON work_order(due_date);

CREATE INDEX ix_wo_status
ON work_order(status);

CREATE INDEX ix_wip_wo
ON wip_event(wo_id);

CREATE INDEX ix_wip_tracking
ON wip_event(tracking_id);
```

For firing:

```text
Load master once
Cache normalized WO data
Bound candidate search
Only perform expensive furniture packing on shortlisted candidates
```

The revised firing planner now uses a bounded same-program candidate window and expands it only when necessary.

---

# 17. UI performance

Use:

```text
Home
Daily
Firing
Track / QR
Files
Reports
```

Do not render every table on every page.

Only load the selected module.

Use:

```python
@st.cache_data
```

for immutable/reference data.

Use:

```python
@st.cache_resource
```

for database connections or long-lived resources where appropriate.

Never cache mutable transaction results without a clear invalidation rule.

---

# 18. How to build manually without AI

## Stage 1 — Python basics

Learn:

```text
variables
functions
classes
exceptions
modules
packages
typing
logging
unit testing
```

Build:

```text
WO calculator
capacity calculator
due-date calculator
```

---

## Stage 2 — Pandas

Learn:

```text
read_excel
merge
groupby
pivot
sort_values
fillna
datetime
```

Build:

```text
Plan 2026 analyzer
```

---

## Stage 3 — SQL

Learn PostgreSQL.

Build:

```text
customer
part
work_order
wo_process
wip_event
```

Do not start with Streamlit.

First make the database correct.

---

## Stage 4 — Backend

Learn FastAPI.

Build:

```text
GET /work-orders
GET /work-orders/{wo}
POST /wip-events
GET /wip/{tracking_id}
```

---

## Stage 5 — Planning engine

Write pure Python functions:

```python
calculate_remaining_qty()
calculate_firing_ready_qty()
find_compatible_kilns()
calculate_kiln_capacity()
pack_kiln()
calculate_delivery_risk()
```

These functions should not know anything about Streamlit.

---

## Stage 6 — Testing

For every rule create a test.

Example:

```text
Input:
Order = 100
Actual = 40

Expected:
Remaining = 60
```

Then:

```text
Input:
Due = today
Cycle = 7 days

Expected:
Risk = LATE
```

Build hundreds of small tests.

---

## Stage 7 — UI

Only after the engine works:

```text
Streamlit
```

or:

```text
React + FastAPI
```

The UI becomes a display/control layer.

---

# 19. Recommended project folder

For a future larger project, use:

```text
planning_system/
│
├── app/
│   ├── api/
│   ├── ui/
│   └── services/
│
├── domain/
│   ├── work_orders/
│   ├── firing/
│   ├── capacity/
│   ├── wip/
│   └── kpi/
│
├── database/
│   ├── models/
│   ├── migrations/
│   └── repositories/
│
├── imports/
├── exports/
├── storage/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── acceptance/
│
├── config/
├── docs/
└── scripts/
```

This is much easier to maintain than a 400,000-line application page.

---

# 20. Development order for a project bigger than SL Planning Center

Build in this order:

```text
1. Database
2. Master data
3. Import engine
4. Work-order service
5. WIP event service
6. Capacity service
7. Firing planner
8. Daily planner
9. KPI service
10. QR/mobile
11. Authentication
12. Audit
13. Reporting
14. Performance optimization
15. Deployment
```

Do not build QR, dashboards and reports first.

The database and business rules are the foundation.

---

# 21. What you should learn next

A strong self-learning path is:

### Beginner → Intermediate

```text
Python
Pandas
SQL
PostgreSQL
Git
pytest
```

### Intermediate → Professional

```text
FastAPI
REST API
Pydantic
SQLAlchemy
Alembic
Docker
Linux
logging
authentication
```

### Planning-engine level

```text
Scheduling algorithms
constraint programming
linear programming
heuristics
bin packing
job-shop scheduling
finite capacity planning
MRP
MES architecture
```

### Production software level

```text
transactions
concurrency
database indexes
caching
queues
background jobs
file storage
observability
backup/recovery
role-based access
```

---

# 22. The most important lesson from this project

Do not start by asking:

> "How do I make this screen?"

Start by asking:

> "What is the business object, what is its state, what event changes it, what rule calculates it, and what evidence proves it?"

For example:

```text
Work Order
    |
    +-- Demand
    +-- Due date
    +-- Process route
    +-- Current status
    +-- WIP
    +-- Firing requirement
    +-- Completion
    +-- Delivery
```

Once this model is correct, the screens become much easier.

---

# 23. Manual development exercise

If you want to learn by rebuilding this yourself, do not copy the whole project.

Build a small version:

```text
20 work orders
5 parts
3 kilns
6 processes
1 month
```

First make:

```text
Excel import
      ↓
PostgreSQL
      ↓
WO dashboard
      ↓
Firing planner
      ↓
KPI
```

Then expand:

```text
20 WOs
→ 200 WOs
→ 2,000 WOs
→ 20,000 WOs
```

At every stage measure:

```text
lookup time
planning time
database query time
memory
error count
```

That teaches real software engineering rather than just coding a screen.

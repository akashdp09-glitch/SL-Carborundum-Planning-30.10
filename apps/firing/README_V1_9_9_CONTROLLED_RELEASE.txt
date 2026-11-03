SL PPC FIRING PLANNER V1.9.9 — CONTROLLED RELEASE

Baseline: V1.9.8 Mapping Fix. No V1.10.x scheduler code used.

Planning priorities:
1. Protect due date as much as possible.
2. Resource utilization: use an available compatible kiln when kiln/program/furniture/capacity are feasible.
3. Workload balance after due date and feasibility are protected.
4. Never release over physical/program/furniture capacity.

Capacity rules:
- T1-T12/T14: max 2 normal vitrified starts/day.
- T0: existing small auxiliary vitrified kiln, normally urgent/test; excluded from normal 2-start limit.
- R4/R5/R6: separate resinoid kiln resources; excluded from normal 2-start limit.
- Every kiln obeys its own firing cycle and next-working-day reload buffer.

Controlled changes:
- Allocator no longer stops after two total starts when T0/resin capacity remains.
- Same-program second normal load is allowed if feasible.
- HOLD suppression resets daily.
- If T0 is already used, a normal compatible kiln can still be used if a normal slot remains.
- Pull horizon follows selected planning days.
- Added real kiln schedule timeline.
- Added normal vitrified planned-vs-capacity graph.
- Added separate T0/resin resource view.
- Added kiln volume utilization chart with target and max references.
- Removed weight-utilization bar as a primary planning graph.
- Added daily unused-slot audit.

Release principle: fast horizon schedule first; exact selected-load furniture/pattern validation remains mandatory before operator release.

SL PPC FIRING PLANNER V1.9.18F6 — CONTINUOUS DAILY FIRING PULL
16-Sep-2026

Controlled correction built from F4 benchmark (not F5).

CORE CHANGE
- Future kiln planning uses ALL feasible open Plan2026 firing demand (Effective Qty), sorted Due Date first.
- Current formed/firing-ready WIP controls RELEASE only; it no longer deletes future kiln loads.
- Planner walks the firing calendar day-by-day and uses available daily kiln-start capacity. When enough compatible demand exists, it continues planning on each working day instead of waiting for current WIP.
- Future physically planned loads are committed to the calendar as FUTURE PLANNED so subsequent working days receive the next due demand.
- Planning horizon expands to cover the open-demand due-date horizon (minimum configured view; capped 730 days for safety).

WO-SPECIFIC PULL
Each planned WO now carries:
- Planned Firing Qty
- Ready Now pcs
- MAKE pcs
- Preparation Required By
- Mixing Required By
- Forming Required By
- Planning Status

RELEASE CONTROL
- RELEASE only when current readiness covers the physically planned load and physical target/weight/resin condition passes.
- FUTURE PLANNED - MAKE PARTS reserves the future firing slot and creates upstream MAKE requirement.
- FUTURE PLANNED - BELOW TARGET / COMBINE keeps the firing opportunity visible and identifies that compatible demand/occupancy still needs improvement.
- Exact physical/furniture reconciliation remains before the load is accepted into the plan.

OPERATOR PRINT
- Adds a prominent readiness block with Planned / Ready / MAKE BEFORE FIRING.
- Adds WO-specific table: WO, Customer, Category, Planned, Ready, MAKE, Forming Required By, Status.
- If MAKE > 0, sheet clearly states DO NOT RELEASE YET.

GRAPH / UI
- Daily kiln graph includes FUTURE PLANNED loads, not only RELEASE loads.
- Load tables include Ready Now and MAKE Before Firing.
- Future planned loads can be selected for A4 planning/operator review, but the sheet itself blocks release until MAKE/readiness is completed.

VALIDATION PERFORMED
- Python compile for modified modules.
- Synthetic allocator test: 12,000 pcs future demand, zero current ready WIP, 8 available vitrified kilns, target 2 starts/day. Result planned 2 starts on 16, 17 and 18 Sep and remaining load on 19 Sep; all quantities became WO-specific MAKE requirements. PASS.
- Static assertions for readiness separation and Operator Print MAKE fields.
- ZIP integrity test.

This is not a claim of factory validation. Actual Plan2026 + capacity + geometry/furniture data must still be run and reviewed before production release.

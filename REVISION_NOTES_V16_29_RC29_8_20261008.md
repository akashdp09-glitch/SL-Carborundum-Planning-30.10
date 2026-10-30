# V16.29-RC29.8 — recovery feasibility and navigation draft retention

## Base

Built on the RC29.7 local-D package, preserving the RC29.5 mobile audit/QR baseline, RC29.6 capacity-path repair and costing/KPI additions.

## Daily recovery plan

- Backorders and urgent open orders already present in Plan-2026 remain in the single calculated daily plan. The recovery view reconciles those WOs to that plan; it does not add a second copy of their quantities.
- The Weekly Recovery Action Plan now includes a WO-level recovery summary and an expandable daily allocation table by process/date.
- It checks planned route quantity against open quantity, the planned finish against the due date, and every rated section-day against its loaded daily capacity. Mixing mills are shown in mills in a separate field, never added to tonnes or pieces.
- A load above 100% is marked infeasible as normal capacity; above 103% is a hard gate. Missing capacity and QC/Cleaning timing-only steps are explicitly unverified rather than reported as feasible.
- Downloaded recovery evidence includes three sheets: Recovery Feasibility, Recovery Capacity Evidence, and Sales Production Actions. The full Daily Plan workbook also carries these recovery sheets.
- The software does not silently add overtime, reassign capacity, change customer due dates, or claim that an overloaded/late WO will be recovered. Such rows remain escalation actions for Planning, Production and Sales.

## Navigation and draft retention

- Safe scalar inputs and planner data-editor drafts now survive leaving and returning to a page within the same browser session, as long as the underlying source data has not changed.
- Uploaded source files and submitted business records continue to use the configured local CENTRAL_DATA database/source folders. Draft edits are session-local until the user saves/submits; they do not survive closing/restarting the app or browser.
- Passwords, authentication tickets and uploaded-file widget objects are excluded from the navigation cache.

## Verification executed

- Python compile check: passed for `hub.py`, `suite/`, and `apps/daily/`.
- Seven focused synthetic unit tests passed: three recovery-to-daily-allocation cases, two navigation-retention cases, and two cost/KPI cases.
- Covered on-time + within-capacity, overload + late finish, no allocation, safe scalar restoration, editor draft invalidation when the source changes, and cost/material-risk basics.
- A real workbook, Windows startup, factory capacity acceptance and operator/network performance were not exercised in this workspace. This remains a release candidate, not a guarantee of on-time recovery.

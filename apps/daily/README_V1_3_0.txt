SL PPC DAILY PLANNER V1.3.1 - QC + WO ROUTE + NCR + START-DATE CONTROL

START: double-click START_DAILY_PLANNER.bat

ROOT-CORRECTION FOR THE 8-SEPTEMBER PROBLEM
- Selected Planning Start is authoritative for EXISTING downstream WIP already evidenced by Plan 2026.
- Existing fired WIP can enter its Grinding/Cutting/Cleaning route on the selected planning start, subject to that route's capacity.
- The uploaded firing plan is an anchor for NEW firing output only. It cannot postpone already-fired Plan 2026 WIP.
- Development regression test: planning start 08-Sep-2026 produced existing Grinding and Cutting rows on 08-Sep-2026 even while a new firing load completed later.

NEW POST-FIRING FLOW
- New Firing output -> next working day QC -> following working day selected route -> next working day Packing.
- Sunday is non-working; Monday-Saturday are working days.
- QC is shown as a mandatory timing gate by default; it does not invent a QC capacity when no QC capacity master is supplied.

WO ROUTE / NCR MANAGER
- Select any Work Order and see the complete process route.
- Change post-firing route per WO: AUTO / Grinding / Cutting / Cleaning / Direct Packing.
- Enable/disable QC for an exceptional WO only when verified.
- Enter NCR quantity, stage and disposition.
- NCR HOLD / REWORK / SCRAP-REJECT reduces downstream executable quantity and remains visible as an issue.
- ACCEPT-USE does not block the quantity.
- Overrides are planning-layer only; source Plan 2026 is not overwritten.

SEPARATE ROUTES
- Grinding and Cutting are separate daily-plan sections and separate capacity/routing evidence.
- AUTO route rules remain:
  HONING / HONNING / HONE / Thai knife-honing family -> Cutting
  SEGMENT variants -> Cutting
  Shape containing ขัดพื้น or Category S/T -> Cleaning
  otherwise -> Grinding

SPEED / ACCURACY ARCHITECTURE
- Plan 2026 is imported once into the local fast store.
- Existing WIP is calculated once and scheduled globally by due date and resource availability.
- Route overrides and NCR are applied before daily calculation.
- No slow exhaustive firing geometry calculation is added to Daily Planner.

INPUTS
1) Latest Plan 2026
2) Firing Planner output
3) Included CAPACITY_DATABASE.xlsx auto-loads
4) Optional stock/BOM and Sales Forecast for material/MPS-MRP functions


V1.3.1 PLAN2026-FIRST CORRECTION
- Existing post-firing WIP is aggregated across all open Plan 2026 rows of the same Work Order.
- It is scheduled from the user-selected Planning Start date, subject only to its own route capacity/resource availability.
- Uploaded Firing Planner output controls only NEW firing output. It cannot delay existing fired WIP already evidenced in Plan 2026.
- This also removes the previous last-row-wins behavior for WOs split across multiple partial-delivery rows.

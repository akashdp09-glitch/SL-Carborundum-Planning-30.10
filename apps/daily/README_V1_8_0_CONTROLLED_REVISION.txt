SL PPC DAILY PLANNER V1.8.0 — CONTROLLED REVISION

Corrections / additions:
1. Plan vs Actual: cumulative Plan2026 Actual quantities are never plotted into future due-date periods. Future Actual is zero after the selected planning date unless dated actual evidence is available.
2. Backorder: monthwise OPEN vs CLOSED shown as grouped bars; future due months are excluded from backorder view.
3. HD JPEG dashboard 2560x1440:
   - Today delivery / packing
   - Tomorrow delivery / packing
   - Current WIP totals
   - Today's targets for all sections with major customer name
   - Today kiln loading: kiln / program / pcs / earliest due / WOs
   - Tomorrow kiln loading: kiln / program / pcs / earliest due / WOs
   - Today execution detail table
4. Capacity/Lead Time:
   - Capacity workbook machine compatibility, normal shift, OT evidence, setup, broken grinding machines, manpower, packing manpower, kiln program/cycle and Lead Time remain controlled.
   - Oven/Curing is explicit in audit/Gantt: S=2, T=3, P=3, R=2, M=1 days from Lead Time row 6; PB does not pass Oven. The time is included in Forming→Firing readiness.
5. Delivery due-date control:
   - Added Sales New Due Date Requested and Requested New Due Date.
   - Safe date still requires visible packing completion/coverage; no invented date when schedule is incomplete.
6. WO Gantt:
   - Select one or many WOs.
   - Shows all planned processes, current Actual progress %, curing/oven time gate where applicable, and suggested safe/revised due date table.
7. Operational MRP:
   - All matched materials, not top-N only.
   - Need Year / Need Month / Need Date.
   - Need Date from scheduled Preparation where available, else Due Date minus controlled internal production lead.
   - Material-specific procurement lead generates Recommended PO Date.
   - All-material monthly graph and all-material PO→Need timeline.
8. MPS:
   - Monthwise MPS pcs, production ton, and firm open WO count.
   - Product/customer/category/size detail retained.
   - Long-term MRP all-material month view no longer truncates to top 15/20.
9. Post-firing flow remains separate and controlled: Firing → QC → Grinding OR Cutting → Packing.

Validation:
- All Python sources compile successfully.
- Linked post-firing Grinding/Cutting/Packing regression passed.
- Capacity Lead Time parser checked; controlled internal lead path avoids double-counting the conflicting M Resin row.
- HD JPEG dashboard rendered successfully at 2560×1440.

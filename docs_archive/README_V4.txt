SL CARBORUNDUM PLANNING CENTER — COMBINED v4

VISIBLE CORRECTIONS AFTER v3 RELEASE REVIEW
1. Main page is now the planning cockpit: Control | Source Upload | WIP | Backorder | MPS | Material MRP.
2. Plan-2026 upload is visible on the main page. Upload automatically synchronizes Mobile Audit Work Orders.
3. Mobile operator page remains no-login and shows where Plan-2026 is controlled. QR/manual WO audit remains operator-simple.
4. Mobile text/buttons enlarged for shop-floor visibility; English/Thai/Burmese operator labels retained.
5. Backorder analysis is visible by product category, D×T×H size, current section, pcs, ton, Work Orders and late days.
6. WIP is visible by section, due month, category, pcs, ton and Work Orders.
7. MPS demand is visible directly on main cockpit; Daily Planner keeps the validated capacity-feasible MPS/backorder-recovery engine.
8. Material MRP directly implements: Plan material codes 1–5 + CY/FB/FC close rule; Sales Forecast IDItem -> P280526 SD -> actual recipe material codes -> g/pc -> kg; stock/incoming/LAB netting when Stock file is loaded.
9. Legacy '#N/A placeholder' source rows are silently skipped rather than reported as operator import errors.

IMPORTANT CONTROLLED LIMITATION
Daily/Firing/Mobile now share Plan-2026 source and Mobile WO synchronization. Full automatic closed-loop rewriting of every process date from mobile actuals into Firing/Daily and back into Plan-2026 remains a controlled future integration; it is not falsely claimed as complete.

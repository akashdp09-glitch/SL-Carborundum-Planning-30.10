SL CARBORUNDUM PLANNING CENTER — COMBINED v3

START: START_SL_CARBORUNDUM_PLANNING_CENTER.bat
Main Control Center: http://127.0.0.1:8510
Daily / Section Planner: 8511
Firing Planner: 8512
Shared Planning Analysis: 8513
Mobile Audit: 8000/mobile

SHARED SOURCE RULE
Upload Plan-2026 once on the main Control Center. It is saved as company_data/Plan-2026-LATEST.xlsx.
Daily and Firing use this shared Plan when no local override is uploaded.
Mobile Audit automatically synchronizes changed shared Plan-2026 into its WO database when /mobile is opened.

Shared Control Center also accepts Sales Forecast, P280526 product/recipe master, and Stock on Hand for MPS/MRP/material analysis.

IMPORTANT PLANNING AUTHORITY
Firing Planner remains the firing-date authority. Daily Planner uses the current Firing Planner output to schedule upstream/downstream processes. v3 improves shared demand/data communication; it does not claim that every firing-plan change is automatically written back into Plan-2026. Approved revised due dates/quantities must remain controlled changes to Plan-2026.

MOBILE
Operator /mobile route requires no login. Large QR + manual WO entry is provided. Main operator labels are English/Thai/Burmese. Admin/upload/export functions remain protected.

ANALYSIS
Shared Analysis provides WIP by section/category/due date; pcs/ton/WO; backorder by category/size/weight/WO/pcs; due-month MPS demand; Plan-2026 material requirement; Sales Forecast -> P280526 SD recipe -> actual material-code requirement; and stock/LAB/incoming shortage views.

SL CARBORUNDUM SMART FACTORY CENTER V16.9 — CONTROLLED PLANNING & MOBILE LOCATION UPDATE

Based on V16.8. This is a targeted improvement; validated daily/firing engines were retained.

CHANGES
1. New Requirement Plan-2026 suggestions no longer accept a requested due date earlier than the current local date.
2. Historical execution, milestone, planning, close and date fields are cleared from copied template rows. Requested sales delivery is written only to the sales delivery field; internal warehouse receipt/revised dates remain blank until confirmed.
3. Similar-row ranking compares product/specification, exact dimensions, customer, and limited category evidence instead of token matches over the entire historical row.
4. Output trims trailing blank headers from the unusually wide formatted Plan-2026 sheet before building suggested rows.
5. Planning Basis identifies a weak/no historical match and explicitly states that capacity, stock/material, route, mould and process readiness still require confirmation before release.
6. Mobile physical audit has an optional phone GPS capture button. The user must still enter/confirm a recognizable factory area, machine, rack or pallet; GPS accuracy and LAN/browser permission vary by device.

IMPORTANT PLANNING LIMIT
This update prevents stale dates/statuses from being presented as a feasible plan. The new-WO screen still produces a Plan-2026-compatible proposal, not an approved finite-capacity schedule. Material coverage, section capacity, mould/tool availability, curing, and upstream/downstream dates must be loaded and confirmed before release. Missing values remain TO CONFIRM.

TESTS EXECUTED
- Python AST/compile check across all project Python files: PASS.
- New Plan-2026 header trimming and row-width fixture: PASS.
- Mobile pytest smoke test: NOT RUN; pytest is not installed in the available environment.
- Mobile Jinja template rendering and full application runtime test: NOT RUN; Jinja2/FastAPI/Streamlit are not installed in the available environment.
- Factory feasibility against stock, sales forecast, daily report and replacement review workbook: NOT RUN; those four spreadsheets were not available in this session.

STARTUP
Use START_SL_CARBORUNDUM_PLANNING_CENTER.bat as before. Review this README and verify the suggested due dates, master data, route, material and capacity before releasing any new WO.

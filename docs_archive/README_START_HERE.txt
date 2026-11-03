SL CARBORUNDUM SMART FACTORY CENTER V16.10 — NEW WO MATERIAL CHECK + SCAN SPEED FIX

This build continues the controlled V16.9 changes and adds the provided Plan-2026 and stock workbook as initial centrally seeded copies. The supplied department capacity workbook exactly matches the capacity database already included in the software (same SHA-256); it was not duplicated.

CHANGES
- New Requirement reads only real Plan-2026 header width, avoiding the formatted 16k-column range that previously caused unnecessary scan/memory work.
- Historical values are copied only after a minimum match score; no weak-match first-row fallback.
- Historical execution/milestone/date/close fields are cleared. Bangkok local today is used to reject past requested due dates. Sales due date stays separate from internal receipt/revised dates.
- Adds MATERIAL_FEASIBILITY output: uses component code/grams from the matched historical recipe, scales by proposed quantity, and compares exact material codes with stock balance in grams. Substitution is not applied automatically.
- Mobile audit includes optional phone GPS capture in addition to manual factory location and photo capture.

DATA / PLANNING LIMITS
- Material consumption is a historical recipe estimate, not a newly confirmed BOM. The stock file is only a snapshot; verify current quantities with Stores before release. Its Plan2026 sheet contains an internal marker date of 2026-07-03; that marker is not treated as a confirmed stock snapshot date.
- The supplied capacity database has process standards, lead times and historical machine/product data, but no live dated machine bookings. This build does not claim to book finite capacity or promise a feasible due date. Confirm machine/mould availability and loaded schedule before releasing new WOs.
- The revised forecast, MD daily report and replacement/review workbook were not available in this session, so forecast netting, current work-center loading and replacement-order logic were not validated.
- Requested values with insufficient evidence remain TO CONFIRM. A proposal is not a released production order.

TESTS EXECUTED
- Python AST parse and compileall across all Python files: PASS.
- Plan-2026 header-width fixture and stock/capacity workbook inspection: PASS.
- Capacity workbook SHA-256 compared with bundled CAPACITY_DATABASE.xlsx: identical.
- ZIP integrity check: PASS.
- Mobile pytest and full app runtime/template checks: NOT RUN; pytest, Jinja2, FastAPI and Streamlit are not installed in the available environment.

STARTUP
Use START_SL_CARBORUNDUM_PLANNING_CENTER.bat. Review active sources, material estimate, route, dates, and real capacity before release.

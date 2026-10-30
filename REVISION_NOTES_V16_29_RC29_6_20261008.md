# V16.29-RC29.6 — RC29.5 capacity recovery and costing/KPI integration

## Base

Built from the complete saved `V16.29-rc29.5_COMPLETE_CORRECTED_20261007.zip`, not RC29.1 or V17. Existing RC29.5 pages, mobile audit/QR, recovery logic, D: storage setup, and bundled capacity workbooks are retained.

## Changes

- Daily Planner repairs a saved capacity path when it points at a missing file from an older extracted release. A valid custom path is retained; otherwise the active shared capacity workbook is tried, then the included `apps/daily/CAPACITY_DATABASE.xlsx`. A final guard reports the exact missing bundled path if the package is incomplete.
- Added a focused regression test for stale and still-valid capacity paths.
- Added traceable Resin/Vitifile/Replacement costing uploads through the revisioned Source Manager, with material shortage exposure, cost-source evidence, Plan rejection reconciliation, and CSV downloads.
- Added the cost page to Reports navigation and English/Thai F1 help. Existing Plan and Stock uploads are reused.
- Source-reported replacement cost remains separate from unapproved diagnostic alternative. Differences in source formulas, units, and rejection counts are not silently resolved.

## Verification executed

- Original RC29.5 ZIP integrity passed; capacity workbooks exist at `apps/daily/CAPACITY_DATABASE.xlsx` and `apps/firing/CAPACITY_DATABASE.xlsx`.
- Full Python compile check passed.
- Cost/KPI synthetic unit tests: 2 passed.
- Capacity fallback regression checks: 2 passed (a stale old path selects the packaged workbook; a valid custom path is retained).
- Recovery worksheet and existing recovery/navigation regression checks passed; two KPI source slots and six section Daily Status slots were checked.
- The mobile source files were carried forward unchanged from RC29.5. Live mobile tests could not run here because pytest, Flask/FastAPI runtime dependencies, and OpenCV are unavailable. Streamlit UI, Windows startup, real phone camera, factory Wi-Fi, concurrent operators, and factory data acceptance are not verified.

## Important diagnosis

The RC29.5 ZIP already contains the capacity workbook. The reported traceback is consistent with `daily_result.pkl` restoring a stale absolute capacity path from an earlier installation. The application now repairs that path instead of treating it as a missing upload.

## Data safety

No live database, CENTRAL_DATA, photos, or source workbooks are packaged. Keep the existing working program and data folder during testing. This RC29.6 ZIP is a development candidate because it is not rebuilt from a Git commit available in this workspace.

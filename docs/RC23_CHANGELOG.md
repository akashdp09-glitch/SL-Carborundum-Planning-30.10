# V16.29-rc23 change log — 2026-10-06

- Reordered Planning Center navigation into Home/Reference, Planning, Production & Part Tracking, Reports, and Data & Control. Removed duplicate WIP navigation links and source-update popups from the Daily Open/Closed and section-entry pages.
- Consolidated WIP reporting into one central page with separate Plan-2026 Planning WIP and Production WIP snapshot sections, units, source files, and cut-off guidance. Removed repeated WIP totals from the Daily dashboard and weekly review; related planning calculations remain in their own planning outputs.
- Made Daily Open/Closed a read-only report and moved section OPEN/CLOSED entry to Production → Update WO Section Status. The report now lists latest saved section status and full event history. Manual section events never close the whole work order by themselves.
- Added Bangkok event ID, Plan-2026 source file/row and explicit quantity-unknown flag to section entries, with additive database upgrade support. Unknown quantity is stored as NULL and an explicit flag.
- Added Monthly Planning KPI Scorecard from the 11 revised output KPI definitions/targets. Each month entry requires numerator, denominator and source evidence, and saves append-only revisions in the main planning database. Department plan-vs-actual and warehouse-delivery KPI workbook analysis remains a separate report.
- Included revised KPI workbooks as references in `knowledge/kpi/`.

## Verification

Python compilation and focused persistence/migration checks passed in the cloud workspace. `pytest` and Streamlit/Plotly were not installed, so the automated suite and interactive UI could not run here. Windows startup, company Z: share, mobile camera/QR, and concurrent operator behavior remain unverified. This ZIP is a release candidate, not a factory-validated production release.

# SL Planning software audit — 23 September 2026

**Result: controlled review candidates, not a factory-approved scheduling release.**

Audited Daily Planner V1.9.52 and Firing Planner F12Z.48. Candidate versions are Daily V1.9.53 and Firing F12Z.49. Existing scheduling, kiln loading, geometry, furniture, physical readiness and safety algorithms have not been rewritten. The shared Plan2026 reader has two deliberate changes: F → P normalization and a fail-fast guard for a recognized incompatible column layout.

## Critical finding: Plan2026 mapping

The available `Plan 2026-2-Update-020926.xlsx` has 3,208 imported order rows, but the default process mapping does not match this workbook. The initial import completed without an exception while returning zero WIP in all downstream stages. **Successful import alone therefore did not establish data correctness.** Those initial WIP results were excluded from delivered reconciliation evidence.

Verified process coordinates in this specific workbook:

| Process | Planned | Actual | Status |
|---|---|---|---|
| Preparation | DW | DX | DY |
| Mixing | FH | FI | FJ |
| Forming | GS | GT | GU |
| Firing | IB | IC | IE |
| Grinding / Cutting | JM | JN | JO |
| Packing | KX | KY | KZ |

The candidates stop when this expanded layout is detected with an incompatible process mapping. They do not silently choose a different mapping. Additional fields also need confirmation: default REJECT=FH reads Mixing plan in this file; default APPROVE=FG reads an actual Mixing date; default Sales Delivery Date=IB reads Firing planned quantity. Do not correct only the six process triplets and assume all other fields are valid. Dates, closure, NCR, reject, approval and firing dates need a complete mapping profile before scheduling.

## Actual Production source audit

All five bundled September WIP workbooks were read at WO level. Counts below are source rows, not unique factory WOs. Negative balances are retained as source evidence rather than clipped to zero.

| Source | WO rows | Negative balances | Rows with any detected issue | Reader time here |
|---|---:|---:|---:|---:|
| Mixing | 542 | 41 | 43 | 0.17 s |
| Forming | 283 | 38 | 46 | 0.18 s |
| Firing including curing area | 304 | 37 | 37 | 5.75 s |
| Grinding / Cutting combined | 599 | 16 | 64 | 0.21 s |
| Packing | 430 | 34 | 43 | 0.13 s |
| Total section records | 2,158 | 166 | 233 | About 6.4 s |

Issue rows include negative quantities, closed orders with nonzero balances, missing quantities, unmapped categories/statuses or cached formula errors. Categories come from the source category field, not the WO prefix. F is normalized to P.

Two Firing summary category rows fail `Total WO = Open WO + Closed WO`. The Firing detail sheet declares 1,048,351 rows although only 304 WO rows were extracted. A sparse XML reader avoids allocating a million-row table and records filename, sheet, Excel row and source SHA256. Times are measurements in this environment, not Windows performance guarantees.

These discrepancies are **data reconciliation items**, not confirmed causes of late delivery. The supplied snapshots do not establish a common factory cutoff. Production gross weight must not be declared equivalent to Planning net weight. Curing is in the Firing area but does not prove firing readiness. Production combines Grinding and Cutting; piece comparisons require verified route and cut-factor definitions.

## Changes made

- Shared category import: exact F category becomes P.
- Shared Plan2026 import: detect the expanded-layout mismatch before calculating a plan.
- Shared interactive review: content fingerprints replace shape-only refresh detection; applying corrections reruns charts and retains a downloadable correction audit.
- Production WIP: upload fingerprints use file content, so replacing a same-named file refreshes the source.
- Planning open-WO counts exclude zero-WIP rows. Nonpositive unit weights remain unavailable in the comparison; incomplete grouped weights do not become misleading partial totals.
- Reconciliation commentary reaches `prod_wip_comparison_current`, which downstream reports read. Calculated fields are protected from edits that would otherwise be silently ignored.
- WO evidence: section selection, category and WO search, clickable all/open/issue counters, row-level evidence and editable cause/action/owner/due/review fields. Notes and their change history persist under `USER_REVIEWS/wip_review.json`; changed source hashes retain separate identities.
- PowerPoint: Monday-to-report-date weekly, month-to-date monthly, half-year-to-date and year-to-date job-history filters. WIP stays a separately labelled snapshot. Blank source cells stay unknown. Current-period KPI upload and sheet selection are available. Only the selected report is generated on request.
- PowerPoint: editable source-weight chart and paginated WO issue/action tables. Axis IDs normalized for package compatibility.
- Daily Excel exporter: unknown attainment displays PENDING, linked headline formulas, planning-load label corrected, per-date review state restored when switching dates, and reviewed WIP comparison exported when available.
- Monthly job reader: day 31 included, invalid month days skipped, content-based refresh and source row/column retained.
- Packaging and Diamond reference files remain bundled unchanged.

## Requirement coverage and remaining work

| Requirement | Candidate status | Remaining acceptance work |
|---|---|---|
| Attractive clickable dashboards | Improved existing drilldown and new WO issue counters | Unified navigation and all dashboard cards/charts still require a full interaction pass |
| Planning vs Production by process/category/WO | WO evidence and diagnostic comparison added | Complete Plan2026 mapping; reconcile Planning-only WOs and duplicate WO keys; common cutoff confirmation |
| P/R/S/T/M/PB; F → P | Implemented in shared reader and review layer | Audit remaining legacy parsers before global normalization claims |
| Curing and Grinding/Cutting distinction | Labels and comparison controls preserve distinction | Explicit curing quantities and conversion evidence remain necessary |
| All edits update all outputs | Review charts and selected exports improved | A single authoritative override store for every module is not yet implemented; legacy analysis edits remain local to that analysis |
| Accurate verified capacity | Actual database parser exercised, algorithms preserved | Verify rate time bases, shift minutes, manpower and Preparation default; reject unsupported conversions across every scheduling path |
| Daily Excel and periodic PowerPoint | Files supplied and report-export functions improved | Latest daily actuals, dispatch evidence and period KPI files needed to populate current performance |
| Bundled standards, period KPI uploads | References preserved; KPI uploader added | Validate the approved KPI workbook schema and targets; no invented score calculations |
| Firing constraints | Safety/geometry/scheduler files unchanged | Run exact output regression against latest issued firing schedule and accepted benchmark |
| Imports/errors/export checks | Eight focused regression tests, real imports, UI smoke and export checks | Windows execution, print scaling and complete live factory scheduling regression pending |

## Capacity findings

The unchanged capacity parser successfully read 20 Mixing records, 39 Forming records, 7 kiln-program records, 3,789 Grinding records, 36 Packing records and 8 validation records from the bundled capacity workbook. This proves parser execution, not the correctness of every scheduling conversion.

Items needing explicit verification include the Mixing `CAP-โม่` time basis, nominal eight-hour columns versus working minutes, manpower/setup deductions, the Preparation default of 1,200 kg/day and any product-specific piece/weight conversion. These defaults were not silently re-engineered in this revision. Ambiguous text dates also generated a parser warning and need a verified date-format profile.

## Tested baseline

- Original sources: 19 Daily Python files and 13 Firing Python files passed syntax parsing.
- Revised apps: initial Streamlit AppTest startup completed without an exception for each application.
- Production WIP screen: initial render, switch to Firing evidence and issue-counter drilldown completed without an exception. This is not a complete browser usability or Windows test.
- Eight regression tests passed: category normalization; scheduling-file preservation; actual WIP extraction; duplicate Planning WO rejection; reporting-period/export behavior; missing Excel attainment; incompatible actual Plan2026 import rejection; atomic note persistence.
- All four PPTX packages passed package-integrity and geometry checks with zero findings. Rendered slides were reviewed; native Microsoft PowerPoint execution was not available.
- Excel: main and supporting views rendered; formulas and source totals inspected; no formula errors in the inspected scan. A4 landscape one-page print area configured. Native Excel printing was not available.
- The standalone daily workbook is formula-linked to editable daily inputs and WIP source summary. Blank current capacity/output/dispatch values remain PENDING. It is not a completed 23 September performance report.

## Controlled development sequence

1. **Data contract first.** Confirm the current Plan2026 file and every mapped field; validate status vocabulary, date formats, source cutoff, weights and duplicate WO rules. Acceptance: selected WOs match Excel cell values in every process, with no silent zero substitution.
2. **Firing regression.** Use current issued firing output and the accepted benchmark. Check T0, resin, two vitrified starts/day, readiness/curing, geometry, furniture and underfilled-load visibility. Acceptance: every reported load reconciles across tables, graphs and operator print.
3. **Capacity verification.** Document native units, rate period, machine availability, setup and manpower for each source row. Acceptance: unsupported capacity remains unavailable and never becomes a fabricated feasible plan.
4. **Shared editable data.** Introduce one versioned review/override store used by both apps, with source hashes, approvals, audit and explicit recalculation dependencies. Acceptance: one test correction updates every affected chart/report, survives restart and never changes source data silently.
5. **Management and UI acceptance.** Populate daily delivery/actual/capacity/risks, period KPIs, MTS safety stock and TEST priority. Validate WO-level actions, reports, desktop/mobile readability and speed using the same data.
6. **Release.** Run actual Windows imports, scheduling and exports in a separate folder. Publish a precise change log and rollback copy only after the acceptance checks pass.

## Use these candidates

Extract each ZIP into a new folder. Keep the working installation and its user data intact. Use the existing start BAT files and existing Python environment. This delivery is Python source, not a standalone EXE or a bundled Windows runtime. `VERIFY_RELEASE.py` checks syntax and unchanged original modules. Its PASS does not authorize factory release.

For the next scheduling-validation step, supply the latest Plan2026 workbook, current issued Firing output, current Production WIP snapshot/confirmed cutoff and KPI workbook for the reporting period. The supplied capacity database and bundled Packaging/Diamond standards have already been retained.

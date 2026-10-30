# V16.29-rc23 navigation, WIP, status and KPI changes

## Navigation map

- **Home & Reference**: main page and code/part knowledge.
- **Planning**: Daily Plan → Firing/Kiln Plan → MPS/Future Plan → New Part Plan → Material MRP → Capacity/Recovery → Packaging → Planning Suite.
- **Production & Part Tracking**: Update WO Section Status → Mobile Part Audit/QR → Mobile Audit Register.
- **Reports**: Daily Open/Closed WO Report → WIP — Planning vs Production → Daily Status Analysis → Monthly Planning KPI Scorecard → Department KPI Workbook Analysis → Backorder/Delivery Risk → Usage & Edit History.
- **Data & Control**: Upload/Replace Source Files and Source Traceability.

The former WIP display in the Daily dashboard and the duplicate Daily Planner WIP page now direct users to the single central WIP page. Home no longer repeats WIP totals. The former status editor inside the report is now a separate Production action.

## WIP definitions shown in the central page

| Display name | Source | Meaning | Units / caveat |
|---|---|---|---|
| **PLAN-2026 PLANNING WIP** | Active Plan-2026 workbook | Remaining planning quantity by process/section | Pieces and estimated net tonnes. Not a physical count. |
| **PRODUCTION WIP** | Active department WIP workbooks | Open production WIP reported by each section | Section WO records and gross tonnes. Section counts are not unique factory WOs; missing sections are blank, not zero. |

The page includes active filenames/paths, upload timestamps when the source registry has them, and display time. Differences are not automatically corrected; compare matching date cut-offs, category, process route, and weight basis.

## Open/Closed workflow and traceability

- **Reports → Daily Open/Closed WO Report** shows workbook-derived open/closed status and the saved manual event register.
- **Production → Update WO Section Status** records a section OPEN/CLOSED event only. It does not alter Plan-2026, the Daily Status source workbook, actual quantities, or whole-order closure.
- Each saved event records unique Event ID, Bangkok timestamp, user, WO, section, status, quantity or explicit quantity-unknown flag, remark, source reference, and Plan-2026 source row when available. Existing event databases receive additive columns on first read/write.
- Event ledger: `%SL_COMPANY_DATA%\daily_status_entries.sqlite3` (default `Z:\Planning\Planning_Python data\COMPANY_DATA\daily_status_entries.sqlite3`). Unknown quantity is saved as NULL plus an explicit flag, not zero. The event ledger is separate from the main database to preserve the existing RC22 storage design.

## Monthly Planning KPI scorecard

The new **Monthly Planning KPI Scorecard** reproduces the 11 output measures and monthly targets in the revised Planning KPI Measurement Evidence workbook. A user enters numerator, denominator, source evidence, and notes. A save appends a new revision; the scorecard shows the latest revision for that KPI/month and offers a revision history and CSV export.

| Code | KPI | Monthly target |
|---|---|---:|
| PL-M01 | Capacity Gate Compliance | 100% |
| PL-M02 | Firm Demand Plan Coverage | 98% |
| PL-M03 | Delivery-risk Recovery Coverage | 100% |
| PL-A01 | Master Plan Cut-off Delivery | 95% |
| PL-A02 | Master Plan First-pass Accuracy | 98% |
| PL-A03 | Production Status Update Timeliness | 95% |
| PL-A04 | Planning Report Delivery On-time | 100% |
| PL-C01 | Work Order First-pass Accuracy | 98% |
| PL-C02 | Work Order Issue SLA | 95% |
| PL-C03 | Material Shortage Action Update On-time | 95% |
| PL-C04 | Daily WO-section Status Record Completion | 95% |

Measurements are manual, evidence-based submissions. They are not yet auto-derived from the live planning or production events. Department plan-vs-actual and warehouse-delivery source KPI workbook analysis remains a different report with two separate inputs. Both revised KPI workbooks are bundled under `knowledge/kpi/` for reference.

## Files and storage

Values are inherited from `SERVER_STORAGE_CONFIG.bat`:

- Shared input workbooks and source copies: `Z:\Planning\Planning_Python data`
- Main planning/audit/KPI database: `Z:\Planning\Planning_Python data\DATABASE\sl_planning.db`
- Manual section-status event ledger: `Z:\Planning\Planning_Python data\COMPANY_DATA\daily_status_entries.sqlite3`
- Part audit photos: `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\PHOTOS\MOBILE_AUDITS`
- QR scan pictures: `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\PHOTOS\QR_SCANS`
- Reports and exports: `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\REPORTS`

## Verification limits

- `py_compile` passed for the modified Python files.
- Focused checks passed for section-event persistence, additive upgrade from an older status table, monthly KPI calculation, and append-only revision history.
- Pytest/Streamlit/Plotly were unavailable in the cloud workspace for full suite and live UI checks.
- Windows install, Z: permissions, real phone camera/QR scan, concurrent mobile submissions and factory network remain untested.

# Development status and verification

## 2026-11-03 — owner clarified firing WIP and loading semantics

- `เข้าเผา` is firing WIP from the preceding drying process after forming; `จำนวนเข้าเตา` means quantity loaded into the firing kiln. Neither establishes firing completion. Recorded the distinction in the revision scope and workbook findings; confirmed firing output remains separate (`เตาจ่าย`).
- Planning must distinguish waiting WIP, reserved existing kiln loads and confirmed output, preventing repeat allocation and double counting. This records the required behavior; engine implementation remains blocked by the unavailable application ZIP. Only KPI-definition questions remain unresolved from the workbook review.

## 2026-11-03 — supplied workbook intake and review (partial; application blocked)

- Received and inspected six real workbooks; see `WORKBOOK_FINDINGS_20261103.md`. The full software ZIP exceeds the 32 MiB transfer limit and could not be downloaded. A smaller source-only ZIP is requested; the missing application modules remain unavailable.
- Added standalone read-only evidence staging, not operational integration: six imports / 92,617 bounded rows retained in a separate evidence database. Repeated actual-file intake produced no duplicates; SQLite integrity passed; four SYNTHETIC tests passed. Original files and application data are unchanged.
- Recovery second sheet: 707 rows / 601 distinct WOs / 62 repeated keys. Source WO labels are 305 on plan, 294 late and 2 mixed; they are not verified performance. Generated a review workbook with customer/period/source detail and explicit quantity/duplicate limitations.
- Six staff KPI measures were found. Requested the three manager KPI mapping/weights, clarification of conflicting target versus threshold cells, and the meaning of kiln-loading versus completed curing evidence. No score, inferred production completion, speed gain, revised UI or completed user manual is claimed.

## 2026-11-03 — owner revision scope and initial inspection (blocked)

- Captured the owner's planning accuracy/speed, three manager KPIs derived from staff evidence, actual-production precedence, Recovery-only sheet analysis, bilingual/icon UI, plan edit traceability, persistence, Help and illustrated Word-manual requirements in `REVISION_SCOPE_20261103.md`.
- Owner confirmed identical inputs/rules must yield identical plans, with reasons for any changed results.
- Inspected current HEAD: daily/firing/mobile/shared source directories and controlled-release tools are missing. New workbooks and UI images were not available. Existing startup validation fails on missing `suite`; mobile tests and cloud validation cannot run because their paths are absent. No application implementation, data import/deletion or speed improvement is claimed.
- Identified general edit-save audit failure suppression, missing edit reasons and three unresolved `uuid` references for correction once the full source and release workflow are restored. Production workbook mapping is recorded, without inventing sheet structure or KPI definitions. Production data and application code remain unchanged.

Version: see `VERSION` (`V16.29-rc29.46`, release candidate; not factory-validated). Windows startup and live factory workbook acceptance remain unverified. Windows uses the private runtime installer in the RC29.7 launcher; it has not been executed on a factory Windows PC here. This package is a workspace snapshot without verified Git commit metadata; do not treat it as a merged PR.
Requirements: `PROJECT_REQUIREMENTS.md` (R1-R12 + factory approval). Rules for agents: `AGENTS.md`. Approval record: `FACTORY_APPROVAL.md` + `knowledge/approved_rules.json`.

Legend: **Done (cloud-verified)** = implemented and covered by an automated or headless-browser check on the cloud VM with synthetic data (not factory validation). **Partial** = some of it exists. **Open** = needs owner input. Nothing here is claimed production-ready; see `docs/LIMITATIONS.md`.

## 1. Stage tracker
| Stage | Scope | State |
|---|---|---|
| A | Desktop/mobile scope; shared audit record model | Done (cloud-verified) |
| B | Mobile identified/unidentified capture; QR workflow; real QR decoder | Done (cloud-verified with real QR images); on-phone tests pending |
| C | Shared Source Manager, consistent closure/backorder, September analysis, performance | Done (cloud-verified) |
| D | Capacity registry, MPS/MRP-style new-part planner, OCR/PPTX extraction, bilingual F1 help | Done as provisional tooling; blocked on owner inputs for confirmation (section 5) |
| E | Release integrity (four failing files), reproducible environment, Windows ZIP and docs | Done; ZIP built from a clean commit (section 6). Windows install untested |

## 2. Factory approval (2026-10-04)
The owner approved the supplied technical documents, capacity standards, process instructions and explicit requirements as factory rules. Recorded in `FACTORY_APPROVAL.md`; machine-readable rules (CAP-1..6, CLOSE-1/2, DATE-1, DATA-1, SRC-1, KNOW-1, MOB-1, PERM-1, CONFLICT-1) in `knowledge/approved_rules.json`, each naming its implementing code and test, and searchable from F1 help in Thai and English. Dated stock, WIP, plans and forecasts remain dated evidence. Conflicts between approved sources are shown with exact cells and a single decision question (section 5).

## 3. Implementation map (new in this stage)
| Requirement | Module | Test |
|---|---|---|
| 1 Capacity (units, time basis, cells, gaps, conflicts, utilisation per unit kind) | `suite/capacity.py`, `suite/capacity_page.py` (workbook `apps/daily/CAPACITY_DATABASE.xlsx`, copy in `apps/firing`) | `suite/test_capacity.py` |
| 2 Shared Source Manager (single import, sha256 dedupe, append-only revisions, 2 KPI + Daily Status per section, header-based sheet roles, active source/timestamp/affected modules) | `suite/source_manager.py`, `source_manager_page.py`, `sheet_roles.py`, `plan_reader.py` | `test_source_manager.py`, `test_shared_source_consistency.py` |
| 3 Closure/backorder, September analysis | `suite/closure_rules.py`, `sept_analysis.py`, `sept_page.py`; `docs/CLOSURE_AND_BACKORDER_RULES.md` | `test_closure_rules.py`, `test_sept_analysis.py` |
| 3 New-part / project planning (Bangkok today, reservations, bookings, firm vs forecast, drafts/scenarios, exports) | `suite/newpart_planner.py`, `newpart_page.py` (scenario store `<SL_SHARED_ROOT>/DATA/newpart_scenarios.sqlite`) | `test_newpart_planner.py`, `test_newpart_page_ui.py` |
| 3 Requirements (MRP-style) | `suite/requirements_engine.py`, `requirements_page.py` | `test_requirements_engine.py` |
| 4 Knowledge extraction (OCR tha+eng, PPTX call-outs, page/slide refs, review flags) | `knowledge/extract_documents.py` -> `DOCUMENT_EXTRACTION.json`, `_REVIEW.csv`; `suite/knowledge_page.py`; `docs/KNOWLEDGE_DATABASE.md` | `test_help_f1.py` |
| 4 Bilingual F1 help (18 entries, approved rules, OCR hits labelled UNVERIFIED) | `suite/help_f1.py`, `suite/wo_codes.py` | `test_help_f1.py`, `test_wo_codes.py` |
| 5 Mobile/desktop scope, permission matrix | `apps/mobile/audit_v2.py`, `app.py`; `docs/PERMISSION_MATRIX.md` | `apps/mobile/tests/` |
| 7 QR decoding | `apps/mobile/qr_decode.py` (fallback passes, multi-code refusal, HEIC status) | `test_qr_decoding.py` (30, real images) |
| 7 Concurrency, retries, quantity, uploads | `audit_v2.py` (`_validate_quantity`, finite and non-negative; no upper cap) | `test_concurrency_and_uploads.py` (23) |

Mobile database migration `v2_001_audit_register` is additive and idempotent; before migrating a database that has data, a copy is written to `<SL_SHARED_ROOT>/BACKUPS/sl_planning_pre_v2_001_audit_register_<time>.db`. Rollback: `docs/MIGRATION_BACKUP_ROLLBACK.md`.

### Deliberate behaviour changes (carried from the earlier stage)
1. Every signed-in role (including View Only) may record, correct and link; every write stores user, time and reason (OD-8). The anonymous hub default stays read-only.
2. `/mobile` shows scan/search/unidentified/submissions, not dashboards; the scan page never auto-opens one of several matches.
3. Server timestamps are Asia/Bangkok.
4. Whole-order closure follows CLOSE-1 (EU or FC) everywhere. The legacy analysis page (`shared_analytics.py`) already used the engine's `Overall Closed` (EU or FC) in its calculation, but its on-screen caption wrongly said "Preparation OPEN + Final OPEN"; only the caption was corrected (no calculation changed). Preparation closure never closes an order (`docs/CLOSURE_AND_BACKORDER_RULES.md`).
5. Quantities that are non-finite or negative are rejected; there is no upper cap (OD-9). Photo file names carry work order, location and date-time (OD-10).

## 4. Test results
Full table and conditions: `docs/TEST_RESULTS.md`. Summary (cloud VM, synthetic data): 91 suite+release tests pass, 85 mobile tests pass, `VERIFY_RELEASE.py` (daily and firing) pass, headless renders pass, mobile API and browser checks 0 failures. Not factory validation.

Performance (conditions in `docs/PERFORMANCE.md`): register page ~85 ms server-side at 20,000 audit rows; pages 0.3-0.5 s under emulated 4 Mbps; one 3.7 MB photo submit 15 s at 2 Mbps up (60 s at 0.5 Mbps). The photo upload is the dominant user-facing cost.

## 5. Owner decisions of 2026-10-04 (applied)
Record: `knowledge/owner_decisions.json`. Closed: OD-1 metric tonne; OD-2 mixing = mills/day only; OD-3 forming hourly rate on rows 28/33/38/40-43; OD-4 machines not working (cells D7-12, D15, D19, D25-26, D32; editable); OD-5 resin firing = PB only, 2 days (workbook 3 days still shown as conservative); OD-6 Sunday off + holiday selector; OD-7 forecast netted by firm same product/month; OD-8 all signed-in roles editable and traceable; OD-9 no quantity cap; OD-10 photo names = WO + location + date; OD-12 example workbook not available.

Still open:
1. Resin 2 days vs workbook 3 days (Lead Time!F7, Cap เตา!H7:H8): both shown until answered.
2. Reasons for the 10 unreviewed legacy controlled changes (`docs/RELEASE_INTEGRITY.md`). The owner asked for them; none were supplied.
3. Knowledge database: restore `knowledge/knowledge_base.sqlite` from the existing installation.
4. Real factory locations (buildings, racks, bins) for `/admin/locations`.
5. Public holiday list for this year (users can enter them; none were supplied).

## 6. Release
* Four files that failed the daily/firing release checks: investigated, each change explained and recorded through `scripts/release/controlled_change.py` with evidence tests; no checksum was edited by hand and no check was disabled (`docs/RELEASE_INTEGRITY.md`).
* Cloud environment is reproducible: exact pins (`requirements-cloud.lock.txt`), `scripts/cloud/install.sh`, `scripts/cloud/validate.sh`, drift check (`docs/ENVIRONMENT.md`).
* Windows ZIP: `python scripts/release/build_release.py --verify` (needs a clean tree) produces `dist/SL_Carborundum_Planning_<version>_<commit8>.zip`, its `.sha256`, and `RELEASE_MANIFEST.json` naming the exact commit. The ZIP excludes live data, databases, photos, QR output, secrets, the cloud tooling and dated Plan/LATEST workbooks. Instructions: `docs/INSTALL_AND_UPDATE.md`, `docs/STORAGE_GUIDE.md`, `docs/MIGRATION_BACKUP_ROLLBACK.md`, `docs/ON_PHONE_CHECKLIST.md`.
* The live factory installation has not been touched or replaced.

## 7. Reference files from `main` (intake 2026-10-04)
Inventory in `knowledge/REFERENCE_INTAKE_2026-10-04.csv`; extraction in `knowledge/DOCUMENT_EXTRACTION.json` (grinding PDF 72 pages, 30 flagged for review; PowerPoint 138 units, 41 flagged, 47 call-outs matched to table rows; pictures on slides 8, 11-16, 18-20 not interpreted). `Packaging-Standard-LATEST.csv` is a registered-product code list (master data); the Plan workbook is dated operational data.


## 8. V16.29-rc22 corrections (2026-10-06)

See docs/RC22_CHANGELOG.md. Daily Status upload prompts now have one shared entry point (Home; multi-file section drop area), manual scan/type section entry requires a confirmed WO, and status events use SQLite with a unique retry ID. Desktop traceability lists the exact event database path; operator mobile no longer exposes the signed-in name or credential-file guidance. Cloud syntax and focused direct persistence checks passed; pytest, live Streamlit, phone camera, Windows and factory network share were not available for verification.


## 9. V16.29-rc23 navigation, WIP and KPI register (2026-10-06)

See `REVISION_NOTES_V16_29_RC23.md`. WIP totals now have one central destination with separate Plan-2026 Planning WIP and Production snapshot definitions. The read-only Open/Closed report is separated from section-status entry, and saved section events include event ID and source reference/row. A monthly Planning KPI scorecard was added using the 11 revised output KPIs; monthly numerator/denominator records are evidence-entered and append-only. Focused Python syntax and SQLite checks passed; this workspace did not have pytest or Streamlit, and Windows/phone/factory-share testing remains pending.

## 10. V16.29-rc24 operator navigation, privacy and local storage (2026-10-06)

See `REVISION_NOTES_V16_29_RC24.md` and `START_HERE_V16_29_RC24.txt`. Home now has direct links and bilingual function search for Daily Plan download, Daily Open/Closed, WIP, monthly Planning KPI, and audit. Dashboard due-today/tomorrow dates include weekday and full calendar date; Thai customer names retain the Plan-2026 source spelling, while production contexts suppress customer fields. Hub login uses a signed eight-hour session handoff to planner pages to avoid repeated login prompts when switching tabs. Database, source, report and photo defaults use the requested local D: `CENTRAL_DATA` root. Mobile live camera QR scanning still requires HTTPS and an installed/trusted certificate. Audit camera, phone connectivity, Windows install, and the D: write permissions are unverified on the actual factory devices. This is an unvalidated release candidate.

## 11. V16.29-rc25 login correction (2026-10-06)

Removed a misplaced Streamlit dialog decorator from the password verification helper. The decorator caused login attempts to open a modal titled “Today's October-2026.xls” and prevented the login check from returning normally. Added a regression test that the password verifier has no dialog decorator. This correction was found after RC24 packaging; use RC25.

## 12. V16.29-rc29.8 recovery and navigation retention (2026-10-08)

See `REVISION_NOTES_V16_29_RC29_8_20261008.md`. Weekly Recovery Action Plan now reconciles urgent WOs already present in the single daily schedule with daily section capacity, mixing mill count, planned quantity and due-date finish; the complete daily Excel export includes recovery feasibility and evidence sheets. Overload is never called feasible, and recovery demand is not duplicated. Hub and Daily Planner scalar inputs/editor drafts survive page navigation in the same browser session; source changes discard stale drafts. Seven focused synthetic tests and Python compilation pass. Real Windows launch, current factory workbook results, live phone and concurrent operator performance remain unverified.

## 13. V16.29-rc29.9 audit connectivity and process status (2026-10-08)

See `REVISION_NOTES_V16_29_RC29_9_20261008.md`. The mobile audit address now prefers configured `SL_MOBILE_HOST` (the approved `176.0.3.99`), starts the mobile service in the background from Home if needed, and the desktop audit page opens HTTP :8000 by default; HTTPS :8443 stays optional for live camera access. Process-wise OPEN/CLOSED promotes typed/USB-scanned WO entry and adds camera/photo QR decoding. When a QR photo is used, its path and SHA-256 are saved in the section event source reference. Process-close workbooks are no longer required; an optional collapsed legacy importer remains. Status events remain append-only and idempotent in local `CENTRAL_DATA`, attributed to the signed-in user. Python compilation and daily/firing release-integrity checks pass. Real Windows firewall, factory Wi-Fi, live camera and desktop Streamlit UI are not verified here; use QR photo or typing/USB scan when HTTP browser camera access is unavailable.


## 14. V16.29-rc29.10 dashboard UI and responsive tiles (2026-10-08)

Home and quick-access navigation tiles now use larger separate icons, smaller labels and a compact two-column layout on phone-width screens. This is a CSS/HTML-only change; it adds no images, network requests or extra workbook/database processing. The home image remains locally cached. See `REVISION_NOTES_V16_29_RC29_10_20261008.md`. Python syntax compilation and release-package integrity checks are recorded with the delivered ZIP. Real Windows startup, phone layout, camera, factory Wi-Fi and concurrent load still require on-device verification.


## 15. V16.29-rc29.12 dashboard hotfix and persistence (2026-10-08)

Fixed `_source_html` dashboard crash, made meeting-size text opt-in, retained daily plan snapshots across navigation and source changes (with stale-source warnings plus latest-valid-snapshot recovery), added saved/traceable recovery-action edits and visible indicative OT/date evidence, labeled Mixing mill-count capacity separately, removed “non-stacked” wording from capacity graph headings, and added a cached local company logo plus section-status QR. See `REVISION_NOTES_V16_29_RC29_10_20261008.md`. Syntax compilation and ZIP/hash verification pass. Windows, company network/firewall, phone camera and multi-operator concurrency remain unverified. Daily schedule uses existing planner overrides; a full arbitrary date/quantity row editor with automatic capacity revalidation is not included in this hotfix.


## 16. V16.29-rc29.13 backorder/recovery restore and dashboard WIP (2026-10-08)

See `REVISION_NOTES_V16_29_RC29_13_20261008.md`. The daily planner now restores the saved calculation and newest valid append-only snapshot before rendering its create action, and Backorder/Recovery reuse that result unless the user explicitly chooses recalculation. Fixed Backorder due-date editor type mismatch. Restored the dashboard Production WIP stacked-by-process/category graph with source filename and import-time evidence. Replaced the dark, short hero with the locally cached abrasive-product photograph and a larger logo. Syntax compilation passed; live Windows/Streamlit, factory files, mobile camera and concurrent user acceptance remain unverified.

## 2026-10-09 — RC29.15 WIP graphs and focused navigation

- Source base: complete RC29.13 ZIP; recovered RC29.14 hub and audit-report changes merged in. The available RC29.14 ZIP did not contain the app tree, so the package is rebuilt from the latest complete source and does not claim to include unavailable RC29.14 mobile route edits.
- Home image moved above breadcrumb; header note shortened; source trace table collapsed by default. Home dashboard analysis now includes monthly open/closed category stack and a distinct overdue-backorder summary.
- Recovery remains a distinct destination; full-day capacity % and separate Mixing mills/day graphs accompany recovery allocation evidence.
- Mobile Report now reads active Production WIP files and presents section/category graphs with source filename/time. Mobile dashboard adds lightweight process/status bars; audit/order-balance quantities stay separate from Production WIP snapshot quantities.
- F1 direct SPEC intent and mobile report aggregation are covered by new synthetic tests; source files retain the user’s D: storage configuration and audit/photo databases are excluded from the ZIP.


## 17. V16.29-rc29.16 Home presentation (2026-10-09)

See `REVISION_NOTES_V16_29_RC29_16_20261009.md`. Home now uses the supplied branded banner directly below a compact language selector, has one non-card shortcut row instead of repeated square grids, shorter status text, and a collapsed mobile-connection details panel. The Home upload expander still opens automatically when required sources are missing. `hub.py` syntax compilation passed; UI rendering and factory Windows/mobile acceptance were not run.


## 18. V16.29-rc29.17 Daily Status prefixes and audit photos (2026-10-09)

See `REVISION_NOTES_V16_29_RC29_17_20261009.md`. Numeric Daily Status prefixes 1–6 map to sections; mobile and desktop audit reports now surface photo evidence and section summaries. The mobile service binds to all PC interfaces and stores client submissions under the configured D: central data root; network routing remains outside app control. Syntax checks and synthetic SQLite/prefix checks passed; no full UI render or factory network test was available.


## 19. V16.29-rc29.18 Daily Plan create control (2026-10-09)

The Daily Plan create/update button is visible even when a snapshot has been restored; saved time and input fingerprint status are shown. A failed/rejected calculation preserves the prior plan. See `REVISION_NOTES_V16_29_RC29_18_20261009.md`. `py_compile` passed; live UI and factory data were not exercised.


## 20. V16.29-rc29.19 backorder and capacity consistency (2026-10-09)

See `REVISION_NOTES_V16_29_RC29_19_20261009.md`. Home, daily Backorder, TV/meeting, and long-range MPS now use the same overdue rule anchored to Thailand/Phan Thong current date. Future open WOs remain MPS demand, not backorders. Recovery evidence separates the recovery WOs already present in the current plan from the total day load and controlled capacity; missing allocations are clearly NOT SCHEDULED. The page shows date/section headroom and Mixing mills/day without silently adding duplicate demand. Focused syntax and synthetic tests passed. Streamlit, Windows, real factory data, and device acceptance were not available in this workspace.


## 21. V16.29-rc29.20 WIP / backorder consistency (2026-10-09)

See `docs/RC29.20_REGRESSION_FIX.md`. Home and Daily Planner use the revised delivery date (Plan-2026 column E), falling back to the initial date (column C), with whole-WO closure from Packing EU or final FC and open balance QTY minus Packing Actual. The MPS parser now uses the same balance/closure basis, separates overdue recovery from future firm demand, and restricts firm demand to the selected calendar year. Home again includes the Production-reported WIP stacked graph and source filenames/import times. Synthetic date, duplicate-WO, year-horizon and recovery checks passed; live factory source reconciliation and Windows/Streamlit acceptance remain pending.


## 22. V16.29-rc29.21 QR labels, portable CENTRAL_DATA and graph separation (2026-10-10)

See `docs/RC29.21_QR_PORTABILITY_BACKORDER.md`. QR labels now use active Plan-2026 open rows only, filter by section/location and current due-date range, print uppercase WOs directly under the QR on the same sticker, and include source/path/import/filter evidence. A copied program-local `CENTRAL_DATA` takes priority over the older rc14 D: fallback, and the ZIP excludes all live data. The TV HTML separates all overdue history from due-today/future open demand. Python syntax checks and synthetic backorder checks pass; QR image workbook test and live Windows/phone/print acceptance are not available in this cloud runtime.


## 23. V16.29-rc29.22 complete audit / status / WIP export (2026-10-10)

See `docs/RC29.22_COMPLETE_AUDIT_WIP_REPORT.md`. The desktop Track / QR → Audit Report now builds one workbook on click with full physical audit history, embedded photo thumbnails plus stored path and SHA-256, scan/event logs, unknown parts, Plan-2026 status, and separately sourced planning/scan-event/Production WIP sheets. The report is no longer rebuilt on each app rerun. This is additive; no live data is included or moved. Source compilation and synthetic report-helper/backorder/recovery tests pass; testing against the user’s full database and thousands of pictures, Windows launch, mobile camera, printer alignment and operator concurrency still requires a copied-data factory trial.


## 24. V16.29-rc29.23 QR label date-range fix (2026-10-10)

See `docs/RC29.23_QR_LABEL_DATE_RANGE.md`. QR label date pickers now allow the full supported calendar range instead of being constrained to the active Plan-2026 due-date minimum/maximum. Search and generation still filter only active-plan open WOs with positive remaining quantity by current due date. Syntax and synthetic historical/today/future date-range checks passed; live workbook and printer validation remain necessary.


## 25. V16.29-rc29.24 QR status/date filters and A4 cut-ready labels (2026-10-10)

See `docs/RC29.24_QR_FILTERS_A4_LABELS.md`. Added Open / Closed / All order selectors, due-date or WO-creation-date from/to filters, include-undated option, and trace columns for order/open quantity, status, dates and plan location. `Sticker Print` is A4 portrait with a 3×4 label grid per page, dashed scissor guides, a larger QR and uppercase WO beneath it. Existing payload remains IP independent. Syntax and synthetic filters passed; QR rendering and real printer/scanner acceptance were not available in the cloud runtime.


## 26. V16.29-rc29.25 login and workspace retention on navigation (2026-10-10)

See `docs/RC29.25_NAVIGATION_STATE_PERSISTENCE.md`. Replaced direct internal page links that dropped the signed hub ticket, clarified that upload boxes clear visually while saved central sources remain active, and retained the existing disk-backed Daily Plan snapshot restore path. Syntax and static navigation/persistence checks passed; interactive browser validation remains required.


## 27. V16.29-rc29.26 QR section selector loads active Plan-2026 (2026-10-10)

Files & Traceability now participates in shared Plan-2026 loading because its QR label generator needs the analyzed master to populate section/location choices and filter active rows. This addresses the empty selector that showed only “All sections” and returned no orders when the plan was loaded but not parsed on that page. Uses the cached plan model; does not re-import or alter the source workbook. Static checks and syntax compilation passed; validation against the active factory workbook remains required.


## 2026-10-12 — V16.29-rc29.37 Planning KPI source correction and page recovery

- Planning KPI scorecard now follows the attached `Planning_KPI_Reference_Q4_2026.xlsx`, with KPI-PL-01 through KPI-PL-09, owners, targets, weights, formulas and worksheet-row references. The two Section and Delivery/Warehouse KPI workbooks remain Production measures and are not used as Planning results.
- Monthly results are selectable across a date range; actual values are NOT RECORDED until numerator, denominator and evidence are entered. Previous score versions remain in the database but are excluded from the new definition version, preventing old incorrect definitions from contaminating the revised scorecard.
- The Planning KPI reference workbook is packaged as a controlled reference and seeded to `CENTRAL_DATA/KPI/Planning-KPI-Evidence-LATEST.xlsx` on first startup; later approved revisions are archived by Source Manager.
- Daily Status upload panel auto-expands when any section workbook is missing; problem/action analysis now says explicitly when it is empty because Daily Status sources are absent.
- Capacity page selects an existing archived, published or bundled capacity source and reports a missing archive without crashing.
- Removed the last TV dashboard chart slide so the recent three-month open/closed category graph remains visible at the end of the dashboard. Added missing `material` Source Manager label to prevent `KeyError`.
- Verification in this environment: all 169 Python files compile; KPI workbook structure/targets/weights matched all nine KPI codes; temporary SQLite KPI numerator/denominator save/load and definition-version isolation passed. `pytest` is unavailable; Streamlit/Plotly UI runtime and live factory files were not exercised. Windows launch, phone camera, server storage, printer and concurrent operators still require on-device acceptance.
- Package base: the locally available RC29.35 candidate; RC29.36 source files were not present in the workspace. No live `CENTRAL_DATA` or production workbook data is included.


## 2026-10-13 — V16.29-rc29.40 candidate (from attached RC29.39)

- Home source upload removes optional source-folder/revision prompts (import filename, content hash, importer and import time remain recorded automatically), labels the universal source picker **All software inputs**, and lists its source families. Home retains dedicated multi-file upload areas for one Daily Status workbook per section and Production WIP snapshots. Daily, Daily Status and Daily Open/Closed pages offer contextual upload links to the same central source store.
- Daily Planner's Open/Closed report now falls back to a clearly labeled Plan-2026 section/whole-order status view when Daily Status actual rows are missing or unreadable; it does not label planned status as production actual.
- Backorder dashboard/HTML totals now derive from one authoritative deduplicated overdue-WO list, directly matching the Backorder detail rule. Monthly/category chart aggregation no longer defines dashboard totals. Export parity text includes all-month WO, pcs and ton totals.
- Verification: focused backorder and open/closed unit checks plus Python compilation passed. This workspace has no project Git metadata or pytest installation; full release-integrity build was not possible. No live factory workbooks, Windows UI, phone camera, concurrent-user or on-device tests were run. The attached source ZIP's CENTRAL_DATA was not replaced or packaged; preserve the active CENTRAL_DATA folder when updating. This is a tested candidate, not a factory-validated release.

## 2026-10-13 — V16.29-rc29.41 candidate (existing firing pattern view)

- Firing page now reads the already-active uploaded firing workbook in a read-only section. It charts and lists the existing kiln loads by date, kiln and program without generating or changing a firing plan.
- If the active full output workbook contains `Floor Pattern Data`, the viewer renders the stored TOP/FRONT floor pattern by selected load and floor. For Operator Print-only sources, it shows the existing load and WO schedule and explains that physical floor coordinates are absent; it does not synthesize a pattern.
- Verification: two focused synthetic workbook tests passed for Operator Print-only and full workbook pattern data; Python compilation passed. Real plant workbook rendering, Windows launch and physical pattern validity were not verified.
- Existing `CENTRAL_DATA` remains excluded from the package and must be preserved during installation.

## 2026-10-21 — V16.29-rc29.43 candidate (recovery and product master comparison)

- Added a Source Manager slot for dated Production Recovery snapshots and Sales registered-product masters; existing Packaging Standard remains a separate Production-owned slot. All three are uploadable from Home → All software inputs and from the new analysis page. Each revision remains archived and traceable.
- Added Reports → Recovery Snapshot & Product Master Review. It preserves original due dates separately from internal recovery dates/hold text, exposes source rows and duplicate work orders, shows a monthly recovery-result graph, and downloads the source-row detail. It does not infer Production approval from the recovery worksheet.
- Added exact product-code reconciliation between Sales registration and Production packaging standard, with distinct flags for pack-quantity mismatch, undefined/missing pack quantity, duplicate Production codes and no matching Production standard. Neither master silently overwrites the other.
- Source analysis performed on the 2026-10-21 attachments: recovery sheet 554 lines / 472 unique Fac Nos; 49 duplicate WO keys. Sales register 6,789 rows / 6,703 distinct codes. Production standard 704 rows / 621 distinct codes; 569 exact codes shared. Distinct-Sales-code results: 296 quantity matches, 62 quantity mismatches, 208 missing/undefined, 3 duplicate Production records requiring review, 6,134 no Production match. Full source names, as-of dates, caveats and examples are in RC29_43_RECOVERY_PRODUCT_REVIEW_FINDINGS.txt.
- Test evidence: Python syntax compilation passed; reading the three actual source workbooks returned expected row/code counts and detected known 1-vs-10 pcs/box discrepancies. Full Streamlit UI, Windows launch and on-device workflow were not tested. Production packaging workbook parsing is deferred to the analysis page; first-run app start does not parse it. No CENTRAL_DATA or user audit data is included or replaced.

## 2026-10-21 — V16.29-rc29.44 candidate (current Plan vs dated Production recovery reconciliation)

- Clarified the different time horizons: Plan-2026 is the continuing current-state master; each Production recovery workbook is a dated activity snapshot that may retain earlier commitments across several months.
- Added a per-WO bridge on Reports → Recovery Snapshot & Product Master Review. It compares the Recovery historical due date and Production proposed date/hold with the active Plan due date, positive remaining pcs, whole-WO closure, current overdue membership, section/location and source rows. A later Plan date is flagged for authorized-revision confirmation; it does not erase the historical date or imply approval.
- Added separate results for still overdue, recovery-only cases, and current Plan overdue WOs absent from the snapshot, with CSV downloads and distinct-WO metrics. Repeated source rows remain visible and are not silently summed as extra WOs.
- Added Plan-2026 source-row tracking and synthetic tests for later dates, overdue membership, closure, missing Plan match and Plan-only overdue WOs.
- Verification: Python compilation and direct synthetic bridge checks passed. Pytest could not run because it is not installed in the provided runtime. No active Plan-2026 workbook was supplied for live reconciliation counts. Windows startup, full UI and factory use remain unverified. CENTRAL_DATA is not included or modified.

## 2026-10-13 — V16.29-rc29.42 candidate (mobile status and dashboard parity)

- The HTML dashboard previously counted overdue rows from the Daily Planner parser, while the shared Backorder page uses the full Plan-2026 model. Added a cached Plan-2026 backorder basis to the TV dashboard using the same v17 reader, due-date fallback and EU/FC closure rules as the shared Backorder page. Category/weight fields enrich that same list; the Daily result is only a fallback if parsing fails.
- Mobile Track now accepts per-section OPEN/CLOSED status with optional actual quantity and remark. It appends to the existing shared desktop floor ledger at `CENTRAL_DATA/COMPANY_DATA/daily_status_entries.sqlite3`, preserving event history and unknown quantities.
- Mobile work-order search no longer blocks for Plan sync and skips sync-thread creation when the active source revision is unchanged.
- Hub pages expose a small source-update link beyond Home; contextual source panels include KPI sources and Daily Status refreshes.
- Verification: `compileall` passed; `python -m unittest suite.test_backorder_views suite.test_floor_open_close` passed (6 tests). `pytest` and FastAPI are not installed, so the mobile HTTP integration tests could not run. This environment has no current factory workbook or phone; production totals, Windows startup, camera permissions, network reachability and concurrent-user performance remain unverified. Preserve CENTRAL_DATA on update; no user data is in the package.


## 2026-10-22 — V16.29-rc29.45 candidate (Production WIP tonnes and separate recovery bridge)

- Added one shared Production WIP reader for monthly section transaction files. It calculates open WO count as Total WO minus Closed WO, cross-checks open detail rows, and converts open-row gross weight from kg to tonnes. Missing source categories remain explicitly unclassified; summary/detail/category and workbook-title discrepancies are exposed with sheet/cell/row evidence.
- Updated Desktop WIP, mobile WIP summary and downloadable audit report to use the same source-backed definition. Production physical WIP is separately labeled from Plan-2026 open-order balance.
- Production Recovery review now deduplicates to distinct WOs for status counts, reports source reasons/notes without inventing missing reasons, and reconciles the dated recovery snapshot against active Plan-2026 separately from strict overdue counts.
- Analysis of supplied 17-Oct/20-Oct Recovery snapshots, five October section WIP workbooks, and available 12-Oct Plan is documented in `RC29_45_WIP_RECOVERY_NOTES.txt`; those attachments are not bundled. Counts are snapshot-specific and update after the latest source workbooks are uploaded.
- Verification: focused WIP/recovery/allocation/action tests passed (7 tests); `compileall` passed. Release-integrity verification and runtime UI/device checks are limited by absent Git metadata and unavailable Windows/factory environment; see `docs/LIMITATIONS.md`. This is a candidate, not a factory-validated release. No live `CENTRAL_DATA` is included.


## 2026-10-22 — V16.29-rc29.46 WIP path and section capacity graph corrections

- Fixed Production WIP workbook loading: a `Path.name` conversion had discarded the stored Central Data directory before the parser opened the workbook. The resolver now passes the full path, chooses the latest dated/revised report per section, retains prior source files, and falls back to the latest readable copy when a newer workbook is malformed.
- The same WIP snapshot reader feeds the central WIP page, Home dashboard, audit WIP summary and HTML management dashboard, so their section/category graphs use the same latest-readable inputs. Production WIP remains a separate physical snapshot from Plan-2026 planned WIP.
- Fixed daily capacity aggregation dropping `Capacity pcs`; without it PCS-rated sections were labeled incomparable and removed from the plan-versus-capacity graph. Tonnes and PCS remain separate comparisons; Mixing remains in its native mill/batch view.
- Added a direct Production Recovery Plan link on the Backorder page and kept the link on WIP, Home quick access and Reports navigation.
- The Plan-2026 WIP page and Home summary now use the light Plan parser if the larger daily analysis fails or returns no open rows; parser errors stay visible and a true empty result is not changed to a guessed value.
- Verification: 13 targeted WIP, capacity and recovery tests passed; all Python files compile. The five supplied October Production WIP reports were copied to an isolated temporary Central Data structure and read as 5 sections / 34 category rows / 122.091 gross tonnes with no source-loader errors. Forming still carries an internal worksheet-title mismatch visible as a source check.
- Release integrity checks pass with carried-forward legacy changes hash-pinned; eight Daily and three Firing entries remain explicitly pending review. Not verified: the user’s updated 22-Oct Plan-2026 workbook, Windows startup, interactive Streamlit pages, live D: Central Data, HTML export, mobile/camera or production-network setup were not available in this environment.


## 2026-10-24 — V16.29-rc29.47 recovery plan execution analysis

Added a week/month/total view to Production Backorder Recovery Plan. It reads the active recovery workbook's `แผน Recovery` plan fields (columns 168–169), actual warehouse record fields (170–171), and estimates weight per piece only where matched `Cover.GW / Cover.QTY` exists. Actual is reconciled to the same normalized WO before remaining is allocated across its planned rows. Period WO counts are distinct within periods and can overlap across periods. It includes row evidence and CSV exports. Actual workbook and synthetic calculation checks passed; browser, Windows launcher, and live-factory validation remain outstanding.

## RC29.49 — WIP, capacity navigation, and KPI trend continuity (2026-10-27)

- Promoted **Capacity vs Plan vs Actual** from Reports into the main Planning navigation and added a direct quick access entry. The Daily Planner uses the same page title and same saved calculation; charts retain the separate units for tonnes, pieces, mill/day and mill batches.
- Daily WIP now points directly to the same central WIP report as the top-level WIP menu. The report keeps Plan-2026 planning WIP and Production section snapshots separate, identifies their sources/cut-offs/units, and does not combine mismatched measures.
- Added a process-by-category stacked Plan-2026 WIP chart with per-process total tonnes labelled above each stack. Production WIP stack charts likewise show section totals. The report continues to show summary totals and source diagnostics.
- Department KPI workbook analysis now reads Source Manager's append-only revisions and preserves the newest saved revision for each calendar month, so older months remain in weekly/monthly/quarterly trend windows after a newer workbook is uploaded. A provenance expander and CSV download show source workbook, revision and import time. Existing manual Planning KPI history remains stored separately.
- Verification: Python compilation and targeted tests recorded in `docs/TEST_RESULTS.md`; tests do not validate live factory inputs or Windows/phone operation.

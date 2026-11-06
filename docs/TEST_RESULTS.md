# RC29.62 — desktop shop-floor portal, private Planning uploads and Daily crash repair

## Daily Plan

Fixes the reported IndexError from _quick_options[10] after removal of a menu item. Focus routes now use named labels and tolerate stale selections; section-specific links open the existing saved daily result with a section filter. No planning data is reset. The menu regression is tested against the actual application option list and reordered lists. This fixes that reported navigation crash; a complete factory-input daily HTML scheduling run is still not claimed.

## Desktop /scan and mobile audit

Desktop has larger Thai labels/icons, smaller English, firing and daily/section plan links, WIP/production analysis links and authenticated downloads of the active Plan 2026 and production-status originals. Section shortcuts pass a real filter into Daily. SL_HUB_URL may override the standard hub address when the factory uses a different host/port; otherwise the request host and existing standard 8510 port are used. Signed central tickets preserve the logged-in identity; target hub validates active accounts.

Find / USB Enter shows source-separated Plan 2026 section status, planned/actual quantities and dates; order/open/due fields; production status rows with source filename/revision/sheet/row/date/pieces/tonnes/quality flags; latest physical audit and photograph link when recorded; and recorded whole-order decision/history. No source is silently treated as another. Missing dates/quantities remain unknown. A formal WO closure date is not fabricated from a stage output date.

Production lookup uses an additive SQLite JSON expression index ix_production_wo and queries only the confirmed WO in the latest production_status source. It does not read private KPI evidence or reopen Excel for every scan. The import parser refreshes once via a new versioned sync marker to populate section quantities/dates. Packing uses EU, and ยังไม่ปิด is correctly OPEN. Original files and old markers remain. A refresh-in-progress message labels potentially older imported data.

Home shows desktop and mobile URLs and separate QR codes. /scan?mode=mobile omits the desktop planning navigation; narrow layouts collapse extended evidence sections. Mobile retains photo/physical-audit functions, manual search and status submission. Confirmed saves still use shared central audit/status databases and photographs, with retry IDs; typed drafts are not silently committed as production.

## Confidential Planning uploads

KPI/open-close uploads have moved to a Planning documents dialog near the bottom of Home, offered to admin/planning roles. Initial Home does not expose those filenames or upload boxes. Public production-status saved-file lists exclude staff/count/Production-KPI documents. Staff/department KPI report routes restrict other roles; management retains report viewing. Existing reports/sources are preserved, not deleted. The two production original-download routes never select KPI originals.

## Checks and limitations

12 focused source-index/navigation/account/Recovery tests passed. Mobile/API suite: 100 passed, 1 skipped. Fourteen browser checks passed, including source-separated evidence rendering, absent confidential filenames until the popup opens, desktop/mobile navigation and admin controls. Physical scanner, actual phone/network, Windows startup and full legacy planner factory acceptance remain on-device/open checks; previous broader/integrity issues remain documented. Existing CENTRAL_DATA, passwords, originals, audits and plan history are not replaced. Extract into the new version folder and reuse the existing shared data; roll back code only after stopping services and keeping the data/backups.


# RC29.61 — Recovery HTML, branded shortcut, build identity and admin accounts

Recovery has a standalone offline HTML dashboard and preview, showing pending pieces and reference tonnes, planned/actual/pending comparisons, customer/category/reason tables and searchable source rows. Generated HTML is saved under the configured REPORTS folder and available for download. It uses the same Recovery calculations as the on-screen and Excel reports; unknown weight remains unknown.

The Windows shortcut uses assets/sl_carborundum.ico converted from the existing supplied SL logo, with multiple icon sizes. Run CREATE_DESKTOP_SHORTCUT.bat (or the normal launcher) to refresh the shortcut. Windows COM shortcut creation and shell icon display remain on-device checks.

A small caption in the interface shows VERSION, the current code-folder name, build timestamp in Bangkok and source commit from RELEASE_MANIFEST.json. A source checkout without a manifest is labelled Development copy rather than inventing a creation date.

Admin → Shared accounts now shows usernames, roles, active state and default passwords ONLY when those defaults still match the saved hashes. Custom existing passwords cannot be recovered from hashes and are labelled Reset. Administrators can create accounts, reset passwords, deactivate/remove login access and reactivate accounts. Removing preserves history, and the final active administrator cannot be removed. Every change is recorded with actor/time. Backend checks require an active admin in the database. Deactivated users are rejected on subsequent hub reruns/mobile requests. Existing passwords are not automatically reset and plaintext custom passwords are not stored.

Validation: ten focused account/HTML/Recovery tests passed; mobile 98 passed/1 skipped. Browser checks cover existing workflows and the new admin controls. Previous review limitations for full planner/factory acceptance remain unchanged. Data changes are additive: account_admin_history only; no old users, source files, audits or production records deleted. Close services, extract new code, reuse existing CENTRAL_DATA; never replace it with an empty directory. Roll back code by stopping services and selecting the previous folder, retaining shared data/backups.


# RC29.60 — simpler files, reports and Recovery analysis

- Home starts with three visible upload boxes: staff KPI; separate opening/closure files; Production status and section/category Production KPI formats. Saved-source details are collapsed. Separate direct report buttons follow. Staff, MD open-close, Production status and Recovery pages expose their own related uploads.
- Production status has its own clearly named destination for สถานะการผลิต 2026-4 88; existing detailed English section/category/customer/size/week/month/source analysis is retained. Imports persist in the shared evidence database and original files/revisions are retained.
- Recovery upload is directly on its page and available on Home. Only แผน Recovery supplies quantities. Displays distinct WOs, unique consistent order quantity, planned/actual/pending pieces, matching Plan-2026 CQ reference-weight tonnes, weight/total-order coverage and conflicts, applied/unmatched actual reconciliation, customers/categories/weeks/months/reasons, one unit-selectable comparison chart and complete Excel.
- Tonnes use pcs × separately identified Plan-2026 CQ grams per piece / 1,000,000. They are reference-weight equivalents, NOT measured actual weights at each production stage. Missing/conflicting matches stay unknown. Repeated Recovery rows remain visible, while unique order total is counted once per consistent WO. Excess actual on one source row never cancels another row's pending quantity.
- Removed owner-rejected preserve-transition checkbox, retain-through date, fixed November 9 date and verbose reservation/PPC captions from standard firing UI. Standard planning starts at the selected date; previous running kiln blocks apply BEFORE allocation; redundant post-allocation date shifting is removed. Optional old transition API/tests remain for compatibility but no freeze is enabled by the normal app. This supersedes the former RC57/58 user-guide transition instructions. Current guide is RC29_60_User_Guide_Thai_English.docx.

Validation: 31 focused QR/Recovery/planning tests passed, including grams-to-tonnes, repeated-WO quantities and conflicting weights. Thirteen real-browser synthetic checks passed, including Home and direct Production/MD/Recovery upload visibility. Supplied Recovery and Plan workbooks were actually read privately; no customer rows or private workbooks are in the code ZIP. Prior mobile results remain unchanged (98 pass/1 skip); inherited broader-suite/integrity failures remain reported. The changes do not certify every push/pull/overtime/resource scenario, exact older issued factory-plan acceptance, physical pattern geometry or Windows/phone/scanner operation. No new shift/overtime capacity or factory behaviour assumptions were invented from internet guidance.

Data/update: additive code change; no CENTRAL_DATA/database/import originals/passwords deleted or reset. Close services, extract into the new version folder and use the EXISTING shared central data. Never replace it with an empty directory. Roll back by selecting the previous code folder after stopping services while retaining central data and backups. Private source files are not bundled in public code downloads.


# RC29.59 — QR image backend repair

Fixes ModuleNotFoundError: qrcode.image.pil on Home and other QR creation routes. The qrcode core builds the QR matrix; a shared PNG encoder writes the image without the optional qrcode/Pillow image backend. Desktop connection QRs, tracking portal, work-order labels, mobile and unidentified-part QR creation share this encoder. The startup readiness probe now generates a real QR PNG using the current code folder instead of merely importing qrcode.

The previous installation's runtime is intentionally shared by the existing Windows launcher; that path alone is not an error. This repair does not change the chosen shared runtime, factory data folders, existing passwords or firing rules. No package installation is needed specifically for the missing qrcode.image.pil backend after applying this code fix. Core dependencies are still required.

Small repair ZIP: close the program, extract its contents into your existing RC29.58 folder containing hub.py, choose Replace for these program files, then run the existing START_SL_CARBORUNDUM_PLANNING_CENTER.bat. Do not replace or delete CENTRAL_DATA. Alternatively use the complete RC29.59 code ZIP in its new version folder and reuse the existing central data.

Validation: QR images decode through OpenCV while imports of qrcode.image.pil and PIL are deliberately blocked. File/BytesIO outputs agree. Exact physical scanner and Windows startup remain on-device checks. Prior firing review limitations remain unchanged.


# RC29.58 — issued plan is a Production instruction

Owner clarification: issued firing dates are targets for Production to achieve, using upstream push/pull and evaluating overtime. Current forming shortages no longer reject an otherwise valid issued commitment. The date and quantity remain in the main Firing Loads and Operator Print. Production Instructions shows the additional forming quantity and required firing date, with exact source rows. Actual output is never invented. Quantities are reserved against remaining firing demand before optimization, including quantities still to be formed.

Physical kiln/program/overlap limits, closed or missing WOs and quantities exceeding remaining demand still produce explicit exceptions. Overtime hours and additional capacity are not assumed approved or calculated without resource inputs. Drying and physical release checks remain separate from the issued production target. Earlier RC29.57 notes describe the superseded formed-WIP rejection policy; this note supersedes that policy only.

Focused regression tests and operational export checks are synthetic, not verification of the older factory workbook named in pasted chat. Other RC29.57 test results/limitations remain applicable; no full factory acceptance is claimed. Extract the new folder and reuse existing CENTRAL_DATA without overwriting it. No private factory files/databases are bundled.


Current broader suite: 318 passed, 8 skipped, 16 failed. Fourteen previously reproduce on the RC29.53 baseline; two additional old monthly-upload assertions expect the format/navigation that the owner explicitly replaced. They remain visible failures, not marked passed. Firing integrity retains three inherited mismatches; daily integrity passes with pending review entries. Missing cloud validation script is recorded.

RC29.57: 38 focused tests passed; mobile 98 passed / 1 skipped; 10 real-browser checks passed. Real fast allocator + merged operational Excel scenario passed with synthetic data, hard pull/upstream validation disabled for that scenario. Full factory-file acceptance remains outstanding. See RC57 logs and review notes.

# RC29.57 — current review

See [RC29.57 notes](docs/RC29_57_REVIEW_NOTES.md) and the RC57 test logs. Revised transition loads now feed main operational output; exact older factory-file acceptance remains outstanding. Existing shared data is preserved.

# Test results

## RC29.54 — 5 November 2026

- Focused: **88 passed** (`RC54_FOCUSED_TESTS.txt`).
- Mobile/scanner/audit/photo/concurrency: **97 passed, 1 skipped**, three dependency/deprecation warnings (`RC54_MOBILE_TESTS.txt`).
- Final planning/release-evidence checks: **25 passed** (`RC54_PLANNING_TESTS.txt`).
- Real Chromium synthetic checks: **9 passed** (`RC54_BROWSER_TESTS.txt`), including a committed save with deliberately lost acknowledgement and duplicate-free retry.
- Broader suite: **297 passed, 8 skipped, 14 failed** (`RC54_BROAD_SUITE.txt`). All 14 failures reproduce on unchanged RC29.53 commit `8ac9005` in an isolated checkout: **33 passed, 14 failed** (`RC54_LEGACY_BASELINE.txt`). These are reported, not silently marked passed.
- Daily integrity passes with pending code reviews; Firing retains three inherited failures. Cloud validation script missing (`RC54_ENGINE_CHECKS.txt`).
- Timing conditions/results: `RC54_COMPONENT_TIMINGS.txt`. Word guide opened/rendered through LibreOffice to PDF for inspection; XML/relationships/images parse; screenshots are synthetic. No physical scanner/camera/GPS/Wi-Fi/Windows acceptance is implied.

**RC29.53 (4 November 2026):** see `RC53_FOCUSED_TESTS.txt`, `RC53_MOBILE_TESTS.txt`,
`RC53_UI_TESTS.txt`, `RC53_HUB_TESTS.txt` and `RC53_ENGINE_CHECKS.txt`. Those current
results supersede historical runs below. Actual-workbook analysis and test
conditions are in `RC29_53_PRODUCTION_ANALYSIS.md`. Synthetic regression checks
are distinct from factory/device acceptance; no engine checksum was altered.

**RC29.52 review candidate (3 November 2026):** 39 focused tests passed, 1 skipped;
the new manager screen passed a rendered save/rerun check. Full suite validation
did not complete and uploaded engine acceptance checks fail. Read
`RC29_52_REVIEW_NOTES.md` and the current `REVIEW_*_TESTS.txt` files before using
historical results below. Archive verification is not scheduling acceptance.

**Windows start-up is not in this table.** Installer decision tests (`suite/test_windows_runtime_env.py`) run on Linux. Creating `.venv`, pip on Windows, and `START_SL_CARBORUNDUM_PLANNING_CENTER.bat` have **not** been executed on a factory PC here.

**Conditions.** All results below were produced on a Linux cloud VM (4 vCPU, Python 3.12.3, headless Chrome) using the exact pins in `requirements-cloud.lock.txt`, with **synthetic records only** in `.cloud-test-data/` plus the supplied repository workbooks. **This is not factory validation.** It does not exercise a real phone camera, GPS, factory Wi-Fi, Windows start-up, or the live `sl_planning.db`.

Re-run everything with `bash scripts/cloud/validate.sh` (cloud) or the commands in `docs/INSTALL_AND_UPDATE.md`.

## Automated results (last full run: 2026-10-05, branch `cursor/extract-sl-v16-28-code-f48f`)
| Check | Result |
|---|---|
| `python -m compileall` | pass |
| `pytest suite tests/release` | **suite + mobile together 179 passed** on this revision (capacity/planner/settings/help + 85 mobile) |
| `pytest apps/mobile/tests` | **85 passed** |
| `selftest_undefined_names.py` | 7 known star-import notes (limit 7), pass |
| `apps/daily/VERIFY_RELEASE.py`, `apps/firing/VERIFY_RELEASE.py` | pass (with 10 legacy controlled changes "PENDING REVIEW", see `docs/RELEASE_INTEGRITY.md`) |
| `scripts/cloud/manifest_report.py` | pass |
| Headless Streamlit render: daily, firing, analysis, hub | pass |
| `scripts/cloud/mobile_api_check.py` (running server) | 0 failures |
| `scripts/cloud/browser_check.py` (Chrome 390x844 and 1366x768) | 0 failures (uses a synthetic camera and a stubbed in-browser detector; it is **not** evidence of QR decoding) |

## What each test group proves
| Group | Tests | Covers |
|---|---|---|
| `apps/mobile/tests/test_audit_v2.py` | 31 | idempotent retry, validation, unknown quantity, several observations per WO, no writes to production `events`, unidentified parts, link/unlink history, permissions, ambiguity, register filters/exports, legacy-database migration |
| `apps/mobile/tests/test_qr_decoding.py` | 30 | the **real** decoder (`qr_decode.py`) on generated QR images: clean, rotated, perspective, low contrast, noise, small, large, multi-code refusal, no-QR, corrupt file, HEIC reporting. Known limit: heavy blur (sigma 8) and strong perspective (0.3) are not detected; they fail safely with an explicit status |
| `apps/mobile/tests/test_concurrency_and_uploads.py` | 23 | concurrent operators (threads against one SQLite file), duplicate retries (same submission id -> one record), quantity validation including NaN/inf/over-limit, photo upload size/type/corruption limits |
| `suite/test_capacity.py` | 14 | units never mixed, tonne->kg only by documented conversion, pieces->kg needs part weight at matching stage, gaps and conflicts reported with cells |
| `suite/test_source_manager.py`, `test_shared_source_consistency.py` | 10 + 7 | one import reused everywhere, duplicate detection, append-only revisions, two KPI sources + one Daily Status per section, sheet-role detection, modules agree on the same numbers |
| `suite/test_closure_rules.py`, `test_sept_analysis.py`, `test_wo_codes.py` | 7 + 4 + 7 | CLOSE-1/2 and backorder, four separate September measures, WO prefix decoding |
| `suite/test_newpart_planner.py`, `test_newpart_page_ui.py` | 14 + 1 | Bangkok date, no inherited dates, reservations/bookings, firm vs forecast, PROVISIONAL/BLOCKED/LATE statuses, drafts/scenarios, exports, UI render |
| `suite/test_help_f1.py`, `test_requirements_engine.py` | 11 + 9 | bilingual help, exact rule-ID search, OCR hits labelled UNVERIFIED, missing-DB notice, requirement engine |
| `tests/release/test_controlled_changes.py` | 7 | controlled-change process, evidence tests for the four formerly failing files |

Some `suite` tests skip when the Plan workbook is absent (it is excluded from the release ZIP because it is dated operational data); they run in the repository.

## Release ZIP, extracted and tested (cloud VM, Linux)
`python scripts/release/build_release.py --verify` builds from a clean committed tree and then checks the ZIP: every file hash against `RELEASE_MANIFEST.json`, every `.py` compiles, no database/key/log/`.pyc`/Plan workbook inside, required docs present, `.bat` files CRLF. The ZIP was also extracted to an empty folder and tested there:
* `pytest suite tests`: 83 passed, 8 skipped. The 8 skips are the tests that need the dated Plan workbook, which is deliberately not in the ZIP.
* `pytest apps/mobile/tests`: 84 passed, 1 skipped, **1 failed**: `test_smoke.py::test_database_exists` (pre-existing test from the original package) asserts that `sl_planning.db` already exists; a fresh extraction has no database because live data is excluded. The database is created on first start of the mobile app. It is not a defect of the package, but it means this one test is not meaningful on a fresh copy.
* `VERIFY_RELEASE.py` (daily, firing): pass.
* Mobile app started from the extracted copy with no `SL_*` variables except a fresh `SL_SHARED_ROOT`: `/health` returned ok with 0 work orders, and the empty database, `PHOTOS`, `REPORTS` and `SOURCE_COPIES` folders were created under that root. (Linux only; the Windows `.bat` start-up was not run.)

## Performance
See `docs/PERFORMANCE.md` (conditions stated there). Headline: pages render in under 0.5 s even throttled; one 3.7 MB photo takes 15 s on an emulated 2 Mbps uplink.

## Not tested anywhere yet
Real phone camera and gallery, iPhone HEIC, GPS indoors, factory Wi-Fi, Windows `.bat` start-up and shared-folder permissions, many simultaneous real operators, any real `sl_planning.db`, and any schedule produced from live stock/WIP. Use `docs/ON_PHONE_CHECKLIST.md` and `docs/INSTALL_AND_UPDATE.md` for those.


## RC26 differential checks (2026-10-06)

- `python -m py_compile` passed for the edited hub, daily planner, mobile entry point and KPI/recovery modules.
- Four targeted checks passed: append-only employee KPI evidence and KPI retirement; rejection of missing evidence/invalid percentage; overdue/urgent recovery action filtering with closed/future orders excluded; additive mobile-audit merge plus copy-only photo restoration.
- The complete pytest/Streamlit/UI suite was not runnable in this workspace because `pytest` and Streamlit are unavailable here. RC25 full-suite results above are historical and do not validate these RC26 changes.
- RC26 has not been run on the company Windows PC or Z: share; phone camera and live multi-operator behavior are not verified.

## RC29.15 targeted checks (2026-10-09)

- `py_compile`: passed for hub, daily planner, mobile app/audit router, WIP report, F1 and knowledge page.
- Manual synthetic checks passed for exact SPEC intent search, physical audit process grouping, location comparison, unknown audit quantity and cumulative order-balance calculation.
- `pytest` could not run because it is not installed in the authoring environment. Added tests are included in the ZIP.
- This does not verify real workbook layouts, actual mobile display/camera, D: drive permissions, phone access on mobile data, or concurrent shop-floor load.


## RC29.16 Home presentation checks (2026-10-09)

- `python -m py_compile hub.py`: passed.
- ZIP checksum, manifest hashes, and extraction were checked during package generation.
- Streamlit rendering, Windows launch, D: data access, mobile camera/network, and concurrent users were not tested here.


## RC29.17 targeted checks (2026-10-09)

- Python syntax compilation passed for hub, Daily Planner, mobile audit routes, audit report, and Daily Status prefix helper.
- Synthetic database test confirmed that the latest audit report includes a linked photo filename and preserves quantity unit. Numbered filenames 1–6 map as requested.
- Jinja2 rendering, Windows startup, D: permissions, public/mobile data routing and camera access remain unverified in this workspace.


## RC29.18 Daily Plan action visibility (2026-10-09)

- Daily Planner syntax compilation passed.
- Source inspection confirms the Create / Update button is always rendered, including when a saved calculation is restored; old plan data remains until a replacement passes consistency checks.
- Streamlit rendering and live workbook recalculation were not available here.


## RC29.19 backorder/date and recovery-capacity checks (2026-10-09)

- Pass: due 2026-10-08 is overdue as of 2026-10-09; due 2026-10-09 is not overdue; due 2027-02-01 is future demand; closed WOs are excluded.
- Pass: repeated source rows collapse to one WO; category F maps to P.
- Pass: recovery allocation is reconciled once against whole-day scheduled load, controlled capacity, implied pre-allocation headroom, and after-plan headroom.
- Pass: 7 focused unittest cases plus Python syntax compilation for modified application modules.
- Not run: Streamlit UI and live data because Streamlit is unavailable in this build workspace; Windows and factory devices were not available.

## RC29.49 focused verification (2026-10-27)

- Python compile check passed for `hub.py`, `suite`, `apps/daily`, and `apps/mobile`.
- Daily and Firing `VERIFY_RELEASE.py` passed. Daily planner controlled change is recorded with evidence; remaining pre-existing pending-review items are still reported by the gate.
- Ran 4 KPI-history / Production-WIP summary assertions directly (same-month newer revision replaces that month, older month remains; malformed KPI input stays empty; Production WIP uses second-sheet open-count/GW summary, flags category discrepancy; F maps to P). `unittest` passed 3 source/navigation/customer regression tests.
- `pytest` is not installed in this authoring environment, so pytest-only suites were not run.
- No live Plan-2026, Production WIP workbook, KPI workbook revisions, Streamlit browser, Windows launch, phone camera or concurrent-user test was run for RC29.49. The ZIP remains a release candidate pending company PC validation.

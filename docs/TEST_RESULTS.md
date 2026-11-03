# Test results

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

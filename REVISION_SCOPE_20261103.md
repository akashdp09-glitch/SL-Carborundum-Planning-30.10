# Owner revision request and source inspection — 3 November 2026

Status: workbook analysis and separate evidence staging completed; application implementation and factory acceptance remain blocked by the oversized source ZIP. No production data or application logic changed.

## Confirmed requirements

- Repeat runs with identical inputs, rules, resource calendars and source revisions must produce identical plans. The owner confirmed this on 3 November 2026. Explain result changes with the changed input/rule and affected orders; explicitly labelled alternative scenarios are separate results.
- Treat Planning Department's three KPIs as Planning Manager KPIs. Owner confirmed: (1) planning accuracy from the Planning Analyst; (2) planning open-versus-closed WO percentage ratio; (3) actual packed WOs versus planned WOs, as a count-based percentage from Production KPI. Confirm KPI 2's ratio direction/cohort and the manager's allocation of 40 marks before final scoring. Do not substitute piece totals for WO counts or aggregate unrelated staff metrics into a manager KPI. Support manual entry and upload, durable history, corrections, trend analysis and source drill-down.
- Owner clarified Chosita M8:M11 are HR maximum marks, not achievement targets: 15, 15, 5 and 5, totalling 40. Preserve source values 0.15/0.15/0.05/0.05 while displaying the confirmed marks. Achievement percentages, targets/score bands and awarded marks are distinct. Do not use N8:N11's four values of 20 as a replacement 80-mark scheme, assume the same split applies to three manager KPIs, or invent a conversion from achievement to awarded marks.
- Retire obsolete KPI formats from the active workflow and stop prompting for them. Preserve historical evidence and revisions; do not delete factory data. New formats must be inspected before activation.
- Daily and firing planning must apply downstream pull and upstream push, actual remaining stage quantities, dependencies, material readiness, approved capacity, resources, working calendars and existing bookings. Keep capacity units and time bases separate. Explain shortages and unused capacity. Never mark an unverified plan feasible.
- An explicitly selected 30 October 2026 anchor stays 30 October in Asia/Bangkok. Distinguish the selected anchor from the first feasible operation date; if a calendar/resource/readiness constraint moves an operation to 31 October, show the exact reason. Never silently add a day or treat a selected historical scenario anchor as today's date.
- Measure firing speed before/after with the same complete workload and inputs. Optimisation must preserve allocation and constraint results. Parse only necessary sources and cache immutable source-derived data by content revision; invalidate results when actuals, rules, calendars or approved edits change.
- Export doubtful kiln loading plans with flagged constraints, WO/quantity allocations, input revisions and reasons. Accurate top/front views must derive from the same physical geometry, furniture and placement coordinates as the load validator. Missing dimensions, clearances or rules are blockers, never guessed geometry.
- Allow Daily and Firing plan edits with a mandatory reason, author, before/after values and time; revalidate constraints and preserve prior versions. Keep drafts and saved results across tab/page changes; refresh must not silently erase edits. Conflicts need explicit handling.
- Recovery analysis reads only the worksheet named `แผน Recovery` (owner identifies it as the second sheet). Validate its identity and structure; do not fall back silently to a different sheet. Report delayed/on-plan/unknown with date and quantity evidence, customer totals, distinct WOs and pieces, pending quantities, week/month views and drill-down exports. Keep original due dates, revised commitments and confirmed actuals distinct. Deduplicate repeated WO rows without discarding valid separate quantity allocations. Distinct WO counts across weeks may overlap and cannot be blindly summed.
- Desktop and mobile audit UI: SL orange/dark blue, large icons with short useful text, Thai/English desktop and retained Burmese mobile support. Use clear confirmation, unknown-quantity handling, visible save/pending/error states, safe retry and accessible layouts. Preserve shared records and server-side role enforcement.
- Contextual Help should return the relevant answer to the selected question, with Thai/English text and source references; avoid showing every answer. Missing knowledge content must be visible, never invented.
- Deliver a Thai/English Word user manual after verified implementation, using real screenshots, workflow examples and limitations. Do not present mock screens or unimplemented actions as working software.

## Owner-specified actual-production workbook mapping

Received file: `Plan 2026-2-Update-271026.xlsx`; see `WORKBOOK_FINDINGS_20261103.md` for evidence and scope of analysis.

| Worksheet | Owner's meaning |
| --- | --- |
| `pack` | Packing completed |
| `เจียร` | Grinding or cutting completed; inspect route/columns to distinguish |
| `เข้าเผา` | WIP of firing from the preceding drying process after forming; owner clarified 3 November 2026. `จำนวนเข้าเตา` is quantity loaded into the firing kiln, not proof of completed firing. |
| `เตาจ่าย` | Firing completed |
| `ขึ้นรูปจ่าย` | Forming completed |
| `ผสมจ่าย` | Mixing completed |
| `เตรียมจ่าย` | Preparation completed |

These are actual-production evidence and take precedence over planned status in `แผนการเผา`. Do not schedule completed quantities again. A partial completion removes only the confirmed completed quantity at its matching stage; it does not close the whole WO. `เข้าเผา` identifies firing WIP; distinguish awaiting kiln loading from quantities already loaded/in process. Reserve an evidenced existing kiln load rather than allocating those same pieces to another load. Neither WIP nor loaded quantity is completed firing: use confirmed firing-output evidence (`เตาจ่าย`) for that transition. Do not add loaded quantities and firing output as separate stock. Inspect WO keys, quantities, transaction dates, reversals and duplicate records before reconciliation. Show freshness and conflicts. Apply the existing whole-order closure rules separately.

## Verified source findings

Inspected local HEAD `8caf1143ce8efd99160cd8862e3e62cbf952cb6c` (90 tracked files). This is not a sparse checkout. During onboarding the same SHA was returned by read-only remote HEAD access.

- `suite/`, `apps/`, `scripts/cloud/`, `knowledge/`, `VERIFY_RELEASE.py` and the controlled-release helper are absent from this commit. The shared source manager, capacity rules, daily/firing engines, KPI implementations, mobile app, recovery parsers, navigation persistence and their tests cannot be inspected or executed.
- `hub.py:12` imports absent `suite.common`; Streamlit AppTest fails with `ModuleNotFoundError: No module named 'suite'`. This precedes application startup and data initialization. Dependency installation succeeded and `pip check` passed during onboarding.
- `hub.py` function `model` delegates parsing to the absent Daily engine and additionally reads `แผนการเผา` directly. Actual-stage precedence cannot be established without that engine and the supplied workbook. Do not claim confirmed double scheduling from this call alone.
- `REVISION_NOTES_20261030_START_DATE_AND_KPI.md` claims a start-date anchor correction, but its firing implementation and tests are absent; the owner's reported regression remains unverified.
- `save_editable` writes a latest Excel report before its audit transaction, suppresses audit exceptions, and returns the report path. `editable_table` then displays success. The general editor does not collect an edit reason. This path needs coordinated durable-save/error handling; inspect missing planner-specific save paths before extending it.
- `selftest_undefined_names.py` reports three `uuid` references in `hub.py` without an import. They are on the desktop audit submission path; runtime confirmation is blocked by startup failure.
- Existing hub editor persistence calls depend on absent `suite.navigation_state`. The presence of these calls does not demonstrate working navigation persistence.
- The only available XLSX is `Row_3_Thai_English_Cell_Mapping_REFERENCE.xlsx`. No new KPI workbook, Recovery workbook, named production workbook or UI reference images were available at inspection. No live CENTRAL_DATA or application database was found in the supplied checkout; no KPI data was removed or imported.

## Work and acceptance sequence once sources arrive

1. Restore the complete source through the repository or supplied application ZIP, retaining the existing checkout and preserving user data. Inspect nested AGENTS instructions, release integrity workflow and current source health. Establish baseline tests and timings before edits.
2. Inspect new files without changing originals. Record content hashes, sheet/header mapping, source rows, revisions and as-of dates. Verify the three KPI definitions and staff-to-department formula against the supplied evidence; surface conflicts.
3. Fix actual-stage reconciliation and start-date propagation first. Test partial/full actuals, duplicate imports, stale/conflicting evidence, reversals where supported, Bangkok midnight boundaries, closed days and explicit historical anchors.
4. Test push/pull scheduling, resource reservations and capacity constraints end to end. Profile workbook parsing, candidate evaluation and physical loading on the same fixture; compare allocations and top/front projections before/after optimisation. Provide downloadable rejected/doubtful loads and reasons.
5. Add traceable KPI entry/upload, reasoned versioned plan edits and persistence. Test navigation, reload, repeat submissions, failed transactions and conflicting edits. Back up before any additive, idempotent migration and document rollback.
6. Validate Recovery counts and quantities against the actual second sheet. Test duplicates, split allocations, missing dates, changed commitments, partial completion and week/month/customer totals; export source evidence.
7. Simplify audit screens and contextual Help. Exercise real rendered desktop/mobile views, then capture screenshots for the bilingual DOCX manual. Real phone camera/GPS, Windows launch, factory Wi-Fi and printer checks remain on-device acceptance tasks.

Blocked inputs requested from the owner: complete application ZIP/source, new three-KPI definitions and staff evidence files, production master workbook, Recovery workbook, and reference interface images. A manual for the revised software cannot accurately be completed before the revised screens work.

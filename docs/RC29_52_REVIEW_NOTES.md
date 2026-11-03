# RC29.52 review candidate — 3 November 2026

This is a reconstructed, partial revision from the owner's Vol1.zip and Vol2.zip,
not completion of the full planning/UI redesign and not a factory-approved release.
Publishing the cloud environment did not validate or publish this software package.

## Included changes

- Restored missing apps, suite, assets, knowledge references, tests and scripts from
  the supplied archives. Existing local documentation/history was retained.
- Restored `uuid` import from the supplied RC29.51 hub; desktop audit submission
  no longer references an unimported name on this path.
- The Monthly Planning KPI screen now shows the three owner-confirmed manager
  KPIs: analyst planning accuracy (15 marks), closed/opened WOs for the same
  period with backlog separately recorded (10), and actually packed/planned WOs
  (15). Ratios above 100% are retained for throughput comparisons.
- New manual and standard-CSV entries persist as append-only evidence events.
  Identical submission retries are idempotent; corrections retain earlier events,
  reason, author and Bangkok timestamp. History and monthly trend/export are
  available. The older nine-measure definitions and evidence are not deleted or
  reused under the new definitions; their legacy screen is no longer the default.
- Achievement percentages and HR maximum marks are separate. Awarded HR marks
  are deliberately not inferred without the HR conversion/score-band rules.
- Corrected Source Manager consistency checking to inspect shared-root/KPI paths
  where those active revisions are actually published, rather than COMPANY_DATA/KPI.
- Release builder excludes a stale tracked RELEASE_MANIFEST.json before generating
  the new manifest, avoiding duplicate/self-referencing manifest entries. Dated
  KPI inputs, WO seed lists and the identified operational history/plan workbooks
  are excluded from the candidate ZIP. Technical reference workbooks remain.

## Validation for this candidate

The hub rendered successfully under Streamlit AppTest with synthetic storage
and local socket access (zero script exceptions). This is not an on-site test.


- 18 focused KPI/intake tests passed before the Source Manager correction.
- 39 focused manager-KPI, legacy-KPI, Source Manager, closure and release tests
  passed; 1 skipped. See `REVIEW_FOCUSED_TESTS.txt` for the exact run.
- Rendered manager screen with Streamlit AppTest: saved synthetic 120 closed /
  100 opened with 35 backlog closures; database persisted and UI showed 120.00%
  after rerun. This is not a real browser/device screenshot or factory acceptance.
- Full suite run was interrupted after failures and a stall; it did not complete.
- A firing-anchor test in the uploaded source compares `_business_days(start,start)`
  to a date list, although that helper returns the integer count 1. This test
  mismatch does not establish that the owner's actual date-shift problem is fixed.
- Uploaded Daily/Firing controlled-change integrity checks FAIL. Daily:
  daily_linear_engine_v1_1.py accepted hash mismatch. Firing: firing_tomorrow_fast.py,
  sl_daily_engine_v3_22_from_v17.py, fast_stage4_v15.py,
  firing_engine_desktop_v2.py and ppc_fast_core_v4_6.py lack matching accepted
  hashes/entries. Those supplied engine files were restored unchanged; no checksum
  was rewritten to make their acceptance checks pass. These require real review.
- The release builder's archive verification checks structure, hashes, compilation
  and excluded files; it is distinct from the failing engine acceptance checks.
- Final mobile regression run with local socket access: **88 passed, 1 skipped**.
  The prior sandbox-only run timed out because local sockets were unavailable.
  Repaired legacy expression indexes before Plan import using the existing
  SQL-only index migration, without changing work-order data. Corrected the
  smoke test to inspect the configured isolated database instead of requiring
  a bundled factory database. Full output: `REVIEW_MOBILE_TESTS.txt`. Older docs retain historical
  test results which do not override this candidate's results.

## Not completed in this package

- Full firing/daily optimisation, actual-stage reconciliation and real-workbook
  confirmation of the 30 October anchor, push/pull, resource and geometry constraints.
- Verified top/front kiln layouts and doubtful-loading export improvements.
- Recovery parser corrections: the supplied implementation still reads additional
  sheets and can double count repeated per-WO warehouse totals. The separate workbook
  review documents the evidence; these reports are not approved for operational totals.
- Automatic import/reconciliation of all supplied Excel KPI formats into the three
  manager measures. The new screen accepts manual measurements and its standard CSV;
  it does not treat cached analyst percentages as invented audited-record counts.
- Production versus plan matching at consistent WO/period/revision granularity,
  full plan-edit audit fixes, whole-application navigation persistence validation,
  full mobile/desktop layout redesign and general Help relevance changes.
- The complete illustrated bilingual user manual. A Thai/English candidate quick
  guide is included; it has no fabricated screenshots or unimplemented instructions.
- Windows installation, phone camera/GPS, factory Wi-Fi and live factory storage.

## Installation for isolated review, data and rollback

Extract into a NEW folder; do not replace the factory installation. Review on a
test machine with synthetic/approved test inputs. Do not point this candidate
at live CENTRAL_DATA while the checks above remain unresolved. Databases,
photos, uploads and live workbooks are not bundled. The missing knowledge database
must be restored separately from the existing installation when appropriate.

The new manager_kpi_events table and index are additive and created only on use;
existing tables are untouched. Back up databases before any reviewed deployment.
Rollback means stopping the candidate and returning to the previous program
folder/configuration. Preserve the new evidence table/database for reconciliation;
do not delete it or overwrite existing evidence as a rollback step.

ภาษาไทย: แพ็กเกจนี้สำหรับตรวจสอบเท่านั้น ยังไม่ผ่านการยืนยันใช้งานจริง
ให้แตกไฟล์ในโฟลเดอร์ใหม่ ห้ามทับโปรแกรมและ CENTRAL_DATA เดิม
KPI ผู้จัดการมีคะแนนเต็ม 15/10/15 รวม 40 แต่ยังไม่คำนวณคะแนน HR
หากไม่มีเกณฑ์แปลงคะแนน ข้อมูลเดิมไม่ถูกลบ และประวัติการแก้ไขยังคงอยู่
งานปรับแผนรายวัน/เตาเผา หน้าจอ และคู่มือฉบับสมบูรณ์ยังไม่เสร็จ

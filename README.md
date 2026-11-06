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


# RC29.58 — issued plan is a Production instruction

Owner clarification: issued firing dates are targets for Production to achieve, using upstream push/pull and evaluating overtime. Current forming shortages no longer reject an otherwise valid issued commitment. The date and quantity remain in the main Firing Loads and Operator Print. Production Instructions shows the additional forming quantity and required firing date, with exact source rows. Actual output is never invented. Quantities are reserved against remaining firing demand before optimization, including quantities still to be formed.

Physical kiln/program/overlap limits, closed or missing WOs and quantities exceeding remaining demand still produce explicit exceptions. Overtime hours and additional capacity are not assumed approved or calculated without resource inputs. Drying and physical release checks remain separate from the issued production target. Earlier RC29.57 notes describe the superseded formed-WIP rejection policy; this note supersedes that policy only.

Focused regression tests and operational export checks are synthetic, not verification of the older factory workbook named in pasted chat. Other RC29.57 test results/limitations remain applicable; no full factory acceptance is claimed. Extract the new folder and reuse existing CENTRAL_DATA without overwriting it. No private factory files/databases are bundled.


# Revised software RC29.57

Read docs/RC29_57_REVIEW_NOTES.md and docs/RC29_57_User_Guide_Thai_English.docx. Extract into a new folder and reuse the existing central data; do not overwrite CENTRAL_DATA.

# SL Carborundum — RC29.54 review

Bilingual function directory; B2D21 USB keyboard scanning; shared status/audit/history; production and section accounts; source-backed drying gates and persistent confirmations. Start with [the release notes](docs/RC29_54_SCANNER_AND_PLANNING.md) and [illustrated Thai/English Word guide](docs/RC29_54_User_Guide_Thai_English.docx).

**Review candidate:** 88 focused and 97 mobile tests passed; the wider suite retains 14 reproduced inherited failures and Firing retains three inherited integrity failures. Hardware/Windows/factory planning acceptance remains pending. Preserve the existing shared data; the code ZIP contains no operational database or private workbooks.

# RC29.53 review — Department KPI and Production Evidence

Read [the current production-analysis notes](docs/RC29_53_PRODUCTION_ANALYSIS.md) and [data import/retention guide](docs/PRODUCTION_EVIDENCE_IMPORT_GUIDE.md) first. Department and manager share the same KPI scheme. The separate English production-analysis page displays all normalised weights in metric tonnes. This remains a review candidate with inherited planner acceptance failures.

Historical project introduction:

# SL Carborundum Planning Center — V16.29-rc29

Start with [START_HERE_V16_29_RC29.txt](START_HERE_V16_29_RC29.txt). RC29 process timing and test limits are in [docs/RC29_CHANGELOG.md](docs/RC29_CHANGELOG.md); local D: paths are in [docs/STORAGE_GUIDE.md](docs/STORAGE_GUIDE.md).

## 2026-10-30 correction
See `REVISION_NOTES_20261030_START_DATE_AND_KPI.md` for the firing Planning Start anchor correction and centralized KPI upload/analysis update.

## 2026-10-30/31 — F12 Push/Pull Capacity Revision
- Firing planning now explicitly follows downstream-pull / upstream-push logic.
- Exact furniture trimming no longer leaves avoidable capacity unused: the planner refills the load from the remaining same-program demand in due-date order.
- A trimmed selected WO can itself be refilled before moving to the next compatible WO.
- Same-program look-ahead is widened when the first candidate window cannot reasonably approach the physical target.
- Output now records `Pull Refill pcs` and the planning method so small loads can be audited.
- See `apps/firing/README_V1_9_18F12_PUSH_PULL_CAPACITY.md` for the logic and limitations.

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

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

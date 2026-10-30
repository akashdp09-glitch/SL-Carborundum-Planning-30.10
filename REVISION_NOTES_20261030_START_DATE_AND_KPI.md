# Revision — 2026-10-30: Firing Start-Date Anchor + Central KPI Upload/Analysis

## Firing Planner
- Fixed the upstream-feasibility guard that forced candidate firing dates from the selected Planning Start to Planning Start + 1 day.
- The selected Planning Start is now the first permissible firing target date.
- Example: selecting 2026-10-29 starts the firing target calendar at 2026-10-29; selecting 2026-10-30 starts it at 2026-10-30, provided the date is a configured working day.
- Upstream capacity/readiness limitations no longer silently rewrite the user's planning anchor. They remain visible as readiness/expedite constraints.

## KPI
- Added a centralized multi-file KPI uploader to Planning KPI analysis.
- Workbooks are classified by structure and registered through Source Manager.
- Supported sources:
  - Planning KPI reference / approved definitions
  - Planning daily execution evidence (material readiness and WO issuance)
  - Planning job closure evidence
  - Employee KPI / appraisal reference
  - Section plan-vs-actual KPI
  - Delivery / warehouse KPI
- Added KPI analysis with target gap, weighted contribution, daily achievement chart, evidence table and employee-KPI reference analysis.
- Blank/zero-target days remain N/A and are not treated as KPI failures.

## Validation
- Python syntax compilation passed for modified modules.
- KPI classifier was tested against the bundled October and reference workbooks.
- Daily October KPI parser successfully reads KPI-PL-07 and KPI-PL-08 evidence.
- Full firing test collection requires the production Streamlit dependency; this build environment does not include Streamlit.

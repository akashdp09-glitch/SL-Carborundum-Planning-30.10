SL PPC DAILY PLANNER V1.9.36C — STABLE TV DASHBOARD HOTFIX

Base: V1.9.36B, with V1.9.33 verified bilingual TV behavior retained as the known-good reference.

Controlled fix:
- TV dashboard never assumes Category or Order Type exists in the risk dataframe.
- Missing Category => UNKNOWN; missing Order Type => NORMAL.
- Adds a second runtime invariant immediately before the risk groupby, preventing KeyError: Category even if an upstream transformation removes the field.
- No production planning, capacity, MRP, firing, material-alternative or risk-decision logic changed.
- F12Z compatibility retained.

Validation:
- Python compile validation completed.
- Source inspected for the failing groupby path.
- This package supersedes V1.9.36 / 36A / 36B for testing.

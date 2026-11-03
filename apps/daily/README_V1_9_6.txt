V1.9.6 DASHBOARD COMPLETE RUNTIME FIX
Reported V1.9.5 error fixed:
NameError: _dueview is not defined.

Root cause:
V1.9.5 removed the undefined helper call but left the downstream display block that expected its return variable.

Fix:
_dueview is now built directly before use from the loaded Plan2026 master:
- selected Dashboard Date + next working day
- valid Due Date is authoritative
- closed WOs excluded
- remaining/open packing target shown
- Daily Planner Packing Qty cross-checked for the same dates

No production scheduling logic changed.
Repeatable due-date/capacity pull, early completion, selected-date dashboard and clear stack totals are preserved.

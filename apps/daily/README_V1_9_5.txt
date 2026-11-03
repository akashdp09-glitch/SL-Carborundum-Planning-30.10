V1.9.5 DASHBOARD RUNTIME FIX
Reported error fixed:
NameError: _master_due_dashboard is not defined.

Root cause:
V1.9.4 contained an orphan call to a helper that was never defined. The call's return value was not used. The selected-date dashboard immediately below already performs the due/overdue calculation directly.

Fix:
Removed the orphan _master_due_dashboard call and checked for the same stale _risk_gantt reference.
No scheduling/planning logic changed.
V1.9.4 repeatable due-date/capacity pull, early completion, selected-date dashboard and stack-total rules are preserved.

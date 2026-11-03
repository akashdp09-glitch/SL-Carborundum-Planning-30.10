V1.9.7 DASHBOARD RUNTIME HARDENED
Fixes reported NameError: working_add is not defined.
The dashboard no longer depends on that missing helper. It calculates the next working day locally using pandas and skips Sunday, matching the planner's Sunday-holiday rule.

Also rechecked the previously failing dashboard chain:
- no _master_due_dashboard reference
- no _risk_gantt reference
- _dueview is initialized before display
- no working_add reference remains
No production scheduling logic was changed.

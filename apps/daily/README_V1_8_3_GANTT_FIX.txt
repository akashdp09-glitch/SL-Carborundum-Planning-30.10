V1.8.3 — GANTT NO RAW NUMBERS + CLEAR CURRENT STATUS

Fixes:
1. Removed raw timeline duration numbers such as 86,400,000 / 172,800,000 /
   518,400,000 from Gantt bars. These were Plotly's internal millisecond durations.
2. Fixed the shared Plotly helper that was re-adding numeric labels after the
   Gantt code had removed them.
3. Hover is now clearer:
   - Work Order = hover heading
   - Process = the planned process represented by the colored bar
   - Current Status = the latest actual/status field from the production master
   - Plan Status, Start, Finish, Actual Progress %, Planned Qty remain visible.
4. Process name is NOT treated as current status.

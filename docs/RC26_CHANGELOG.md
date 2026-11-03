# Historical: V16.29-rc26 changes — 2026-10-06

This records the temporary RC26 Z: configuration. RC28 supersedes it and uses local D: storage; follow `START_HERE_V16_29_RC28.txt` and `STORAGE_GUIDE.md` for current paths.

- Server storage now defaults to the requested company share `Z:\Planning\Planning_Python data` for the live database, photo evidence, QR scan images, source copies, reports, and backups. Startup stops if the mapped share is missing or not writable; it does not silently fall back to D:.
- Startup supports additive recovery of audit rows from the former D: RC14 database and copies referenced photos from the old D: photo folder. Original databases and photos are retained. Verify recovery counts and images before cleaning up any old folders.
- The Weekly Demand–Capacity–Risk workbook now includes a `Recovery Actions` sheet for overdue, due-within-3-days, or high-risk OPEN orders. It pre-fills calculated WO, customer (role-permission dependent), due date, open quantity, WIP/status, bottleneck and projected finish, then leaves Sales priority/date and Production capacity/feasible date for confirmation. It explicitly does not alter customer commitments.
- Added employee-specific custom KPI definitions and evidence for weekly, monthly, quarterly, yearly, or custom periods. Results use explicit target direction, unit, calculation rule, numerator/denominator or numeric actual, evidence reference, owner, timestamp, and append-only history. The existing monthly Planning scorecard and department KPI reports remain intact.
- Existing central WIP comparisons, category/pcs/ton/WO views, material/backorder/delivery/capacity reports, audit/QR functions, separate department KPI workbooks, and language-link styling are retained.

## Limits

This is a release candidate. The environment cannot verify a real factory Z: mapping, Windows permissions, phone camera, Wi-Fi uploads, live database/photo reconciliation, concurrent operators, or actual schedule agreement. Test the copied package on the PC and phone before operational use.

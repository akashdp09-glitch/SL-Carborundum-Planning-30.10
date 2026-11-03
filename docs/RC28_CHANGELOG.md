# V16.29-RC28 change notes

- Removed the mapped Z: drive requirement. Windows startup uses the stable local root `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA` for the database, source files, photos, reports, Daily Status, KPI, backups, caches, scenarios and settings.
- Kept data in the existing RC14 CENTRAL_DATA folder so a code update does not create a new empty database/photo library. No live files were moved by building this package.
- Startup now checks local D: availability and write access, and does not silently redirect data if the configured root is missing.
- Added direct Home and Quick Access links for **Backorder / Delivery Risk** and **Risk & Backorder Recovery Plan**. The Reports & Tools navigation retains both entries.
- Removed hard-coded Z: database and photo migration probes. Optional legacy recovery can still use explicitly configured legacy paths.

## Verification and limits

Static checks and unit/navigation tests were run in the packaging workspace. This environment cannot access the user's Windows D: drive or factory phone. Run on the factory PC with a backup and confirm the active database path, historical audit photos, Backorder page, Recovery Plan, and a real phone scan before operational rollout. This is a release candidate, not a claim of verified live operation.

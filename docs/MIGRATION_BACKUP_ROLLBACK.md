# Migration, backup and rollback

## Backup before every update (manual, always)
1. Stop all services (so SQLite is not mid-write).
2. Copy the entire `SL_SHARED_ROOT` folder to a dated backup, e.g. `D:\SL\BACKUP_2026-10-05\CENTRAL_DATA` (this includes the database with its `-wal`/`-shm` files, photos, source copies, scenarios).
3. Copy the old program folder (or at least `apps\mobile\qr`, `apps\mobile\uploads`, `apps\mobile\data`, `knowledge\knowledge_base.sqlite`, `SERVER_STORAGE_CONFIG.bat`).
4. Test the copy by opening the backup database read-only (`sqlite3 sl_planning.db "PRAGMA integrity_check;"` -> `ok`).

## What migrates, and how
**Mobile database (`sl_planning.db`)** - migration `v2_001_audit_register`, run automatically on first start of the new release:
* Additive only: new nullable/defaulted columns on `mobile_audits`, `mobile_audit_photos`, `unidentified_parts`; new tables `factory_locations`, `unidentified_photos`, `reconciliation_history`, `schema_migrations`; partial unique indexes on `client_submission_id`.
* Idempotent: running it again changes nothing (`schema_migrations` records it).
* Before the first migration of a database that contains data, the app copies it to `<SL_SHARED_ROOT>\BACKUPS\sl_planning_pre_v2_001_audit_register_<time>.db`.
* Tested (synthetic): a database created by the original code with legacy rows keeps those rows; quantities stay as recorded.

**Source registry** - the Source Manager creates `source_manager.sqlite` and, the first time a user with edit rights opens the Source Manager panel (Hub -> Files & Traceability), *adopts* the workbooks already present in `COMPANY_DATA` as revision 1 (a copy goes to `SOURCE_COPIES`; the existing file is not moved or edited). Daily Status and KPI files in the Daily Planner folders are adopted the same way.

**Nothing else** is migrated: no calculation results, no production events are rewritten. Audit observations stay separate from production `events`.

## Rollback
*Code only (data untouched)*: stop; start the old program folder. The old code ignores the new columns and tables, so this is safe. New observations made with the new release remain in the database but are not shown by the old release.

*Code and data* (discards everything recorded since the update): stop; restore the backed-up `SL_SHARED_ROOT` (or only `DATABASE\sl_planning.db*` plus `PHOTOS\`) over the current one; start the old folder. The automatic `BACKUPS\...pre_v2_001...db` is a database-only copy taken right before migration; photos taken afterwards remain on disk but are no longer referenced.

*A single source file* (wrong workbook imported): Hub -> Source Manager -> choose the slot -> **Roll back to revision** ("Revision history, sheet roles and rollback"). This publishes the earlier original again and records a new revision; nothing is deleted.

## Verifying after an update or rollback
`VERIFY_RELEASE.py` in `apps\daily` and `apps\firing`; Source Manager "Consistency check" (every published file equals the active revision); part register row counts equal the pre-update count; open two known work orders on a phone and on the desktop and compare photos, location and history.

# V16.29-rc22 — Daily status and operator interface corrections

Date: 2026-10-06 (Asia/Bangkok)

## Changes

- Storage configuration now keeps the shared database, source uploads and manual section-status ledger on `Z:\Planning\Planning_Python data`, while physical audit photos, unidentified-part photos, QR scan images and saved report files go to the previously supplied local D: central-data folder. This is the app-server PC drive; the phone uploads through the app and does not need direct access to D:.

- Daily Open / Closed source uploads are managed from Home → Upload / Replace Source Files. The embedded Daily Planner no longer presents a second group of Daily Status upload controls.
- Home has one multi-file drop area for Daily Status workbooks. The shared-data root remains Z:\Planning\Planning_Python data. Filenames containing one section name are assigned automatically; ambiguous filenames require an explicit section selection. Source Manager SHA-256 deduplication prevents an unchanged re-upload from creating a new active revision.
- The mobile QR button now opens the rear-camera live scanner where the browser permits it, decodes on-device when supported, and saves a captured scan frame as evidence; a live-frame server decode and phone-camera/photo fallback are available. HTTPS and a real device are required to validate this end-to-end. The scan/type manual section-status page now blocks saving until a work order is confirmed from Plan-2026 or the shared WO database. Only an exact normalized match auto-confirms; partial/multiple results need a human choice.
- Manual section-status events now use Z:\Planning\Planning_Python data\COMPANY_DATA\daily_status_entries.sqlite3 under the included Windows configuration, with SQLite WAL, transactions and a unique event ID. A retry with the same ID is idempotent. Legacy CSV rows are imported once and the original CSV is retained.
- Home and desktop traceability show the manual status ledger path. Mobile operator views no longer show storage paths, the signed-in username or credential-file instructions. The mobile path-details endpoint was removed. The login form still requires an account; credentials are not printed.
- F1 help now directs users to the single source upload location. A visible Shop Floor Support navigation item opens the QR-label workflow; work-order QR payload remains SLWO:<WO> and contains no server IP.

## Verification

- compileall passed for the changed Python modules.
- Direct checks passed for exact-match confirmation, refusal of fuzzy matches, SQLite save/read, and duplicate retry handling.
- Full pytest was not run because pytest is absent from this workspace runtime. Streamlit is also absent, so a live desktop render was not available. The daily release-integrity check still flags the pre-existing daily_job_control.py hash mismatch; the firing release check still flags the pre-existing firing_tomorrow_fast.py mismatch. These were not bypassed or re-baselined.
- Real phone QR camera, Android/iPhone, factory LAN, Windows startup, Z: database/source permissions and local D: photos/reports permissions and concurrent operator testing remain outstanding. This is a release candidate, not a factory-approved production deployment.

## Rollback

Keep a backup of CENTRAL_DATA first. To restore the old manual-status behavior, restore suite/floor_open_close.py and hub.py from V16.29-rc21. The new SQLite file is additive; the original CSV is preserved. Do not delete either data file during rollback.

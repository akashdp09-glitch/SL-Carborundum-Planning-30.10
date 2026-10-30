# V16.29-rc29.9 — mobile database repair, audit links, process status and sticker QR

## Root-cause repairs

- Plan import now registers the legacy SQLite `norm_wo()` function on every application database connection. At startup, the two known old work-order indexes built with that Python-only function are safely dropped and recreated with SQLite's built-in normalization expression. This addresses the reported `sqlite3.OperationalError: unknown function: norm_wo()` during `sync_mobile_plan.py`; no work-order rows are deleted.
- Mobile URLs honor `SL_MOBILE_HOST` first, including the configured `176.0.3.99`. The mobile service starts in the background when Home is opened if it is not already running. The desktop audit's live-register link now opens HTTP `:8000` instead of forcing optional HTTPS `:8443`. HTTPS remains an optional camera route; photo QR, typing and USB scanning remain available without it.
- Process OPEN/CLOSED is an in-software event ledger. Enter/USB-scan the WO or take/upload a QR photo; confirm the WO, choose section and status, enter actual quantity or mark it unknown, then save. A QR photo is retained in the configured `PHOTOS/QR_SCANS` location and its path plus SHA-256 are stored on the status event. The section workbook uploader is no longer a required Home source; old source manager entries are preserved.
- QR export workbooks now include a dedicated `Sticker Print` sheet (A4, 3 × 8 label layout per page). Human-readable WO text is lowercase and small; the source WO and QR payload (`SLWO:<original WO>`) remain available on the data sheet and payload field.
- Removed the stale Home warning that said every section's process-close workbook was missing. Updated the optional source-folder example to local D: rather than Z:.

## Traceability and storage

- Plan workbook: `CENTRAL_DATA/COMPANY_DATA/Plan-2026-LATEST.xlsx` (uploaded by the user; exact original path is not inferred).
- Mobile work orders and audit data: `CENTRAL_DATA/DATABASE/sl_planning.db`.
- Process section status: `CENTRAL_DATA/COMPANY_DATA/daily_status_entries.sqlite3` (append-only/idempotent event IDs, user and Thailand timestamp).
- QR scan pictures: `CENTRAL_DATA/PHOTOS/QR_SCANS`; each saved scan event records the full server-side path and SHA-256.
- Physical part audit pictures: `CENTRAL_DATA/PHOTOS/MOBILE_AUDITS`.
- Sticker label workbook and PNGs are generated under the configured reports / QR output folder and are downloaded by the user; printing uses the `Sticker Print` worksheet, whose small human-readable WO label is lowercase. The QR payload and `Work Order (source)` remain unchanged for traceability.

## Verification / limits

- Python compilation passed for hub, suite, mobile, daily and firing modules.
- Daily and firing `VERIFY_RELEASE.py` checks passed; existing legacy controlled changes remain visibly pending review.
- Existing 8 focused synthetic planning/KPI/recovery tests passed. The release adds regressions for an old `norm_wo()` index during Plan import and lowercase sticker output. The current workspace lacks FastAPI, Streamlit, qrcode and pytest, so those app-level tests and a live server start could not run here.
- This fixes the reported software failure mechanism, but does not configure Windows Firewall or prove factory Wi-Fi, camera permissions, a live mobile phone, concurrent operators, or the specific D: database contents. On a phone over plain HTTP, use QR photo or type/USB scan if the browser refuses live camera access. Keep sign-in enabled so captured events retain the operator identity.

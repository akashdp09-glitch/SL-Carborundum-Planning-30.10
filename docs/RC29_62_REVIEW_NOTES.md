# RC29.62 — desktop shop-floor portal, private Planning uploads and Daily crash repair

## Daily Plan

Fixes the reported IndexError from _quick_options[10] after removal of a menu item. Focus routes now use named labels and tolerate stale selections; section-specific links open the existing saved daily result with a section filter. No planning data is reset. The menu regression is tested against the actual application option list and reordered lists. This fixes that reported navigation crash; a complete factory-input daily HTML scheduling run is still not claimed.

## Desktop /scan and mobile audit

Desktop has larger Thai labels/icons, smaller English, firing and daily/section plan links, WIP/production analysis links and authenticated downloads of the active Plan 2026 and production-status originals. Section shortcuts pass a real filter into Daily. SL_HUB_URL may override the standard hub address when the factory uses a different host/port; otherwise the request host and existing standard 8510 port are used. Signed central tickets preserve the logged-in identity; target hub validates active accounts.

Find / USB Enter shows source-separated Plan 2026 section status, planned/actual quantities and dates; order/open/due fields; production status rows with source filename/revision/sheet/row/date/pieces/tonnes/quality flags; latest physical audit and photograph link when recorded; and recorded whole-order decision/history. No source is silently treated as another. Missing dates/quantities remain unknown. A formal WO closure date is not fabricated from a stage output date.

Production lookup uses an additive SQLite JSON expression index ix_production_wo and queries only the confirmed WO in the latest production_status source. It does not read private KPI evidence or reopen Excel for every scan. The import parser refreshes once via a new versioned sync marker to populate section quantities/dates. Packing uses EU, and ยังไม่ปิด is correctly OPEN. Original files and old markers remain. A refresh-in-progress message labels potentially older imported data.

Home shows desktop and mobile URLs and separate QR codes. /scan?mode=mobile omits the desktop planning navigation; narrow layouts collapse extended evidence sections. Mobile retains photo/physical-audit functions, manual search and status submission. Confirmed saves still use shared central audit/status databases and photographs, with retry IDs; typed drafts are not silently committed as production.

## Confidential Planning uploads

KPI/open-close uploads have moved to a Planning documents dialog near the bottom of Home, offered to admin/planning roles. Initial Home does not expose those filenames or upload boxes. Public production-status saved-file lists exclude staff/count/Production-KPI documents. Staff/department KPI report routes restrict other roles; management retains report viewing. Existing reports/sources are preserved, not deleted. The two production original-download routes never select KPI originals.

## Checks and limitations

12 focused source-index/navigation/account/Recovery tests passed. Mobile/API suite: 100 passed, 1 skipped. Fourteen browser checks passed, including source-separated evidence rendering, absent confidential filenames until the popup opens, desktop/mobile navigation and admin controls. Physical scanner, actual phone/network, Windows startup and full legacy planner factory acceptance remain on-device/open checks; previous broader/integrity issues remain documented. Existing CENTRAL_DATA, passwords, originals, audits and plan history are not replaced. Extract into the new version folder and reuse the existing shared data; roll back code only after stopping services and keeping the data/backups.

# SL Part Tracking — V16.29-rc25

## Start

On Windows, extract the package and run the root `INSTALL_REQUIREMENTS.bat` once, then `START_SL_CARBORUNDUM_PLANNING_CENTER.bat`. Keep the host window running. The mobile API binds to `0.0.0.0` (all host interfaces), has no client-IP allowlist, and writes scans/audits/photos to the host PC’s configured `CENTRAL_DATA` folders on D:. Login remains required for traceability. Company firewall, router/NAT, VPN and carrier routing still determine whether a phone on another network can reach the PC; the application cannot open those network paths by itself.

## Work Order QR labels

The default Work Order QR contains `SLWO:<Work Order ID>` and has no IP address or server URL. Scan it inside SL Part Tracking. Use **QR Generator** in the top navigation for one label or a printable workbook for all current WOs. Labels only generate when requested so importing a large workbook remains faster. The desktop hub generates the same IP-independent labels.

Older QR labels that contain a URL such as `/q/<WO>` are still accepted by the in-app scanner. A separate phone-connection QR may show a network address because it opens the server; it is not the Work Order label.

For live phone QR video, open the **secure HTTPS camera scan** link on port 8443 and grant browser camera permission. The camera certificate may need to be installed and trusted on the phone. Ordinary LAN HTTP supports typing and photo upload but commonly blocks live camera access. The phone's camera permission and the company network/firewall must both allow access.

## File locations and traceability

In the application, open **Files & Traceability** to see active server paths and the source-import log. The default host data root is `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA`:

- Work Order database: `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\DATABASE\sl_planning.db` (`SL_DB_PATH`).
- Scan photos: `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\PHOTOS\QR_SCANS\YYYY\MM\DD`.
- Physical audit photos: `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\PHOTOS\MOBILE_AUDITS`.
- Cached single Work Order QR PNGs: `apps/mobile/qr`.
- Uploaded Work Order source files and optional QR companions: `apps/mobile/uploads`.
- Imported sources and snapshots: `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\COMPANY_DATA` and `...\SOURCE_COPIES`.
- Reports / generated QR workbooks: `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\REPORTS`.

Uploaded Work Order source logs record original filename, server copy path, SHA-256, importing user, timestamp, imported count and rejected count. QR scan history records the decoded payload, resolved WO, scan method, result, timestamp, and photo details when a scan photo is submitted. A live video scan does not save a camera frame. Back up the database and photo/source/report folders on the host PC.

`SL_PUBLIC_URL` is optional and must be explicitly set by an administrator to a stable reachable URL to enable direct-open QR labels. The starter does not configure it from a changing LAN IP.

## Operator accounts

For first-run demo access, open `user details.txt` in the unzipped program folder. Change those passwords before other people log in.

This is a release candidate. Confirm the actual host PC, HTTPS certificate, camera permission, LAN/firewall access, and D: write permission using a real phone before relying on production audit capture.

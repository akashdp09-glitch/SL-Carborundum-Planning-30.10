V16.3 MOBILE CONNECTION / QR / WO STATUS CORRECTION

ROOT CAUSES CORRECTED
1) Mobile work-order DB was synchronized from active Plan-2026 only when /mobile was opened. The normal operator page is /operator, so WO lookup could be stale or blank. V16.3 synchronizes before /operator, /api/wo-search and /api/wo/{wo}.
2) Mobile live camera can be blocked by browsers when opened by http://LAN-IP. V16.3 retains live scan where supported and adds camera-photo capture + LOCAL SERVER QR decoding. Run INSTALL_REQUIREMENTS.bat once to install opencv-python-headless used by this fallback.
3) Desktop Mobile/QR navigation looked like it returned to Home. The Mobile Phone + QR page now visibly shows a large phone connection QR and LAN URL plus desktop WO tracking.
4) The Home-page WO search was removed as requested.

OLD QR WORKBOOK COMPATIBILITY
The uploaded old QR workbook was checked. Its QR images encode URLs such as:
http://10.10.10.12:8000/q/P001-210826
The V16.3 in-app scanner extracts the final WO number from this old URL, so it does not depend on the old 10.10.10.12 address. If the server IP is no longer 10.10.10.12, scan old labels from inside V16.3 rather than using the normal phone camera to open the old URL.

VERIFICATION PERFORMED
- Python compilation: hub.py, mobile app.py, Daily Planner, Firing Planner, shared analytics.
- FastAPI TestClient runtime: health 200; operator login; /operator 200; WO lookup with P001-010926, p001010926 and P001 010926 all resolved to the same WO; exact API lookup succeeded.
- QR decode runtime: newly generated plain-WO QR decoded successfully.
- QR decode runtime: an actual embedded QR image extracted from the user's old workbook decoded successfully to its old URL.
- Invalid camera image returns a controlled message instead of server error.
- ZIP integrity checked after packaging.

PHONE USE
1) Start the center on the server PC.
2) Desktop left menu -> Mobile Phone + QR.
3) Scan the CONNECTION QR with the normal phone Camera to open V16.3 on the current LAN address.
4) Log in once.
5) For PART labels, use SCAN QR WITH CAMERA inside the mobile operator screen. On HTTP it may open the phone camera to take a photo; the local server then decodes the QR.
6) Or type the WO in any case and with/without hyphen.

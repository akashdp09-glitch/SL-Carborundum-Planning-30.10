# HTTPS for phones and the company network

The shop-floor app listens on **HTTP port 8000** (the page that opens). **HTTPS port 8443** is optional so browsers that require a secure context can use the live camera. Company servers that refuse plain HTTP can still use 8443.

## What starts
* `http://FACTORY-PC-IP:8000/mobile` — phones and the live register (opens without a certificate)
* `https://FACTORY-PC-IP:8443/mobile` — same app, for the live camera after the certificate is installed
* `http://FACTORY-PC-IP:8000/health` — health check (work-order count)
* `http://FACTORY-PC-IP:8000/tls/ca.crt` — install this certificate **once** on each phone only if you want HTTPS
* HTTP does **not** redirect `/mobile` to HTTPS. A dead TLS port must not block the phone app.

Work-order QR labels stay `SLWO:<WO>`. They do not contain an IP or http/https.

## First time on a phone
1. Start `START_SL_CARBORUNDUM_PLANNING_CENTER.bat`.
2. On the phone, open `http://FACTORY-PC-IP:8000/tls/ca.crt` and install the certificate (Android: Settings → Security → Encryption & credentials → Install a certificate → CA certificate. iPhone: install the profile, then Settings → General → About → Certificate Trust Settings → enable full trust).
3. Open `http://FACTORY-PC-IP:8000/mobile` and log in. That is the shop-floor app.
4. Optional: open `https://FACTORY-PC-IP:8443/mobile` after installing the certificate if you need the live camera. Type and photo-of-QR still work on HTTP.
5. The Home page QR on the desktop points at whichever of HTTP/HTTPS is actually answering.

Windows may show a firewall prompt for Python. Allow it on the **private** factory network for ports 8000 and 8443.

## Company / official certificate
The local file is a factory-LAN certificate, not a public internet CA. To use the company certificate:

1. Copy the official PEM files to `CENTRAL_DATA/TLS/company.crt` and `CENTRAL_DATA/TLS/company.key` (or set `SL_TLS_CERT` and `SL_TLS_KEY`).
2. Restart the Planning Center.
3. Phones that already trust the company CA do not need `ca.crt`.

Do not put a password-protected key here; the starter needs a plain PEM key.

## Audit database
On the desktop hub: **Audit database** (Home tile or Track page). That screen shows every mobile audit row, the live SQLite path, photos folder, Excel export and a copy of `sl_planning.db`.  
On the phone: **All audits** / **Audits** opens the same register over HTTPS.

## Not a public website
This HTTPS is for the factory LAN (or an IT reverse-proxy in front of it). It does not publish the factory on the internet. IT can still put IIS / nginx in front and terminate their own certificate there; point the proxy at `https://127.0.0.1:8443` or `http://127.0.0.1:8000`.

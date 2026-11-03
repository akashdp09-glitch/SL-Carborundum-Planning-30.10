"""Start the mobile audit server on HTTP :8000 (full app) and HTTPS :8443 (camera).

HTTP used to only answer /health and /tls, then 302 every other path to HTTPS :8443.
When TLS, the certificate, or port 8443 failed, /mobile never opened. HTTP now serves
the same FastAPI app. HTTPS starts in a background thread when certificates work.
Phones can open http://FACTORY-PC-IP:8000/mobile immediately.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT / "apps" / "mobile")
if str(ROOT / "apps" / "mobile") not in sys.path:
    sys.path.insert(0, str(ROOT / "apps" / "mobile"))

from suite.tls_certs import HTTP_PORT, HTTPS_PORT, ensure_certs, public_urls  # noqa: E402


def _shared_root() -> Path:
    return Path(os.environ.get("SL_SHARED_ROOT", str(ROOT / "CENTRAL_DATA"))).resolve()


def _serve(port: int, ssl_cert: str | None = None, ssl_key: str | None = None) -> None:
    import uvicorn

    kwargs = dict(app="app:app", host="0.0.0.0", port=int(port), log_level="info")  # bind all PC interfaces; login remains required
    if ssl_cert and ssl_key:
        kwargs["ssl_certfile"] = ssl_cert
        kwargs["ssl_keyfile"] = ssl_key
    uvicorn.Server(uvicorn.Config(**kwargs)).run()


def start_https(tls: dict) -> None:
    def _run():
        try:
            _serve(HTTPS_PORT, str(tls["cert"]), str(tls["key"]))
        except Exception as exc:
            print(f"HTTPS :{HTTPS_PORT} not started: {exc}")
            print(f"Phone app stays available on HTTP :{HTTP_PORT}/mobile")

    threading.Thread(target=_run, daemon=True, name="sl-https").start()


def main():
    mobile_host = os.environ.get("SL_MOBILE_HOST", "").strip() or None
    tls = None
    try:
        tls = ensure_certs(_shared_root(), extra_hosts=[mobile_host] if mobile_host else None)
    except Exception as exc:
        print(f"TLS certificates not ready ({exc}). Phone app still opens on HTTP :{HTTP_PORT}.")
    urls = public_urls(mobile_host)
    print(f"Phone URL (HTTP — opens now): {urls['http']}/mobile")
    print(f"PC browser: {urls['http_local']}/mobile")
    if tls:
        print(f"TLS source: {tls['source']}")
        print(f"Certificate: {tls['cert']}")
        print(f"Phone URL (HTTPS camera, optional): {urls['https']}/mobile")
        print(f"Install on phones once: {urls['http']}/tls/ca.crt")
        start_https(tls)
    print(f"HTTP :{HTTP_PORT} serves the full shop-floor app on all PC network interfaces. It does not redirect /mobile to HTTPS.")
    print(f"All scans/audits/photos write to the configured host folders: {_shared_root()}")
    _serve(HTTP_PORT)


if __name__ == "__main__":
    raise SystemExit(main())

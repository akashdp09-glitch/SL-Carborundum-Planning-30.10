"""Factory-LAN TLS files for the mobile audit server.

Company-issued PEM files in the TLS folder are used when present.
Otherwise a local certificate is created for localhost and the PC's LAN IPs
so phones can open https:// and use the camera. The certificate is not a
public CA; IT can replace it with the official company certificate.
"""
from __future__ import annotations

import os
import socket
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


HTTP_PORT = int(os.environ.get("SL_PORT", "8000"))
HTTPS_PORT = int(os.environ.get("SL_HTTPS_PORT", "8443"))


def lan_ips() -> list[str]:
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        found.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except Exception:
        pass
    return found


def tls_dir(shared_root) -> Path:
    env = os.environ.get("SL_TLS_DIR")
    if env:
        p = Path(env)
    else:
        p = Path(shared_root) / "TLS"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pair(cert: Path, key: Path):
    if cert.is_file() and key.is_file() and cert.stat().st_size > 40 and key.stat().st_size > 40:
        return cert, key
    return None


def company_pair(directory: Path):
    env_c, env_k = os.environ.get("SL_TLS_CERT"), os.environ.get("SL_TLS_KEY")
    if env_c and env_k:
        got = _pair(Path(env_c), Path(env_k))
        if got:
            return got + ("company-env",)
    for name in ("company", "official", "server"):
        got = _pair(directory / f"{name}.crt", directory / f"{name}.key")
        if got and name != "server":
            return got + ("company-file",)
    return None


def _names(extra=None) -> list[str]:
    names = ["localhost", "127.0.0.1"]
    for ip in lan_ips():
        if ip not in names:
            names.append(ip)
    host = socket.gethostname().split(".")[0]
    if host and host not in names:
        names.append(host)
    for n in extra or []:
        if n and n not in names:
            names.append(n)
    return names


def _via_cryptography(cert_path: Path, key_path: Path, names: list[str], days: int):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SL Carborundum Planning")])
    san = []
    for n in names:
        try:
            san.append(x509.IPAddress(__import__("ipaddress").ip_address(n)))
        except ValueError:
            san.append(x509.DNSName(n))
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    cert_path.write_bytes(pem)
    (cert_path.parent / "ca.crt").write_bytes(pem)


def _via_openssl(cert_path: Path, key_path: Path, names: list[str], days: int):
    openssl = os.environ.get("OPENSSL_BIN", "openssl")
    cfg = cert_path.parent / "openssl.cnf"
    alt = []
    di = 1
    ii = 1
    for n in names:
        try:
            __import__("ipaddress").ip_address(n)
            alt.append(f"IP.{ii}={n}")
            ii += 1
        except ValueError:
            alt.append(f"DNS.{di}={n}")
            di += 1
    cfg.write_text(
        "[req]\ndistinguished_name=req_distinguished_name\nx509_extensions=v3_req\nprompt=no\n"
        "[req_distinguished_name]\nCN=SL Carborundum Planning\n"
        "[v3_req]\nbasicConstraints=CA:TRUE\nsubjectAltName=@alt\n"
        "[alt]\n" + "\n".join(alt) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", str(days),
         "-nodes", "-keyout", str(key_path), "-out", str(cert_path), "-config", str(cfg)],
        check=True, capture_output=True, text=True,
    )
    (cert_path.parent / "ca.crt").write_bytes(cert_path.read_bytes())


def ensure_certs(shared_root, extra_hosts=None, days=825) -> dict:
    directory = tls_dir(shared_root)
    company = company_pair(directory)
    if company:
        cert, key, source = company
        ca = directory / "ca.crt"
        if not ca.exists():
            ca.write_bytes(cert.read_bytes())
        return {"cert": cert, "key": key, "ca": ca if ca.exists() else cert, "source": source, "dir": directory, "names": _names(extra_hosts)}

    cert, key = directory / "server.crt", directory / "server.key"
    names = _names(extra_hosts)
    stamp = directory / "san.txt"
    wanted = "\n".join(names)
    reuse = cert.exists() and key.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == wanted
    if not reuse:
        try:
            _via_cryptography(cert, key, names, days)
            source = "generated-cryptography"
        except ImportError:
            _via_openssl(cert, key, names, days)
            source = "generated-openssl"
        stamp.write_text(wanted, encoding="utf-8")
        readme = directory / "README.txt"
        readme.write_text(
            "TLS for the SL mobile audit server.\n"
            "To use a company certificate, place company.crt and company.key in this folder and restart.\n"
            "Phones: install ca.crt once (Settings → Security → Install certificate), then open the https:// URL.\n",
            encoding="utf-8",
        )
    else:
        source = "cached"
    ca = directory / "ca.crt"
    if not ca.exists():
        ca.write_bytes(cert.read_bytes())
    return {"cert": cert, "key": key, "ca": ca, "source": source, "dir": directory, "names": names}


def public_urls(hostname=None) -> dict:
    host = hostname or (lan_ips()[0] if lan_ips() else "127.0.0.1")
    return {
        "https": f"https://{host}:{HTTPS_PORT}",
        "http": f"http://{host}:{HTTP_PORT}",
        "https_local": f"https://127.0.0.1:{HTTPS_PORT}",
        "http_local": f"http://127.0.0.1:{HTTP_PORT}",
        "https_port": HTTPS_PORT,
        "http_port": HTTP_PORT,
    }

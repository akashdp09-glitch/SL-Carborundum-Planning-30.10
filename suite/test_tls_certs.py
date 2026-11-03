from pathlib import Path
import ssl

from suite.tls_certs import company_pair, ensure_certs, public_urls


def test_ensure_certs_writes_pem(tmp_path: Path):
    info = ensure_certs(tmp_path, extra_hosts=["factory-pc"], days=30)
    assert info["cert"].is_file() and info["key"].is_file() and info["ca"].is_file()
    assert "localhost" in info["names"]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ssl.PEM_cert_to_DER_cert(info["cert"].read_text())
    again = ensure_certs(tmp_path, extra_hosts=["factory-pc"], days=30)
    assert again["source"] == "cached"


def test_company_files_win(tmp_path: Path):
    tls = tmp_path / "TLS"
    tls.mkdir()
    (tls / "company.crt").write_text("NOT-A-REAL-CERT\nplaceholder-company-certificate-file\n")
    (tls / "company.key").write_text("NOT-A-REAL-KEY\nplaceholder-company-private-key-file\n")
    cert, key, source = company_pair(tls)
    assert source == "company-file" and cert.name == "company.crt"


def test_public_urls_have_https():
    u = public_urls("10.0.0.8")
    assert u["https"].startswith("https://10.0.0.8:")
    assert u["http"].startswith("http://10.0.0.8:")

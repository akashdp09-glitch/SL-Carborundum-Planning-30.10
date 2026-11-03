from pathlib import Path

from suite.common import REPO_ROOT

SRC = (REPO_ROOT / "scripts" / "windows" / "start_mobile.py").read_text(encoding="utf-8")


def test_http_serves_the_full_app_not_a_redirect_stub():
    assert "does not redirect /mobile to HTTPS" in SRC
    assert "start_http_helper" not in SRC
    assert 'Location' not in SRC or "302" not in SRC
    assert "HTTP_PORT" in SRC and "app:app" in SRC
    assert "Phone URL (HTTP — opens now)" in SRC


def test_https_is_optional_background():
    assert "start_https" in SRC
    assert "daemon=True" in SRC
    assert "HTTPS" in SRC

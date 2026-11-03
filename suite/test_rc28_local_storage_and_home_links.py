from pathlib import Path


def test_rc28_uses_local_d_root_and_has_no_z_drive_startup_dependency():
    config = Path("SERVER_STORAGE_CONFIG.bat").read_text(encoding="utf-8")
    assert r"D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA" in config
    assert "Z:\\" not in config
    assert "SL_DB_PATH=%SL_SHARED_ROOT%\\DATABASE\\sl_planning.db" in config
    assert "SL_PHOTO_ROOT=%SL_SHARED_ROOT%\\PHOTOS" in config


def test_backorder_and_recovery_are_direct_home_shortcuts():
    hub = Path("hub.py").read_text(encoding="utf-8")
    home = hub.split("if _page in ('control',):", 1)[1].split("if _page == 'daily':", 1)[0]
    assert "_hub_page_href('back')" in home
    assert "_hub_page_href('daily_recovery')" in home
    assert "Backorder / Delivery Risk" in hub
    assert "Risk & Backorder Recovery Plan" in hub


def test_start_guide_documents_persistent_local_storage():
    guide = Path("START_HERE_V16_29_RC29.txt").read_text(encoding="utf-8")
    assert "does not require Z:" in guide
    assert r"D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA" in guide
    assert "PHOTOS\\MOBILE_AUDITS" in guide


def test_contextual_uploads_and_issued_qr_identity_are_preserved():
    hub = Path("hub.py").read_text(encoding="utf-8")
    qr = Path("suite/qr_labels.py").read_text(encoding="utf-8")
    assert "HOME_SOURCE_FILES=(\n    ('Plan-2026'" in hub
    assert "_render_context_source_updates(_page)" in hub
    assert "QR identity" in hub
    assert 'payload = "SLWO:" + wo' in qr
    assert "CENTRAL_DATA" in Path("docs/INSTALL_AND_UPDATE.md").read_text(encoding="utf-8")

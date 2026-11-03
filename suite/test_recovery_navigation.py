from pathlib import Path


def test_weekly_recovery_action_pack_has_direct_hub_and_daily_access():
    hub = Path("hub.py").read_text(encoding="utf-8")
    daily = Path("apps/daily/daily_planner_app.py").read_text(encoding="utf-8")
    assert "daily_recovery" in hub
    assert "Open Weekly Recovery Action Plan" in hub
    assert "Weekly Recovery Action Plan / แผนกู้คืนงานค้างและความเสี่ยง" in daily
    assert "'recovery':_quick_options[8]" in daily
    assert "'🧯 Weekly Recovery Action Plan / แผนกู้คืนงานค้างและความเสี่ยง':19" in daily


def test_hub_does_not_print_internal_iframe_urls_or_auth_tickets():
    hub = Path("hub.py").read_text(encoding="utf-8")
    assert "st.caption(('เปิดแท็บใหม่: ' if thai else 'Open in a new tab: ') + url)" not in hub
    assert "Do not print iframe URLs" in hub


def test_frequent_planning_views_use_text_headers_instead_of_decorative_photos():
    hub = Path("hub.py").read_text(encoding="utf-8")
    daily = Path("apps/daily/daily_planner_app.py").read_text(encoding="utf-8")
    assert "background:url(data:image/jpeg" not in hub
    assert "st.image(str(APP_DIR/" not in daily
    assert "product_01.jpg" not in daily


def test_home_banner_uses_small_bundled_factory_photo_without_external_request():
    hub = Path("hub.py").read_text(encoding="utf-8")
    home = hub.split("if _page in ('control',):", 1)[1].split("if _page == 'daily':", 1)[0]
    assert 'aria-label="SL Carborundum Planning Center"' in home
    assert "assets'/'company_front_clear.jpeg" in home
    assert "data:image/jpeg;base64," in home
    assert "One source · Clear plan" not in home
    assert "url('http" not in home and 'url("http' not in home
    assert "st.image(_bio.getvalue()" in home  # Functional phone-connection QR stays visible.


def test_daily_status_cache_uses_source_revision_fingerprint_and_does_not_clear_every_cache():
    daily = Path("apps/daily/daily_planner_app.py").read_text(encoding="utf-8")
    assert "def _daily_status_files(_uploads, source_fingerprint," in daily
    assert "_ds_fingerprint=tuple((str(p.resolve())" in daily
    assert "st.cache_data.clear()" not in daily


def test_home_registry_reads_are_cached_by_file_revision():
    hub = Path("hub.py").read_text(encoding="utf-8")
    assert "def _load_registry_cached(path, mtime_ns, size):" in hub
    assert "_load_registry_cached(str(REGISTRY),int(stat.st_mtime_ns),int(stat.st_size))" in hub
    assert "st.cache_data.clear()" not in hub


def test_uploaded_files_are_not_rehashed_and_reimported_on_every_rerun():
    hub = Path("hub.py").read_text(encoding="utf-8")
    assert "def _upload_token(upload, scope):" in hub
    assert "if _upload_seen(upload,_scope):return None" in hub
    assert "if _saved_path is None:continue" in hub
    assert "_mark_upload_seen(_u,_wip_scope)" in hub

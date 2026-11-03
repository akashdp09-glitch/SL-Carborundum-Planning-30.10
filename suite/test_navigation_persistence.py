from pathlib import Path
import re


def test_internal_hub_page_links_preserve_authentication_ticket():
    hub = Path("hub.py").read_text(encoding="utf-8")
    # Direct query-string anchors start a fresh page session without the signed
    # ticket. Internal links must be created through the ticket-preserving helper.
    assert not re.search(r"href\s*=\s*['\"]\??page=", hub)
    assert "def _hub_page_href(page, focus=''):" in hub
    assert "_q['auth_ticket']=_t" in hub
    assert "_hub_page_href('audits')" in hub
    assert "_hub_page_href('audit')" in hub


def test_uploaded_sources_and_calculated_plan_have_disk_persistence():
    hub = Path("hub.py").read_text(encoding="utf-8")
    daily = Path("apps/daily/daily_planner_app.py").read_text(encoding="utf-8")
    assert "SM.import_bytes(_slot,upload.name,b" in hub
    assert "CENTRAL_DATA" in hub
    assert "DAILY_PLAN_SNAPSHOTS" in daily
    assert "daily_result.pkl" in daily
    assert "st.session_state.clear()" not in hub
    assert "st.session_state.clear()" not in daily

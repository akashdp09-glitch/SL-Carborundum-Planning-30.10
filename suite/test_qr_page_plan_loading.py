from pathlib import Path


def test_files_page_loads_plan_for_qr_section_filter():
    hub = Path("hub.py").read_text(encoding="utf-8")
    assert "'src'}" in hub.split("_NEED_PLAN=", 1)[1].splitlines()[0]
    assert "_qrbase=rows_from_plan_frame(master)" in hub

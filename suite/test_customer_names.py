from suite.customer_names import (
    apply_customer_language,
    contains_thai,
    display_customer,
    is_thai_ui,
    language_font_css,
    latin_only,
    localize_customer_columns,
)


def test_thai_ui_keeps_plan_2026_original():
    src = "บริษัท ตัวอย่าง จำกัด ABC"
    assert display_customer(src, "ไทย") == src
    assert display_customer(src, "Thai") == src
    assert is_thai_ui("ไทย")


def test_english_ui_never_shows_thai_script():
    src = "บริษัท ABC จำกัด"
    out = display_customer(src, "English")
    assert not contains_thai(out)
    assert "ABC" in out


def test_english_passthrough_when_already_latin():
    assert display_customer("Saint-Gobain Abrasives", "English") == "Saint-Gobain Abrasives"
    assert display_customer("Saint-Gobain Abrasives", "ไทย") == "Saint-Gobain Abrasives"


def test_apply_customer_language_switches_display_column():
    import pandas as pd
    df = pd.DataFrame({
        "Work Order": ["P001"],
        "Customer Thai": ["บริษัท ตัวอย่าง"],
        "Customer English": ["Borisat Tuayang"],
        "Customer": ["บริษัท ตัวอย่าง"],
    })
    th = apply_customer_language(df, "ไทย")
    assert th.loc[0, "Customer"] == "บริษัท ตัวอย่าง"
    en = apply_customer_language(df, "English")
    assert en.loc[0, "Customer"] == "Borisat Tuayang"
    assert not contains_thai(en.loc[0, "Customer"])
    assert df.loc[0, "Customer Thai"] == "บริษัท ตัวอย่าง"


def test_localize_customername_column():
    import pandas as pd
    df = pd.DataFrame({"Customername": ["ลูกค้า ABC"]})
    en = localize_customer_columns(df, "English")
    assert not contains_thai(en.loc[0, "Customername"])
    th = localize_customer_columns(df, "ไทย")
    assert th.loc[0, "Customername"] == "ลูกค้า ABC"


def test_latin_only_strips_thai():
    assert "ABC" in latin_only("บริษัท ABC")
    assert not contains_thai(latin_only("บริษัท ABC"))


def test_hub_does_not_force_english_customer_in_cache():
    from pathlib import Path
    text = Path("hub.py").read_text(encoding="utf-8")
    assert "Cached Customer is the Plan-2026 original" in text
    assert "master['Customer']=master['Customer English']" not in text
    assert "_language_font_css" in text
    css = language_font_css("ไทย")
    assert "TH Sarabun" in css or "Sarabun" in css
    assert "Tahoma" in css
    assert '[class*="st-"]' not in css
    assert "html, body" not in css
    assert "stIconMaterial" in css
    assert "font-size: 0" in css
    en = language_font_css("English")
    assert "Segoe UI" in en
    assert "Sarabun" not in en
    assert '[class*="st-"]' not in en

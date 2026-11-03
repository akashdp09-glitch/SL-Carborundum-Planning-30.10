"""Plan-2026 customer names follow the UI language.

Thai: the original Customername text from Plan-2026 (Thai script, factory font).
English: English/Latin only — Thai script is romanized, never shown.
The Plan-2026 file is not rewritten.
"""
from __future__ import annotations

import re

THAI_RE = re.compile(r"[ก-๙]")
CUSTOMER_DISPLAY_COLS = (
    "Customer", "Customername", "customer_name", "Pack Customer",
    "Customer Thai", "Customer Thai — source", "Customer Source",
)

THAI_FONT_STACK = (
    '"TH Sarabun New", "TH SarabunPSK", "Sarabun", "Leelawadee UI", '
    '"Tahoma", "Angsana New", "Noto Sans Thai", sans-serif'
)
EN_FONT_STACK = '"Segoe UI", "Calibri", "Source Sans 3", Arial, sans-serif'


def is_thai_ui(lang) -> bool:
    t = str(lang or "").strip().lower()
    return t in {"ไทย", "th", "thai", "th-th"}


def contains_thai(value) -> bool:
    return bool(THAI_RE.search(str(value or "")))


def latin_only(value) -> str:
    return re.sub(r"\s+", " ", THAI_RE.sub(" ", str(value or ""))).strip()


def roman_customer_name(value) -> str:
    """Readable English-script companion. Source Thai is never changed."""
    txt = str(value or "").strip()
    if not txt or not contains_thai(txt):
        return txt
    try:
        from pythainlp.tokenize import word_tokenize
        from pythainlp.transliterate import romanize
        tokens = [t.strip() for t in word_tokenize(txt, engine="newmm", keep_whitespace=False) if str(t).strip()]
        out = []
        for t in tokens:
            if contains_thai(t):
                try:
                    r = str(romanize(t, engine="royin") or "").strip()
                except Exception:
                    r = ""
                out.append(r or t)
            else:
                out.append(t)
        joined = re.sub(r"\s+", " ", " ".join(out)).strip() or txt
        return latin_only(joined)
    except Exception:
        return latin_only(txt)


def display_customer(value, lang) -> str:
    """Thai UI → Plan-2026 original. English UI → English/Latin only."""
    if value is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(value):
            return ""
    except Exception:
        pass
    src = str(value).strip()
    if not src or src.lower() in {"nan", "none"}:
        return ""
    if is_thai_ui(lang):
        return src
    if not contains_thai(src):
        return src
    return roman_customer_name(src)


def apply_customer_language(df, lang, inplace: bool = False):
    """Set display Customer (and Customername) from Plan-2026 source according to UI language."""
    if df is None:
        return df
    try:
        import pandas as pd
    except Exception:
        return df
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    x = df if inplace else df.copy()
    source = None
    for col in ("Customer Thai", "Customer Source", "Customername", "Customer"):
        if col in x.columns:
            source = col
            break
    if source is None:
        return x
    if is_thai_ui(lang) and "Customer Thai" in x.columns:
        shown = x["Customer Thai"].fillna("").astype(str)
        shown = shown.mask(shown.str.lower().isin({"nan", "none"}), "")
    elif (not is_thai_ui(lang)) and "Customer English" in x.columns:
        shown = x["Customer English"].fillna("").astype(str)
        shown = shown.mask(shown.str.lower().isin({"nan", "none"}), "")
        shown = shown.map(lambda v: v if not contains_thai(v) else display_customer(v, lang))
    else:
        shown = x[source].map(lambda v: display_customer(v, lang))
    if "Customer" in x.columns:
        x["Customer"] = shown
    if "Customername" in x.columns:
        x["Customername"] = shown
    if "customer_name" in x.columns:
        x["customer_name"] = shown
    return x


def localize_customer_columns(df, lang):
    """Rewrite customer text columns for a table that is about to be shown."""
    if df is None:
        return df
    try:
        import pandas as pd
    except Exception:
        return df
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    x = df.copy()
    for c in list(x.columns):
        key = str(c)
        if key in CUSTOMER_DISPLAY_COLS or (re.search(r"customer", key, re.I) and "id" not in key.lower() and "english" not in key.lower()):
            x[c] = x[c].map(lambda v: display_customer(v, lang))
    if not is_thai_ui(lang) and "Customer English" in x.columns and "Customer" in x.columns:
        x["Customer"] = x["Customer English"].map(lambda v: display_customer(v, "English"))
    return x


def read_ui_language(session=None, env=None, start=None) -> str:
    if session is not None:
        v = session.get("lang") or session.get("global_language")
        if v:
            return str(v)
    try:
        import streamlit as st
        v = st.session_state.get("lang") or st.session_state.get("global_language")
        if v:
            return str(v)
    except Exception:
        pass
    try:
        from .central_paths import company_data
        p = company_data(env, start) / "UI_LANGUAGE.txt"
        t = p.read_text(encoding="utf-8").strip()
        if t:
            return t
    except Exception:
        pass
    return "English"


def language_font_css(lang) -> str:
    """Thai UI uses the same family Thai Excel / Plan-2026 typically uses on Windows."""
    if is_thai_ui(lang):
        family = THAI_FONT_STACK
        google = "@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600;700&display=swap');"
    else:
        family = EN_FONT_STACK
        google = ""
    return f"""<style>
{google}
[data-testid="stMarkdownContainer"],
[data-testid="stCaptionContainer"],
[data-testid="stDataFrame"],
[data-testid="stDataEditor"],
[data-testid="stMetricValue"],
[data-testid="stWidgetLabel"] p {{
  font-family: {family} !important;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stIconMaterial"] {{
  display: none !important;
}}
[data-testid="stExpander"] [data-testid="stIconMaterial"] {{
  font-size: 0 !important;
  line-height: 0 !important;
  color: transparent !important;
  width: 1.15rem !important;
  min-width: 1.15rem !important;
  height: 1.15rem !important;
  overflow: hidden !important;
  position: relative !important;
  flex-shrink: 0 !important;
}}
[data-testid="stExpander"] [data-testid="stIconMaterial"]::after {{
  content: "▾";
  font-size: 14px !important;
  font-family: "Segoe UI", Arial, sans-serif !important;
  color: #12395b !important;
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1 !important;
}}
[data-testid="stExpander"] [aria-expanded="false"] [data-testid="stIconMaterial"]::after {{
  content: "▸";
}}
</style>"""


def bilingual_customer_name(value) -> str:
    """Return Plan-2026 Thai name plus a readable Latin companion for dashboards."""
    src = str(value or "").strip()
    if not src or src.lower() in {"nan", "none"}:
        return ""
    if not contains_thai(src):
        return src
    latin = roman_customer_name(src)
    return f"{src} / {latin}" if latin and latin != src else src

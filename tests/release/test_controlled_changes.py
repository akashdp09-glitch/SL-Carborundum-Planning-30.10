"""Behavioural evidence for the files that differ from BASELINE_MANIFEST.json (see docs/RELEASE_INTEGRITY.md)."""
import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(folder, name, blocked=()):
    sys.path.insert(0, str(ROOT / "apps" / folder))
    saved = {k: sys.modules.get(k) for k in blocked}
    try:
        for k in blocked:
            sys.modules[k] = None          # makes `import k` raise ImportError
        spec = importlib.util.spec_from_file_location(f"_ev_{folder}_{name}", ROOT / "apps" / folder / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod        # dataclasses look the module up by name
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(ROOT / "apps" / folder))
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


@pytest.mark.parametrize("folder", ["daily", "firing"])
def test_missing_plotly_fails_with_clear_message(folder):
    mod = _load(folder, "firing_engine_desktop_v2", blocked=("plotly", "plotly.graph_objects", "plotly.express"))
    with pytest.raises(ImportError, match="plotly is required"):
        mod.go.Figure()
    with pytest.raises(ImportError, match="INSTALL_REQUIREMENTS.bat"):
        mod.px.bar


@pytest.mark.parametrize("folder", ["daily", "firing"])
def test_plotly_present_keeps_real_modules(folder):
    mod = _load(folder, "firing_engine_desktop_v2")
    assert mod.go.Figure().__class__.__name__ == "Figure"


def test_excel_serial_dates_never_become_1970():
    sys.path.insert(0, str(ROOT / "apps" / "daily"))
    try:
        from date_and_wo_rules import parse_date
    finally:
        sys.path.remove(str(ROOT / "apps" / "daily"))
    assert parse_date(45000) == dt.date(2023, 3, 15)
    assert parse_date("45000") == dt.date(2023, 3, 15)
    assert parse_date("05/10/2569") == dt.date(2026, 10, 5)      # Thai Buddhist year
    assert parse_date(1) is None or parse_date(1).year != 1970


def test_fast_store_deserialises_dates_without_nat():
    sys.path.insert(0, str(ROOT / "apps" / "daily"))
    try:
        import pandas as pd
        import sl_ppc_fast_store_v4_6 as fs
    finally:
        sys.path.remove(str(ROOT / "apps" / "daily"))
    df = pd.DataFrame({"Due Date": ["2026-10-05", "45000", "", None]})
    out = fs._deserialize_dates(df)
    assert out["Due Date"].iloc[0] == dt.date(2026, 10, 5) and out["Due Date"].iloc[1] == dt.date(2023, 3, 15)
    assert out["Due Date"].iloc[2] is None and out["Due Date"].iloc[3] is None


def test_linear_engine_uses_the_safe_parser():
    sys.path.insert(0, str(ROOT / "apps" / "daily"))
    try:
        import daily_linear_engine_v1_1 as le
    finally:
        sys.path.remove(str(ROOT / "apps" / "daily"))
    assert le.pdate(45000) == dt.date(2023, 3, 15)

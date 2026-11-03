import pytest
from suite.common import REPO_ROOT
from suite.sept_analysis import read_sept, by_product

SRC = REPO_ROOT / "apps/daily/JOB_REGISTER_REFERENCE_SEP2026.xlsx"


@pytest.fixture(scope="module")
def res():
    return read_sept(SRC)


def test_four_measures_are_kept_separate(res):
    got = dict(zip(res.measures.measure, res.measures.total_by_day_cells))
    assert got == {"sales_requests": 59, "wos_issued": 41, "unissued_items": 18, "production_closures": 66}


def test_day_cells_agree_with_sheet_total_cells(res):
    assert res.totals.matches.all() and len(res.totals) > 0
    m = res.measures
    assert (m.total_by_day_cells == m.total_by_sheet_total_cells).all()
    assert res.issues == []


def test_every_figure_is_traceable(res):
    assert res.long.sheet.notna().all() and res.long.cell.str.match(r"^[A-Z]+\d+$").all()
    assert set(res.long.measure) == {"sales_requests", "wos_issued", "unissued_items", "production_closures"}


def test_measures_never_netted_into_one_total(res):
    wide = by_product(res)
    for col in ("unissued_items", "production_closures"):
        assert col in wide.columns
    assert "total" not in [c.lower() for c in wide.columns]

from datetime import date
import pandas as pd

from suite.backorder_views import recent_open_closed_month_category, overdue_backorders


def test_recent_open_closed_bounded_and_separates_status_from_backorder():
    master = pd.DataFrame([
        {"Work Order": "A", "Due Date": "2026-08-15", "Product Category": "F", "Order Qty": 10, "pcs": 4, "Plan2026 kg/pc": 2.0},
        {"Work Order": "B", "Due Date": "2026-09-15", "Product Category": "R", "Order Qty": 20, "pcs": 0, "Plan2026 kg/pc": 0.5, "Overall Closed": True},
        {"Work Order": "C", "Due Date": "2026-10-20", "Product Category": "S", "Order Qty": 30, "pcs": 30, "Plan2026 kg/pc": 0.1},
        {"Work Order": "D", "Due Date": "2026-11-01", "Product Category": "P", "Order Qty": 40, "pcs": 40, "Plan2026 kg/pc": 1.0},
    ])
    out = recent_open_closed_month_category(master, date(2026, 10, 10), months=3)
    assert set(out["Due Month"]) == {"2026-08", "2026-09", "2026-10"}
    assert set(out["Status"]) == {"OPEN", "CLOSED"}
    assert out.loc[out["Due Month"].eq("2026-08"), "Product Category"].iloc[0] == "P"
    assert out.loc[out["Due Month"].eq("2026-09"), "Qty pcs"].iloc[0] == 20
    # The dashboard's strict overdue metric remains only open positive-balance WOs due before today.
    assert overdue_backorders(master, date(2026, 10, 10))["Work Order"].tolist() == ["A"]


def test_empty_recent_status_has_stable_schema():
    out = recent_open_closed_month_category(pd.DataFrame(), date(2026, 10, 10), months=3)
    assert list(out.columns) == ["Due Month", "Status", "Product Category", "Qty pcs", "Weight ton", "WOs"]

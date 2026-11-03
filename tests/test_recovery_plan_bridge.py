import pandas as pd

from suite.recovery_product_review import reconcile_recovery_to_plan


def test_recovery_snapshot_is_reconciled_to_current_plan_without_overwriting_dates():
    recovery = pd.DataFrame([
        {"Fac No": "WO-1", "_key": "WO-1", "Recovery Source Row": 4,
         "Original Due Date": pd.Timestamp("2026-10-01"), "Internal Date / Hold Status": "2026-10-25",
         "Recovery Result": "OPEN", "QTY": 100, "Wip": 20},
        {"Fac No": "WO-2", "_key": "WO-2", "Recovery Source Row": 5,
         "Original Due Date": pd.Timestamp("2026-09-01"), "Internal Date / Hold Status": "รอแผนขาย",
         "Recovery Result": "OPEN", "QTY": 50, "Wip": 10},
        {"Fac No": "WO-3", "_key": "WO-3", "Recovery Source Row": 6,
         "Original Due Date": pd.Timestamp("2026-08-01"), "Internal Date / Hold Status": "",
         "Recovery Result": "OPEN", "QTY": 75, "Wip": 0},
        {"Fac No": "WO-4", "_key": "WO-4", "Recovery Source Row": 7,
         "Original Due Date": pd.Timestamp("2026-08-01"), "Internal Date / Hold Status": "",
         "Recovery Result": "OPEN", "QTY": 80, "Wip": 5},
    ])
    plan = pd.DataFrame([
        {"Work Order": "WO-1", "Due Date": pd.Timestamp("2026-10-30"), "pcs": 80,
         "Authoritative Closed": False, "Section": "Firing", "Plan-2026 Source Row": 10},
        {"Work Order": "WO-2", "Due Date": pd.Timestamp("2026-09-01"), "pcs": 40,
         "Authoritative Closed": False, "Section": "Mixing", "Plan-2026 Source Row": 11},
        {"Work Order": "WO-3", "Due Date": pd.Timestamp("2026-08-01"), "pcs": 0,
         "Authoritative Closed": True, "Section": "Packing", "Plan-2026 Source Row": 12},
    ])
    overdue = plan[plan["Work Order"].eq("WO-2")].copy()

    result, plan_only = reconcile_recovery_to_plan(recovery, plan, overdue, "2026-10-21")
    by_wo = result.set_index("_key")
    assert result["_key"].nunique() == 4
    assert by_wo.loc["WO-1", "Historical due date (Recovery)"] == pd.Timestamp("2026-10-01")
    assert by_wo.loc["WO-1", "Current Plan due date"] == pd.Timestamp("2026-10-30")
    assert "confirm authorized revision" in by_wo.loc["WO-1", "Reconciliation result"]
    assert bool(by_wo.loc["WO-2", "Current overdue in Plan-2026"])
    assert "closed" in by_wo.loc["WO-3", "Reconciliation result"].lower()
    assert "Not found" in by_wo.loc["WO-4", "Reconciliation result"]
    assert plan_only.empty


def test_plan_overdue_wo_missing_from_recovery_snapshot_is_returned_separately():
    recovery = pd.DataFrame([{"Fac No": "WO-1", "_key": "WO-1", "Recovery Source Row": 4}])
    plan = pd.DataFrame([{"Work Order": "WO-1", "Due Date": "2026-10-01", "pcs": 10, "Authoritative Closed": False}])
    overdue = pd.DataFrame([
        {"Work Order": "WO-1", "Due Date": "2026-10-01", "pcs": 10},
        {"Work Order": "WO-2", "Due Date": "2026-09-01", "pcs": 5, "Section": "Forming", "Plan-2026 Source Row": 22},
    ])
    result, plan_only = reconcile_recovery_to_plan(recovery, plan, overdue, "2026-10-21")
    assert result["Current overdue in Plan-2026"].tolist() == [True]
    assert plan_only["Work Order"].tolist() == ["WO-2"]

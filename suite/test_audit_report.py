import sqlite3

import pandas as pd

from suite.audit_report import analyze, enrich_from_plan, load_latest_audits, load_open_wip_by_process


def test_analyze_groups_category_and_date():
    audits = pd.DataFrame([
        {"wo_id": "P001-010126", "physical_status": "OK", "physical_location": "Forming",
         "verified_qty": 10, "created_at": "2026-10-04 08:00:00", "product_category": "VITRIFY"},
        {"wo_id": "P002-010126", "physical_status": "HOLD", "physical_location": "Firing",
         "verified_qty": 4, "created_at": "2026-10-05 09:00:00", "product_category": "VITRIFY"},
        {"wo_id": "PB001-010126", "physical_status": "OK", "physical_location": "Forming",
         "verified_qty": 2, "created_at": "2026-10-05 10:00:00", "product_category": ""},
    ])
    out = analyze(audits)
    assert int(out["summary"].iloc[0]["Audited WOs"]) == 3
    cats = dict(zip(out["by_category"]["Product category"], out["by_category"]["WOs"]))
    assert cats["VITRIFY"] == 2 and cats["NOT IN PLAN"] == 1
    assert list(out["by_date"]["Date"]) == ["2026-10-04", "2026-10-05"]
    assert int(out["by_location"].set_index("Location").loc["Forming", "WOs"]) == 2


def test_enrich_uses_plan_category_when_audit_blank():
    audits = pd.DataFrame([{"wo_id": "p001-010126", "product_category": "", "verified_qty": 1}])
    plan = pd.DataFrame([{"Work Order": "P001-010126", "Product Category": "RESIN", "pcs": 5}])
    got = enrich_from_plan(audits, plan)
    assert str(got.iloc[0]["product_category"]).upper() == "RESIN"


def test_load_all_audits_keeps_history(tmp_path):
    import sqlite3
    from suite.audit_report import load_all_audits
    db = tmp_path / "t2.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE mobile_audits(id INTEGER PRIMARY KEY, wo_id TEXT, physical_status TEXT, physical_location TEXT, verified_qty REAL, user_name TEXT, created_at TEXT, notes TEXT)")
    con.executemany("INSERT INTO mobile_audits(wo_id,physical_status,physical_location,verified_qty,user_name,created_at,notes) VALUES(?,?,?,?,?,?,?)",
                    [("WO-1", "OPEN", "A", 1, "u", "2026-10-01 08:00:00", ""), ("WO-1", "OK", "B", 9, "u", "2026-10-02 08:00:00", "")])
    con.commit(); con.close()
    df = load_all_audits(db)
    assert len(df) == 2


def test_load_latest_audits_prefers_newest_row(tmp_path):
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE mobile_audits(id INTEGER PRIMARY KEY, wo_id TEXT, physical_status TEXT, physical_location TEXT, verified_qty REAL, user_name TEXT, created_at TEXT, notes TEXT)")
    con.executemany(
        "INSERT INTO mobile_audits(wo_id,physical_status,physical_location,verified_qty,user_name,created_at,notes) VALUES(?,?,?,?,?,?,?)",
        [
            ("WO-1", "OPEN", "A", 1, "u", "2026-10-01 08:00:00", ""),
            ("WO-1", "OK", "B", 9, "u", "2026-10-02 08:00:00", ""),
        ],
    )
    con.commit()
    con.close()
    df = load_latest_audits(db)
    assert len(df) == 1 and df.iloc[0]["physical_status"] == "OK" and float(df.iloc[0]["verified_qty"]) == 9


def test_mobile_wip_graph_uses_cumulative_output_not_last_event_qty(tmp_path):
    db = tmp_path / "wip.db"
    con = sqlite3.connect(db)
    con.executescript("""
      CREATE TABLE work_orders(wo_id TEXT, qty REAL, status TEXT, plan_location TEXT);
      CREATE TABLE events(id INTEGER PRIMARY KEY, wo_id TEXT, event_type TEXT, qty REAL, process_name TEXT, event_time TEXT);
    """)
    con.execute("INSERT INTO work_orders VALUES('WO-1',100,'ACTIVE','Planning')")
    con.executemany("INSERT INTO events(wo_id,event_type,qty,process_name,event_time) VALUES(?,?,?,?,?)", [
      ('WO-1','PARTIAL_COMPLETE',40,'Forming','2026-10-01'),
      ('WO-1','START',None,'Firing','2026-10-02'),
    ])
    con.commit(); con.close()
    got = load_open_wip_by_process(db)
    assert got.iloc[0]['Process'] == 'Firing'
    assert got.iloc[0]['Remaining order pcs'] == 60


def test_mobile_audit_report_separates_physical_process_and_quantity_unknown():
    got = analyze(pd.DataFrame([{
        'wo_id':'WO-1','physical_status':'HOLD','physical_location':'Rack A',
        'observed_process':'Firing','verified_qty':None,'created_at':'2026-10-09',
        'product_category':'P','plan_location':'Forming'
    }]))
    assert got['by_process'].iloc[0]['Observed process'] == 'Firing'
    assert got['summary'].iloc[0]['Quantity unknown'] == 1
    assert got['by_location_comparison'].iloc[0]['Location comparison'] == 'DIFFERENT — CHECK'

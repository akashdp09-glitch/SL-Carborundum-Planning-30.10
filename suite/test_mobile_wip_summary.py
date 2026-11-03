from pathlib import Path

from openpyxl import Workbook

from suite.audit_report import load_open_wip_by_process, load_production_wip_snapshot


def test_mobile_wip_graph_uses_open_balance_by_last_scanned_process(tmp_path):
    import sqlite3

    db = tmp_path / "mobile.db"
    con = sqlite3.connect(db)
    con.executescript("""
      CREATE TABLE work_orders(wo_id TEXT, qty REAL, status TEXT, plan_location TEXT);
      CREATE TABLE events(id INTEGER PRIMARY KEY, wo_id TEXT, event_type TEXT, qty REAL, process_name TEXT, event_time TEXT);
    """)
    con.execute("INSERT INTO work_orders VALUES('WO-1', 100, 'ACTIVE', 'Planning')")
    con.executemany("INSERT INTO events(wo_id,event_type,qty,process_name,event_time) VALUES(?,?,?,?,?)", [
        ("WO-1", "PARTIAL_COMPLETE", 40, "Forming", "2026-10-08"),
        ("WO-1", "START", None, "Firing", "2026-10-09"),
    ])
    con.commit()
    con.close()
    result = load_open_wip_by_process(db)
    assert result.iloc[0]["Process"] == "Firing"
    assert result.iloc[0]["Remaining order pcs"] == 60


def test_mobile_production_wip_reads_active_section_workbook_without_guessing(tmp_path, monkeypatch):
    root = tmp_path / "CENTRAL_DATA"
    folder = root / "PRODUCTION_WIP"
    folder.mkdir(parents=True)
    monkeypatch.setenv("SL_SHARED_ROOT", str(root))
    app_root = tmp_path / "program"
    daily_root = app_root / "apps" / "daily"
    daily_root.mkdir(parents=True)
    wb = Workbook()
    cover = wb.active
    cover.title = "Cover"
    cover.append(["placeholder"])
    ws = wb.create_sheet("สรุปใบสั่งผลิต")
    ws.append(["Category", "Total WO", "Open WO", "Open kg", "Closed WO"])
    ws.append(["P", 10, 4, 12500, 6])
    ws.append([None, 10, 4, 12500, 6])
    wb.save(folder / "Mixing_20261009.xlsx")

    frame, errors = load_production_wip_snapshot(daily_root)
    assert not errors
    assert len(frame) == 1
    assert frame.iloc[0]["Section"] == "Mixing"
    assert frame.iloc[0]["Category"] == "P"
    assert frame.iloc[0]["Open t"] == 12.5

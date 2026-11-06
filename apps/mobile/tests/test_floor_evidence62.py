"""SYNTHETIC section dates/quantities are retained without reopening files on scan."""
import json
from datetime import datetime
from openpyxl import Workbook


def test_plan_import_retains_section_dates_quantities_and_negative_closed_marker(core,tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB_PATH',tmp_path/'SYNTHETIC-plan62.db');core.init_db()
    w=Workbook();s=w.active;s.title='แผนการเผา'
    for col,value in [(1,'ProductionCode'),(10,'QTY'),(11,'รหัสสินค้า')]:s.cell(3,col,value)
    s.cell(4,1,'SYNTH-62');s.cell(4,2,datetime(2026,10,1));s.cell(4,10,100);s.cell(4,11,'SYNTHETIC-PART')
    for col,value in [('DF',100),('DG',40),('DH','ยังไม่ปิด'),('DB',datetime(2026,11,6)),('DE',datetime(2026,11,5)),('EU','ปิดใบสั่ง')]:s[f'{col}4']=value
    path=tmp_path/'SYNTHETIC Plan.xlsx';w.save(path)
    core.import_plan2026(path,path.name,'SYNTHETIC')
    c=core.db();row=c.execute("SELECT order_date,section_status_json FROM work_orders WHERE wo_id='SYNTH-62'").fetchone();c.close()
    sections={r['section']:r for r in json.loads(row['section_status_json'])}
    assert sections['Mixing']['status']=='OPEN' and sections['Mixing']['actual_qty']==40
    assert sections['Mixing']['planned_qty']==100 and sections['Mixing']['actual_date'].startswith('2026-11-05')
    assert sections['Packing']['status']=='CLOSED' and row['order_date'].startswith('2026-10-01')


def test_scan_desktop_and_mobile_have_different_plan_options(operator):
    desktop=operator.get('/scan').text;mobile=operator.get('/scan?mode=mobile').text
    assert 'desktop-plan-links' in desktop and 'Section plans' in desktop
    assert '<nav class="desktop-plan-links">' not in mobile
    result=operator.get('/api/wo/WO-TEST-0001').json()
    assert 'section_status' in result and 'production_evidence' in result and 'last_audit' in result

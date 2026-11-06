import io,sqlite3
from pathlib import Path
import pandas as pd
import pytest
from openpyxl import Workbook,load_workbook
from suite import order_status as O
from suite import supply_workspace as S
from suite import recovery_workspace as R
from suite.tracking_portal import validate_base


def test_whole_wo_decision_is_retry_safe_does_not_change_actual_and_reopens(tmp_path):
    db=tmp_path/'SYNTHETIC.db'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE work_orders(wo_id TEXT,source_file TEXT,imported_at TEXT)');c.execute("INSERT INTO work_orders VALUES('SYNTH-1','SYNTHETIC Plan','revision1')")
    a=O.save(db,'SYNTH-1','CLOSED','SYNTHETIC manager decision','operator','id1')
    assert a==O.save(db,'SYNTH-1','CLOSED','SYNTHETIC manager decision','operator','id1')
    with pytest.raises(ValueError):O.save(db,'SYNTH-1','OPEN','Changed','operator','id1')
    frame=pd.DataFrame([{'Work Order':'SYNTH-1','Overall Closed':False,'Authoritative Closed':False,'Packing Actual Qty':2,'pcs':8}])
    out=O.apply_frame(frame,db);assert bool(out.iloc[0]['Authoritative Closed']) and out.iloc[0]['Packing Actual Qty']==2 and out.iloc[0].pcs==8
    O.save(db,'SYNTH-1','OPEN','SYNTHETIC review pending balance','operator','id2')
    assert not bool(O.apply_frame(frame,db).iloc[0]['Authoritative Closed'])
    assert len(O.history(db))==2


def test_material_grams_scaled_to_unmixed_fraction_and_receipts_not_firm():
    raw=pd.DataFrame([{'ProductionCode':'SYNTH-1','mat':'A','grams':1000000}])
    master=pd.DataFrame([{'Work Order':'SYNTH-1','Mixing Remaining Qty':50,'Mixing Plan Qty':100,'Overall Closed':False}])
    demand,gaps=S.material_requirements(raw,master,[('mat','grams')]);assert demand.iloc[0]['Required tonnes']==.5
    stock=pd.DataFrame([{'material':'A','stock_g':100000,'incoming_g':1000000,'lab_g':2000000}])
    result=S.reconcile_materials(demand,stock).iloc[0]
    assert result['Physical stock tonnes']==.1 and result['Hard shortage tonnes']==.4
    assert result['Potential shortage after incoming tonnes']==0
    duplicate=S.reconcile_materials(demand,pd.concat([stock,stock]))
    assert pd.isna(duplicate.iloc[0]['Physical stock tonnes'])


def test_recovery_only_approved_sheet_row_linked_quantities_and_conflicts(tmp_path):
    p=tmp_path/'SYNTHETIC recovery.xlsx';w=Workbook();w.active.title='Cover';s=w.create_sheet('แผน Recovery')
    for r,actual,status in [(4,10,'ตามแผน'),(5,0,'ตกแผน')]:
        s.cell(r,2,'SYNTH-1');s.cell(r,5,'SYNTHETIC CUSTOMER');s.cell(r,7,10);s.cell(r,168,'30/10/2026');s.cell(r,169,5);s.cell(r,170,'31/10/2026');s.cell(r,171,actual);s.cell(r,173,status)
    w['Cover']['A1']='DO NOT USE THIS SHEET';w.save(p);w.close()
    d=R.read(p);assert len(d)==2 and d['Planned pcs'].sum()==10 and d['Actual pcs'].sum()==10
    assert d['Pending planned pcs'].sum()==5 # one row's excess cannot erase another row
    assert d['Actual applied pcs'].sum()==5 and d['Unmatched actual pcs'].sum()==5
    assert d['WO status'].str.startswith('CONFLICT').all()
    assert R.wo_reconciliation(d).iloc[0]['Pending_pcs']==5
    assert set(d['Plan date'].dt.month)=={10}


def test_access_url_is_explicit_and_model_independent():
    assert validate_base('http://176.0.3.99:8000/scan')=='http://176.0.3.99:8000'
    for bad in ['javascript:alert(1)','http://user:pw@server:8000','http://server?secret=1']:
        with pytest.raises(ValueError):validate_base(bad)


def test_mps_preserves_missing_dates_and_weights():
    d=pd.DataFrame([{'Work Order':'SYNTH-1','Due Date':None,'Product Category':'P','Section':'Mixing','pcs':4,'ton':0,'Plan2026 kg/pc':0}])
    t=S.mps_tables(d)
    assert t['Monthly category'].iloc[0]['Month']=='NO DATE'
    assert pd.isna(t['Monthly category'].iloc[0]['Known_tonnes'])

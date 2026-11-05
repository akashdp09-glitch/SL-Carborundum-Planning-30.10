import datetime as dt
import sqlite3
import pandas as pd
import pytest
from suite import drying_confirmations as D
from suite.common import bkk_today


def db(tmp_path):
    p=tmp_path/'SYNTHETIC_shared.db'
    with sqlite3.connect(p) as con:
        con.execute('CREATE TABLE work_orders(wo_id TEXT,imported_at TEXT)')
        con.execute("INSERT INTO work_orders VALUES('SYNTH-P1','revision-1')")
    return p


def test_confirmed_drying_is_shared_idempotent_and_invalidated_on_new_source(tmp_path):
    p=db(tmp_path);today=bkk_today()
    for _ in range(2):D.save(p,'SYNTH-P1',20,today,'SYNTHETIC oven register row 7','Verified physical output','operator','retry-1')
    h=D.history(p);assert len(h)==1 and h.iloc[0]['user']=='operator'
    frame=pd.DataFrame([{'Work Order':'SYNTH-P1'}])
    assert D.apply(frame,p).iloc[0]['Confirmed Drying Qty']==20
    with pytest.raises(ValueError):D.save(p,'SYNTH-P1',21,today,'SYNTHETIC oven register row 7','Verified physical output','operator','retry-1')
    with sqlite3.connect(p) as con:con.execute("UPDATE work_orders SET imported_at='revision-2'")
    assert pd.isna(D.apply(frame,p).iloc[0]['Confirmed Drying Qty'])
    assert len(D.history(p))==1 # original evidence remains


def test_future_unknown_and_unattributed_evidence_is_rejected(tmp_path):
    p=db(tmp_path)
    for wo,qty,day,source,reason,user in [
        ('MISSING',2,bkk_today(),'SYNTH','checked','op'),
        ('SYNTH-P1',2,bkk_today()+dt.timedelta(days=1),'SYNTH','checked','op'),
        ('SYNTH-P1',float('inf'),bkk_today(),'SYNTH','checked','op'),
        ('SYNTH-P1',2,bkk_today(),'','','')]:
        with pytest.raises(ValueError):D.save(p,wo,qty,day,source,reason,user)


def test_active_capacity_changes_route_offsets_without_mutating_defaults(tmp_path):
    from suite.lead_time_source import attach
    from apps.daily.lead_time_control_v1 import applied_offsets
    from openpyxl import Workbook
    p=tmp_path/'SYNTHETIC_capacity.xlsx';w=Workbook();s=w.active;s.title='Lead Time'
    for c,group in enumerate(['S','T','P','R','PB','M'],2):
        s.cell(2,c,'กลุ่ม '+group)
        for r in range(3,13):s.cell(r,c,'1 Day')
    s['D6']='8 Day';w.save(p);w.close()
    frame=attach(pd.DataFrame([{'Category':'P'}]),p)
    result=applied_offsets(frame.iloc[0])
    assert result['Curing/Oven Gate WD']==8
    assert result['Forming→Firing WD']==9
    assert 'D6=8 Day' in result['Source']
    assert applied_offsets({'Category':'P'})['Curing/Oven Gate WD']==3


def test_closed_historical_rows_do_not_block_active_lead_time_mapping():
    from suite.lead_time_source import attach
    p=__import__('pathlib').Path(__file__).parents[1]/'apps/daily/CAPACITY_DATABASE.xlsx'
    frame=pd.DataFrame([{'Work Order':'SYNTH-OPEN','Category':'P','Overall Closed':False},
                        {'Work Order':'SYNTH-CLOSED','Category':'OLD-UNKNOWN','Overall Closed':True}])
    result=attach(frame,p)
    assert isinstance(result.iloc[0]['_Capacity Lead Profile'],dict)
    assert result.iloc[1]['_Capacity Lead Profile'] is None
    frame.loc[1,'Overall Closed']=False
    with pytest.raises(ValueError,match='OLD-UNKNOWN'):attach(frame,p)

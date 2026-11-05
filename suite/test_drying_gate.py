import datetime as dt
from pathlib import Path
import pandas as pd
from suite.drying_gate import apply_upstream_drying,drying_rules,evaluate_drying,forming_to_firing
WB=Path(__file__).parents[1]/'apps/firing/CAPACITY_DATABASE.xlsx'


def test_real_capacity_drying_cells_and_bypass_are_retained():
    rules,sha=drying_rules(WB)
    assert rules['P'][:3]==(3.0,'3 Day','Lead Time!D6')
    assert rules['PB'][0]==0
    assert len(sha)==64


def test_workbook_route_offset_replaces_unsafe_next_day_firing():
    start=dt.date(2026,10,30)
    master=pd.DataFrame([{'Work Order':'SYNTH-P1','Type':'P'}])
    forming=pd.DataFrame([{'Work Order':'SYNTH-P1','Plan Date':start}])
    check=pd.DataFrame([{'Work Order':'SYNTH-P1','Plan Date':dt.date(2026,10,31),'Earliest Release Date':dt.date(2026,10,31)}])
    out=apply_upstream_drying(check,master,forming,WB)
    assert out.iloc[0]['Earliest Release Date']==dt.date(2026,11,5) # 2 forming + 3 oven WD; Sunday skipped
    assert out.iloc[0]['Sequence Status']=='FAIL'
    assert 'NOT VERIFIED' in out.iloc[0]['Drier capacity status']
    assert check.iloc[0]['Earliest Release Date']==dt.date(2026,10,31)


def test_existing_formed_wip_is_not_assumed_dried():
    d=pd.DataFrame([{'Load ID':'L1','Work Order':'SYNTH-P1','Load Date':dt.date(2026,10,30)}])
    p=pd.DataFrame([{'Work Order':'SYNTH-P1','Category':'P','Forming Actual':100}])
    out=evaluate_drying(d,p,None,WB,dt.date(2026,10,30))
    assert out.iloc[0]['Timing status']=='HOLD'
    assert 'no confirmed drying' in out.iloc[0]['Reason']
    p['Confirmed Drying Complete Date']=dt.date(2026,10,29)
    p['Confirmed Drying Qty']=100
    assert evaluate_drying(d,p,None,WB,dt.date(2026,10,30)).iloc[0]['Timing status']=='TIMING CONFIRMED'


def test_pb_bypass_unknown_group_and_exact_wo_exception():
    d=pd.DataFrame([{'Load ID':'L1','Work Order':'SYNTH-PB','Load Date':dt.date(2026,10,30)}])
    p=pd.DataFrame([{'Work Order':'SYNTH-PB','Category':'PB'}])
    assert evaluate_drying(d,p,None,WB,dt.date(2026,10,30)).iloc[0]['Timing status']=='BYPASS'
    p['Category']='UNKNOWN'
    assert evaluate_drying(d,p,None,WB,dt.date(2026,10,30)).iloc[0]['Timing status']=='HOLD'
    end,basis=forming_to_firing(dt.date(2026,10,30),'P005-110826',3,2)
    assert end==dt.date(2026,11,5) # exact-WO reference: 4 + 2 calendar days
    assert 'Q26-009' in basis

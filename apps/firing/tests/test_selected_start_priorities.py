from datetime import date
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).parents[1]))
import ppc_fast_core_v4_6 as fc
from suite.firing_start_policy import split_planning_lots,prior_availability

START=date(2026,11,6)


def test_partial_formed_wo_not_delayed_to_monday_by_open_mixing_label():
    raw=pd.DataFrame([{'Work Order':'SYNTH-1','Current Planning WIP Qty':40,'Current Shop-floor Release Qty':0}])
    prepared=pd.DataFrame([{'Work Order':'SYNTH-1','Effective Qty':100,'Include':True,'Readiness':'MIXING REQUIRED','Earliest Normal Firing':date(2026,11,9),'Mixing Status':'OPEN','Forming Status':'OPEN'}])
    out=split_planning_lots(prepared,raw,START)
    assert list(out['Effective Qty'])==[40,60]
    assert out.iloc[0]['Earliest Normal Firing']==START
    assert out.iloc[0]['Execution-ready quantity']==0 # no invented drying approval
    assert out.iloc[1]['Earliest Normal Firing']==date(2026,11,9)
    assert out['Effective Qty'].sum()==100 and out['Verified Ready for Firing Qty'].sum()==40
    assert out['Forming Status'].eq('OPEN').all() # source statuses preserved


def test_previously_issued_busy_kiln_is_excluded_before_another_kiln_is_chosen(monkeypatch):
    from suite import drying_confirmations
    monkeypatch.setattr(drying_confirmations,'apply',lambda frame,path:frame)
    monkeypatch.setattr(fc,'read_plan2026_kiln_calendar',lambda *a:pd.DataFrame())
    observed={}
    def fake_prior(*args,**kwargs):
        # args includes the kiln editor at position 9, before allocation starts.
        editor=args[9];observed.update(editor.set_index('Kiln')['Available From'].to_dict())
        free=editor[editor['Available From'].le(START)].iloc[0]
        return {'settings':fc.fire.Settings(planning_start=START),'loads':pd.DataFrame([{'Load ID':'SYNTH-L1','Load Date':START,'Kiln':free.Kiln}]),'details':pd.DataFrame()}
    monkeypatch.setattr(fc,'_run_firing_v45',fake_prior)
    editor=pd.DataFrame([{'Kiln':'T1','Available From':START},{'Kiln':'T4','Available From':START}])
    result=fc.run_firing_fast(pd.DataFrame(),Path(fc.__file__).parent/'CAPACITY_DATABASE.xlsx',START,kiln_editor=editor,previous_blocks={'T1':date(2026,11,9)})
    assert observed['T1']==date(2026,11,9) and observed['T4']==START
    assert result['loads'].iloc[0]['Kiln']=='T4' and result['loads'].iloc[0]['Load Date']==START
    assert result['selected_start_check'].iloc[0]['Loads on selected day']==1


def test_future_calendar_plan_does_not_block_selected_cutover(monkeypatch):
    rows={2:{10:11},4:{11:9},6:{10:'เช้า',11:'บ่าย'},7:{1:'T4',3:'PLAN',10:8,11:'P1'}}
    monkeypatch.setattr(fc,'_xlsx_sparse_sheet_v46',lambda *a:rows)
    table=fc.read_plan2026_kiln_calendar(__file__,START)
    assert table.iloc[0]['Available From']==START
    assert 'replaceable' in table.iloc[0]['Calendar Warning']


def test_split_does_not_duplicate_ready_quantity_across_repeated_prepared_rows():
    raw=pd.DataFrame([{'Work Order':'SYNTH-1','Current Planning WIP Qty':30,'Current Shop-floor Release Qty':10}])
    base={'Work Order':'SYNTH-1','Effective Qty':50,'Include':True,'Readiness':'MIXING REQUIRED','Earliest Normal Firing':date(2026,11,9)}
    out=split_planning_lots(pd.DataFrame([base,base]),raw,START)
    assert out['Effective Qty'].sum()==100
    assert out['Verified Ready for Firing Qty'].sum()==30
    assert out['Execution-ready quantity'].sum()==10


def test_real_kiln_candidate_filter_keeps_sixth_available_after_prior_busy_block():
    settings=fc.fire.Settings(planning_start=START)
    editor=fc.fire.default_kilns(settings)
    editor=editor[editor['Kiln'].isin(['T1','T4'])].copy();editor['Available From']=START
    editor=prior_availability(editor,{'T1':date(2026,11,9)},START)
    kilns=fc.fire.prepare_kilns(editor,settings)
    eligible=fc.fire.candidate_kilns(kilns,'P1',START)
    names=set(kilns.loc[eligible,'Kiln'])
    assert 'T1' not in names and 'T4' in names

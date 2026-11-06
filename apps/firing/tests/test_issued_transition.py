"""SYNTHETIC issued records: dates reproduce the requested shape, not factory proof."""
from datetime import date,datetime,timedelta
from io import BytesIO
from pathlib import Path
import sys
import pandas as pd
from openpyxl import Workbook
sys.path.insert(0,str(Path(__file__).parents[1]))
import ppc_fast_core_v4_6 as fc
from apps.firing.issued_transition import read_commitments,reconcile,reserve_frame,merge_operational

START=date(2026,11,6);END=date(2026,11,9)
class Upload:
    name='SYNTHETIC issued.xlsx'
    def __init__(self,data):self.data=data
    def getvalue(self):return self.data


def evidence():
    w=Workbook();s=w.active;s.title='Operator Print'
    s.append(['Load ID / รหัสโหลด','Loading Date / วันที่เข้าเตา','Kiln / เตา','Program / โปรแกรม','Work Order / ใบสั่งผลิต','Planned Qty (pcs) / จำนวนแผน (ชิ้น)','Firing Finish Date / วันที่เผาเสร็จ'])
    starts=[(6,'T12'),(7,'R5'),(7,'T14'),(7,'T4'),(9,'R4'),(9,'R6'),(9,'T1'),(9,'T3')]
    master=[]
    for n,(day,kiln) in enumerate(starts):
        for j in range(4 if n==0 else 3):
            wo=f'SYNTHETIC-{n}-{j}';program='KM-185' if kiln.startswith('R') else 'P1'
            s.append([f'SYNTH-L{n}',datetime(2026,11,day),kiln,program,wo,10,datetime(2026,11,day)+timedelta(days=7)])
            master.append({'Work Order':wo,'Firing Plan':30,'Order Qty':30,'Forming Actual':30,'Firing Actual':0,'Overall Closed':False})
    b=BytesIO();w.save(b)
    editor=pd.DataFrame([{'Kiln':k,'Available From':START,'Programs':'P1,KM-185','Physical kg':1000} for _,k in starts])
    return Upload(b.getvalue()),pd.DataFrame(master),editor


def test_main_outputs_and_export_include_all_eight_starts_and_25_rows(tmp_path,monkeypatch):
    upload,plan,editor=evidence();observed={}
    monkeypatch.setattr(fc,'read_plan2026_kiln_calendar',lambda *a:pd.DataFrame())
    def allocator(*args,**kwargs):
        observed['start']=args[2];observed['plan']=args[0].copy();observed['editor']=args[9].copy()
        new={'Load ID':'SYNTHETIC-NEW','Load Date':date(2026,11,10),'Kiln':'T5','Program':'P1','Work Order':'SYNTHETIC-0-0','Planned Firing Qty':20,'Qty pcs':20,'Firing Complete':date(2026,11,17)}
        return {'settings':fc.fire.Settings(planning_start=args[2]),'loads':pd.DataFrame([new]),'details':pd.DataFrame([new]),'floor':pd.DataFrame()}
    monkeypatch.setattr(fc,'_run_firing_v45',allocator)
    result=fc.run_firing_fast(plan,Path(fc.__file__).parent/'CAPACITY_DATABASE.xlsx',START,kiln_editor=editor,previous_files=[upload],retain_through=END)
    assert observed['start']==date(2026,11,10)
    assert observed['plan']['Retained firing reservation Qty'].sum()==250
    assert observed['plan']['Firing Actual'].sum()==0 and plan['Firing Actual'].sum()==0
    assert result['loads']['Plan origin'].eq('RETAINED ISSUED').sum()==8
    assert result['details']['Plan origin'].eq('RETAINED ISSUED').sum()==25
    assert result['details']['Planned Firing Qty'].sum()==270
    assert result['loads'].groupby('Load Date').size().to_dict()=={START:1,date(2026,11,7):3,END:4,date(2026,11,10):1}
    assert result['settings'].planning_start==START
    assert result['selected_start_check'].iloc[0]['Loads on selected day']==1
    out=tmp_path/'SYNTHETIC_FIRING_OUTPUT.xlsx';fc.save_firing(result,out)
    with pd.ExcelFile(out) as book:
        assert len(pd.read_excel(book,'Firing Loads'))==9
        operator=pd.read_excel(book,'Operator Print')
        assert len(operator)==26 and operator['Plan origin'].eq('RETAINED ISSUED').sum()==25
        assert 'Transition Reconciliation' in book.sheet_names
    reread=read_commitments([out],START,END)
    assert len(reread)==25 and reread['Planned Firing Qty'].sum()==250


def test_unfinished_forming_preserves_issued_instruction_and_reports_required_supply():
    upload,plan,editor=evidence();plan.loc[0,'Forming Actual']=9
    rows=read_commitments([upload],START,END)
    retained,review,qty,blocks=reconcile(rows,plan,editor)
    assert len(retained)==25 and len(review)==25
    first=review[review['Kiln'].eq('T12')]
    assert first.Result.ne('REJECTED').all()
    assert 'PRODUCTION INSTRUCTION' in first.iloc[0].Reason
    assert qty['SYNTHETIC-0-0']==10 and retained['Load Date'].min()==START
    out=merge_operational({'loads':pd.DataFrame(),'details':pd.DataFrame()},retained,review,START,END+timedelta(days=1))
    actions=out['transition_production_actions']
    assert len(actions)==1 and actions.iloc[0]['Additional forming supply pcs']==1
    assert plan.loc[0,'Forming Actual']==9 # target is not invented actual output


def test_issued_quantity_above_remaining_demand_is_rejected_with_reason():
    upload,plan,editor=evidence();plan.loc[0,'Firing Actual']=25
    retained,review,qty,blocks=reconcile(read_commitments([upload],START,END),plan,editor)
    assert len(retained)==21
    assert review[review.Kiln.eq('T12')].Result.eq('REJECTED').all()
    assert 'remaining unreserved firing demand 5' in review.iloc[0].Reason


def test_quantities_and_drying_budget_reserved_once_without_modifying_actuals():
    plan=pd.DataFrame([{'Work Order':'SYNTHETIC-Q','Firing Plan':100,'Order Qty':100,'Forming Actual':70,'Firing Actual':10,'Category':'PB','Program':'P1','Due Date':START,'Forming Status':'OPEN'}])
    reserved=reserve_frame(plan,{'SYNTHETIC-Q':40})
    raw=fc.firing_input(reserved,START,False,False)
    assert raw.iloc[0]['Remaining Qty']==20 and raw.iloc[0]['Candidate Ready Qty']==20
    assert raw.iloc[0]['Firing Actual Qty']==10 and plan.iloc[0]['Firing Actual']==10


def test_calendar_overlap_and_duplicate_upload_do_not_duplicate_commitments():
    upload,plan,editor=evidence();rows=read_commitments([upload,upload],START,END)
    assert len(rows)==25
    kept,review,qty,blocks=reconcile(rows,plan,editor,{'T12':date(2026,11,8)})
    assert 'T12' not in set(kept.Kiln)
    assert review[review.Kiln.eq('T12')].Reason.str.contains('occupied').all()
    assert blocks['T12']==date(2026,11,8)
    # Explicit capacity limits still apply to retained commitments.
    rows.loc[rows.Kiln.eq('T4'),'Geometric Occupancy Util']=.99
    kept,review,_,_=reconcile(rows,plan,editor,max_volume=.95)
    assert 'T4' not in set(kept.Kiln)
    assert review[review.Kiln.eq('T4')].Reason.str.contains('maximum occupancy').all()

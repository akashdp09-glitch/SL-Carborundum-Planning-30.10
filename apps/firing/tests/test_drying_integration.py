from pathlib import Path
import sys
from datetime import date
import pandas as pd
sys.path.insert(0,str(Path(__file__).parents[1]))
import ppc_fast_core_v4_6 as fc


def test_final_entry_point_holds_unconfirmed_drying_and_exports_it(monkeypatch,tmp_path):
    from suite import drying_confirmations
    monkeypatch.setattr(drying_confirmations,'apply',lambda frame,path:frame.copy())
    monkeypatch.setattr(fc.fire,'default_kilns',lambda settings:pd.DataFrame())
    monkeypatch.setattr(fc,'read_plan2026_kiln_calendar',lambda *a:pd.DataFrame())
    monkeypatch.setattr(fc,'apply_plan2026_kiln_calendar',lambda editor,*a:editor)
    def prior(*a,**kw):
        return {'loads':pd.DataFrame([{'Load ID':'SYNTH-L1','Load Date':date(2026,10,30)}]),
                'details':pd.DataFrame([{'Load ID':'SYNTH-L1','Work Order':'SYNTH-P1','Load Date':date(2026,10,30),'Qty pcs':10}])}
    monkeypatch.setattr(fc,'_run_firing_v45',prior)
    p=pd.DataFrame([{'Work Order':'SYNTH-P1','Category':'P'}])
    result=fc.run_firing_fast(p,Path(fc.__file__).parent/'CAPACITY_DATABASE.xlsx',date(2026,10,30))
    assert result['release_summary'].iloc[0]['Status']=='HOLD'
    assert result['loads'].iloc[0]['Load Date']==date(2026,10,30) # anchor retained, shortage explained
    assert 'HOLD' in result['details'].iloc[0]['Drying release']
    out=tmp_path/'SYNTHETIC-review.xlsx';fc.save_firing(result,out)
    from openpyxl import load_workbook
    w=load_workbook(out,read_only=True)
    assert 'Drying Readiness' in w.sheetnames and 'Release Summary' in w.sheetnames
    w.close()


def test_simultaneous_firing_sessions_cannot_overwrite_legacy_global_settings(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading,time
    from suite import drying_confirmations
    monkeypatch.setattr(drying_confirmations,'apply',lambda frame,path:frame.copy())
    monkeypatch.setattr(fc.fire,'default_kilns',lambda settings:pd.DataFrame())
    monkeypatch.setattr(fc,'read_plan2026_kiln_calendar',lambda *a:pd.DataFrame())
    monkeypatch.setattr(fc,'apply_plan2026_kiln_calendar',lambda editor,*a:editor)
    state={'active':0,'peak':0};guard=threading.Lock()
    def prior(*a,**kw):
        with guard:state['active']+=1;state['peak']=max(state['peak'],state['active'])
        time.sleep(.01)
        with guard:state['active']-=1
        return {'details':pd.DataFrame()}
    monkeypatch.setattr(fc,'_run_firing_v45',prior)
    def run(_):return fc.run_firing_fast(pd.DataFrame(),Path(fc.__file__).parent/'CAPACITY_DATABASE.xlsx',date(2026,10,30))
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(run,range(3)))
    assert state['peak']==1

"""Exercise the actual final Daily engine in isolation from similarly named Firing modules."""
import subprocess
import sys
from pathlib import Path


def test_daily_firing_requires_drying_evidence_and_keeps_selected_anchor():
    root=Path(__file__).parents[2]
    code='''
import daily_linear_engine_v1_1 as dl
import pandas as pd
from datetime import date
r={'Work Order':'SYNTH-P1','Category':'P','Order Qty':10,'Gross Weight g/pc':100,'Net Weight g/pc':100,'Due Date':date(2026,11,30),'WIP Preparation':0,'WIP Mixing':0,'WIP Forming':0,'WIP Firing':10,'WIP Grinding / Cutting':0,'WIP Packing':0}
f=pd.DataFrame([{'Work Order':'SYNTH-P1','Firing Date':date(2026,11,5),'Firing Complete':date(2026,11,10),'Firing Qty':10,'kg/pc':.1,'Program':'P1','Kiln':'T1'}]);empty=pd.DataFrame()
for confirmed,quantity in [(False,0),(True,4),(True,10)]:
 r.update({'Confirmed Drying Complete Date':date(2026,11,4) if confirmed else None,'Confirmed Drying Qty':quantity})
 result=dl.build_daily(pd.DataFrame([r]),f,empty,empty,empty,empty,empty,date(2026,11,5),horizon=1)
 row=result['all'].iloc[0]
 assert row['Plan Date']==date(2026,11,5)
 assert row['Executable Qty']==quantity
 assert ('HOLD' in row['Release Status'])==(quantity<10)
 assert 'VERIFY DRYING RESOURCES' in row['Release Status'] if quantity==10 else True
from lead_time_control_v1 import forming_release_date
assert forming_release_date(date(2026,11,5),{'Work Order':'P005-110826','Category':'P'})==date(2026,11,11)
'''
    r=subprocess.run([sys.executable,'-c',code],cwd=root/'apps/daily',text=True,capture_output=True,timeout=20)
    assert r.returncode==0,r.stdout+r.stderr

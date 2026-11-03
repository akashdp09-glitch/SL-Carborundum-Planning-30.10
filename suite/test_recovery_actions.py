import pandas as pd
from suite.recovery_actions import build_recovery_actions

def test_recovery_sheet_keeps_overdue_open_only_and_waits_for_confirmation():
    master=pd.DataFrame([
      {'Work Order':'LATE-1','Due Date':'2026-10-01','Overall Closed':False,'_open_qty':12,'Product Code':'P1','Customer':'Cust'},
      {'Work Order':'DUE-2','Due Date':'2026-10-08','Overall Closed':False,'_open_qty':8,'Product Code':'P2','Customer':'Cust'},
      {'Work Order':'DONE-3','Due Date':'2026-10-01','Overall Closed':True,'_open_qty':0,'Product Code':'P3','Customer':'Cust'},
      {'Work Order':'FUTURE-4','Due Date':'2026-12-01','Overall Closed':False,'_open_qty':9,'Product Code':'P4','Customer':'Cust'},
      {'Work Order':'RISK-5','Due Date':'2026-11-01','Overall Closed':False,'_open_qty':7,'Product Code':'P5','Customer':'Cust'},
    ])
    risk=pd.DataFrame([{'Work Order':'RISK-5','Delivery Risk':'HIGH','Bottleneck Process':'Firing','Projected Finish':'2026-11-03','Recovery Action':'Check kiln recovery'}])
    x=build_recovery_actions(master,risk,'2026-10-06')
    assert set(x['Work Order'])=={'LATE-1','DUE-2','RISK-5'}
    assert x.loc[x['Work Order'].eq('LATE-1'),'Recovery Priority'].iloc[0]=='1 OVERDUE'
    assert x.loc[x['Work Order'].eq('RISK-5'),'Recovery Action'].iloc[0]=='Check kiln recovery'
    assert x['Agreement Status'].str.startswith('PENDING').all()
    assert x['Sales Priority — confirm'].eq('').all()
    assert 'DONE-3' not in set(x['Work Order']) and 'FUTURE-4' not in set(x['Work Order'])

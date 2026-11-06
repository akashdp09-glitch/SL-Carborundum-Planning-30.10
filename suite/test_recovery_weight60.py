from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from suite.recovery_workspace import with_weights,total_orders,summary


def test_matched_grams_to_tonnes_and_unique_order_total(tmp_path):
    w=Workbook();s=w.active;s.title='แผนการเผา';s.cell(4,1,'SYNTH-60');s.cell(4,95,2000)
    p=tmp_path/'SYNTHETIC Plan.xlsx';w.save(p)
    d=pd.DataFrame([{'Work Order':'SYNTH-60','_WO key':'SYNTH60','Customer':'SYNTHETIC','Order pcs':100,'Planned pcs':20,'Actual pcs':10,'Pending planned pcs':10,'Actual unrecorded':False}, {'Work Order':'SYNTH-60','_WO key':'SYNTH60','Customer':'SYNTHETIC','Order pcs':100,'Planned pcs':30,'Actual pcs':None,'Pending planned pcs':30,'Actual unrecorded':True}])
    x=with_weights(d,p)
    assert x['Planned tonnes'].sum()==.1 and x['Actual tonnes'].sum()==.02
    assert pd.isna(x.iloc[1]['Actual tonnes'])
    t=total_orders(x);assert len(t)==1 and t.iloc[0]['Total order pcs']==100 and t.iloc[0]['Total order tonnes']==.2
    report=summary(x,['Customer']);assert report.iloc[0]['Work_orders']==1 and report.iloc[0]['Planned_tonnes']==.1


def test_conflicting_part_weights_and_order_quantities_are_not_invented(tmp_path):
    w=Workbook();s=w.active;s.title='แผนการเผา'
    for n,g in [(4,1000),(5,2000)]:s.cell(n,1,'SYNTH-60');s.cell(n,95,g)
    p=tmp_path/'SYNTHETIC conflicting.xlsx';w.save(p)
    d=pd.DataFrame([{'Work Order':'SYNTH-60','Order pcs':10,'Planned pcs':10,'Actual pcs':0,'Pending planned pcs':10},{'Work Order':'SYNTH-60','Order pcs':20,'Planned pcs':10,'Actual pcs':None,'Pending planned pcs':10}])
    x=with_weights(d,p)
    assert x['Planned tonnes'].isna().all()
    t=total_orders(x);assert pd.isna(t.iloc[0]['Total order pcs']) and t.iloc[0]['Order quantity conflict']

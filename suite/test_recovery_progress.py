from datetime import datetime
from openpyxl import Workbook
from suite.recovery_progress import read_recovery_progress

def test_recovery_progress_reconciles_at_work_order_and_period_level(tmp_path):
    p=tmp_path/'recovery.xlsx'; w=Workbook(); c=w.active; c.title='Cover'
    h=['ProductionCode']+[None]*8+['QTY']+[None]*23+['GW']
    c.append(h); c.append(['WO-1']+[None]*8+[100]+[None]*23+[10000])
    s=w.create_sheet('แผน Recovery')
    s.append(['']*176); s.append(['']*176)
    hdr=[None]*176; hdr[1]='Fac No';hdr[167]='date';hdr[168]='จำนวน Plan';hdr[169]='วันที่เริ่มเข้าคลัง';hdr[170]='Actual'
    s.append(hdr)
    for wo,pdate,pq,adate,aq in [('WO-1',datetime(2026,10,1),60,'1/10/2026',40),('WO-1',datetime(2026,10,8),40,'8/10/2026',20)]:
        r=[None]*176;r[1]=wo;r[167]=pdate;r[168]=pq;r[169]=adate;r[170]=aq;s.append(r)
    w.save(p)
    detail,week,month,total,meta=read_recovery_progress(p)
    t=total.iloc[0]
    assert t['Planned WOs']==1 and t['Planned pcs']==100
    assert t['Actual-produced WOs']==1 and t['Actual pcs']==60
    assert t['Remaining WOs']==1 and t['Remaining pcs']==40
    assert round(t['Planned kg'],3)==10 and round(t['Actual kg'],3)==6 and round(t['Remaining kg'],3)==4
    assert len(week)==2 and len(month)==1 and meta['weight_coverage_wos']==1

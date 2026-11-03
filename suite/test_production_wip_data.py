from pathlib import Path
from openpyxl import Workbook
from suite.production_wip_data import read_production_wip

def _fixture(path):
    wb=Workbook(); cover=wb.active; cover.title='Cover'; cover.append(['placeholder'])
    summary=wb.create_sheet('สรุปใบสั่งผลิต')
    summary.append(['Group','ใบสั่งผลิตทั้งหมด','ยังไม่ปิด','GW (Kg)','ปิดใบสั่ง'])
    summary.append(['S',37,17,7441.8935,20]);summary.append(['T',21,10,4836.6328,11])
    summary.append(['P',277,137,15396.4048,140]);summary.append(['R',33,36,3948.7604,88])
    summary.append(['PB',124,8,1160.1215,25]);summary.append(['M',9,1,52.1121,8])
    summary.append([None,501,209,32835.925,292])
    # Deliberately conflicting detail rows: must not replace sheet-2 summary or add fake categories.
    detail=wb.create_sheet('ตุลาคม');detail.append(['WO','Category','Open kg']);detail.append(['WO-1','#N/A',999])
    wb.save(path)

def test_second_sheet_summary_is_authoritative_and_category_mismatch_is_flagged(tmp_path):
    path=tmp_path/'firing.xlsx';_fixture(path)
    d=read_production_wip(path,'Firing + curing',{'original_name':'firing.xlsx','registered_at':'2026-10-24'})
    assert d['Source sheet'].unique().tolist()==['สรุปใบสั่งผลิต']
    assert 'SOURCE CATEGORY MISSING' not in set(d.Category)
    assert set(d.Category)=={'S','T','P','R','PB','M'}
    r=d[d.Category.eq('R')].iloc[0];pb=d[d.Category.eq('PB')].iloc[0]
    assert r['Open WO']==36 and r['WIP WOs (source open)']==36 and r['Open WIP WO (Total − Closed)']==-55
    assert 'CHECK SUMMARY' in r['Summary variance / check']
    assert pb['Open WO']==8 and pb['Open WIP WO (Total − Closed)']==99
    assert d[d.Category.eq('P')].iloc[0]['Open kg']==15396.4048
    assert d.iloc[0]['Original filename']=='firing.xlsx'

def test_f_category_maps_to_p_and_second_sheet_generic_headers(tmp_path):
    p=tmp_path/'forming.xlsx';w=Workbook();w.active.title='Cover';s=w.create_sheet('Summary')
    s.append(['Category','Total WO','Open WO','Open kg','Closed WO']);s.append(['F',10,4,12500,6]);s.append([None,10,4,12500,6]);w.save(p)
    d=read_production_wip(p,'Forming')
    assert len(d)==1 and d.iloc[0]['Category']=='P' and d.iloc[0]['Open t']==12.5

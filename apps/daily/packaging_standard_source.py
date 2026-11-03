"""Shared, cached reader for approved Thai and legacy English packing masters."""
from pathlib import Path
from functools import lru_cache
import pandas as pd
from openpyxl import load_workbook

ALIASES={'รหัสสินค้า':'Product Code','ชื่อลูกค้า':'Pack Customer','Spec .สินค้า':'Pack Spec','จำนวนบรรจุต่อกล่อง':'Pcs/Box','กลุ่มงาน':'Pack Category'}
PAIRS=[('กล่องนอก','จำนวน'),('กล่องใน','จำนวน.1'),('ไส้ใน','จำนวน.2'),('ตราสินค้า','จำนวน.3'),('แผนรอง 1','จำนวน.4'),('แผนรอง 2','จำนวน.5'),('แผนรอง 3','จำนวน.6'),('บู๊ซ 1','จำนวน.7'),('บู๊ซ 2','จำนวน.8'),('บู๊ซ 3','จำนวน.9'),('บู๊ซ 4','จำนวน.10'),('ใบรับประกัน','จำนวน.11'),('คู่มือการใช้งาน','จำนวน.12'),('อื่น ๆ','จำนวน.13')]

def resolve_source(root,central):
    root,central=Path(root),Path(central)
    canonical=central/'Packaging-Standard-LATEST.xlsx'
    if canonical.exists():return canonical
    candidates=[base/'1.มาตรฐานการบรรจุ-1.xlsx' for base in [central,root/'company_data',root/'apps'/'daily',root]]
    hits=list(dict.fromkeys(p.resolve() for p in candidates if p.is_file()))
    if len(hits)>1:raise ValueError('Multiple original packaging sources found; select the approved one in Source Upload: '+', '.join(map(str,hits)))
    return hits[0] if hits else None

@lru_cache(maxsize=4)
def _read(path,size,mtime):
    book=load_workbook(path,read_only=True,data_only=True)
    try:
        sheet=next((s for s in book.sheetnames if s.strip()=='มาตรฐานการบรรจุ'),None)
        if sheet:
            ws=book[sheet];ws.reset_dimensions()
            headers=None;rows=[];header_row=None
            for rownum,row in enumerate(ws.iter_rows(values_only=True),1):
                if headers is None:
                    if rownum>15:raise ValueError('Packaging header was not found in the first 15 rows.')
                    texts=[str(v).strip() if v is not None else '' for v in row]
                    if 'รหัสสินค้า' not in texts or 'จำนวนบรรจุต่อกล่อง' not in texts:continue
                    counts={};headers=[]
                    for i,h in enumerate(texts):
                        h=h or f'Unnamed: {i}';n=counts.get(h,0);counts[h]=n+1;headers.append(h if n==0 else f'{h}.{n}')
                    key=headers.index('รหัสสินค้า');header_row=rownum;continue
                value=row[key] if key<len(row) else None
                if value is None or str(value).strip().lower() in {'','nan','none','#n/a','0','-'}:continue
                rows.append(list(row[:len(headers)])+[None]*max(0,len(headers)-len(row)))
            if headers is None:raise ValueError('No product/packing headers found.')
            frame=pd.DataFrame(rows,columns=headers)
            frame.attrs.update(source_sheet=sheet,header_row=header_row,source_path=path)
            return {'Packaging standard':frame,'มาตรฐานการบรรจุ':frame}
    finally:book.close()
    out={};xls=pd.ExcelFile(path)
    for sh in xls.sheet_names:
        norm=sh.strip().lower()
        if norm in {'packaging standard','per piece','usage','final report','dashboard','ยอดจองคงเหลือ'}:
            header=1 if norm in {'packaging standard','per piece'} else (3 if norm=='usage' else (2 if norm=='final report' else 0))
            out[{'usage':'Usage','packaging standard':'Packaging standard'}.get(norm,sh.strip())]=pd.read_excel(xls,sheet_name=sh,header=header)
    if 'Packaging standard' not in out:raise ValueError('Uploaded workbook has no supported packaging standard sheet: '+', '.join(xls.sheet_names))
    return out

def read_tables(path):
    p=Path(path);stat=p.stat()
    return {k:v.copy() for k,v in _read(str(p.resolve()),stat.st_size,stat.st_mtime_ns).items()}

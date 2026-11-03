"""Fast, traceable Production WIP reader using each uploaded workbook's second sheet.

The second worksheet summary is the report source. Detail tabs are not re-aggregated
for WIP totals, so the application cannot invent an extra category from blank detail rows.
The reported "ยังไม่ปิด" count and GW (Kg) are shown as supplied; Total minus Closed is
retained as a validation check and never silently substituted when the values conflict.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook

CATEGORIES={"P","R","S","T","M","PB"}

def _text(v): return str(v or '').replace('\xa0',' ').strip()
def _num(v):
    try:
        if v is None or _text(v).upper() in {'','#N/A','#VALUE!','#REF!','NAN'}: return None
        return float(str(v).replace(',',''))
    except (TypeError,ValueError): return None
def _cat(v):
    raw=_text(v).upper()
    if raw=='F': return 'P'
    return raw if raw in CATEGORIES else f'OTHER ({raw})'

def _find_headers(ws):
    for hr in range(1,6):
        vals=next(ws.iter_rows(min_row=hr,max_row=hr,values_only=True),())
        labels={_text(v).casefold():i+1 for i,v in enumerate(vals) if v is not None}
        def col(pred): return next((c for label,c in labels.items() if pred(label)),None)
        group=col(lambda x:x in {'group','category','product category','กลุ่ม','ประเภทสินค้า'})
        total=col(lambda x:'ใบสั่งผลิตทั้งหมด' in x or x in {'total wo','total work orders','total orders'})
        opened=col(lambda x:'ยังไม่ปิด' in x or x in {'open wo','open work orders','open orders'})
        weight=col(lambda x:('gw' in x and 'kg' in x) or x in {'open kg','open weight kg'})
        closed=col(lambda x:'ปิดใบสั่ง' in x or x in {'closed wo','closed work orders','closed orders'})
        if all((group,total,opened,weight,closed)):
            return hr,group,total,opened,weight,closed
    return None

def read_production_wip(path, section='', metadata=None):
    """Read summary rows from worksheet 2; retain workbook/sheet/cell provenance."""
    path=Path(path); meta=metadata or {}
    wb=load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        if len(wb.worksheets)<2: raise ValueError('Production WIP workbook has no second-sheet summary.')
        ws=wb.worksheets[1]
        found=_find_headers(ws)
        if not found: raise ValueError(f'Second sheet "{ws.title}" has no recognizable WIP summary columns.')
        hr,gc,tc,oc,wc,cc=found
        out=[]; grand=None; category_sum={k:0.0 for k in ('Total WO','Open WO','Open kg','Closed WO')}
        maxrow=min(ws.max_row or hr+35,hr+60)
        for rn,values in enumerate(ws.iter_rows(min_row=hr+1,max_row=maxrow,max_col=max(gc,tc,oc,wc,cc),values_only=True),hr+1):
            raw=values[gc-1] if len(values)>=gc else None
            vals=[values[i-1] if len(values)>=i else None for i in (tc,oc,wc,cc)]
            parsed=[_num(v) for v in vals]
            if not _text(raw):
                if out and any(v is not None for v in parsed):
                    grand={'Total WO':parsed[0],'Open WO':parsed[1],'Open kg':parsed[2],'Closed WO':parsed[3],'Summary row':rn}
                    break  # first summary grand total ends the authoritative category block
                if out:
                    break  # blank separator ends the first summary block; later mini-tables are history
                continue
            if _text(raw).casefold() in {'group','category','product category','กลุ่ม','ประเภทสินค้า'}:
                if out: break
                continue
            cat=_cat(raw)
            if cat.startswith('OTHER (') and cat=='OTHER ()': continue
            total,opened,kg,closed=parsed
            calculated=(total-closed) if total is not None and closed is not None else None
            balance=(total-opened-closed) if None not in (total,opened,closed) else None
            variance=(calculated-opened) if None not in (calculated,opened) else None
            check='Summary matches detail' if variance is not None and abs(variance)<0.001 else (f'CHECK SUMMARY: reported open {opened:g}; Total − Closed {calculated:g}' if variance is not None else 'CHECK: summary count fields incomplete')
            ref=f"{ws.title}!{__import__('openpyxl').utils.get_column_letter(gc)}{rn}:{__import__('openpyxl').utils.get_column_letter(cc)}{rn}"
            out.append({'Section':section,'Category':cat,'Total WO':total,'Open WO':opened,'Closed WO':closed,'Open kg':kg,'Open t':kg/1000 if kg is not None else None,
                'WIP WOs (source open)':opened,'Open WIP WO (Total − Closed)':calculated,'WO Balance Error':balance,'Summary Open WO':opened,'Summary Open kg':kg,'Summary Closed WO':closed,
                'Summary row':rn,'Summary source cells':ref,'Summary variance / check':check,'Summary grand-total source cells':'','Summary grand total open kg':None,'Summary grand total open WOs':None,'Summary grand-total check':'',
                'Workbook section title':ws.title,'Workbook month title':'','Section title mismatch':False,'Section title check':'Section assignment comes from source manager / file name',
                'Unknown status rows':0,'Weight error rows':0,'Duplicate WO records':0,'Unmapped category source value(s)':'',
                'Detail source rows':'','Source sheet':ws.title,'Source evidence':ref,'Data basis':'Second worksheet WIP summary; reported open WO and GW (Kg)',
                'Monthly last movement day':None})
            for k,v in zip(('Total WO','Open WO','Open kg','Closed WO'),parsed):
                if v is not None:category_sum[k]+=v
        if not out: raise ValueError(f'No product-category summary rows found on second sheet "{ws.title}".')
        if grand:
            issues=[]
            for k in ('Total WO','Open WO','Open kg','Closed WO'):
                if grand[k] is not None and abs(category_sum[k]-grand[k])>(.01 if k=='Open kg' else .001):issues.append(f'{k}: group sum {category_sum[k]:g}; sheet total {grand[k]:g}')
            for row in out:
                row['Summary grand-total source cells']=f"{ws.title}!A{grand['Summary row']}:{__import__('openpyxl').utils.get_column_letter(cc)}{grand['Summary row']}"
                row['Summary grand total open kg']=grand['Open kg'];row['Summary grand total open WOs']=grand['Open WO']
                row['Summary grand-total check']='; '.join(issues) if issues else 'Summary grand total matches category rows'
        result=pd.DataFrame(out)
        result['Source']=str(path.resolve());result['Original filename']=meta.get('original_name') or meta.get('original_filename') or path.name
        result['Uploaded at']=meta.get('registered_at') or meta.get('uploaded_at') or 'Not recorded'
        return result
    finally: wb.close()

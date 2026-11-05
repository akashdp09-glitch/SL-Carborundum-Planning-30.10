"""Read the active capacity workbook's route lead times with exact cells/hash."""
import hashlib,io,re
from functools import lru_cache
from pathlib import Path
from openpyxl import load_workbook
import pandas as pd

PROCESSES=['Preparation','Mixing','Forming','Oven','Resin Firing','Vitrified Firing','Screening','Grinding','QC','Grinding/Packing']

@lru_cache(maxsize=3)
def _parse(data,name):
    wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True)
    try:
        ws=wb['Lead Time'];out={}
        for c in range(2,8):
            group=str(ws.cell(2,c).value or '').replace('กลุ่ม','').strip().upper()
            if group not in {'S','T','P','R','PB','M'}:raise ValueError('Unrecognized capacity Lead Time group at '+ws.cell(2,c).coordinate)
            profile={};cells=[]
            for r,process in enumerate(PROCESSES,3):
                raw=str(ws.cell(r,c).value or '').strip();nums=re.findall(r'\d+(?:\.\d+)?',raw)
                value=None if 'ไม่ผ่าน' in raw else float(nums[0]) if len(nums)==1 else raw if nums else None
                profile[process]=value;cells.append(f'{ws.cell(r,c).coordinate}={raw}')
            for required in ['Preparation','Mixing','Forming']:
                if not isinstance(profile[required],(int,float)):raise ValueError('Missing numeric '+required+' lead for '+group)
            profile['_Source']=f"{name} / Lead Time / "+'; '.join(cells)+'; SHA256 '+hashlib.sha256(data).hexdigest()
            out[group]=profile
        return out
    finally:wb.close()


def profiles(path):
    p=Path(path)
    return _parse(p.read_bytes(),p.name)


def attach(frame,path):
    out=frame.copy();rules=profiles(path)
    if 'Category' not in out:raise ValueError('Product category is required before scheduling')
    cats=out['Category'].fillna('').astype(str).str.strip().str.upper()
    active=~out.get('Overall Closed',pd.Series(False,index=out.index)).fillna(False).astype(bool)
    if 'Work Order' in out:active &= out['Work Order'].fillna('').astype(str).str.strip().ne('')
    unknown=sorted(set(cats[active])-set(rules))
    if unknown:raise ValueError('Map product category before scheduling; no capacity lead rule for '+', '.join(unknown))
    out['_Capacity Lead Profile']=[dict(rules[c]) if c in rules else None for c in cats]
    return out

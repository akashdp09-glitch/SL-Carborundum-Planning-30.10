"""Explicit Excel-date decoding and controlled two-layer WO identity."""
from datetime import date,datetime,timedelta
from numbers import Real
import re
import pandas as pd

def parse_date(value):
    if value is None:return None
    try:
        if pd.isna(value):return None
    except (ValueError,TypeError):return None
    if isinstance(value,pd.Timestamp):
        if value.year==1970 and 20000<=value.value<=80000:return parse_date(float(value.value))
        d=value.date()
    elif isinstance(value,(datetime,date)):d=value.date() if isinstance(value,datetime) else value
    elif isinstance(value,Real):
        if not 20000<=float(value)<=80000:return None
        d=(datetime(1899,12,30)+timedelta(days=float(value))).date()
    else:
        text=str(value).strip()
        if not text or text.lower() in {'nan','none','nat','0'}:return None
        if re.fullmatch(r'\d+(?:\.\d+)?',text):return parse_date(float(text))
        match=re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](25\d{2})(.*)$',text)
        if match:text=f'{match[1]}/{match[2]}/{int(match[3])-543}{match[4]}'
        parsed=pd.to_datetime(text,errors='coerce',dayfirst=not bool(re.match(r'^\d{4}-',text)))
        if pd.isna(parsed):return None
        d=parsed.date()
    return d if 2020<=d.year<=2100 else None

def normalize_wo(value):
    return re.sub(r'\s+','',str(value or '')).upper().replace('／','/')

def joined_parts(value):
    text=normalize_wo(value);match=re.fullmatch(r'(.*)A/B(-.+)',text)
    return (match[1]+'A'+match[2],match[1]+'B'+match[2]) if match else ()

def resolve_wo(value,mapping):
    key=normalize_wo(value);normalized={normalize_wo(k):v for k,v in mapping.items()}
    if key in normalized:return normalized[key],()
    parts=joined_parts(key)
    if not parts or not all(p in normalized for p in parts):return None,parts
    row=normalized[parts[0]].copy();row['Work Order']=key;row['Layer Work Orders']='; '.join(parts)
    dates=[parse_date(normalized[p].get('Due Date')) for p in parts];dates=[d for d in dates if d]
    if dates:row['Due Date']=min(dates)
    return row,parts

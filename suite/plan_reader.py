"""Plan-2026 reader (sheet 'แผนการเผา'): fixed column-letter map, verified 2026-10-03 against Plan_2026-2-Update-021026.xlsx.
Reads by POSITION (not header text) because several headers are '#VALUE!'/'#REF!'. Cached to a pickle keyed by file size+mtime."""
from __future__ import annotations
import datetime as dt, hashlib, os, pickle, re
from pathlib import Path
import openpyxl, pandas as pd
from openpyxl.utils import column_index_from_string as CI

SHEET = 'แผนการเผา'
HEADER_ROW, FIRST_ROW = 3, 4
LAST_COL = 'IB'
BASE = {'wo':'A','order_date':'B','wh_due':'C','po':'D','new_due':'E','customer':'F','spec':'H','brand':'I','qty':'J',
        'prod_code':'K','real_spec':'L','dia':'M','thick':'N','hole':'O','bond':'P','shape':'BW','mills':'BY','cuts_per_block':'CP',
        'piece_g':'CQ','mix_bond_g':'BE','status':'FB','prod_closed':'FC','akash_closed':'IA','sales_due':'IB','machine':'BA','program':'BB',
        'remark':'FD','ncr':'FF','reject':'FH','wh_actual':'EV','wh_qty':'EZ','wh_weight':'FA'}
MATERIAL_PAIRS = [('R','S'),('T','U'),('V','W'),('X','Y'),('Z','AA')]   # (material code, grams for the WO)
# section blocks: plan date, plan qty, done qty, closure flag, actual date
SECTIONS = {
 'Preparation':dict(plan='CR',plan_qty='CW',done='CX',closed='CY',actual='CV'),
 'Mixing':     dict(plan='DB',plan_qty='DF',done='DG',closed='DH',actual='DE'),
 'Forming':    dict(plan='DK',plan_qty='DP',done='DQ',closed='DR',actual='DO'),
 'Firing':     dict(plan='DU',plan_qty='DZ',done='EA',closed='EC',actual='DX',in_date='EB'),
 'Grinding':   dict(plan='EF',plan_qty='EJ',done='EK',closed='EL',actual='EI'),
 'Packing':    dict(plan='EO',plan_qty='ES',done='ET',closed='EU',actual='ER'),
}
ORDER = list(SECTIONS)
CLOSED, NOT_CLOSED = 'ปิดใบสั่ง', 'ยังไม่ปิด'

def norm_wo(s) -> str:
    """P005-110826 / p005110826 / 'P005 110826' -> P005-110826 (canonical). Unknown shapes -> upper-case alnum."""
    t = re.sub(r'[^A-Za-z0-9]', '', str(s or '')).upper()
    m = re.fullmatch(r'(P[BSTRM]?|PS|PB|SD)(\d{3})(\d{6})', t)
    return f'{m.group(1)}{m.group(2)}-{m.group(3)}' if m else t

def _num(v):
    try:
        f = float(v); return 0.0 if f != f else f
    except Exception: return 0.0

def _date(v):
    if isinstance(v, dt.datetime): return v.date()
    if isinstance(v, dt.date): return v
    if isinstance(v, str):
        m = re.fullmatch(r'\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*', v)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3)); y = y-543 if y > 2400 else y
            try: return dt.date(y, mo, d)
            except ValueError: return None
    return None

def _master_sheet(wb, path):
    """The sheet whose HEADER says it is the master plan (not whichever is first). Known names are only a fast path and are verified."""
    from .sheet_roles import classify_sheet, MASTER_PLAN
    for name in (SHEET, 'Plan2026'):
        if name in wb.sheetnames and classify_sheet(wb[name]).role == MASTER_PLAN:
            return wb[name]
    for ws in wb.worksheets:
        if classify_sheet(ws).role == MASTER_PLAN:
            return ws
    raise ValueError(f'{Path(path).name}: no sheet with the master-plan header (ProductionCode / กำหนดเข้าคลัง / กำหนดส่งใหม่). Sheets: {wb.sheetnames}')

def load_plan(path, cache_dir=None, force=False) -> pd.DataFrame:
    path = Path(path); st = path.stat()
    key = hashlib.md5(f'v2|{path.name}{st.st_size}{int(st.st_mtime)}'.encode()).hexdigest()[:12]
    cache = (Path(cache_dir) if cache_dir else path.parent) / f'.plancache_{key}.pkl'
    if cache.exists() and not force:
        try: return pickle.loads(cache.read_bytes())
        except Exception: pass
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = _master_sheet(wb, path)
    want = dict(BASE)
    for n,(a,b) in enumerate(MATERIAL_PAIRS,1): want[f'mat{n}']=a; want[f'mat{n}_g']=b
    for s,d in SECTIONS.items():
        for k,c in d.items(): want[f'{s}.{k}']=c
    idx = {k: CI(c)-1 for k,c in want.items()}
    rows = []
    for r in ws.iter_rows(min_row=FIRST_ROW, max_col=CI(LAST_COL), values_only=True):
        if not r or not r[0]: continue
        r = tuple(r) + (None,)*(CI(LAST_COL)-len(r))
        rows.append({k: r[i] for k,i in idx.items()})
    wb.close()
    df = pd.DataFrame(rows)
    df['wo'] = df['wo'].map(norm_wo)
    for c in ['wh_due','new_due','sales_due','order_date','wh_actual']: df[c] = df[c].map(_date)
    df['due'] = [n or w for n,w in zip(df['new_due'], df['wh_due'])]
    for c in ['qty','mix_bond_g','mills','piece_g','cuts_per_block','wh_qty','wh_weight']+[f'mat{n}_g' for n in range(1,6)]: df[c] = df[c].map(_num)
    for s in ORDER:
        for k in ('plan_qty','done'): df[f'{s}.{k}'] = df[f'{s}.{k}'].map(_num)
        for k in ('plan','actual','in_date'):
            if f'{s}.{k}' in df: df[f'{s}.{k}'] = df[f'{s}.{k}'].map(_date)
        df[f'{s}.closed'] = df[f'{s}.closed'].map(lambda v: str(v).strip() == CLOSED)
    from .closure_rules import is_closed_text
    df['fc_closed'] = df['prod_closed'].map(is_closed_text)
    df['whole_closed'] = df['fc_closed'] | df['Packing.closed']       # approved rule: EU (Packing) OR FC; earlier sections never close the WO
    df['open'] = ~df['whole_closed']
    def cur(row):
        for s in ORDER:
            if not row[f'{s}.closed']: return s
        return 'Done'
    df['current_section'] = df.apply(cur, axis=1)
    df['bond'] = df['bond'].map(lambda v: str(v or '').strip())
    for c in ('customer','spec','brand','status','remark'): df[c] = df[c].map(lambda v: '' if v is None else str(v))
    try: cache.write_bytes(pickle.dumps(df))
    except Exception: pass
    return df

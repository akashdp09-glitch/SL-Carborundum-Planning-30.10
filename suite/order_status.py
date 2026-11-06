"""Explicit whole-order decisions, separate from section completion and packed actuals."""
from pathlib import Path
import json,sqlite3,uuid
import pandas as pd
from .common import bkk_now


def history(db_path):
    if not Path(db_path).exists():return pd.DataFrame()
    with sqlite3.connect(db_path,timeout=15) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='wo_status_events'").fetchone():return pd.DataFrame()
        return pd.read_sql_query('SELECT * FROM wo_status_events ORDER BY id DESC',c)


def revision(db_path):
    if not Path(db_path).exists():return 0
    with sqlite3.connect(db_path,timeout=15) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='wo_status_events'").fetchone():return 0
        return c.execute('SELECT COALESCE(MAX(id),0) FROM wo_status_events').fetchone()[0]


def save(db_path,wo,status,reason,user,submission_id,source='Shared scanner / whole WO'):
    if status not in {'OPEN','CLOSED'} or not reason.strip() or not user.strip() or not submission_id:raise ValueError('Whole WO status needs OPEN/CLOSED, reason, identified user and submission ID')
    with sqlite3.connect(db_path,timeout=15) as c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute('SELECT wo_id,source_file,imported_at FROM work_orders WHERE wo_id=?',(wo,)).fetchone()
        if not r:raise ValueError('Confirm the exact work order first')
        c.execute('''CREATE TABLE IF NOT EXISTS wo_status_events(id INTEGER PRIMARY KEY,submission_id TEXT UNIQUE NOT NULL,wo TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,user TEXT NOT NULL,recorded_at TEXT NOT NULL,source TEXT NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS ix_wo_status_wo ON wo_status_events(wo,id DESC)')
        old=c.execute('SELECT wo,status,reason,user,id FROM wo_status_events WHERE submission_id=?',(submission_id,)).fetchone()
        fields=(wo,status,reason.strip(),user.strip())
        if old:
            if old[:4]!=fields:raise ValueError('Submission ID already used with different data')
            return old[4]
        ref=f'{source}; Plan source={r[1] or "not recorded"}; imported={r[2] or "not recorded"}'
        cur=c.execute('INSERT INTO wo_status_events(submission_id,wo,status,reason,user,recorded_at,source) VALUES(?,?,?,?,?,?,?)',(submission_id,*fields,bkk_now().isoformat(timespec='seconds'),ref))
        return cur.lastrowid


def apply_frame(frame,db_path):
    out=frame.copy();h=history(db_path)
    if out.empty or h.empty:return out
    col=next((x for x in ('Work Order','wo','ProductionCode') if x in out),None)
    if not col:return out
    from .wo_lookup import norm_wo
    latest=h.drop_duplicates('wo').copy();latest['_key']=latest.wo.map(norm_wo);latest=latest.drop_duplicates('_key').set_index('_key')
    keys=out[col].map(norm_wo);status=keys.map(latest.status);mask=status.notna();closed=status.eq('CLOSED')
    out['Manual Whole WO status']=status
    out['Manual status reason']=keys.map(latest.reason)
    out['Manual status user']=keys.map(latest.user)
    for name in ['Overall Closed','Authoritative Closed','whole_closed']:
        if name in out:out.loc[mask,name]=closed[mask]
    if 'open' in out:out.loc[mask,'open']=~closed[mask]
    # Quantities, confirmed actuals and section closures are deliberately preserved.
    return out

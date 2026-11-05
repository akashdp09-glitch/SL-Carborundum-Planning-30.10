"""Append-only confirmed drying evidence, shared by Daily and Firing planners."""
from __future__ import annotations
import datetime as dt
import math
from pathlib import Path
import sqlite3
import uuid
import pandas as pd
from .common import bkk_now,bkk_today


def save(db_path,wo,qty,completed,source,reason,user,submission_id=None):
    completed=pd.Timestamp(completed).date()
    if completed>bkk_today():raise ValueError('Actual drying completion cannot be in the future')
    qty=float(qty)
    if not math.isfinite(qty) or qty<=0:raise ValueError('Confirmed ready pieces must be positive')
    if not str(source).strip() or not str(reason).strip() or not str(user).strip():raise ValueError('Source evidence, reason and identified user are required')
    with sqlite3.connect(db_path,timeout=15) as con:
        row=con.execute('SELECT wo_id,imported_at FROM work_orders WHERE wo_id=?',(wo,)).fetchone()
        if not row:raise ValueError('Confirm an existing exact work order first')
        con.execute('''CREATE TABLE IF NOT EXISTS drying_confirmations(
            id INTEGER PRIMARY KEY, submission_id TEXT UNIQUE NOT NULL, wo TEXT NOT NULL,
            qty REAL NOT NULL, completed TEXT NOT NULL, source TEXT NOT NULL, reason TEXT NOT NULL,
            user TEXT NOT NULL, recorded_at TEXT NOT NULL, wo_revision TEXT)''')
        con.execute('CREATE INDEX IF NOT EXISTS ix_drying_confirm_wo ON drying_confirmations(wo,id DESC)')
        sid=submission_id or uuid.uuid4().hex
        fields=(wo,qty,completed.isoformat(),source.strip(),reason.strip(),user.strip())
        existing=con.execute('SELECT wo,qty,completed,source,reason,user FROM drying_confirmations WHERE submission_id=?',(sid,)).fetchone()
        if existing and existing!=fields:raise ValueError('Submission ID already used with different evidence')
        con.execute('INSERT OR IGNORE INTO drying_confirmations(submission_id,wo,qty,completed,source,reason,user,recorded_at,wo_revision) VALUES(?,?,?,?,?,?,?,?,?)',(sid,*fields,bkk_now().isoformat(timespec='seconds'),row[1]))
    return sid


def history(db_path):
    if not Path(db_path).exists():return pd.DataFrame()
    with sqlite3.connect(db_path,timeout=15) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='drying_confirmations'").fetchone():return pd.DataFrame()
        return pd.read_sql_query('SELECT d.*, w.imported_at AS active_wo_revision FROM drying_confirmations d LEFT JOIN work_orders w ON w.wo_id=d.wo ORDER BY d.id DESC',con)


def apply(frame,db_path):
    out=frame.copy();h=history(db_path)
    if h.empty:return out
    latest=h.drop_duplicates('wo');latest=latest[latest.wo_revision.fillna('').eq(latest.active_wo_revision.fillna(''))]
    for name,column in [('Confirmed Drying Complete Date','completed'),('Confirmed Drying Qty','qty'),('Drying Confirmation Source','source')]:
        out[name]=out['Work Order'].astype(str).map(latest.set_index('wo')[column])
    return out


def render(st,db_path,*,can_edit=False,user=''):
    st.header('🌬️ ยืนยันการอบแห้ง / Confirm drying readiness')
    st.caption('เข้าเผา / formed WIP does not confirm drying completion. Record actual evidence and ready pieces; this does not add production or close a WO. A revised imported WO requires reconfirmation.')
    wo=st.text_input('Work Order / ใบสั่งผลิต',key='drying_confirm_wo')
    canonical=None
    if wo:
        from .scanner_lookup import exact_work_orders
        from .wo_lookup import norm_wo
        with sqlite3.connect(db_path) as con:
            con.row_factory=sqlite3.Row
            rows=exact_work_orders(con,wo) if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_orders'").fetchone() else []
        if len(rows)==1:
            canonical=rows[0]['wo_id'];st.success(canonical+' · '+str(rows[0]['product_code'] or ''))
        else:st.warning('Scan the full unique WO / กรุณาสแกนใบสั่งที่ตรงกันเพียงรายการเดียว')
    with st.form('drying_confirmation'):
        qty=st.number_input('Ready pieces / จำนวนที่อบเสร็จ',min_value=0.0,step=1.0)
        completed=st.date_input('Actual completion / วันที่อบเสร็จจริง',value=bkk_today(),max_value=bkk_today())
        source=st.text_input('Source document / หลักฐานอ้างอิง')
        reason=st.text_input('Reason / เหตุผลการยืนยันหรือแก้ไข')
        submit=st.form_submit_button('💾 Confirm / ยืนยัน',disabled=not(can_edit and canonical))
    if submit:
        try:
            import hashlib
            signature=hashlib.sha256(repr((canonical,qty,completed,source,reason,user)).encode()).hexdigest()
            request=st.session_state.setdefault('_drying_confirmation_requests',{})
            sid=save(db_path,canonical,qty,completed,source,reason,user,request.setdefault(signature,uuid.uuid4().hex))
            st.success('Saved / บันทึกแล้ว · '+sid)
        except Exception as exc:st.error(str(exc))
    h=history(db_path)
    if not h.empty:
        st.dataframe(h,use_container_width=True,hide_index=True)
        st.caption('Latest valid confirmation per WO is used; earlier confirmations remain in history. Quantity is a snapshot, not an additional production transaction.')

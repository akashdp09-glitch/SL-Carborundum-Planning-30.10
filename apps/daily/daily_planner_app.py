import pickle
import os
import re
import sys
from pathlib import Path
_ROOT=Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path: sys.path.insert(0,str(_ROOT))
from suite.central_paths import company_data as _company_data, resolve_file as _resolve_central, missing_plan_message as _missing_plan_message
from suite.backorder_views import overdue_backorders, overdue_month_category, overdue_backorder_totals, future_open_month_category, recent_open_closed_month_category
from suite.daily_capacity_view import capacity_validation as _capacity_validation_view, collapse_capacities as _collapse_capacities_view
from suite.common import bkk_today
from datetime import date, timedelta
from zoneinfo import ZoneInfo
import io, traceback, math, base64, json, hashlib, datetime, zipfile, html, sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from matplotlib import font_manager as fm
import streamlit as st
import sl_ppc_fast_store_v4_6 as store
import sl_mps_mrp_engine_v2_4 as lm
import integrated_daily_engine_v1_1 as eng
import daily_linear_engine_v1_1 as dl
import ppc_desktop_core_v1_9 as coremap
import lead_time_control_v1 as lt
import presentation_quality as pq
import daily_md_report as mdreport
import traceable_views as tv48
import production_wip_control as pw49
from date_and_wo_rules import parse_date, resolve_wo
import meeting_presentation as meeting52
import daily_job_control as jobs50
import source_sheet_review as ss48
import mixing_capacity_trace as mixcap
import packaging_standard_source as packing_source
import daily_snapshot as dailysnap

VERSION='V1.9.57 CONTENT SNAPSHOT GUARD'
APP_DIR=Path(__file__).resolve().parent

@st.cache_data(show_spinner=False, ttl=300)
def _shared_backorder_master(plan_path, mtime_ns, size):
    """Rebuild the Backorder-tab's Plan-2026 basis for dashboard parity.

    Daily scheduling uses a richer planning parser, while the shared Backorder
    page uses the v17 Plan-2026 parser. Keep the overdue KPI and graphs on that
    same full-WO source so a dashboard subset cannot silently undercount.
    """
    from suite.closure_rules import is_closed_text
    import sl_daily_engine_v3_22_from_v17 as shared_engine
    path=Path(plan_path); blob=path.read_bytes()
    master,_,_=shared_engine.read_plan2026(io.BytesIO(blob),{})
    raw=pd.read_excel(io.BytesIO(blob),sheet_name='แผนการเผา',header=2,usecols='A:IA')
    if 'Work Order' not in master or 'ProductionCode' not in raw:
        return pd.DataFrame()
    raw=raw.drop_duplicates('ProductionCode',keep='last').copy()
    raw['_wo_key']=raw['ProductionCode'].fillna('').astype(str).str.strip().str.upper()
    raw=raw.set_index('_wo_key')
    keys=master['Work Order'].fillna('').astype(str).str.strip().str.upper()
    def mapped(col, fallback=None):
        return keys.map(raw[col]) if col in raw.columns else fallback
    # Match the central Home / Backorder parser: revised date (E), then initial (C).
    initial=mapped('กำหนดเข้าคลัง')
    revised=mapped('กำหนดส่งใหม่')
    master['Due Date']=pd.to_datetime(revised,errors='coerce').combine_first(pd.to_datetime(initial,errors='coerce'))
    for target,source in [('Product Category','ประเภทสินค้า'),('Customer Thai','Customername'),('Product Code','รหัสสินค้า'),('Specification','Specification')]:
        vals=mapped(source)
        if vals is not None: master[target]=vals.values
    # Whole-order closure only: Packing (EU, source column 150) or final (FC, 158).
    # Section fields such as preparation/mixing never close the whole work order.
    closed=[]
    for pos in (150,158):
        if raw.shape[1]>pos:
            vals=keys.map(raw.iloc[:,pos])
            closed.append(vals.map(is_closed_text).fillna(False).to_numpy())
    master['Authoritative Closed']=np.logical_or.reduce(closed) if closed else False
    oq=pd.to_numeric(master.get('Order Qty',0),errors='coerce')
    if not isinstance(oq,pd.Series): oq=pd.Series(float(oq or 0),index=master.index)
    packed=pd.to_numeric(master.get('Packing Actual Qty',master.get('Packing Actual',0)),errors='coerce')
    if not isinstance(packed,pd.Series): packed=pd.Series(float(packed or 0),index=master.index)
    master['pcs']=(oq.fillna(0)-packed.fillna(0)).clip(lower=0)
    if 'Plan2026 kg/pc' in master:
        master['ton']=master['pcs']*pd.to_numeric(master['Plan2026 kg/pc'],errors='coerce').fillna(0)/1000
    return master


def _active_backorder_master(fallback=None):
    """Load the shared Home/Backorder Plan-2026 view, cached by file revision."""
    p=Path(str(st.session_state.get('plan_path') or ''))
    if not p.is_file(): return fallback if isinstance(fallback,pd.DataFrame) else pd.DataFrame()
    try:
        return _shared_backorder_master(str(p.resolve()),p.stat().st_mtime_ns,p.stat().st_size)
    except Exception as exc:
        st.warning(f'Backorder source parity could not be verified; showing the saved Daily Planner master. Source parse: {exc}')
        return fallback if isinstance(fallback,pd.DataFrame) else pd.DataFrame()
st.set_page_config(page_title=f'SL Daily Planner {VERSION}',layout='wide',page_icon=str(APP_DIR/'SL_DAILY_PLANNER_ICON.png') if (APP_DIR/'SL_DAILY_PLANNER_ICON.png').exists() else '🏭')

def _persistent_data_editor(data, *args, **kwargs):
    """Keep an editable table draft when navigating away and back in this app session."""
    from suite.navigation_state import restore_editor_draft as _restore_editor_draft, save_editor_draft as _save_editor_draft
    key = kwargs.get("key")
    source = data.copy(deep=True) if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    seed = _restore_editor_draft(st.session_state, str(key), source) if key is not None else None
    edited = st.data_editor(seed if seed is not None else data, *args, **kwargs)
    if key is not None and isinstance(edited, pd.DataFrame):
        _save_editor_draft(st.session_state, str(key), source, edited)
    return edited

from suite.navigation_state import preserve_navigation_values as _preserve_navigation_values
_preserve_navigation_values(st.session_state)

try:
    from suite.hub_auth import validate as _validate_hub_ticket
    _hub_identity=_validate_hub_ticket(_company_data(),st.query_params.get('hub_ticket',''))
    if _hub_identity:
        st.session_state['sl_user']=_hub_identity['username']
        st.session_state['sl_role']=_hub_identity['role']
        st.session_state['sl_authenticated']=True
except Exception:
    pass

st.markdown("""<style>
div[data-testid="stDataFrame"] {width:100% !important;}
div[data-testid="stDataFrame"] [role="columnheader"],
div[data-testid="stDataFrame"] [role="gridcell"] {white-space:normal !important;line-height:1.2 !important;}
</style>""",unsafe_allow_html=True)

st.markdown('''<style>
.block-container{padding-top:1.2rem}.stMetric{background:#f7f9fc;border:1px solid #e5e7eb;border-radius:14px;padding:10px}
/* V1.9.30: real sidebar navigation; no horizontal tab strip */
div[data-testid="stExpander"]{border-radius:12px}.small-note{font-size:.86rem;color:#596273}
div[data-baseweb="tab-list"]{gap:10px;flex-wrap:wrap!important;}
div[data-baseweb="tab"]{font-size:1.02rem!important;font-weight:800!important;min-height:58px!important;padding:8px 13px!important;border-radius:13px!important;background:#f1f5f9!important;border:1px solid #d7dee8!important;}
div[data-baseweb="tab"][aria-selected="true"]{background:#dbeafe!important;border:2px solid #60a5fa!important;}
div[data-testid="stMetric"]{background:linear-gradient(135deg,#ffffff,#eef6ff)!important;box-shadow:0 2px 8px rgba(0,0,0,.07)!important;}
h1,h2,h3{letter-spacing:.1px}.stAlert{border-radius:14px!important;}
</style>''',unsafe_allow_html=True)
st.markdown("""<style>
/* V1.9.32 animated industrial control-center UI */
@keyframes ppcGlow{0%,100%{box-shadow:0 0 0 rgba(30,136,229,0)}50%{box-shadow:0 0 22px rgba(30,136,229,.20)}}
@keyframes ppcTicker{0%{transform:translateX(100%)}100%{transform:translateX(-100%)}}
@keyframes ppcEnter{from{opacity:.25;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.block-container{max-width:100%!important;padding-left:1.5rem!important;padding-right:1.5rem!important}
div[data-testid="stMetric"]{min-height:112px!important;padding:16px!important;animation:ppcEnter .45s ease-out,ppcGlow 4s ease-in-out infinite}
div[data-testid="stMetricValue"]{font-size:2.05rem!important;font-weight:850!important}
div[data-testid="stPlotlyChart"]{background:white;border:1px solid #e2e8f0;border-radius:18px;padding:10px 12px;margin:12px 0 26px 0;box-shadow:0 6px 18px rgba(15,23,42,.07);animation:ppcEnter .5s ease-out}
.ppc-ticker{overflow:hidden;white-space:nowrap;border-radius:14px;padding:11px 0;background:linear-gradient(90deg,#0f172a,#1e3a5f,#0f172a);color:white;font-weight:750;margin:8px 0 18px 0}
.ppc-ticker span{display:inline-block;padding-left:100%;animation:ppcTicker 34s linear infinite}
.ppc-control-card{border:1px solid #dbe4ef;border-radius:18px;padding:14px;background:linear-gradient(135deg,#fff,#f4f8fc);box-shadow:0 5px 16px rgba(15,23,42,.06)}
div[data-testid="stSidebar"] div[role="radiogroup"] label{border:1px solid #d8e2ee;border-radius:15px;padding:11px 10px;margin:6px 0;background:#fff;font-size:1.02rem;font-weight:800}
div[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){border:2px solid #3b82f6;background:#eff6ff;animation:ppcGlow 3s ease-in-out infinite}
/* Horizontal page controls behave like large clickable tabs */
div[data-testid="stRadio"] div[role="radiogroup"]{gap:8px;flex-wrap:wrap!important}
div[data-testid="stRadio"] div[role="radiogroup"] label{border:1px solid #cbd5e1;border-radius:12px;padding:9px 13px;background:#f8fafc;font-weight:800}
div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked){background:#dbeafe;border:2px solid #3b82f6}
/* Keep chart titles/legends away from neighboring panels */
.js-plotly-plot .plotly .main-svg{overflow:visible!important}
</style>""",unsafe_allow_html=True)

# Top-positioned navigation placeholders; filled after source calculations.
_top_sidebar_nav=st.sidebar.container()
_top_page_nav=st.container()

# Display-only controls: no effect on plan calculations or source data.
with st.sidebar.expander('🔎 DISPLAY / การแสดงผล',expanded=True):
    _large_view=st.toggle('📺 Meeting / TV text (large) / ตัวอักษรใหญ่',value=False,key='sl_large_view')
    _english_first=st.toggle('English-first graph titles / ภาษาอังกฤษเป็นหลัก',value=True,key='sl_english_first')
    st.caption('All Plotly charts: scroll/pinch zoom, fullscreen, vector SVG and offline HTML.')
if _large_view:
    st.markdown('''<style>html{font-size:19px!important}div[data-testid="stMetricValue"]{font-size:2.45rem!important}
    .stButton button,.stDownloadButton button{font-size:1.12rem!important;min-height:48px!important}
    div[data-testid="stDataFrame"]{font-size:17px!important}
    h2{font-size:2rem!important}h3{font-size:1.55rem!important}</style>''',unsafe_allow_html=True)

st.title('🏭 SL PLANNING DEPARTMENT / แผนกวางแผน')
st.markdown("<div style='padding:10px 16px;margin:0 0 10px;border-left:5px solid #e76613;background:#fff6ed;border-radius:8px;color:#12395b'><b>Production plan</b>　·　Capacity　·　Material　·　Delivery risk　·　Recovery</div>",unsafe_allow_html=True)
from suite.customer_names import apply_customer_language as _cust_lang, language_font_css as _cust_font, read_ui_language as _ui_lang, bilingual_customer_name as _bilingual_customer, display_customer as _display_customer
_LANG=_ui_lang()
_hub_sources_url=st.query_params.get('hub_sources_url','')
if _hub_sources_url:
    st.markdown(f"<a href='{html.escape(str(_hub_sources_url),quote=True)}' target='_top' style='font-size:.78rem;color:#0057b8;text-decoration:underline'>↻ {'อัปเดตไฟล์ข้อมูล' if _LANG=='ไทย' else 'Update input files'}</a>",unsafe_allow_html=True)
def _retain_customer_source_cols(df):
    if not isinstance(df,pd.DataFrame) or df.empty:return df
    x=df.copy()
    _candidates=[c for c in ['Customer Thai','Customername','Customer Source','Customer'] if c in x.columns]
    if _candidates:
        _name=pd.Series('',index=x.index,dtype=object)
        for _c in _candidates:
            _v=x[_c].fillna('').astype(str).str.strip()
            _good=_v.str.lower().ne('') & ~_v.str.lower().isin({'n/a','na','nan','none'})
            _name=_name.where(_name.astype(str).str.strip().ne(''),_v.where(_good,''))
        if 'Customer Thai' not in x.columns:x['Customer Thai']=_name
        else:
            _old=x['Customer Thai'].fillna('').astype(str).str.strip()
            _good=_old.str.lower().ne('') & ~_old.str.lower().isin({'n/a','na','nan','none'})
            x['Customer Thai']=_old.where(_good,_name)
        if 'Customer English' not in x.columns:x['Customer English']=x['Customer Thai'].map(lambda v:_display_customer(v,'English'))
    return x
st.markdown(_cust_font(_LANG), unsafe_allow_html=True)
st.success('CONTROL LOGIC: Plan 2026 open demand is the base. Existing WIP pushes forward; due-date requirements pull upstream. Capacity is a hard daily gate in every section.')
st.caption('REPEATABLE RULE: every valid open WO and every planning day follows the same due-date → finite capacity → synchronization → balance sequence. Early completion is allowed when protected demand is covered and usable capacity remains.')
st.info('📌 FLOW / ขั้นตอน: ① Plan 2026 WIP in ALL processes → ② ALL executable sections start from selected date → ③ next-working-day process flow → ④ Firing Planner anchor → ⑤ controlled Curing/Oven time gate after Forming where applicable → Firing → QC → Grinding OR Cutting when required → Packing → ⑥ Capacity/WIP/MPS/MRP/Risk')



def _wo_class_table(master, firing_df=None):
    """Return one controlled WO classification row for dashboard use.

    Firing Planner WO-level TEST/NORMAL classification has priority.  When an
    older firing output has no work-type field, Product Code starting with 1
    defaults to TEST; code 4 is NOT automatically TEST.
    """
    md = master.copy() if isinstance(master, pd.DataFrame) else pd.DataFrame()
    if md.empty or 'Work Order' not in md.columns:
        return pd.DataFrame(columns=['Work Order','Order Type','Category'])

    out = pd.DataFrame()
    out['Work Order'] = md['Work Order'].fillna('').astype(str).str.strip()
    pc_col = next((c for c in ['Product Code','Product','Item Code'] if c in md.columns), None)
    if pc_col:
        pc = md[pc_col].fillna('').astype(str).str.strip().str.upper()
    else:
        pc = pd.Series('', index=md.index, dtype=str)

    cat_col = next((c for c in ['Category','Product Category','Type'] if c in md.columns), None)
    out['Category'] = md[cat_col].fillna('').astype(str).str.strip() if cat_col else pc.str[:1]
    out['Order Type'] = np.where(pc.str[:1].eq('1'), 'TEST', 'NORMAL')

    fd = firing_df.copy() if isinstance(firing_df, pd.DataFrame) else pd.DataFrame()
    if not fd.empty and 'Work Order' in fd.columns:
        type_col = next((c for c in ['Work Type / ประเภทงาน','Work Type','Test Work','Test Type'] if c in fd.columns), None)
        if type_col:
            fm = fd[['Work Order', type_col]].copy()
            fm['Work Order'] = fm['Work Order'].fillna('').astype(str).str.strip()
            v = fm[type_col].fillna('').astype(str).str.upper().str.strip()
            fm['_Order Type'] = np.where(
                v.str.contains('TEST|งานทดสอบ', regex=True), 'TEST',
                np.where(v.str.contains('NORMAL|SALE|งานปกติ', regex=True), 'NORMAL', '')
            )
            fm = fm[fm['Work Order'].ne('') & fm['_Order Type'].ne('')].drop_duplicates('Work Order', keep='last')
            if not fm.empty:
                mp = fm.set_index('Work Order')['_Order Type']
                ov = out['Work Order'].map(mp)
                out.loc[ov.notna(), 'Order Type'] = ov[ov.notna()]

    out = out[out['Work Order'].ne('')].drop_duplicates('Work Order', keep='last')
    out['Category'] = out['Category'].replace('', 'UNKNOWN')
    return out[['Work Order','Order Type','Category']]

def _tv_html_v1935(master,risk,plans,caps,stock,firing_df,from_d,to_d,logo_path=None,wip_df=None,snapshot_meta=None,source_refs=None,backorder_master=None):
    """TV control centre: defensive, colourful and execution-first.
    Missing optional fields must degrade to N/A rather than stop the dashboard.
    """
    import plotly.io as pio
    md=master.copy() if isinstance(master,pd.DataFrame) else pd.DataFrame()
    bo_md=backorder_master.copy() if isinstance(backorder_master,pd.DataFrame) and not backorder_master.empty else md
    md=_retain_customer_source_cols(md)
    rr=risk.copy() if isinstance(risk,pd.DataFrame) else pd.DataFrame()
    pp=plans.copy() if isinstance(plans,pd.DataFrame) else pd.DataFrame()
    cls=_wo_class_table(md,firing_df)
    if 'Work Order' in md.columns and 'Work Order' in rr.columns:
        # Risk calculations can carry empty placeholder customer fields. Always
        # recover the authoritative name from Plan-2026 by WO, then fill blanks.
        _display_fields=[c for c in ['Customer','Customer Thai','Customer English','Customername','Customer Source','Specification','Product Code'] if c in md.columns]
        if _display_fields:
            _display_master=md[['Work Order']+_display_fields].copy()
            _display_master['_wo_key']=_display_master['Work Order'].fillna('').astype(str).str.strip().str.upper()
            _display_master=_display_master.drop_duplicates('_wo_key',keep='last').set_index('_wo_key')
            _risk_key=rr['Work Order'].fillna('').astype(str).str.strip().str.upper()
            for _c in _display_fields:
                _authoritative=_risk_key.map(_display_master[_c])
                if _c not in rr.columns:
                    rr[_c]=_authoritative
                else:
                    _current=rr[_c]
                    _valid=_current.notna() & _current.astype(str).str.strip().str.lower().ne('') & ~_current.astype(str).str.strip().str.lower().isin({'n/a','na','nan','none'})
                    rr[_c]=_current.where(_valid,_authoritative)
        # Normalize alternate source-column names into the customer fields used
        # by the HTML report, without replacing a valid language-specific name.
        for _target,_sources in [('Customer Thai',['Customername','Customer Source','Customer']),('Customer',['Customer Thai','Customername','Customer Source']),('Customer English',['Customer','Customer Thai'])]:
            if _target not in rr.columns: rr[_target]=''
            _current=rr[_target]
            _valid=_current.notna() & _current.astype(str).str.strip().str.lower().ne('') & ~_current.astype(str).str.strip().str.lower().isin({'n/a','na','nan','none'})
            _fallback=pd.Series('',index=rr.index,dtype=object)
            for _source in _sources:
                if _source in rr.columns:
                    _sv=rr[_source]
                    _ok=_sv.notna() & _sv.astype(str).str.strip().str.lower().ne('') & ~_sv.astype(str).str.strip().str.lower().isin({'n/a','na','nan','none'})
                    _fallback=_fallback.where(_fallback.astype(str).str.strip().ne(''),_sv.where(_ok,''))
            rr[_target]=_current.where(_valid,_fallback)
    # Controlled classification enrichment.
    if not rr.empty:
        if 'Work Order' in rr.columns and not cls.empty:
            for _c in ['Order Type','Category']:
                if _c not in rr.columns and _c in cls.columns:
                    rr=rr.merge(cls[['Work Order',_c]].drop_duplicates('Work Order'),on='Work Order',how='left')
        if 'Order Type' not in rr.columns: rr['Order Type']='NORMAL'
        if 'Category' not in rr.columns: rr['Category']='UNKNOWN'
        rr['Order Type']=rr['Order Type'].fillna('NORMAL').astype(str).str.strip().replace('', 'NORMAL')
        rr['Category']=rr['Category'].fillna('UNKNOWN').astype(str).str.strip().replace('', 'UNKNOWN')
        rr['_due']=pd.to_datetime(rr['Due Date'],errors='coerce') if 'Due Date' in rr.columns else pd.NaT
        if hasattr(rr['_due'],'dt'): rr=rr[(rr['_due'].dt.date>=from_d)&(rr['_due'].dt.date<=to_d)].copy()
        rr['_qty']=pd.to_numeric(rr['Open Qty'],errors='coerce').fillna(0) if 'Open Qty' in rr.columns else 0
        rr['_risk']=rr['Delivery Risk'].fillna('').astype(str).str.upper() if 'Delivery Risk' in rr.columns else 'WATCH'
        rr=rr[rr['_risk'].isin(['HIGH','LATE','AT RISK','WATCH'])].copy()
        if 'Projected Finish' in rr.columns and 'Due Date' in rr.columns:
            _pf=pd.to_datetime(rr['Projected Finish'],errors='coerce'); _dd=pd.to_datetime(rr['Due Date'],errors='coerce')
            rr=rr[~(_pf.notna()&_dd.notna()&(_pf<=_dd))].copy()
    if not pp.empty:
        pp['_d']=pd.to_datetime(pp['Plan Date'],errors='coerce') if 'Plan Date' in pp.columns else pd.NaT
        if hasattr(pp['_d'],'dt'): pp=pp[(pp['_d'].dt.date>=from_d)&(pp['_d'].dt.date<=to_d)].copy()
        if 'Category' not in pp.columns: pp['Category']='UNKNOWN'
        pp['Category']=pp['Category'].fillna('UNKNOWN').astype(str).str.strip().replace('', 'UNKNOWN')
        if 'Plan Qty' not in pp.columns: pp['Plan Qty']=0
        pp['Plan Qty']=pd.to_numeric(pp['Plan Qty'],errors='coerce').fillna(0)

    # Today = dashboard window start; tomorrow = next working day (Sunday skipped).
    today=from_d; tomorrow=(pd.Timestamp(today)+pd.Timedelta(days=1)).date()
    while pd.Timestamp(tomorrow).weekday()==6: tomorrow=(pd.Timestamp(tomorrow)+pd.Timedelta(days=1)).date()
    def _day_targets(day):
        if pp.empty or '_d' not in pp.columns:return pd.DataFrame(columns=['Section','Plan Qty'])
        x=pp[pp['_d'].dt.date.eq(day)].copy()
        if x.empty:return pd.DataFrame(columns=['Section','Plan Qty'])
        return x.groupby('Section',as_index=False)['Plan Qty'].sum().sort_values('Plan Qty',ascending=False)
    td=_day_targets(today); tm=_day_targets(tomorrow)
    def _due_rows(day):
        if md.empty or 'Due Date' not in md.columns:return pd.DataFrame()
        x=md.copy(); x['_due']=pd.to_datetime(x['Due Date'],errors='coerce').dt.date
        closed=x['Overall Closed'].fillna(False).astype(bool) if 'Overall Closed' in x.columns else pd.Series(False,index=x.index)
        x=x[x['_due'].eq(day)&~closed].copy()
        if x.empty:return x
        oq=pd.to_numeric(x['Order Qty'],errors='coerce').fillna(0) if 'Order Qty' in x.columns else pd.Series(0,index=x.index)
        pa=pd.to_numeric(x['Packing Actual Qty'],errors='coerce').fillna(0) if 'Packing Actual Qty' in x.columns else (pd.to_numeric(x['Packing Actual'],errors='coerce').fillna(0) if 'Packing Actual' in x.columns else pd.Series(0,index=x.index))
        x['PCS']=pd.to_numeric(x['Remaining Packing'],errors='coerce').fillna(0) if 'Remaining Packing' in x.columns else (oq-pa).clip(lower=0)
        ag={'PCS':'max'}
        for c in ['Customer','Customer Thai','Customer English','Category','Specification','Due Date']:
            if c in x.columns:ag[c]='first'
        return x.groupby('Work Order',as_index=False).agg(ag) if 'Work Order' in x.columns else x
    due_today=_due_rows(today); due_tom=_due_rows(tomorrow)

    # Decorative logo intentionally omitted; this report uses text and vector charts for faster reruns.
    logo=''
    palette=['#2563EB','#16A34A','#DC2626','#7C3AED','#0891B2','#EAB308','#EC4899','#14B8A6','#F97316','#64748B']
    category_colors={'P':'#2563EB','R':'#16A34A','S':'#DC2626','T':'#7C3AED','M':'#0891B2','PB':'#EAB308','UNKNOWN':'#64748B'}
    def _customer_html(value, english=''):
        raw=str(value or '').strip()
        if not raw or raw.lower() in {'n/a','na','nan','none'}:return html.escape(raw or 'N/A')
        thai_name=raw.split(' / ',1)[0].strip()
        if any('\u0e00' <= ch <= '\u0e7f' for ch in thai_name):
            latin=str(english or _display_customer(thai_name,'English') or '').strip()
            small=f' <small class="customer-en">/ {html.escape(latin)}</small>' if latin and latin!=thai_name else ''
            return html.escape(thai_name)+small
        return html.escape(raw)
    figs=[]; slide_lists=[]
    def _add_stack_totals(fig,df,xcol,ycol,font_size=14):
        try:
            tt=df.groupby(xcol,as_index=False)[ycol].sum()
            for _,z in tt.iterrows(): fig.add_annotation(x=z[xcol],y=float(z[ycol]),text=f'{float(z[ycol]):,.0f}',showarrow=False,yshift=10,font=dict(size=font_size,color='#17324D'))
        except Exception: pass
        return fig
    def _major_orders_html(df,sections=None,title='MAJOR ORDERS',n=10,qtycol='Plan Qty'):
        if df is None or df.empty or 'Work Order' not in df.columns:return f'<div class="sidebox"><h3>{title}</h3><div class="empty">No applicable orders</div></div>'
        x=df.copy()
        if sections and 'Section' in x.columns:x=x[x['Section'].astype(str).isin(sections)].copy()
        if x.empty:return f'<div class="sidebox"><h3>{title}</h3><div class="empty">No applicable orders</div></div>'
        if qtycol not in x.columns:x[qtycol]=0
        x[qtycol]=pd.to_numeric(x[qtycol],errors='coerce').fillna(0)
        keys=['Work Order']+([c for c in ['Customer Thai','Customer English','Customer','Specification','Section'] if c in x.columns])
        x=x.groupby(keys,dropna=False,as_index=False)[qtycol].sum().sort_values(qtycol,ascending=False).head(n)
        rows=''.join(f'<tr><td>{html.escape(str(r.get("Work Order",""))[:20])}</td><td>{_customer_html(r.get("Customer Thai",r.get("Customer","")),r.get("Customer English",""))}</td><td>{html.escape(str(r.get("Specification",""))[:28])}</td><td>{html.escape(str(r.get("Section",""))[:12])}</td><td class="num">{float(r.get(qtycol,0)):,.0f}</td></tr>' for _,r in x.iterrows())
        return f'<div class="sidebox"><h3>{title}</h3><table><tr><th>WO</th><th>Customer / ลูกค้า</th><th>Specification / สเปก</th><th>Process</th><th>Qty</th></tr>{rows}</table></div>'
    def _risk_customer(row):
        for _field in ('Customer Thai','Customer','Customername','Customer Source','Customer English'):
            _value=row.get(_field,'')
            if pd.notna(_value):
                _value=str(_value).strip()
                if _value and _value.lower() not in {'n/a','na','nan','none'}:
                    return _value
        return 'N/A'
    def _major_risk_by_category_html(df,n_each=12):
        title='MAJOR DELIVERY-RISK ORDERS BY PRODUCT CATEGORY / งานเสี่ยงหลักตามกลุ่มสินค้า'
        if df is None or df.empty or 'Work Order' not in df.columns:
            return f'<div class="sidebox"><h3>{title}</h3><div class="empty">No applicable risk orders</div></div>'
        x=df.copy(); x['_qty']=pd.to_numeric(x.get('_qty',x.get('Open Qty',0)),errors='coerce').fillna(0)
        for c in ['Category','Specification','Bottleneck Process','Due Date']:
            if c not in x.columns:x[c]='N/A'
            x[c]=x[c].fillna('N/A').astype(str).replace('', 'N/A')
        for c in ['Customer','Customer Thai']:
            if c not in x.columns:x[c]=''
            x[c]=x[c].fillna('').astype(str).replace({'nan':'','None':''})
        keys=['Category','Work Order','Customer Thai','Customer English','Customer','Specification','Bottleneck Process','Due Date']
        x=x.groupby(keys,dropna=False,as_index=False)['_qty'].sum()
        x=x.sort_values(['Category','_qty'],ascending=[True,False]).groupby('Category',group_keys=False).head(n_each)
        rows=''.join(f'<tr><td><b>{html.escape(str(r.get("Category",""))[:5])}</b></td><td>{html.escape(str(r.get("Work Order",""))[:18])}</td><td>{_customer_html(_risk_customer(r),r.get('Customer English',''))}</td><td>{html.escape(str(r.get("Specification",""))[:24])}</td><td>{html.escape(str(r.get("Bottleneck Process","N/A"))[:16])}</td><td>{pd.to_datetime(r.get("Due Date"),errors='coerce').strftime('%d-%b-%y') if pd.notna(pd.to_datetime(r.get("Due Date"),errors='coerce')) else ''}</td><td class="num">{float(r.get("_qty",0)):,.0f}</td></tr>' for _,r in x.iterrows())
        return f'<div class="sidebox risklist"><h3>{title}</h3><table><tr><th>Cat.</th><th>WO</th><th>Customer / ลูกค้า</th><th>Spec / สเปก</th><th>Bottleneck / คอขวด</th><th>Due / กำหนด</th><th>Qty</th></tr>{rows}</table></div>'
    if not pp.empty:
        g=pp.groupby(['_d','Section'],as_index=False)['Plan Qty'].sum()
        f=px.bar(g,x='_d',y='Plan Qty',color='Section',title='Production schedule / แผนการผลิต',color_discrete_sequence=palette)
        f=_add_stack_totals(f,g,'_d','Plan Qty',11); f.update_layout(bargap=.08); figs.append(f)
        slide_lists.append(_major_orders_html(pp,['Forming','Firing','Grinding','Cutting'],'MAJOR FORMING • FIRING • GRINDING/CUTTING',12))
    if not rr.empty:
        # Management planning class: TEST has priority; normal work is separated into MPS (make-to-stock) and MTO.
        _wo=rr['Work Order'].fillna('').astype(str).str.upper() if 'Work Order' in rr.columns else pd.Series('',index=rr.index)
        rr['Planning Group']=np.where(rr['Order Type'].astype(str).str.upper().str.contains('TEST'),'TEST',np.where(_wo.str.startswith(('PM','PBM')),'MPS','MTO'))
        g=rr.groupby(['Planning Group','Category'],as_index=False,dropna=False)['_qty'].sum()
        _riskfig=px.bar(g,x='Planning Group',y='_qty',color='Category',barmode='stack',title='Delivery risk — TEST / MTO / MPS',color_discrete_map=category_colors)
        _riskfig=_add_stack_totals(_riskfig,g,'Planning Group','_qty')
        if 'Bottleneck Process' in rr.columns:
            bp=rr.groupby('Bottleneck Process',as_index=False)['_qty'].sum().sort_values('_qty',ascending=False)
            _bottleneck_fig=px.pie(bp,names='Bottleneck Process',values='_qty',title='Bottleneck process share / สัดส่วนกระบวนการคอขวด',color='Bottleneck Process',color_discrete_sequence=palette,hole=.38)
            # Keep delivery-risk bars, bottleneck share, and the major-risk WO
            # table together on one management slide.
            from plotly.subplots import make_subplots
            _combined=make_subplots(rows=1,cols=2,specs=[[{'type':'xy'},{'type':'domain'}]],
                column_widths=[0.58,0.42],horizontal_spacing=0.08,
                subplot_titles=('Delivery risk by planning group / กลุ่มงานเสี่ยง','Bottleneck process share / สัดส่วนคอขวด'))
            for _trace in _riskfig.data:_combined.add_trace(_trace,row=1,col=1)
            for _trace in _bottleneck_fig.data:_combined.add_trace(_trace,row=1,col=2)
            _combined.update_layout(title='DELIVERY RISK + BOTTLENECK + MAJOR RISK ORDERS',barmode='stack',showlegend=True,
                legend=dict(orientation='h',y=-0.14),margin=dict(l=42,r=20,t=82,b=75))
            figs.append(_combined)
        else:
            figs.append(_riskfig)
        slide_lists.append(_major_risk_by_category_html(rr,30))
    if not pp.empty:
        w=pp.groupby(['Section','Category'],as_index=False)['Plan Qty'].sum()
        f=px.bar(w,x='Section',y='Plan Qty',color='Category',barmode='stack',title='Demand by process and product category / ความต้องการตามกระบวนการและกลุ่มสินค้า',color_discrete_map=category_colors)
        f=_add_stack_totals(f,w,'Section','Plan Qty',13); figs.append(f)
        # Use the right side of the final TV slide for backorder and bottleneck evidence.
        _side_parts=[]
        try:
            _bmc=_backorder_month_category(bo_md)
            if not _bmc.empty:
                _curm=pd.Period(pd.Timestamp(today),freq='M')
                _bmc=_bmc[pd.PeriodIndex(_bmc['Due Month'],freq='M')<=_curm].copy()
                # TV backorder uses the same shared past-due/open definition as Home.
                _bmc['_period']=pd.PeriodIndex(_bmc['Due Month'],freq='M')
                # Show the full overdue history so the TV snapshot explains the
                # accumulated backlog; future demand is plotted on its own slide.
                _bo=_bmc.groupby(['Due Month','Status','Product Category'],as_index=False).agg(**{'Qty pcs':('Qty pcs','sum'),'WOs':('WOs','sum'),'Weight ton':('Weight ton','sum')})
                if not _bo.empty:
                    _bo['_m']=pd.to_datetime(_bo['Due Month'].astype(str).str[:7]+'-01',errors='coerce')
                    _bo['Month / Status']=_bo['_m'].dt.strftime('%b-%y')+' '+_bo['Status'].astype(str).str.upper()
                    _months=sorted(_bo['Month / Status'].unique(),key=lambda z:pd.Period(z[:6],freq='M'))
                    _bf=px.bar(_bo,x='Month / Status',y='Qty pcs',color='Product Category',barmode='stack',hover_data=['WOs','Weight ton'],category_orders={'Month / Status':_months,'Product Category':['P','R','S','T','M','PB']},title=f'PAST-DUE OPEN BACKORDERS — all past-due months · remaining pcs × category · as of {bkk_today():%d %b %Y} / งานค้างส่งที่เปิด',color_discrete_map=category_colors)
                    _bf=_add_stack_totals(_bf,_bo,'Month / Status','Qty pcs',9)
                    _bf.update_layout(template='plotly_white',height=255,margin=dict(l=42,r=18,t=48,b=62),font=dict(size=9),legend=dict(orientation='h',y=-.31),bargap=.14)
                    _bf.update_xaxes(type='category',tickangle=-25)
                    _side_parts.append(pio.to_html(_bf,full_html=False,include_plotlyjs=False,config={'displayModeBar':True,'responsive':True,'scrollZoom':True,'displaylogo':False,'toImageButtonOptions':{'format':'svg','filename':'SL_Planning_TV'}}))
                # Backorder bottleneck evidence: use risk engine bottleneck only for overdue OPEN WOs.
                if not rr.empty and 'Work Order' in rr.columns and 'Bottleneck Process' in rr.columns and 'Work Order' in md.columns:
                    _od=overdue_backorders(bo_md,bkk_today())
                    _ows=set(_od['Work Order'].fillna('').astype(str))
                    _rb=rr[rr['Work Order'].fillna('').astype(str).isin(_ows)].copy()
                    if not _rb.empty:
                        _rb['_boqty']=pd.to_numeric(_rb.get('Open Qty',_rb.get('_qty',0)),errors='coerce').fillna(0)
                        _bg=_rb.groupby('Bottleneck Process',as_index=False)['_boqty'].sum().sort_values('_boqty',ascending=False).head(6)
                        if not _bg.empty:
                            _bpf=px.bar(_bg,x='_boqty',y='Bottleneck Process',orientation='h',title='Backorder bottleneck / กระบวนการคอขวดงานค้างส่ง',color='Bottleneck Process',color_discrete_sequence=palette)
                            _bpf.update_layout(template='plotly_white',height=205,margin=dict(l=115,r=18,t=48,b=30),font=dict(size=10),showlegend=False)
                            _side_parts.append(pio.to_html(_bpf,full_html=False,include_plotlyjs=False,config={'displayModeBar':True,'responsive':True,'scrollZoom':True,'displaylogo':False,'toImageButtonOptions':{'format':'svg','filename':'SL_Planning_TV'}}))
        except Exception: pass
        _prod_wip_rows, _prod_wip_errors = pw49.production_snapshot(APP_DIR)
        if _prod_wip_rows.empty:
            _prod_wip_folder = pw49.root_for(APP_DIR) / 'PRODUCTION_WIP'
            _prod_wip_error_html = '<br>'.join(html.escape(str(e)) for e in _prod_wip_errors) if _prod_wip_errors else 'Upload or activate section workbooks on Home.'
            _prod_box = f'<div class="sidebox"><h3>PRODUCTION WIP / WIP ฝ่ายผลิต</h3><div class="empty">No readable active Production WIP source.<br>{_prod_wip_error_html}<br>Folder: {html.escape(str(_prod_wip_folder))}</div></div>'
        else:
            _prod_wip_sum = _prod_wip_rows.groupby(['Section','Category'], as_index=False)['Open t'].sum(min_count=1)
            _prod_fig = px.bar(_prod_wip_sum, x='Section', y='Open t', color='Category', barmode='stack',
                category_orders={'Category':['P','R','S','T','M','PB']}, color_discrete_map=pw49.COLORS,
                title='Production WIP by section and product category (gross t)')
            _prod_totals = _prod_wip_sum.groupby('Section', as_index=False)['Open t'].sum(min_count=1)
            for _, _wr in _prod_totals.iterrows():
                _prod_fig.add_annotation(x=_wr['Section'], y=float(_wr['Open t']), text=f'{float(_wr["Open t"]):,.2f}', showarrow=False, yshift=9, font=dict(size=11, color='#17324D'))
            _prod_fig.update_traces(hovertemplate='%{x}<br>Category: %{fullData.name}<br>Production WIP: %{y:,.2f} gross t<extra></extra>')
            _prod_fig.update_layout(template='plotly_white', height=475, margin=dict(l=38,r=18,t=55,b=95), font=dict(size=11),
                legend=dict(orientation='h',y=-0.28), xaxis_title='', yaxis_title='Production WIP (gross t)')
            _prod_graph = pio.to_html(_prod_fig, full_html=False, include_plotlyjs=False,
                config={'displayModeBar':True,'responsive':True,'scrollZoom':True,'displaylogo':False,
                        'toImageButtonOptions':{'format':'svg','filename':'SL_Production_WIP_Dashboard'}})
            _prod_wip_files = ', '.join(sorted(_prod_wip_rows['Original filename'].dropna().astype(str).unique())) if 'Original filename' in _prod_wip_rows else 'File name unavailable'
            _prod_wip_uploads = ', '.join(sorted(_prod_wip_rows['Uploaded at'].dropna().astype(str).unique())) if 'Uploaded at' in _prod_wip_rows else 'Upload time unavailable'
            _prod_box = f'<div class="sidebox"><h3>PRODUCTION WIP / WIP ฝ่ายผลิต</h3>{_prod_graph}</div>'
        slide_lists.append(_prod_box)
        slide_lists.append('<div class="sidebox twographs"><h3>BACKORDER + BOTTLENECK / งานค้างส่ง + คอขวด</h3>'+''.join(_side_parts)+'</div>' if _side_parts else '')
    # Current OPEN/CLOSED status by due month, bounded to the latest 3 months. This is not a month-end history.
    try:
        _recent_status=recent_open_closed_month_category(md,bkk_today(),months=3)
        if not _recent_status.empty:
            _recent_status['_Month']=pd.to_datetime(_recent_status['Due Month'].astype(str)+'-01',errors='coerce')
            _recent_status['_MonthStatus']=_recent_status['_Month'].dt.strftime('%b %Y')+' · '+_recent_status['Status']
            _recent_fig=px.bar(_recent_status,x='_MonthStatus',y='Qty pcs',color='Product Category',barmode='stack',
                category_orders={'Product Category':['P','R','S','T','M','PB','UNKNOWN'],'Status':['OPEN','CLOSED']},color_discrete_map=category_colors,
                hover_data=['Status','WOs','Weight ton'],title='LAST 3 DUE MONTHS · CURRENT OPEN / CLOSED WO BALANCE BY CATEGORY')
            _recent_fig.update_layout(template='plotly_white',height=620,margin=dict(l=55,r=35,t=85,b=75),font=dict(size=15),
                xaxis_title='Current Plan-2026 due month',yaxis_title='Quantity (pcs)',legend_title='Category / status')
            _recent_fig.update_xaxes(type='category',tickangle=-25)
            figs.append(_recent_fig);slide_lists.append('')
    except Exception:
        pass
    # Space utilization: capacity load ratio by process where controlled capacity is available.
    try:
        if isinstance(caps,pd.DataFrame) and not caps.empty and not pp.empty:
            sec_col=next((c for c in ['Section','Process','Process Name'] if c in caps.columns),None)
            cap_col=next((c for c in ['Capacity pcs/day','Capacity pcs','Daily Capacity','Capacity'] if c in caps.columns),None)
            if sec_col and cap_col:
                cg=caps[[sec_col,cap_col]].copy();cg[cap_col]=pd.to_numeric(cg[cap_col],errors='coerce');cg=cg.dropna().groupby(sec_col,as_index=False)[cap_col].sum()
                dg=pp.groupby('Section',as_index=False)['Plan Qty'].sum();days=max((to_d-from_d).days+1,1);dg['Avg Daily Plan']=dg['Plan Qty']/days
                u=dg.merge(cg,left_on='Section',right_on=sec_col,how='left');u['Utilization %']=(u['Avg Daily Plan']/u[cap_col]*100).replace([float('inf')],0).fillna(0)
                figs.append(px.bar(u,x='Section',y='Utilization %',color='Section',title='Average capacity utilization / การใช้กำลังการผลิตเฉลี่ย',color_discrete_sequence=palette)); slide_lists.append('')
    except Exception:pass
    divs=[]
    for i,f in enumerate(figs):
        f.update_layout(template='plotly_white',paper_bgcolor='#FFFFFF',plot_bgcolor='#F8FAFC',font=dict(size=21,color='#17324D'),margin=dict(l=50,r=25,t=70,b=65),height=700,legend=dict(orientation='h',y=-0.16),colorway=palette)
        f.update_xaxes(showgrid=False);f.update_yaxes(gridcolor='#DCE6F1')
        divs.append(pio.to_html(f,full_html=False,include_plotlyjs=True if i==0 else False,config={'displayModeBar':True,'responsive':True,'scrollZoom':True,'displaylogo':False,'toImageButtonOptions':{'format':'svg','filename':'SL_Planning_TV','width':1920,'height':1080}}))
    # The trailing capacity slide omitted month context in TV view. Keep the
    # 3-month category stack (the preceding slide) and remove only that final slide.
    if divs:
        divs.pop()
        if slide_lists: slide_lists.pop()
    def _target_html(df,title):
        if df.empty:return f'<div class="workbox"><h3>{title}</h3><div class="empty">No scheduled workload</div></div>'
        mx=max(float(df['Plan Qty'].max()),1)
        rows=''.join(f'<div class="barrow"><b>{str(r["Section"])}</b><div class="bar"><i style="width:{min(float(r["Plan Qty"])/mx*100,100):.0f}%"></i></div><strong>{float(r["Plan Qty"]):,.0f} pcs</strong></div>' for _,r in df.iterrows())
        return f'<div class="workbox"><h3>{title}</h3>{rows}</div>'
    def _due_html(df,title):
        if df.empty:return f'<div class="duebox"><h3>{title}</h3><div class="empty">No open due delivery</div></div>'
        cols=[c for c in ['Due Date','Work Order','Customer','Specification','Category','PCS'] if c in df.columns]
        head=''.join(f'<th>{c}</th>' for c in cols);body=''
        for _,r in df.head(8).iterrows():
            body+='<tr>'+''.join(f'<td>{float(r[c]):,.0f}</td>' if c=='PCS' else (f'<td>{_customer_html(r.get("Customer Thai",r[c]),r.get("Customer English",""))}</td>' if c=='Customer' else f'<td>{html.escape(pd.to_datetime(r[c]).strftime("%d-%m-%Y") if pd.notna(pd.to_datetime(r[c],errors="coerce")) else "—")}</td>' if c=='Due Date' else f'<td>{html.escape(str(r[c])[:32])}</td>') for c in cols)+'</tr>'
        return f'<div class="duebox"><h3>{title}</h3><table><tr>{head}</tr>{body}</table></div>'
    risk_n=rr['Work Order'].nunique() if (not rr.empty and 'Work Order' in rr.columns) else len(rr);riskq=float(rr['_qty'].sum()) if not rr.empty else 0
    # Use the same authoritative planning master as Backorder Analysis when available.
    # The HTML dashboard receives md as a parameter; do not silently substitute
    # its subset for the full WO master. Warn when it differs from the shared master.
    _bo_total=overdue_backorders(bo_md,bkk_today())
    # Count/quantity come directly from the same one-row-per-WO source as the
    # Backorder page. Grouped charts are for display only and never define totals.
    _bo_summary=overdue_backorder_totals(bo_md,bkk_today())
    backorder_wo=_bo_summary['WOs']
    backorder_qty=_bo_summary['Qty pcs']
    backorder_ton=_bo_summary['Weight ton']
    today_qty=float(td['Plan Qty'].sum()) if not td.empty else 0;tom_qty=float(tm['Plan Qty'].sum()) if not tm.empty else 0
    ops=f"""<section class="slide active"><div class="opsgrid">{_target_html(td,'TODAY WORKLOAD / เป้าหมายวันนี้')}{_target_html(tm,'NEXT WORKDAY / เป้าหมายวันทำงานถัดไป')}</div><div class="opsgrid duegrid">{_due_html(due_today,f'DUE TODAY / ส่งมอบวันนี้ — {pd.Timestamp(today).strftime("%d-%m-%Y")}')}{_due_html(due_tom,f'DUE NEXT WORKDAY / ส่งมอบวันทำงานถัดไป — {pd.Timestamp(tomorrow).strftime("%d-%m-%Y")}')}</div></section>"""
    slides=ops+''.join((f'<section class="slide"><div class="split"><div class="chart">{d}</div>{slide_lists[i] if i < len(slide_lists) else ""}</div></section>' if (i < len(slide_lists) and slide_lists[i]) else f'<section class="slide"><div class="chart">{d}</div></section>') for i,d in enumerate(divs))
    _meta=snapshot_meta or {}
    _stamp=str(_meta.get('generated_at','snapshot time unavailable'))
    _fingerprint=str(_meta.get('signature','unverified'))
    _source_items=[]
    for _source_label,_source_path in (source_refs or {}).items():
        try:
            _source_file=Path(str(_source_path)) if _source_path else None
            if _source_file and _source_file.is_file():
                _source_items.append(f'{html.escape(str(_source_label))}: {html.escape(_source_file.name)}')
            elif _source_path:
                _source_items.append(f'{html.escape(str(_source_label))}: {html.escape(Path(str(_source_path)).name)} (path unavailable)')
        except Exception:
            continue
    _source_html=' · '.join(_source_items) if _source_items else 'Source file names unavailable in this snapshot'
    _html=f"""<!doctype html><html><head><meta charset="utf-8"><meta name="sl-snapshot-generated-at" content="{_stamp}"><meta name="sl-snapshot-fingerprint" content="{_fingerprint}"><title>SL Planning Department TV Dashboard</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#F3F4F6;color:#333333;font-family:Arial,"Noto Sans Thai",sans-serif;overflow:hidden}}header{{height:92px;padding:12px 30px;display:flex;align-items:center;gap:22px;background:#FFFFFF;border-bottom:6px solid #F28C00}}header img{{height:60px;max-width:250px;object-fit:contain}}h1{{font-size:31px;margin:0;color:#333333}}.period{{font-size:16px;color:#6B7280;margin-top:4px}}.cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;padding:12px 30px}}.card{{border-radius:12px;padding:11px 16px;background:#FFFFFF;border-top:5px solid #F28C00;box-shadow:0 4px 14px #00000018}}.card b{{display:block;font-size:14px;color:#6B7280}}.card span{{display:block;font-size:27px;font-weight:800;margin-top:3px;color:#333333}}.stage{{height:calc(100vh - 194px);padding:0 36px 24px 30px}}.slide{{display:none;height:100%;animation:in .55s ease}}.slide.active{{display:block}}.chart{{height:100%;background:white;border-radius:12px;padding:4px;box-shadow:0 5px 18px #00000016}}.split{{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(430px,.95fr);gap:20px;height:100%;padding-right:10px}}.split .chart{{min-width:0}}.sidebox{{height:100%;background:white;border-radius:12px;padding:12px 18px 12px 12px;box-shadow:0 5px 18px #00000012;overflow:hidden;margin-right:8px}}.sidebox table{{font-size:15px}}.risklist{{overflow-y:auto!important;scrollbar-width:thin}}.risklist table{{font-size:13px}}.sidebox th,.sidebox td{{padding:8px 5px}}.risklist th,.risklist td{{padding:4px 3px}}.sidebox .num{{text-align:right;font-weight:800;color:#D97706}}.twographs{{padding:7px 18px 7px 10px}}.twographs h3{{font-size:15px;margin:2px 4px 0;color:#D97706}}.opsgrid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;height:48%;margin-bottom:15px}}.workbox,.duebox{{background:white;border-radius:12px;padding:14px 18px;box-shadow:0 5px 18px #00000012;overflow:hidden}}h3{{font-size:20px;margin:0 0 10px;color:#D97706}}.barrow{{display:grid;grid-template-columns:23% 1fr 20%;align-items:center;gap:10px;margin:8px 0;font-size:15px}}.bar{{height:18px;background:#E5E7EB;border-radius:10px;overflow:hidden}}.bar i{{display:block;height:100%;background:linear-gradient(90deg,#F28C00,#FDBA74,#6B7280);border-radius:10px}}table{{width:100%;border-collapse:collapse;font-size:14px}}.customer-en{{font-size:.72em;color:#6B7280;font-weight:400;white-space:nowrap}}th{{background:#4B5563;color:white}}th,td{{padding:7px;border-bottom:1px solid #E5E7EB;text-align:left}}.empty{{padding:35px;text-align:center;color:#6B7280;font-size:18px;font-weight:700}}@keyframes in{{from{{opacity:.2;transform:translateX(30px)}}to{{opacity:1;transform:none}}}}.dots{{position:fixed;right:30px;bottom:7px;font-size:12px;color:#6B7280}}.prepared{{position:fixed;left:30px;bottom:7px;font-size:12px;color:#6B7280;font-weight:700}}.sources{{position:fixed;left:30px;right:30px;bottom:25px;font-size:10px;color:#64748B;font-weight:600}}
    </style></head><body><header>{('<img src="'+logo+'">') if logo else ''}<div><h1>PLANNING DEPARTMENT / แผนกวางแผน</h1><div class="period">{from_d:%d-%m-%Y} → {to_d:%d-%m-%Y} </div></div></header><div class="cards"><div class="card"><b>TODAY TARGET / เป้าหมายวันนี้</b><span>{today_qty:,.0f} pcs</span></div><div class="card"><b>NEXT WORKDAY / วันทำงานถัดไป</b><span>{tom_qty:,.0f} pcs</span></div><div class="card"><b>DELIVERY RISK / ความเสี่ยงส่งมอบ</b><span>{risk_n:,} WO</span></div><div class="card"><b>RISK REMAINING / จำนวนเสี่ยงคงเหลือ</b><span>{riskq:,.0f} pcs</span></div><div class="card"><b>OPEN BACKORDERS / งานค้างเปิด</b><span>{backorder_wo:,} WO · {backorder_qty:,.0f} pcs</span></div></div><main class="stage">{slides}</main><div class="sources">Graph source files / แหล่งข้อมูลกราฟ: {_source_html}</div><div class="prepared">Prepared by / จัดทำโดย: Akash Deep — Planning Manager / ผู้จัดการฝ่ายวางแผน · Static snapshot; risk card and risk charts use due dates {from_d:%d-%m-%Y}–{to_d:%d-%m-%Y}.</div><div class="dots">Space = pause • ← → slides • Ctrl +/- = browser zoom • chart toolbar = SVG</div><script>let i=0,p=false;const s=[...document.querySelectorAll('.slide')];function show(n){{if(!s.length)return;s.forEach(x=>x.classList.remove('active'));i=(n+s.length)%s.length;s[i].classList.add('active')}}show(0);setInterval(()=>{{if(!p)show(i+1)}},12000);document.addEventListener('keydown',e=>{{if(e.code==='Space')p=!p;if(e.key==='ArrowRight')show(i+1);if(e.key==='ArrowLeft')show(i-1)}});</script></body></html>"""
    audit={'window_start':from_d.isoformat(),'window_end':to_d.isoformat(),'today_target_pcs':today_qty,'next_workday_target_pcs':tom_qty,'delivery_risk_wo_count':int(risk_n),'risk_remaining_pcs':riskq,'overdue_backorder_wo_count':backorder_wo,'overdue_backorder_pcs':backorder_qty,'overdue_backorder_ton':backorder_ton,'generated_at':_stamp,'fingerprint':_fingerprint}
    return _html,audit


# ---------- Controlled chart renderer: values + hover + download ----------
def _safe_name(s): return ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in str(s))[:80] or 'SL_PPC_GRAPH'
def _show_plotly(fig,name='SL_PPC_GRAPH'):
    # ADAPTIVE CHART RULE: when a graph is only a simple one-dimensional
    # categorical distribution with a few categories (2-4), use a pie chart.
    # Do NOT convert date/process/capacity comparison/grouped/stacked/Gantt charts,
    # because pie would destroy the planning comparison or time sequence.
    try:
        _bars=[tr for tr in fig.data if getattr(tr,'type','')=='bar']
        _barmode=str(getattr(fig.layout,'barmode','') or '').lower()
        if len(_bars)==1 and _barmode not in {'stack','relative','group'}:
            _tr=_bars[0]; _x=list(getattr(_tr,'x',[]) or []); _y=list(getattr(_tr,'y',[]) or [])
            _labels=[str(v) for v in _x]
            _few=2 <= len(_labels) <= 4 and len(set(_labels))==len(_labels)
            _timeish=any(re.search(r'\d{4}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec',z,re.I) for z in _labels)
            _processish=any(any(k in z.lower() for k in ['preparation','mixing','forming','firing','grinding','cutting','packing','เตรียม','ผสม','ขึ้นรูป','เผา','เจียร','ตัด','บรรจุ']) for z in _labels)
            _vals=[]
            for v in _y:
                try:_vals.append(float(v))
                except:_vals.append(float('nan'))
            if _few and not _timeish and not _processish and _vals and all(pd.notna(v) and v>=0 for v in _vals) and sum(_vals)>0:
                _title=getattr(getattr(fig.layout,'title',None),'text',None) or str(name).replace('_',' ')
                fig=go.Figure(go.Pie(labels=_labels,values=_vals,hole=.30,textinfo='label+value+percent',hovertemplate='%{label}<br>%{value:,.2f}<br>%{percent}<extra></extra>'))
                fig.update_layout(title=_title);fig.add_annotation(text=f'Total {sum(_vals):,.0f}',x=.5,y=.5,showarrow=False,font=dict(size=14))
    except Exception:
        pass
    # Timeline/Gantt bars use datetime durations internally (milliseconds).
    # Never print those raw internal numbers on the chart.
    _nm=str(name)
    suppress_segment_labels = (
        _nm.startswith('WIP_category_stack')
        or _nm.startswith('WO_Gantt_')
        or _nm.startswith('Operational_MRP_')
        or 'timeline' in _nm.lower()
    )
    _is_stack=str(getattr(fig.layout,'barmode','') or '').lower() in {'stack','relative'}
    for tr in fig.data:
        try:
            if getattr(tr,'type','')=='bar':
                if suppress_segment_labels or _is_stack:
                    # Empty texttemplate is stronger than None because None can allow
                    # Plotly/default helper logic to restore the bar's numeric x value.
                    tr.text=[]
                    tr.texttemplate=''
                    tr.textposition='none'
                    tr.cliponaxis=True
                else:
                    vals=getattr(tr,'y',None) if getattr(tr,'orientation',None)!='h' else getattr(tr,'x',None)
                    nums=[float(v) for v in vals if pd.notna(v)] if vals is not None else []
                    whole=bool(nums) and all(abs(v-round(v))<1e-9 for v in nums)
                    fmt=',.0f' if whole else ',.2f'
                    tr.texttemplate=('%{y:'+fmt+'}' if getattr(tr,'orientation',None)!='h' else '%{x:'+fmt+'}')
                    tr.textposition='outside' if len(nums)<=10 else 'none'; tr.cliponaxis=False; tr.textfont=dict(size=12 if not _large_view else 14)
            elif getattr(tr,'type','')=='scatter' and not suppress_segment_labels:
                y=getattr(tr,'y',None)
                if y is not None:
                    tr.mode='lines+markers+text' if 'lines' in (getattr(tr,'mode','') or 'lines') else 'markers+text'
                    tr.text=[f'{float(v):,.0f}' if pd.notna(v) and abs(float(v)-round(float(v)))<1e-9 else (f'{float(v):,.2f}' if pd.notna(v) else '') for v in y]
                    tr.textposition='top center'
        except Exception: pass
    # For every stacked graph show only ONE total for the whole stack. Segment values remain in hover.
    _no_stack_total=False
    if _is_stack:
        try:
            totals={}
            for tr in fig.data:
                if getattr(tr,'type','')!='bar': continue
                xs=list(getattr(tr,'x',[]) or []); ys=list(getattr(tr,'y',[]) or [])
                if getattr(tr,'orientation',None)=='h': continue
                for xx,yy in zip(xs,ys):
                    try: totals[xx]=totals.get(xx,0.0)+float(yy or 0)
                    except: pass
            for xx,tt in totals.items():
                fig.add_annotation(x=xx,y=tt,text=f'{tt:,.0f}',showarrow=False,yshift=10,font=dict(size=15))
        except Exception: pass
    # V1.9.36: no hidden/global date clipping here. Each time-based analysis owns its
    # local FROM/TO controls and filters its underlying dataset before plotting. This prevents
    # one graph's period from silently changing unrelated management evidence.
    fig=pq.chart_layout(fig,large=_large_view)
    if 'capacity' in _nm.lower() or 'demand_capacity' in _nm.lower():
        try: fig.update_xaxes(tickangle=-90,automargin=True)
        except Exception: pass
    if _english_first:
        _title=str(getattr(getattr(fig.layout,'title',None),'text','') or '')
        if ' / ' in _title:fig.update_layout(title_text=_title.split(' / ')[0].strip())
        # Thai text remains available in tables and the bilingual Reporting page.

    # A date-range selector beside every chart with a true date axis. No global clipping.
    if pq.is_date_axis(fig):
        try:
            _ds=[]
            for _tr in fig.data:
                for _x in (list(_tr.x) if _tr.x is not None else []):
                    _d=pd.to_datetime(_x,errors='coerce')
                    if pd.notna(_d):_ds.append(_d.date())
            if _ds:
                with st.expander('📅 Chart date range / ช่วงวันที่กราฟ',expanded=False):
                    _dc1,_dc2=st.columns(2)
                    _from=_dc1.date_input('FROM / จาก',value=min(_ds),key='chfrom_'+_safe_name(name))
                    _to=_dc2.date_input('TO / ถึง',value=max(_ds),key='chto_'+_safe_name(name))
                    if _from<=_to:fig.update_xaxes(range=[str(_from),str(_to+timedelta(days=1))])
                    else:st.warning('FROM must be on or before TO')
        except Exception as _date_error:st.caption(f'Chart date control unavailable: {_date_error}')
    st.plotly_chart(fig,use_container_width=True,config=pq.chart_config(_safe_name(name)),key='plot_'+_safe_name(name))
    _chart_name=str(name).lower()
    _source_refs=[]
    def _add_source_ref(label,path):
        try:
            _sp=Path(str(path)) if path else None
            if _sp and _sp.is_file(): _source_refs.append(f"{label}: {_sp.name}")
        except Exception: pass
    if 'kpi_section' in _chart_name: _add_source_ref('Section KPI',st.session_state.get('kpi_section_path'))
    elif 'kpi_delivery' in _chart_name or 'warehouse' in _chart_name: _add_source_ref('Delivery KPI',st.session_state.get('kpi_delivery_path') or (_company_data()/'KPI'/'Warehouse-Delivery-KPI-LATEST.xlsx'))
    else:
        _add_source_ref('Plan-2026',st.session_state.get('plan_path'))
        if any(k in _chart_name for k in ('capacity','demand_capacity','utilization')): _add_source_ref('Capacity',st.session_state.get('cap_path'))
        if any(k in _chart_name for k in ('firing','kiln')): _add_source_ref('Firing plan',st.session_state.get('fire_path'))
        if any(k in _chart_name for k in ('stock','material','mrp')): _add_source_ref('Stock',st.session_state.get('stock_path'))
        if any(k in _chart_name for k in ('actual','daily_status','wip','open_closed')):
            try:
                _dsf=_ds_cache_valid
                if isinstance(_dsf,pd.DataFrame) and 'Source File' in _dsf:
                    _daily_files=sorted(set(_dsf['Source File'].dropna().astype(str)))
                    if _daily_files: _source_refs.append('Daily actual/status: '+', '.join(Path(x).name for x in _daily_files[:8]))
            except Exception: pass
    if _source_refs:
        st.caption('Source files / แหล่งข้อมูล: ' + ' · '.join(_source_refs) + ' · full path, revision and import time: Files & Traceability.')
    with st.expander('🔎 EXPORT / ขยายภาพ — 4K PNG • SVG vector • offline HTML / ส่งออกกราฟ',expanded=False):
        st.caption('SVG stays sharp at any zoom. Offline HTML includes all graph data and works without internet. Use its 4K PNG button for slides.')
        st.download_button('🌐 Offline interactive HTML / HTML แบบออฟไลน์',pq.offline_html(fig,name).encode('utf-8'),file_name=_safe_name(name)+'.html',mime='text/html',key='html_'+_safe_name(name),use_container_width=True)
        st.caption('Use the camera toolbar above to save a vector SVG directly, or open the HTML and click 4K PNG.')
def _show_mpl(fig,name='SL_PPC_GRAPH'):
    for ax in fig.axes:
        for cont in ax.containers:
            try: ax.bar_label(cont,fmt='%.2f',padding=3,fontsize=8)
            except Exception: pass
        for ln in ax.lines:
            try:
                for x,y in zip(ln.get_xdata(),ln.get_ydata()):
                    if pd.notna(y): ax.annotate(f'{float(y):,.2f}',(x,y),xytext=(0,6),textcoords='offset points',ha='center',fontsize=8)
            except Exception: pass
    b=io.BytesIO(); fig.savefig(b,format='jpg',dpi=180,bbox_inches='tight',facecolor='white'); data=b.getvalue(); st.pyplot(fig,use_container_width=True); st.download_button('⬇️ Download graph JPEG',data,file_name=_safe_name(name)+'.jpg',mime='image/jpeg',key='jpg_'+_safe_name(name)); plt.close(fig)

def _gantt_excel_bytes(gd,due):
    """Print-ready Excel Gantt for selected WOs.
    Plan2026 does not provide dated actual history for every process, therefore
    actual is shown as verified cumulative progress % inside the planned bar;
    no historical actual dates are invented.
    """
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='xlsxwriter',datetime_format='yyyy-mm-dd') as writer:
        book=writer.book
        hdr=book.add_format({'bold':True,'bg_color':'#D9EAF7','border':1,'align':'center','valign':'vcenter','text_wrap':True})
        cell=book.add_format({'border':1,'valign':'top','text_wrap':True})
        datefmt=book.add_format({'border':1,'num_format':'yyyy-mm-dd','align':'center'})
        pctfmt=book.add_format({'border':1,'num_format':'0%','align':'center'})
        planfmt=book.add_format({'bg_color':'#BDD7EE','border':1,'align':'center'})
        actfmt=book.add_format({'bg_color':'#70AD47','font_color':'#FFFFFF','bold':True,'border':1,'align':'center'})
        duefmt=book.add_format({'bg_color':'#FFD966','border':1,'align':'center'})
        safefmt=book.add_format({'bg_color':'#F4B183','border':1,'align':'center'})
        note=book.add_format({'italic':True,'font_color':'#595959','text_wrap':True})
        gd2=gd.copy()
        if not gd2.empty:
            gd2['Start']=pd.to_datetime(gd2['Start'],errors='coerce')
            gd2['Finish']=pd.to_datetime(gd2['Finish'],errors='coerce')
            gd2['Actual Progress %']=pd.to_numeric(gd2['Actual Progress %'],errors='coerce').fillna(0).clip(0,100)
        gd2.to_excel(writer,sheet_name='Gantt Data',index=False)
        if due is None: due=pd.DataFrame()
        due.to_excel(writer,sheet_name='Due Date Review',index=False)
        for sn in ['Gantt Data','Due Date Review']:
            ws=writer.sheets[sn];ws.freeze_panes(1,0);ws.autofilter(0,0,max(len(gd2) if sn=='Gantt Data' else len(due),1),max((len(gd2.columns) if sn=='Gantt Data' else len(due.columns))-1,0))
            ws.set_row(0,28)
            for c in range(len(gd2.columns) if sn=='Gantt Data' else len(due.columns)): ws.write(0,c,(gd2.columns if sn=='Gantt Data' else due.columns)[c],hdr)
            ws.set_column(0,30,18)
        ws=book.add_worksheet('Gantt Chart');writer.sheets['Gantt Chart']=ws
        ws.freeze_panes(5,7);ws.set_landscape();ws.fit_to_pages(1,0);ws.set_margins(.25,.25,.35,.35)
        ws.merge_range('A1:G1','WORK ORDER GANTT — PLAN vs ACTUAL PROGRESS + DUE DATE REVIEW',book.add_format({'bold':True,'font_size':16,'align':'center','bg_color':'#1F4E78','font_color':'#FFFFFF'}))
        ws.merge_range('A2:G2','Blue = planned time | Green = proportion completed from current process actual | Yellow = current due date | Orange = suggested safe/revised due date',note)
        ws.merge_range('A3:G3','Actual dates are not invented when Plan2026 supplies cumulative actual quantity/status only.',note)
        fixed=['Work Order','Process','Start','Finish','Plan Qty pcs','Actual Progress %','Customer / Due Review']
        for c,h in enumerate(fixed): ws.write(4,c,h,hdr)
        if gd2.empty:
            ws.write(5,0,'No selected WO schedule rows.',cell)
            return out.getvalue()
        start=pd.to_datetime(gd2['Start'],errors='coerce').min().normalize()
        end=pd.to_datetime(gd2['Finish'],errors='coerce').max().normalize()
        if not due.empty:
            for col in ['Due Date','Suggested Safe Due Date','Requested New Due Date']:
                if col in due.columns:
                    v=pd.to_datetime(due[col],errors='coerce').max()
                    if pd.notna(v): end=max(end,v.normalize())
        # keep workbook readable for long selections
        max_days=180
        if (end-start).days+1>max_days:end=start+pd.Timedelta(days=max_days-1)
        dates=pd.date_range(start,end,freq='D')
        for j,d in enumerate(dates,start=len(fixed)):
            ws.write_datetime(4,j,d.to_pydatetime(),book.add_format({'bold':True,'border':1,'num_format':'dd-mmm','rotation':90,'align':'center'}))
            ws.set_column(j,j,3.2)
        ws.set_column('A:A',20);ws.set_column('B:B',24);ws.set_column('C:D',11);ws.set_column('E:F',12);ws.set_column('G:G',34)
        duemap={}
        if not due.empty and 'Work Order' in due.columns:
            for _,r in due.iterrows():duemap[str(r.get('Work Order',''))]=r
        for i,(_,r) in enumerate(gd2.sort_values(['Work Order','Start','Process']).iterrows(),start=5):
            wo=str(r.get('Work Order',''));dr=duemap.get(wo,{})
            cust=str(dr.get('Customer','')) if hasattr(dr,'get') else ''
            cd=pd.to_datetime(dr.get('Due Date'),errors='coerce') if hasattr(dr,'get') else pd.NaT
            sd=pd.to_datetime(dr.get('Suggested Safe Due Date'),errors='coerce') if hasattr(dr,'get') else pd.NaT
            notev=f"{cust} | Due {cd.date() if pd.notna(cd) else '-'} | Suggested {sd.date() if pd.notna(sd) else '-'}"
            vals=[wo,str(r.get('Process','')),r.get('Start'),r.get('Finish'),float(r.get('Planned Qty pcs',0) or 0),float(r.get('Actual Progress %',0) or 0)/100.0,notev]
            for c,v in enumerate(vals):
                if c in (2,3) and pd.notna(v): ws.write_datetime(i,c,pd.Timestamp(v).to_pydatetime(),datefmt)
                elif c==5: ws.write(i,c,v,pctfmt)
                else: ws.write(i,c,v,cell)
            rs=pd.Timestamp(r['Start']).normalize();rf=(pd.Timestamp(r['Finish'])-pd.Timedelta(days=1)).normalize();prog=float(r.get('Actual Progress %',0) or 0)/100.0
            pdays=max((rf-rs).days+1,1);done_days=int(round(pdays*prog))
            for j,d in enumerate(dates,start=len(fixed)):
                if rs<=d<=rf:
                    elapsed=(d-rs).days
                    ws.write(i,j,'A' if elapsed<done_days else 'P',actfmt if elapsed<done_days else planfmt)
            if pd.notna(cd) and start<=cd.normalize()<=end:
                j=len(fixed)+(cd.normalize()-start).days;ws.write(i,j,'DUE',duefmt)
            if pd.notna(sd) and start<=sd.normalize()<=end:
                j=len(fixed)+(sd.normalize()-start).days;ws.write(i,j,'NEW',safefmt)
        ws.autofilter(4,0,4+len(gd2),len(fixed)-1)
    out.seek(0);return out.getvalue()

work=Path.home()/'SL_PPC_DATA';work.mkdir(parents=True,exist_ok=True)
default_cap=Path(__file__).with_name('CAPACITY_DATABASE.xlsx')
_central_pack=Path(os.environ.get('SL_COMPANY_DATA',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA'/'COMPANY_DATA')))/'Packaging-Standard-LATEST.xlsx'
default_packaging=_central_pack if _central_pack.exists() else Path(__file__).with_name('PACKAGING_STANDARD_DATABASE.xlsx')
default_diamond=(Path(__file__).with_name('DIAMOND_CURRENT_PLAN_160926.xlsx') if Path(__file__).with_name('DIAMOND_CURRENT_PLAN_160926.xlsx').exists() else Path(__file__).with_name('DIAMOND_HISTORY_DATABASE.xlsx'))
default_diamond_issue=Path(__file__).with_name('DIAMOND_AUG2026_ISSUE.xlsx')

def _current_manpower_from_capacity(path):
    out={'Mixing':7,'Forming':28,'Firing':12,'Grinding':28,'Packing':12,'Mounted Stone':3}
    try:
        d=pd.read_excel(path,sheet_name='กำลังคนแผนกผลิต',header=None)
        mp={'ผสม':'Mixing','ขึ้นรูป':'Forming','เตา':'Firing','เจียร':'Grinding','บรรจุ':'Packing','หินแกน':'Mounted Stone'}
        for _,r in d.iterrows():
            sec=str(r.iloc[0]).strip() if len(r)>0 and pd.notna(r.iloc[0]) else ''
            if sec in mp:
                v=pd.to_numeric(pd.Series([r.iloc[2] if len(r)>2 else None]),errors='coerce').iloc[0]
                if pd.notna(v): out[mp[sec]]=int(v)
    except Exception: pass
    return out
CAP_MANPOWER=_current_manpower_from_capacity(default_cap)
for k,v in {
    'daily_result':None,'daily_result_meta':None,'daily_stale_reason':'','plan_path':'','fire_path':'','stock_path':'','sales_path':'',
    'cap_path':str(default_cap),'packaging_path':str(default_packaging),'diamond_path':str(default_diamond),'diamond_issue_path':str(default_diamond_issue),'db_path':str(work/'SL_PPC_DAILY_DATA.db'),'long_result':None,
    'policy':None,'firing_override':None,'fire_sig':'','actual_seed':None,'plan_overrides':pd.DataFrame(),'test_override_daily':{},'kpi_section_path':'','kpi_delivery_path':''
}.items():
    if k not in st.session_state: st.session_state[k]=v

# Restore the saved calculation's controls before widgets are created.
_restore_cache=Path(os.environ.get('SL_SHARED_ROOT',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA')))/'CACHE'/'daily_result.pkl'
if not st.session_state.get('_daily_snapshot_restored'):
    if _restore_cache.exists():
        try:
            with _restore_cache.open('rb') as _f:_restore=pickle.load(_f)
            if isinstance(_restore,dict) and _restore.get('schema')=='SL_DAILY_RESULT_V2':
                for _key,_value in (_restore.get('state') or {}).items():st.session_state[_key]=_value
                _saved_settings=(_restore.get('meta') or {}).get('parameters') or {}
                for _key,_value in _saved_settings.items():st.session_state['_saved_daily_'+_key]=_value
                if st.session_state.get('daily_result') is None and isinstance(_restore.get('result'),dict):
                    st.session_state['daily_result']=_restore['result']
                    st.session_state['daily_result_meta']=_restore.get('meta') or {}
        except Exception as _restore_error:st.session_state.daily_stale_reason=f'Saved plan settings could not be restored: {_restore_error}'
    # Recover the last complete snapshot before the Create button is shown. This
    # prevents Backorder / Recovery navigation from prompting for a duplicate run.
    if st.session_state.get('daily_result') is None:
        try:
            _early_snapshot_dir=_restore_cache.parent/'DAILY_PLAN_SNAPSHOTS'
            _early_snapshots=sorted(_early_snapshot_dir.glob('daily_plan_*.pkl'),key=lambda _p:_p.stat().st_mtime_ns,reverse=True) if _early_snapshot_dir.is_dir() else []
            for _early_snapshot in _early_snapshots:
                try:
                    with _early_snapshot.open('rb') as _early_handle:_early_payload=pickle.load(_early_handle)
                    if isinstance(_early_payload,dict) and _early_payload.get('schema')=='SL_DAILY_RESULT_V2' and isinstance(_early_payload.get('result'),dict):
                        st.session_state['daily_result']=_early_payload['result']
                        st.session_state['daily_result_meta']=_early_payload.get('meta') or {}
                        st.session_state['daily_stale_reason']=f"Recovered saved plan snapshot {_early_snapshot.name}. It remains available for review; verify active sources before release."
                        break
                except Exception:continue
        except Exception as _early_snapshot_error:
            st.session_state.daily_stale_reason=f'Could not inspect saved plan snapshots ({_early_snapshot_error}); no saved data was deleted.'
    st.session_state['_daily_snapshot_restored']=True

# A saved plan can hold an absolute capacity path from an older extracted folder.
# Keep a still-valid user path; otherwise use the shared active capacity, then this
# release's bundled copy. This prevents an old rc14 cache path breaking new releases.
def _repair_capacity_path(saved_path):
    try:
        candidate=Path(saved_path).expanduser() if saved_path else None
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    except (OSError, TypeError, ValueError):
        pass
    try:
        shared=_resolve_central('CAPACITY_DATABASE.xlsx')
        if shared and Path(shared).is_file():
            return Path(shared).resolve()
    except Exception:
        pass
    bundled=Path(__file__).resolve().parent/'CAPACITY_DATABASE.xlsx'
    return bundled.resolve() if bundled.is_file() else None

_repaired_capacity=_repair_capacity_path(st.session_state.get('cap_path'))
if _repaired_capacity is not None:
    st.session_state['cap_path']=str(_repaired_capacity)

# KPI evidence is uploaded for each reporting period; never silently reuse stale bundled KPI files.

with st.sidebar:
    st.header('📥 ACTIVE CENTRAL INPUTS')
    _cd=_company_data()
    _central_files={'Plan-2026':_resolve_central('Plan-2026-LATEST.xlsx') or _cd/'Plan-2026-LATEST.xlsx','Firing Plan':_resolve_central('Firing-Plan-LATEST.xlsx') or _cd/'Firing-Plan-LATEST.xlsx','Stock':_resolve_central('Stock-on-Hand-LATEST.xlsx') or _cd/'Stock-on-Hand-LATEST.xlsx','Sales Forecast':_resolve_central('Sales-Forecast-LATEST.xlsx') or _cd/'Sales-Forecast-LATEST.xlsx','Packaging Standard':packing_source.resolve_source(Path(__file__).resolve().parents[2],_cd) or _resolve_central('Packaging-Standard-LATEST.xlsx') or _cd/'Packaging-Standard-LATEST.xlsx'}
    try:_source_registry=json.loads((Path(os.environ.get('SL_SHARED_ROOT',str(_cd.parent)))/'source_registry.json').read_text(encoding='utf-8'))
    except Exception:_source_registry={}
    for _nm,_pp in _central_files.items():
        _entry=_source_registry.get(_pp.name,{})
        st.caption(('✅ ' if _pp.exists() else '❌ ')+_nm+' — original: '+(_entry.get('original_name','Original name not recorded') if _pp.exists() else 'not loaded'))
        if _pp.exists():
            st.caption(f"Central file: {_pp}")
            st.caption(f"Source folder: {_entry.get('client_source_path','Not recorded')} · uploaded {_entry.get('registered_at','Not recorded')} · workbook revised {_entry.get('excel_document_modified_at') or 'Not recorded'}")
    st.info('Upload/replace source files only in Home → Upload / replace source files. Daily Planner always uses those same central files. Close any Daily window from an older ZIP folder.')
    _today_bkk=datetime.datetime.now(ZoneInfo('Asia/Bangkok')).date()
    start=st.date_input('📅 Planning start / วันเริ่มแผน',value=date.fromisoformat(st.session_state.get('_saved_daily_start',str(_today_bkk+timedelta(days=1)))),key='daily_start')
    dashboard_date=st.date_input('📺 Dashboard date / วันที่ต้องการดู Dashboard',value=start)
    horizon=st.number_input('🗓️ Planning days / จำนวนวัน',7,365,int(st.session_state.get('_saved_daily_horizon',60)),1,key='daily_horizon')
    prep=st.number_input('⚙️ Preparation capacity kg/day — Planning control',100.0,10000.0,float(st.session_state.get('_saved_daily_prep_kg_day',1200.0)),100.0,key='daily_prep')
    packpeople=st.number_input('👥 Packing people / จำนวนคนบรรจุ',1,50,int(st.session_state.get('_saved_daily_packing_people',CAP_MANPOWER.get('Packing',12))),1,key='daily_packpeople')
    normal_hours=st.number_input('⏱️ Normal productive hours/day',min_value=1.0,max_value=12.0,value=float(st.session_state.get('_saved_daily_normal_hours',7.7)),step=0.1,key='daily_normal_hours')
    safe_buffer=st.number_input('🛡️ Safe due-date protection buffer (working days)',min_value=0,max_value=10,value=int(st.session_state.get('_saved_daily_safe_buffer_workdays',2)),step=1,key='daily_safe_buffer')
    import_lead=st.number_input('🚢 Import lead time days',1,180,int(st.session_state.get('_saved_daily_import_lead',45)),1,key='daily_import_lead')
    domestic_lead=st.number_input('🚚 Domestic lead time days',1,180,int(st.session_state.get('_saved_daily_domestic_lead',20)),1,key='daily_domestic_lead')
_shared_plan=_central_files['Plan-2026'];_shared_fire=_central_files['Firing Plan'];_sp=_central_files['Stock'];_sf=_central_files['Sales Forecast'];_pk=_central_files['Packaging Standard']
if _shared_plan.exists():st.session_state.plan_path=str(_shared_plan)
if _shared_fire.exists():
    st.session_state.fire_path=str(_shared_fire)
    _fire_source_sig='SHARED:'+str(_shared_fire.resolve())+':'+str(_shared_fire.stat().st_size)+':'+str(_shared_fire.stat().st_mtime_ns)
    if st.session_state.get('fire_sig')!=_fire_source_sig:
        try:st.session_state.firing_override=dl.load_firing_excel(str(_shared_fire));st.session_state.fire_sig=_fire_source_sig
        except Exception as _fire_error:st.warning(f'Firing input could not be restored: {_fire_error}')
if _sp.exists():st.session_state.stock_path=str(_sp)
if _sf.exists():st.session_state.sales_path=str(_sf)
_approved_pack=packing_source.resolve_source(Path(__file__).resolve().parents[2],_cd)
if _approved_pack:st.session_state.packaging_path=str(_approved_pack)
if not st.session_state.fire_path or not Path(st.session_state.fire_path).exists():st.session_state.firing_override=pd.DataFrame()
# Previous issued firing plan is intentionally NOT uploaded here. The Current Firing Planner Output is already rollover-reconciled.
# Current WIP, actual quantities and closure/status are authoritative from Latest Plan 2026.

# All operational source uploads are controlled centrally from Home → Active Files / Upload.
# Daily Planner reads the shared files above. Optional specialist inputs remain unset unless
# they are added through a dedicated controlled source in a future mapping revision.
su = salesu = packu = diamu = kpisecu = kpidevu = None

# Flexible Plan 2026 mapping. Defaults remain the confirmed SL mapping; user only edits if source columns move.
_saved_mapping=st.session_state.get('_saved_daily_mapping',coremap.DEFAULT_MAP)
def_mapping={k:v for k,v in _saved_mapping.items() if k not in {'sheet','data_start_row'}}
with st.expander('🧭 COLUMN MAPPING + KILN CHANGE / ปรับคอลัมน์ + เปลี่ยนเตา',expanded=False):
    m1,m2=st.tabs(['🧭 Plan 2026 column mapping','🔥 Firing / kiln adjustment'])
    with m1:
        c1,c2=st.columns([2,1])
        sheet_name=c1.text_input('Plan sheet / ชื่อชีต',value=str(_saved_mapping.get('sheet','แผนการเผา')),key='daily_sheet_name')
        data_row=c2.number_input('First data row',min_value=1,max_value=100,value=int(_saved_mapping.get('data_start_row',4)),key='daily_data_row')
        mapdf=pd.DataFrame([{'Field':k,'Excel Column':v} for k,v in def_mapping.items()])
        edited_map=_persistent_data_editor(mapdf,use_container_width=True,hide_index=True,disabled=['Field'],key='mapping_editor')
        st.caption('Defaults updated to the revised Plan 2026 addresses supplied 10-Sep-2026. Cut Factor = CP; process columns CW:EU; overall closure FC; sales delivery IB. Change here if the workbook moves again.')
    with m2:
        fo=st.session_state.firing_override
        if isinstance(fo,pd.DataFrame) and not fo.empty:
            ecols=[c for c in ['Firing Date','Firing Complete','Kiln','Program','Work Order','Firing Qty','kg/pc','Due Date'] if c in fo.columns]
            st.caption('Production did not follow the planned kiln? Change Kiln/date/program/qty here before creating the Daily Plan. The original firing file is not overwritten.')
            _edited_fire=_persistent_data_editor(fo[ecols].copy(),use_container_width=True,height=420,num_rows='dynamic',key='firing_editor')
            _full_fire=fo.reindex(_edited_fire.index).copy()
            for _column in ecols:_full_fire[_column]=_edited_fire[_column]
            st.session_state.firing_override=_full_fire
        else:
            st.info('Upload Firing Planner output first to enable kiln adjustment.')

mapping={'sheet':sheet_name,'data_start_row':int(data_row)}
for _,r in edited_map.iterrows():
    fld=str(r.get('Field','')).strip(); col=str(r.get('Excel Column','')).strip().upper()
    if fld and col: mapping[fld]=col

def _daily_current_signature(force_hash=False):
    """Fingerprint selected inputs and planning controls. Timestamp-only file touches are not part of the digest."""
    inputs={}
    paths={'Plan 2026':st.session_state.get('plan_path'),'Firing Plan':st.session_state.get('fire_path'),'Capacity':st.session_state.get('cap_path'),'Stock':st.session_state.get('stock_path'),'Sales Forecast':st.session_state.get('sales_path'),'Packaging':st.session_state.get('packaging_path')}
    _hash_cache=st.session_state.setdefault('_daily_source_hash_cache',{})
    for name,value in paths.items():
        inputs[name]=dailysnap.file_record(value,_hash_cache,force_hash)
    params={'calculation_rules_version':'V16.23_DATE_AB','start':str(start),'horizon':int(horizon),'prep_kg_day':float(prep),'packing_people':int(packpeople),'normal_hours':float(normal_hours),'safe_buffer_workdays':int(safe_buffer),'import_lead':int(import_lead),'domestic_lead':int(domestic_lead),'mapping':mapping,'plan_overrides':dailysnap.dataframe_fingerprint(st.session_state.get('plan_overrides')),'firing_override':dailysnap.dataframe_fingerprint(st.session_state.get('firing_override'))}
    from suite.order_status import revision as _whole_status_revision
    from suite.central_paths import db_path as _status_db
    params['Whole WO decision revision']=_whole_status_revision(_status_db())
    return dailysnap.content_digest(inputs,params),inputs,params

_run_daily_plan=False
_saved_daily_result=st.session_state.get('daily_result')
if isinstance(_saved_daily_result,dict):
    _button_meta=st.session_state.get('daily_result_meta') or {}
    _button_stamp=_button_meta.get('generated_at','Generation time not recorded')
    _button_sig,_,_=_daily_current_signature()
    _snapshot_current=bool(_button_meta.get('signature') and _button_meta.get('signature')==_button_sig)
    st.info(f'Saved plan snapshot: {_button_stamp} (Thailand time). The plan below is this saved calculation.')
    if not _snapshot_current:
        st.warning('This may be an older plan: active files or planning controls differ from its saved fingerprint. Review its source trace, then create a new plan below before release.')
    _run_daily_plan=st.button('🔄 CREATE / UPDATE DAILY PLAN from current files and settings / สร้างหรือปรับแผนจากไฟล์ปัจจุบัน',type='primary',use_container_width=True,key='daily_plan_create_or_update_visible')
else:
    st.info('No saved daily calculation was found. Create one after loading the required sources; Backorder and Recovery will reuse it.')
    _run_daily_plan=st.button('🚀 CREATE DAILY PLAN / สร้างแผนรายวัน',type='primary',use_container_width=True,key='daily_plan_create_or_update_visible')

if _run_daily_plan:
    try:
        _plan=_resolve_central('Plan-2026-LATEST.xlsx')
        if _plan: st.session_state.plan_path=str(_plan)
        if not st.session_state.plan_path or not Path(st.session_state.plan_path).exists():
            st.error(_missing_plan_message())
            st.stop()
        # Firing output is OPTIONAL. Plan2026 existing WIP/open demand must still be planned across all sections.
        if not st.session_state.fire_path or not Path(st.session_state.fire_path).exists():
            st.session_state.firing_override=pd.DataFrame()
        if not st.session_state.get('cap_path') or not Path(st.session_state.cap_path).is_file():
            _fallback_capacity=Path(__file__).resolve().parent/'CAPACITY_DATABASE.xlsx'
            if _fallback_capacity.is_file(): st.session_state.cap_path=str(_fallback_capacity.resolve())
            else: raise FileNotFoundError(f'Capacity workbook is missing. Expected bundled file: {_fallback_capacity}. Re-extract the complete ZIP; capacity is not an upload.')
        _sig_before,_inputs_before,_params_before=_daily_current_signature(force_hash=True)
        prog=st.progress(0);msg=st.empty()
        msg.info('① Read Plan 2026 + WIP / อ่าน Plan 2026 และ WIP')
        store.full_sync(st.session_state.plan_path,st.session_state.db_path,mapping=mapping);wip=store.load(st.session_state.db_path);prog.progress(20)
        msg.info('② Match mixer, forming machine, grinding resource and packing capacity')
        fire_override=st.session_state.firing_override if isinstance(st.session_state.firing_override,pd.DataFrame) else None
        res=eng.build_detailed(st.session_state.plan_path,st.session_state.fire_path,st.session_state.cap_path,start,int(horizon),float(prep),int(packpeople),0.0,0.0,mapping=mapping,firing_override=fire_override,plan_overrides=st.session_state.plan_overrides,previous_firing=None,normal_hours=float(normal_hours),safe_buffer_workdays=int(safe_buffer))
        # Case-insensitive category normalization across planner outputs. Valid categories: P/R/S/T/M/PB only.
        def _canon_cat(v):
            z=str(v or '').strip().upper()
            if z.startswith('PB'): return 'PB'
            if z[:1] in {'P','R','S','T','M'}: return z[:1]
            return 'UNCLASSIFIED'
        for _rk,_rv in list(res.items()):
            if isinstance(_rv,pd.DataFrame):
                for _cc in ['Category','Product Category','Type']:
                    if _cc in _rv.columns: _rv[_cc]=_rv[_cc].apply(_canon_cat)

        prog.progress(60)
        res['wip']=wip;res['wip_category']=eng.wip_category(wip);res['wip_category_ton']=eng.wip_category_ton(wip)
        msg.info('③ Check Stock + BOM / ตรวจสต็อกและ BOM')
        if st.session_state.stock_path and Path(st.session_state.stock_path).exists():
            stock=lm.parse_stock(Path(st.session_state.stock_path).read_bytes()); master,bom,formmeta,meta=lm.parse_product_capacity(Path(st.session_state.cap_path).read_bytes())
            res['stock']=stock;res['bom']=bom;res=eng.apply_material_check(res,bom,stock)
            st.session_state.policy=eng.make_material_policy(stock,bom,int(import_lead),int(domestic_lead))
        else:
            res['stock']=pd.DataFrame();res['bom']=pd.DataFrame();res=eng.apply_material_check(res,pd.DataFrame(),pd.DataFrame())
        prog.progress(78)
        msg.info('④ Capacity vs Plan + limiting reasons / กำลังการผลิตเทียบแผน')
        res['capacity_summary']=eng.capacity_summary(res['plans'],res['issues']);prog.progress(90)
        msg.info('⑤ Finish WIP + delivery risk / สรุป WIP และความเสี่ยงส่งมอบ')
        _sig_after,_inputs_after,_params_after=_daily_current_signature(force_hash=True)
        if _sig_before!=_sig_after:
            _changed=dailysnap.describe_changes(_inputs_before,_params_before,_inputs_after,_params_after)
            _what='; '.join(_changed) if _changed else 'an input fingerprint changed'
            st.error('A source file or planning control changed during calculation. No mixed-snapshot dashboard was published. '+_what+'. Click CREATE DAILY PLAN again after uploads finish.')
        else:
            _meta={'plan_id':hashlib.sha256((_sig_after+datetime.datetime.now(ZoneInfo('Asia/Bangkok')).isoformat()).encode()).hexdigest()[:16],'signature':_sig_after,'generated_at':datetime.datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds'),'inputs':_inputs_after,'parameters':_params_after}
            st.session_state.daily_result=res;st.session_state.daily_result_meta=_meta;st.session_state.daily_stale_reason=''
            try:
                _cache_root=Path(os.environ.get('SL_SHARED_ROOT',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA')))/'CACHE'
                _cache_root.mkdir(parents=True,exist_ok=True)
                _cache_payload={'schema':'SL_DAILY_RESULT_V2','signature':_sig_after,'meta':_meta,'result':res,'state':{k:st.session_state.get(k) for k in ['firing_override','fire_sig','plan_overrides','plan_path','fire_path','stock_path','sales_path','cap_path','packaging_path']}}
                _snap_dir=_cache_root/'DAILY_PLAN_SNAPSHOTS';_snap_dir.mkdir(parents=True,exist_ok=True)
                _snap_path=_snap_dir/f"daily_plan_{_meta['generated_at'].replace(':','').replace('-','')}_{_meta['plan_id']}.pkl"
                _snap_tmp=_snap_path.with_suffix('.pkl.tmp')
                with _snap_tmp.open('wb') as _sfh:pickle.dump(_cache_payload,_sfh,protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(_snap_tmp,_snap_path)
                _latest_cache=_cache_root/'daily_result.pkl'
                _latest_tmp=_latest_cache.with_suffix('.pkl.tmp')
                with _latest_tmp.open('wb') as _lfh:pickle.dump(_cache_payload,_lfh,protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(_latest_tmp,_latest_cache)
            except Exception as _cache_write_error:st.warning(f'Calculation is live but its verified snapshot could not be persisted: {_cache_write_error}')
            prog.progress(100);msg.success('✅ Finished / เสร็จสิ้น')
    except Exception as e:
        st.error(str(e));st.code(traceback.format_exc())


# ---------- Validation / packaging / tooling helpers ----------
def _normtxt(v):
    return re.sub(r'[^0-9A-Za-zก-๙]+','',str(v or '')).upper()

def _firing_consistency(daily_plans, firing_df):
    cols=['Work Order','Daily Firing Date','Firing Planner Date','Daily Qty','Firing Planner Qty','Date Match','Qty Match','Result']
    if daily_plans is None or daily_plans.empty or firing_df is None or firing_df.empty:
        return pd.DataFrame(columns=cols)
    dp=daily_plans[daily_plans['Section'].astype(str).eq('Firing')].copy()
    if dp.empty:return pd.DataFrame(columns=cols)
    dp['_d']=pd.to_datetime(dp['Plan Date'],errors='coerce').dt.date
    dg=dp.groupby('Work Order',as_index=False).agg(**{'Daily Firing Date':('_d','min'),'Daily Qty':('Plan Qty','sum')})
    ff=firing_df.copy();ff['_d']=pd.to_datetime(ff['Firing Date'],errors='coerce').dt.date
    fg=ff.groupby('Work Order',as_index=False).agg(**{'Firing Planner Date':('_d','min'),'Firing Planner Qty':('Firing Qty','sum')})
    x=dg.merge(fg,on='Work Order',how='outer')
    x['Date Match']=x['Daily Firing Date'].eq(x['Firing Planner Date'])
    x['Qty Match']=(pd.to_numeric(x['Daily Qty'],errors='coerce').fillna(-1)-pd.to_numeric(x['Firing Planner Qty'],errors='coerce').fillna(-2)).abs()<1e-6
    x['Result']=np.where(x['Date Match']&x['Qty Match'],'PASS','FAIL')
    return x[cols]

def _capacity_validation(plans,caps):
    return _capacity_validation_view(plans,caps)

def _pull_balance_validation(plans,caps):
    cv=_capacity_validation(plans,caps)
    if cv.empty:return cv
    cv['Unused Capacity %']=np.where(pd.to_numeric(cv['Load %'],errors='coerce').notna(),(100-pd.to_numeric(cv['Load %'],errors='coerce')).clip(lower=0),np.nan)
    cv['Balance Band']=pd.cut(pd.to_numeric(cv['Load %'],errors='coerce'),[-np.inf,60,85,100,np.inf],labels=['LOW / CHECK PULL','BALANCED','HIGH','OVERLOAD'])
    return cv

def _packaging_tables(path):
    if not path or not Path(path).exists():return {'_error':'Packaging source file is missing.'}
    try:return packing_source.read_tables(path)
    except Exception as ex:return {'_error':f'File is present but unreadable: {ex}'}

def _packaging_requirement(master,plans,path):
    tabs=_packaging_tables(path)
    usage=tabs.get('Usage',pd.DataFrame()); std=tabs.get('Packaging standard',pd.DataFrame())
    _thai_standard='รหัสสินค้า' in std.columns and 'จำนวนบรรจุต่อกล่อง' in std.columns
    if master is None or master.empty or plans is None or plans.empty:return pd.DataFrame(),tabs
    pack=plans[plans['Section'].astype(str).eq('Packing')].copy()
    if pack.empty:return pd.DataFrame(),tabs
    pack['_PackDate']=pd.to_datetime(pack['Plan Date'],errors='coerce')
    pg=pack.groupby('Work Order',as_index=False).agg(**{'Packing Plan Date':('_PackDate','min'),'Packing Plan Qty':('Plan Qty','sum')})
    mm=master.merge(pg,on='Work Order',how='inner')
    rows=[]
    material_pairs=[('กล่องนอก','จำนวน'),('ไส้ใน','จำนวน.1'),('ไส้นอก','จำนวน.2'),('แผ่นรองล่าง/บน','จำนวน.3'),('แผ่นรองสั้น','จำนวน.4'),('แผ่นรองยาว','จำนวน.5'),('สติ๊กเกอร์','จำนวน.6')]
    for _,r in mm.iterrows():
        item=str(r.get('Product Code','')).strip(); qty=float(pd.to_numeric(pd.Series([r.get('Packing Plan Qty',0)]),errors='coerce').fillna(0).iloc[0])
        if _thai_standard:
            matched=std[std['รหัสสินค้า'].astype(str).str.strip().eq(item)].copy()
            definition=['จำนวนบรรจุต่อกล่อง']+[c for pair in packing_source.PAIRS for c in pair if c in matched.columns]
            if not matched.empty and len(matched[definition].astype(str).drop_duplicates())==1:
                u=matched.iloc[0];basis=pd.to_numeric(pd.Series([u.get('จำนวนบรรจุต่อกล่อง')]),errors='coerce').iloc[0]
                if pd.notna(basis) and basis>0:
                    boxes=math.ceil(qty/float(basis))
                    for mc,qc in packing_source.PAIRS:
                        code=str(u.get(mc,'') or '').strip();per=pd.to_numeric(pd.Series([u.get(qc)]),errors='coerce').iloc[0]
                        if code.lower() not in {'','-','none','nan','0'} and pd.notna(per) and per>0:
                            rows.append({'Work Order':r.get('Work Order'),'Customer':r.get('Customer'),'Product Code':item,'Packing Plan Date':r.get('Packing Plan Date'),'Packing Plan Qty':qty,'Packaging Material':code,'Required Qty':boxes*float(per),'Match Method':'EXACT PRODUCT CODE — Thai approved standard','Risk':'OK','Source Sheet':std.attrs.get('source_sheet','มาตรฐานการบรรจุ'),'Pcs/Box':float(basis),'Boxes Required':boxes})
                    continue
            reason='CONFLICTING STANDARD ROWS' if not matched.empty and len(matched[definition].astype(str).drop_duplicates())>1 else ('INVALID PCS/BOX' if not matched.empty else 'PRODUCT CODE NOT FOUND IN LOADED STANDARD')
            rows.append({'Work Order':r.get('Work Order'),'Customer':r.get('Customer'),'Product Code':item,'Packing Plan Date':r.get('Packing Plan Date'),'Packing Plan Qty':qty,'Packaging Material':'UNRESOLVED','Required Qty':np.nan,'Match Method':reason,'Risk':'CHECK'})
            continue
        candidates=pd.DataFrame(); method='NO MATCH'
        if not usage.empty:
            pc=next((c for c in usage.columns if _normtxt(c) in {_normtxt('Product code'),_normtxt('Code Product'),_normtxt('รหัสสินค้า')}),None)
            if pc:
                candidates=usage[usage[pc].astype(str).str.strip().eq(item)].copy()
        if not candidates.empty:
            method='EXACT PRODUCT CODE'
        else:
            # Sizewise fallback: find nearest standard D/T/H within same group/shape where possible,
            # then use that standard product code to find historical packaging usage.
            if not std.empty and not usage.empty:
                scols={_normtxt(c):c for c in std.columns}
                dc=scols.get('D');tc=scols.get('T');hc=scols.get('H')
                code=next((c for c in std.columns if _normtxt(c) in {_normtxt('Code Product'),_normtxt('Code.Product')}),None)
                if dc and tc and hc and code:
                    sd=std.copy()
                    D=float(pd.to_numeric(pd.Series([r.get('D',0)]),errors='coerce').fillna(0).iloc[0]);T=float(pd.to_numeric(pd.Series([r.get('T',0)]),errors='coerce').fillna(0).iloc[0]);H=float(pd.to_numeric(pd.Series([r.get('H',0)]),errors='coerce').fillna(0).iloc[0])
                    for c in [dc,tc,hc]:sd[c]=pd.to_numeric(sd[c],errors='coerce')
                    sd['_dist']=((sd[dc]-D).abs()/max(D,1)+(sd[tc]-T).abs()/max(T,1)+(sd[hc]-H).abs()/max(H,1))
                    sd=sd.dropna(subset=['_dist']).sort_values('_dist')
                    if not sd.empty:
                        matchcode=str(sd.iloc[0][code]).strip()
                        pc=next((c for c in usage.columns if _normtxt(c) in {_normtxt('Product code'),_normtxt('Code Product'),_normtxt('รหัสสินค้า')}),None)
                        if pc:candidates=usage[usage[pc].astype(str).str.strip().eq(matchcode)].copy()
                        if not candidates.empty:method=f'SIZEWISE FALLBACK → {matchcode} — VERIFY'
        if candidates.empty:
            rows.append({'Work Order':r.get('Work Order'),'Customer':r.get('Customer'),'Product Code':item,'Packing Plan Date':r.get('Packing Plan Date'),
                         'Packing Plan Qty':qty,'Packaging Material':'UNRESOLVED','Required Qty':np.nan,'Match Method':'NO MATCH — MANUAL STANDARD REQUIRED','Risk':'CHECK'})
            continue
        u=candidates.iloc[0]
        woqty=float(pd.to_numeric(pd.Series([u.get('QTY',u.get('Qty',1))]),errors='coerce').fillna(1).iloc[0]) or 1
        for mc,qc in material_pairs:
            code=str(u.get(mc,'')).strip()
            per=float(pd.to_numeric(pd.Series([u.get(qc,0)]),errors='coerce').fillna(0).iloc[0])
            if code and code not in {'0','nan','NaN'} and per>0:
                rows.append({'Work Order':r.get('Work Order'),'Customer':r.get('Customer'),'Product Code':item,'Packing Plan Date':r.get('Packing Plan Date'),
                             'Packing Plan Qty':qty,'Packaging Material':code,'Required Qty':qty*per/woqty,'Match Method':method,'Risk':'VERIFY FALLBACK' if 'FALLBACK' in method else 'OK'})
    return pd.DataFrame(rows),tabs

def _diamond_plan(path, issue_path):
    """Map both the older Diamond history database and Planning's 16-09-2026
    reservation workbook. The current workbook is treated as the authoritative
    tooling/reservation view when its Sum sheet is present; no product→diamond
    usage relationship is invented.
    """
    if not path or not Path(path).exists():return pd.DataFrame()
    try:
        xls=pd.ExcelFile(path)
        if 'Sum' in xls.sheet_names:
            raw=pd.read_excel(path,sheet_name='Sum',header=2)
            if raw.shape[1] < 18:return pd.DataFrame()
            x=pd.DataFrame({
                'Code':raw.iloc[:,1].astype(str).str.strip(),
                'Category':raw.iloc[:,2], 'Tool':raw.iloc[:,3], 'Unit':raw.iloc[:,4],
                'Min Level':pd.to_numeric(raw.iloc[:,5],errors='coerce'),
                'Mid Level':pd.to_numeric(raw.iloc[:,6],errors='coerce'),
                'Max Level':pd.to_numeric(raw.iloc[:,7],errors='coerce'),
                'Warehouse Stock':pd.to_numeric(raw.iloc[:,12],errors='coerce'),
                'Reservation / Booking Signal':pd.to_numeric(raw.iloc[:,14],errors='coerce'),
                'Avg Monthly':pd.to_numeric(raw.iloc[:,15],errors='coerce')})
            x=x[x['Code'].notna() & ~x['Code'].isin(['','nan','None'])].copy()
            x['Stock']=x['Warehouse Stock'].fillna(0)
            x['Months Cover']=np.where(x['Avg Monthly'].fillna(0)>0,x['Stock']/x['Avg Monthly'],np.nan)
            x['Recommended Action']=np.select([x['Stock']<x['Min Level'].fillna(-np.inf),x['Stock']<x['Mid Level'].fillna(-np.inf),x['Months Cover'].notna()&(x['Months Cover']<1)],['URGENT — BELOW MIN','PLAN REPLENISH — BELOW MID','URGENT — <1 MONTH COVER'],default='MONITOR')
            x['Source']='Diamond reservation plan 16-09-2026 / Sum sheet'
            return x.sort_values(['Recommended Action','Months Cover'],na_position='last')
        usage=pd.read_excel(path,sheet_name='ปริมาณการใช้',header=1);stock=pd.read_excel(path,sheet_name='ยอดคงเหลือ Diamond',header=2)
        usage=usage.rename(columns={usage.columns[1]:'Code',usage.columns[3]:'Tool',usage.columns[4]:'Unit',usage.columns[17]:'Avg Monthly',usage.columns[20]:'Total Usage',usage.columns[21]:'Stock Legacy'})
        stock=stock.rename(columns={stock.columns[0]:'Code',stock.columns[2]:'Stock Tool',stock.columns[3]:'Stock Unit',stock.columns[4]:'Stock'})
        x=usage[['Code','Tool','Unit','Avg Monthly','Total Usage']].merge(stock[['Code','Stock']],on='Code',how='left');x['Avg Monthly']=pd.to_numeric(x['Avg Monthly'],errors='coerce').fillna(0);x['Stock']=pd.to_numeric(x['Stock'],errors='coerce').fillna(0);x['Months Cover']=np.where(x['Avg Monthly']>0,x['Stock']/x['Avg Monthly'],np.nan);x['Recommended Action']=np.select([x['Months Cover'].notna()&(x['Months Cover']<1),x['Months Cover'].notna()&(x['Months Cover']<2)],['URGENT REPLENISH','PLAN REPLENISH'],default='MONITOR');x['Source']='Legacy Diamond history';return x.sort_values(['Recommended Action','Months Cover'],na_position='last')
    except Exception:return pd.DataFrame()



# ---------- traceable monthly/yearly Daily Status parser ----------
_DAILY_STATUS_SECTION_HINTS=[
    ('เตรียม','Preparation'),('RAW MATERIAL','Preparation'),
    ('ผสม','Mixing'),('MIX','Mixing'),
    ('ขึ้นรูป','Forming'),('ชึ้นรูป','Forming'),('FORMING','Forming'),
    ('เตา','Firing'),('FIRING','Firing'),
    ('เจีย','Grinding'),('GRIND','Grinding'),
    ('PACK','Packing'),('บรรจุ','Packing')
]
def _status_section_from_file_sheet(filename,sheet,grid=None):
    from suite.daily_status_files import section_from_filename
    _numbered=section_from_filename(filename)
    if _numbered:return _numbered
    text=(str(filename)+' '+str(sheet)).upper()
    for k,v in _DAILY_STATUS_SECTION_HINTS:
        if k.upper() in text:return v
    if grid is not None:
        sample=' '.join(grid.astype(str).fillna('').head(8).values.ravel().tolist()).upper()
        for k,v in _DAILY_STATUS_SECTION_HINTS:
            if k.upper() in sample:return v
    return ''

def _parse_sheet_date(sheet,grid):
    m=re.fullmatch(r'\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\s*',str(sheet))
    if m:
        dd,mm,yy=map(int,m.groups())
        if len(m.group(3))==2: yy=2000+yy if yy<70 else 1900+yy
        elif len(m.group(3))==3:
            # A few supplied tabs truncate 2026 to 206; workbook-year inference
            # is applied by _daily_status_files before accepting those tabs.
            yy=0
        if yy:
            try:return datetime.date(yy,mm,dd)
            except ValueError:return None
    for fmt in ('%d-%m-%Y','%d/%m/%Y','%d.%m.%Y','%d-%m-%y','%d/%m/%y'):
        try:return pd.Timestamp(datetime.datetime.strptime(str(sheet).strip(),fmt)).date()
        except:pass
    return None

def _find_daily_header(grid):
    for i in range(min(15,len(grid))):
        vals=[str(v).strip() if pd.notna(v) else '' for v in grid.iloc[i].tolist()]
        joined='|'.join(vals).upper()
        if ('LOT NO' in joined or 'WORK ORDER' in joined or 'PRODUCTIONCODE' in joined) and ('PLAN(PCS)' in joined or 'ACTUAL(PCS)' in joined):
            return i
    return None

def _valid_wo(v):
    x=str(v or '').strip()
    if x=='' or x.lower() in {'nan','none','0'}:return False
    # Factory WO formats observed: P..., PB..., PBS..., PM..., PS..., including A/B suffixes.
    return bool(re.match(r'^(?:P|PB|PBS|PM|PS)[A-Z0-9-]*\d[A-Z0-9-]*$',x,re.I))

@st.cache_data(show_spinner=False)
def _plan_delivery_trace(path,mtime):
    """Read due dates and actual warehouse date from user-confirmed Plan-2026 fields."""
    try:
        x=pd.read_excel(path,sheet_name='แผนการเผา',header=None,skiprows=3,usecols=[0,2,4,5,9,10,151])
        x.columns=['Work Order','Initial Due Date (C)','Revised Due Date (E)','Customer','Order Qty','Product Code','Actual Warehouse Date (EV)']
        x=x.dropna(subset=['Work Order']).copy();x['Work Order']=x['Work Order'].astype(str).str.strip()
        x=x[x['Work Order'].map(_valid_wo)].copy();x['_WO_KEY']=x['Work Order'].str.upper().str.replace(r'[^A-Z0-9]','',regex=True)
        for c in ['Initial Due Date (C)','Revised Due Date (E)','Actual Warehouse Date (EV)']:
            x[c]=pd.to_datetime(x[c],errors='coerce',dayfirst=True)
        x['Order Qty']=pd.to_numeric(x['Order Qty'],errors='coerce')
        x['Plan Source Row']=x.index+4
        return x.drop_duplicates('_WO_KEY',keep='last')
    except Exception:return pd.DataFrame()

@st.cache_data(show_spinner=False)
def _daily_status_files(_uploads, source_fingerprint, fixed_override=None, date_cell_override="R1", data_start_row_override=5):
    """Controlled Daily Status import.
    Fixed business columns supplied by Planning take precedence over header guessing.
    Data begins at Excel row 5. Production date comes only from the dated worksheet tab.
    Blank/invalid WO rows never enter KPI calculations.

    The upload wrapper is deliberately excluded from Streamlit's cache key. A stable
    path/mtime/size/hash fingerprint detects real revisions, so repeated page reruns
    do not reopen every worksheet in every section workbook.
    """
    uploads=_uploads
    valid=[];rejected=[];errors=[]
    # zero-based Excel column addresses
    fixed={
      'Preparation': {'wo':1,'spec':2,'customer':3,'plan':13,'actual':14,'category':16,'plan_weight':17,'problem':18,'action':19},
      'Mixing':      {'wo':1,'spec':2,'customer':3,'plan':13,'actual':14,'category':16,'plan_weight':17,'problem':18,'action':19},
      'Forming':     {'wo':1,'spec':2,'customer':3,'plan':13,'actual':14,'category':16,'plan_weight':17,'problem':18,'action':19},
      'Firing':      {'wo':1,'spec':2,'customer':3,'plan':14,'actual':15,'category':17,'plan_weight':18,'problem':19,'action':20},
      'Grinding':    {'wo':1,'spec':2,'customer':3,'plan':13,'actual':14,'category':16,'plan_weight':17,'actual_weight':18,'problem':19,'action':20},
      'Packing':     {'wo':1,'spec':2,'customer':3,'plan':13,'actual':14,'category':16,'problem':17,'action':18},
    }
    if fixed_override:
        for _sec,_cfg in fixed_override.items():
            if _sec in fixed: fixed[_sec].update(_cfg)
    def _xlcol(addr):
        m=re.match(r'([A-Za-z]+)',str(addr or 'R1')); letters=m.group(1).upper() if m else 'R'
        n=0
        for ch in letters:n=n*26+(ord(ch)-64)
        return max(0,n-1)
    _date_col=_xlcol(date_cell_override)
    _data_start=max(1,int(data_start_row_override))-1
    for up in uploads or []:
        try:
            raw=up.getvalue();xls=pd.ExcelFile(io.BytesIO(raw))
        except Exception as e:
            errors.append({'Source File':getattr(up,'name',''),'Error':str(e)});continue
        _tab_dates=[]
        for _sn in xls.sheet_names:
            _mm=re.fullmatch(r'\s*\d{1,2}[-/.]\d{1,2}[-/.](\d{2,4})\s*',str(_sn))
            if _mm and len(_mm.group(1))==4:
                try:
                    _yy=int(_mm.group(1));_yy=_yy-543 if _yy>2400 else _yy
                    if 2000<=_yy<=2100:_tab_dates.append(_yy)
                except Exception:pass
        _default_tab_year=max(set(_tab_dates),key=_tab_dates.count) if _tab_dates else None
        for sh in xls.sheet_names:
            # Department workbooks also contain Cover, monthly plans, and category summaries.
            # Only dated production sheets are daily status evidence.
            if not re.fullmatch(r'\s*\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\s*',str(sh)):
                continue
            try:grid=xls.parse(sh,header=None,nrows=10000,usecols=range(21))
            except Exception as e:
                errors.append({'Source File':up.name,'Sheet':sh,'Error':str(e)});continue
            sec=_status_section_from_file_sheet(up.name,sh,grid)
            cfg=fixed.get(sec)
            if cfg is None:continue

            # The dated worksheet name is authoritative; date cells in these templates
            # can be stale or wrong. A truncated 3-digit year uses the workbook's
            # dominant valid tab year and remains visible in the sheet trace.
            day_value=_parse_sheet_date(sh,None)
            if day_value is None and _default_tab_year and re.search(r'[-/.]\d{3}\s*$',str(sh)):
                try:
                    _parts=re.fullmatch(r'\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{3})\s*',str(sh))
                    day_value=datetime.date(_default_tab_year,int(_parts.group(2)),int(_parts.group(1)))
                except Exception:day_value=None
            day=pd.to_datetime(day_value,errors='coerce')
            day=day.date() if pd.notna(day) else None

            # Header row is only used for fields not explicitly fixed by Planning.
            h=_find_daily_header(grid)
            hdr=[str(v).strip() if pd.notna(v) else '' for v in grid.iloc[h].tolist()] if h is not None else []
            def hcol(*keys):
                for j,c in enumerate(hdr):
                    u=c.upper().replace(' ','')
                    for k in keys:
                        if k.upper().replace(' ','') in u:return j
                return None
            cdue=hcol('DUE DATE','กำหนดเข้าคลัง','กำหนดส่ง')
            cprogram=12 if sec=='Firing' else hcol('โปรแปรมเผา','PROGRAM')
            ckiln=13 if sec=='Firing' else hcol('เตาที่/ครั้งที่','KILN')

            def cell(row,idx):
                return row.iloc[idx] if idx is not None and idx<len(row) else np.nan
            # Excel row 5 = pandas row index 4. Never read template/header rows as production records.
            for ridx in range(_data_start,len(grid)):
                row=grid.iloc[ridx]
                wo=cell(row,cfg['wo'])
                rec={
                  'Date':day,'Section':sec,
                  'Work Order':str(wo).strip() if pd.notna(wo) else '',
                  'Specification':str(cell(row,cfg.get('spec'))).strip() if pd.notna(cell(row,cfg.get('spec'))) else '',
                  'Customer':str(cell(row,cfg.get('customer'))).strip() if pd.notna(cell(row,cfg.get('customer'))) else '',
                  'Production Plan Qty':pd.to_numeric(cell(row,cfg['plan']),errors='coerce'),
                  'Production Actual Qty':pd.to_numeric(cell(row,cfg['actual']),errors='coerce'),
                  'Section Required Qty':pd.to_numeric(cell(row,4),errors='coerce'),
                  'Cumulative Actual Qty':pd.to_numeric(cell(row,6),errors='coerce'),
                  'Balance Qty':pd.to_numeric(cell(row,7),errors='coerce'),
                  'Product Category':str(cell(row,cfg['category'])).strip().upper() if pd.notna(cell(row,cfg['category'])) else '',
                  'Planned Weight':pd.to_numeric(cell(row,cfg.get('plan_weight')),errors='coerce'),
                  'Actual Weight':pd.to_numeric(cell(row,cfg.get('actual_weight')),errors='coerce'),
                  'Problem':str(cell(row,cfg['problem'])).strip() if pd.notna(cell(row,cfg['problem'])) else '',
                  'Production Action':str(cell(row,cfg['action'])).strip() if pd.notna(cell(row,cfg['action'])) else '',
                  'Production Due Date':cell(row,cdue),
                  'Firing Program':str(cell(row,cprogram)).strip() if pd.notna(cell(row,cprogram)) else '',
                  'Kiln':str(cell(row,ckiln)).strip() if pd.notna(cell(row,ckiln)) else '',
                  'Date Source':'Worksheet name; year inferred from sibling tabs' if re.search(r'[-/.]\d{3}\s*$',str(sh)) else 'Worksheet name',
                  'Source File':getattr(up,'original_name',up.name),'Source Stored File':up.name,'Source Sheet':str(sh),'Source Row':ridx+1
                }
                payload=[rec['Production Plan Qty'],rec['Production Actual Qty'],rec['Section Required Qty'],rec['Cumulative Actual Qty'],rec['Balance Qty'],rec['Problem'],rec['Production Action'],rec['Product Category'],rec['Planned Weight'],rec['Actual Weight']]
                has_payload=any(pd.notna(x) and str(x).strip() not in {'','nan','None'} for x in payload)
                if _valid_wo(rec['Work Order']):valid.append(rec)
                elif has_payload:
                    rec['Reject Reason']='INVALID / BLANK WORK ORDER — EXCLUDED FROM ALL KPI'
                    rejected.append(rec)
    v=pd.DataFrame(valid);r=pd.DataFrame(rejected);e=pd.DataFrame(errors)
    if not v.empty:
        v['Date']=pd.to_datetime(v['Date'],errors='coerce').dt.normalize()
        for c in ['Production Plan Qty','Production Actual Qty','Planned Weight','Actual Weight']:
            v[c]=pd.to_numeric(v[c],errors='coerce')
        v['Production Plan Qty']=v['Production Plan Qty'].fillna(0)
        v['Production Actual Qty']=v['Production Actual Qty'].fillna(0)
        v['Product Category']=v['Product Category'].replace({'':'UNCLASSIFIED','NAN':'UNCLASSIFIED'})
        v=v.drop_duplicates(subset=['Section','Date','Work Order','Source Sheet','Source Row'],keep='last')
    return v,r,e

def _english_factory_text(v):
    """Offline factory-English normalization for Daily Status reason/action.
    Original Thai is preserved separately; this column is for management analysis.
    Unknown Thai is explicitly marked for review rather than silently mistranslated.
    """
    t=str(v or '').strip()
    if not t:return ''
    repl={
      'เครื่องเสีย':'Machine breakdown','เครื่องจักรเสีย':'Machine breakdown','เครื่องมีปัญหา':'Machine problem',
      'รอวัตถุดิบ':'Waiting for raw material','วัตถุดิบไม่พอ':'Insufficient raw material','วัตถุดิบขาด':'Raw material shortage',
      'รอของ':'Waiting for material/parts','รอชิ้นงาน':'Waiting for parts','งานไม่มา':'Parts not available',
      'คนไม่พอ':'Insufficient manpower','พนักงานไม่พอ':'Insufficient manpower','ขาดคน':'Manpower shortage',
      'งานด่วน':'Urgent work','แทรกงานด่วน':'Urgent job inserted','เปลี่ยนแผน':'Plan changed','เปลี่ยนแผนการผลิต':'Production plan changed',
      'รอซ่อม':'Waiting for repair','ซ่อมเครื่อง':'Repair machine','แก้ไขเครื่อง':'Correct/repair machine',
      'ไฟดับ':'Power outage','ไฟตก':'Power interruption','เตาเสีย':'Kiln breakdown','รอเตา':'Waiting for kiln',
      'รอเผา':'Waiting for firing','รอขึ้นรูป':'Waiting for forming','รอผสม':'Waiting for mixing','รอบรรจุ':'Waiting for packing',
      'งานเสีย':'Defect/reject','ของเสีย':'Defect/reject','แตก':'Cracked/broken','เสียรูป':'Deformation',
      'ผลิตไม่ทัน':'Production could not meet plan','ทำไม่ทัน':'Could not complete to plan','ไม่ทันแผน':'Behind plan',
      'เพิ่มโอที':'Add overtime','ทำโอที':'Use overtime','โอที':'Overtime',
      'เร่งผลิต':'Expedite production','ติดตาม':'Follow up','ติดตามงาน':'Follow up production',
      'แก้ไข':'Corrective action','ปรับแผน':'Revise production plan','ย้ายเครื่อง':'Move to alternate machine',
      'เสร็จ':'Completed','ปิดใบสั่ง':'Work order/process closed','ยังไม่ปิด':'Process not finished'
    }
    out=t
    for th,en in sorted(repl.items(),key=lambda z:-len(z[0])):out=out.replace(th,en)
    if re.search(r'[ก-๙]',out):
        # Keep management English clean. Original Thai remains in Problem / Production Action columns.
        # Translate common factory tokens even inside longer phrases; unresolved Thai is labelled concisely.
        cleaned=re.sub(r'[ก-๙]+',' ',out)
        cleaned=re.sub(r'\s+',' ',cleaned).strip(' -:/')
        return cleaned if cleaned else 'Translation needed — see original Thai'
    return out

def _crosscheck_ppc_production_actual(status,plans,master):
    if status is None or status.empty:return pd.DataFrame()
    x=status.copy()
    # MERGE-KEY CONTRACT: both sides use the same normalized pandas datetime dtype.
    # Do not mix Python date objects with datetime64[s/ns] (pandas 3 / Python 3.14 is stricter).
    x['Date']=pd.to_datetime(x.get('Date'),errors='coerce').dt.normalize()
    x['Section']=x.get('Section',pd.Series('',index=x.index)).fillna('').astype(str).str.strip()
    x['Work Order']=x.get('Work Order',pd.Series('',index=x.index)).fillna('').astype(str).str.strip()
    pp=plans.copy() if isinstance(plans,pd.DataFrame) else pd.DataFrame()
    if not pp.empty:
        pp['_Date']=pd.to_datetime(pp['Plan Date'],errors='coerce').dt.normalize()
        pp['Section']=pp.get('Section',pd.Series('',index=pp.index)).fillna('').astype(str).str.strip()
        pp['Work Order']=pp.get('Work Order',pd.Series('',index=pp.index)).fillna('').astype(str).str.strip()
        ppg=pp.groupby(['_Date','Section','Work Order'],as_index=False,dropna=False)['Plan Qty'].sum().rename(columns={'_Date':'Date','Plan Qty':'PPC Issued Plan Qty'})
        # Defensive dtype normalization immediately before merge.
        ppg['Date']=pd.to_datetime(ppg['Date'],errors='coerce').dt.normalize()
        x=x.merge(ppg,on=['Date','Section','Work Order'],how='left',validate='many_to_one')
    else:x['PPC Issued Plan Qty']=np.nan
    mm=master.copy() if isinstance(master,pd.DataFrame) else pd.DataFrame()
    if not mm.empty:
        keep=[c for c in ['Work Order','Due Date','Category','Customer'] if c in mm.columns]
        if keep:
            mm=mm[keep].drop_duplicates('Work Order')
            x=x.merge(mm,on='Work Order',how='left',suffixes=('',' Master'))
    x['Category']=x.get('Category',x.get('Product Category','')).fillna(x.get('Product Category','')).astype(str).str.upper()
    x['PPC Issued Plan Qty']=pd.to_numeric(x['PPC Issued Plan Qty'],errors='coerce')
    x['Production Plan Qty']=pd.to_numeric(x['Production Plan Qty'],errors='coerce').fillna(0)
    x['Production Actual Qty']=pd.to_numeric(x['Production Actual Qty'],errors='coerce').fillna(0)
    x['PPC→Production Variance']=x['Production Plan Qty']-x['PPC Issued Plan Qty']
    x['Production→Actual Variance']=x['Production Actual Qty']-x['Production Plan Qty']
    x['PPC Plan Adherence %']=np.where(x['PPC Issued Plan Qty']>0,x['Production Plan Qty']/x['PPC Issued Plan Qty']*100,np.nan)
    x['Production Achievement %']=np.where(x['Production Plan Qty']>0,x['Production Actual Qty']/x['Production Plan Qty']*100,np.nan)
    x['Miss Qty']=(x['Production Plan Qty']-x['Production Actual Qty']).clip(lower=0)
    x['Problem English']=x.get('Problem','').apply(_english_factory_text)
    x['Action English']=x.get('Production Action','').apply(_english_factory_text)
    x['Reason Quality']=np.where(x['Miss Qty']<=0,'N/A',np.where(x['Problem'].astype(str).str.strip().eq(''),'MISSING REASON','REASON PROVIDED'))
    x['Action Quality']=np.where(x['Miss Qty']<=0,'N/A',np.where(x['Production Action'].astype(str).str.strip().eq(''),'MISSING ACTION','ACTION PROVIDED'))
    x['PPC Recommended Action']=np.where(x['Miss Qty']<=0,'',
        np.where(x['Problem'].astype(str).str.strip().eq(''),'Obtain root cause + owner + recovery quantity/date.',
        np.where(x['Production Action'].astype(str).str.strip().eq(''),'Define corrective action + recovery date; check due-date impact.',
                 'Verify action closes the quantity gap and protects due date.')))
    return x

def _daily_status_summary(cx):
    if cx is None or cx.empty:return pd.DataFrame()
    rows=[]
    for (sec,cat),g in cx.groupby(['Section','Category'],dropna=False):
        p=float(g['Production Plan Qty'].sum());a=float(g['Production Actual Qty'].sum())
        pp=float(g['PPC Issued Plan Qty'].fillna(0).sum())
        rows.append({'Section':sec,'Product Category':cat,'Production Plan pcs':p,'Actual pcs':a,
                     'Qty Achievement %':a/p*100 if p>0 else np.nan,
                     'Planned WOs':g.loc[g['Production Plan Qty']>0,'Work Order'].nunique(),
                     'WOs Achieving Plan':g.loc[(g['Production Plan Qty']>0)&(g['Production Actual Qty']>=g['Production Plan Qty']),'Work Order'].nunique(),
                     'Under-plan Records':int((g['Miss Qty']>0).sum()),
                     'PPC Plan pcs matched':pp,
                     'PPC→Production Adherence %':p/pp*100 if pp>0 else np.nan,
                     'Missing Reasons':int(((g['Miss Qty']>0)&g['Problem'].astype(str).str.strip().eq('')).sum()),
                     'Missing Actions':int(((g['Miss Qty']>0)&g['Production Action'].astype(str).str.strip().eq('')).sum())})
    return pd.DataFrame(rows)


# ---------- optional daily actual input ----------
def _normalize_section(v):
    s=str(v or '').strip().upper().replace('&','/').replace('  ',' ')
    aliases={'PREP':'Preparation','PREPARATION':'Preparation','MIX':'Mixing','MIXING':'Mixing','FORM':'Forming','FORMING':'Forming','FIRE':'Firing','FIRING':'Firing',
             'QC':'QC / ตรวจสอบคุณภาพ','QUALITY':'QC / ตรวจสอบคุณภาพ','GRINDING':'Grinding / เจียร','CUTTING':'Cutting / ตัด',
             'GRINDING / CUTTING':'ROUTE REQUIRED / ต้องเลือก เจียร หรือ ตัด','GRINDING/CUTTING':'ROUTE REQUIRED / ต้องเลือก เจียร หรือ ตัด','PACK':'Packing','PACKING':'Packing'}
    return aliases.get(s,str(v or '').strip())

def _read_actual_upload(up):
    if up is None:return pd.DataFrame()
    try:
        b=up.getvalue()
        d=pd.read_csv(io.BytesIO(b)) if up.name.lower().endswith('.csv') else pd.read_excel(io.BytesIO(b))
        return d
    except Exception:return pd.DataFrame()

def _actual_table(seed, master, planrows):
    cols=['Date','Section','Work Order','Actual Qty','Actual ton']
    d=seed.copy() if isinstance(seed,pd.DataFrame) else pd.DataFrame(columns=cols)
    rename={}
    for c in d.columns:
        k=str(c).strip().lower()
        if k in ['date','plan date','production date','actual date']:rename[c]='Date'
        elif k in ['section','process','department']:rename[c]='Section'
        elif k in ['work order','wo','productioncode']:rename[c]='Work Order'
        elif k in ['actual qty','qty','actual pcs','pcs']:rename[c]='Actual Qty'
        elif k in ['actual ton','actual t','ton','tons']:rename[c]='Actual ton'
    d=d.rename(columns=rename)
    for c in cols:
        if c not in d.columns:d[c]=None
    return d[cols]

def _aggregate_actual(d,master,planrows):
    if d is None or d.empty:return pd.DataFrame(columns=['Plan Date','Section','Actual pcs','Actual ton','Actual WOs'])
    x=d.copy();x['Plan Date']=pd.to_datetime(x['Date'],errors='coerce').dt.date;x['Section']=x['Section'].apply(_normalize_section)
    x['Actual Qty']=pd.to_numeric(x['Actual Qty'],errors='coerce').fillna(0);x['Actual ton']=pd.to_numeric(x['Actual ton'],errors='coerce')
    pm={}
    if planrows is not None and not planrows.empty:
        for _,r in planrows.iterrows():
            q=float(pd.to_numeric(pd.Series([r.get('Plan Qty',0)]),errors='coerce').fillna(0).iloc[0]);kg=float(pd.to_numeric(pd.Series([r.get('Plan kg',0)]),errors='coerce').fillna(0).iloc[0])
            if q>0:pm[(str(r.get('Work Order','')).strip(),str(r.get('Section','')).strip())]=kg/q/1000.0 # ton/pc
    mm={}
    if master is not None and not master.empty:
        for _,r in master.iterrows():mm[str(r.get('Work Order','')).strip()]=r
    vals=[]
    for _,r in x.iterrows():
        at=r.get('Actual ton');q=float(r.get('Actual Qty',0));wo=str(r.get('Work Order','')).strip();sec=str(r.get('Section','')).strip()
        if pd.isna(at):
            tonpc=pm.get((wo,sec))
            if tonpc is None:
                mr=mm.get(wo,{});wg=float(pd.to_numeric(pd.Series([mr.get('Gross Weight g/pc',0) if sec=='Firing' else mr.get('Net Weight g/pc',0)]),errors='coerce').fillna(0).iloc[0]);tonpc=wg/1e6
            at=q*tonpc
        vals.append(float(at or 0))
    x['Actual ton']=vals
    x=x[x['Plan Date'].notna() & x['Section'].ne('')]
    return x.groupby(['Plan Date','Section'],as_index=False).agg(**{'Actual pcs':('Actual Qty','sum'),'Actual ton':('Actual ton','sum'),'Actual WOs':('Work Order',lambda z:z.astype(str).str.strip().replace('',pd.NA).dropna().nunique())})

def _merge_override_row(base, row):
    """Merge one WO override without losing previously saved machine/data corrections."""
    b=base.copy() if isinstance(base,pd.DataFrame) else pd.DataFrame()
    r=pd.DataFrame([row])
    if b.empty:return r
    wo=str(row.get('Work Order','')).strip()
    b=b[b['Work Order'].astype(str).str.strip().ne(wo)] if 'Work Order' in b.columns else b
    return pd.concat([b,r],ignore_index=True,sort=False)


def _configure_thai_font():
    """Use an installed Thai-capable font for charts/JPEG. No font file is distributed."""
    candidates=[
        r'C:\\Windows\\Fonts\\tahoma.ttf',r'C:\\Windows\\Fonts\\leelawui.ttf',r'C:\\Windows\\Fonts\\LeelUIsl.ttf',
        '/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf','/usr/share/fonts/opentype/tlwg/Tahoma.ttf','/usr/share/fonts/opentype/tlwg/Garuda.ttf']
    for fp in candidates:
        try:
            if Path(fp).exists():
                fm.fontManager.addfont(fp); name=fm.FontProperties(fname=fp).get_name();plt.rcParams['font.family']=name;return name
        except Exception: pass
    # Last resort: Windows usually resolves Tahoma; DejaVu remains fallback for Latin.
    plt.rcParams['font.family']=['Tahoma','Leelawadee UI','DejaVu Sans'];return 'Tahoma'

THAI_FONT_NAME=_configure_thai_font()

CATEGORY_COLORS={'P':'#2563eb','R':'#dc2626','S':'#16a34a','T':'#f59e0b','M':'#7c3aed','PB':'#0891b2','UNCLASSIFIED':'#6b7280'}

def _common_postfire(df):
    """Never display a combined Grinding/Cutting process. Internal Plan2026 fields may
    share source columns, but each WO is displayed as exactly one confirmed route.
    """
    if not isinstance(df,pd.DataFrame):return df
    x=df.copy()
    sec_col='Section' if 'Section' in x.columns else ('Section / กระบวนการ' if 'Section / กระบวนการ' in x.columns else None)
    if sec_col is not None:
        m=x[sec_col].astype(str).str.contains('Grinding.?/?.?Cutting|Grinding / Cutting|Grinding/Cutting',case=False,regex=True,na=False)
        if m.any():
            route=x.get('Post-Firing Route',pd.Series('',index=x.index)).fillna('').astype(str)
            x.loc[m & route.str.contains('CUT',case=False,na=False),sec_col]='Cutting / ตัด'
            x.loc[m & ~route.str.contains('CUT',case=False,na=False),sec_col]='Grinding / เจียร'
    return x

def _collapse_caps(c):
    """Keep each date/process unit intact; prior code dropped pcs capacity."""
    return _collapse_capacities_view(c)

def _wip_long(w):
    """Queue view with Grinding and Cutting separated by confirmed WO route."""
    if w is None or w.empty:return pd.DataFrame()
    x=w.copy();x['Product Category']=x['Category'].apply(eng.normcat)
    kgpc=pd.to_numeric(x.get('Net Weight g/pc',0),errors='coerce').fillna(0)/1000.0
    specs=[
        ('Preparation Required','Open Demand / Preparation Required','WIP Preparation','OPEN DEMAND - not yet prepared',None),
        ('Mixing','Ready for Mixing','WIP Mixing','Prepared, waiting Mixing',None),
        ('Forming','Ready for Forming','WIP Forming','Mixed, waiting Forming',None),
        ('Firing','Ready for Firing','WIP Firing','Formed, waiting Firing',None),
        ('Grinding','Ready for Grinding / Cutting','WIP Grinding / Cutting','Fired, waiting Grinding','Grinding'),
        ('Cutting','Ready for Grinding / Cutting','WIP Grinding / Cutting','Fired, waiting Cutting','Cutting'),
        ('Packing','Ready for Packing','WIP Packing','Ground/Cut/direct-route quantity waiting Packing',None)]
    routes=x.apply(dl.route,axis=1)
    out=[]
    for sec,col,legacy,definition,route_req in specs:
        q=pd.to_numeric(x[col] if col in x.columns else x.get(legacy,0),errors='coerce').fillna(0)
        route_mask=pd.Series(True,index=x.index)
        if route_req=='Grinding': route_mask=routes.astype(str).str.startswith('Grinding')
        elif route_req=='Cutting': route_mask=routes.astype(str).str.startswith('Cutting')
        for cat in ['P','R','S','T','M','PB','UNCLASSIFIED']:
            m=x['Product Category'].eq(cat)&route_mask
            pcs=float(q[m].sum());ton=float((q[m]*kgpc[m]).sum()/1000.0)
            out.append({'Section':sec,'Category':cat,'WIP pcs':pcs,'WIP ton':ton,
                        'Work Orders':int(x.loc[m & q.gt(0),'Work Order'].astype(str).nunique()),'Definition':definition})
    return pd.DataFrame(out)


def _monthly_open_closed(master, as_of=None):
    """Shared overdue-only month summary; future open demand is never called backorder."""
    d=overdue_backorders(master, as_of or bkk_today())
    if d.empty:return pd.DataFrame(columns=['Due Month','Status','Qty pcs','WOs'])
    return d.groupby('Due Month',as_index=False).agg(**{'Qty pcs':('pcs','sum'),'WOs':('Work Order','nunique')}).assign(Status='OVERDUE OPEN').sort_values('Due Month')

def _process_risk_matrix(master, risk):
    """Risk quantity for ALL product categories x PPC processes, not only one bottleneck label."""
    cats=['P','R','S','T','M','PB']; procs=['Preparation','Mixing','Forming','Firing','Grinding / เจียร','Cutting / ตัด','Packing']
    if master is None or master.empty:return pd.DataFrame([{'Process':p,'Product Category':c,'Risk Qty pcs':0.0} for p in procs for c in cats])
    m=master.copy(); riskwo=set(risk['Work Order'].astype(str)) if isinstance(risk,pd.DataFrame) and not risk.empty and 'Work Order' in risk.columns else set()
    if riskwo:m=m[m['Work Order'].astype(str).isin(riskwo)].copy()
    rows=[]
    for _,r in m.iterrows():
        cat=str(r.get('Category','')).strip().upper()
        if cat not in cats:continue
        oq=float(pd.to_numeric(pd.Series([r.get('Order Qty',0)]),errors='coerce').fillna(0).iloc[0])
        _route=dl.route(r)
        eff={'Preparation':r.get('Eff Preparation',r.get('Preparation Actual',0)), 'Mixing':r.get('Eff Mixing',r.get('Mixing Actual',0)), 'Forming':r.get('Eff Forming',r.get('Forming Actual',0)), 'Firing':r.get('Eff Firing',r.get('Firing Actual',0)), 'Packing':r.get('Eff Packing',r.get('Packing Actual',0))}
        _post=r.get('Eff Grinding / Cutting',r.get('Grinding / Cutting Actual',0))
        for proc in procs:
            if proc=='Grinding / เจียร' and not str(_route).startswith('Grinding'):continue
            if proc=='Cutting / ตัด' and not str(_route).startswith('Cutting'):continue
            donev=_post if proc in ['Grinding / เจียร','Cutting / ตัด'] else eff[proc]
            done=float(pd.to_numeric(pd.Series([donev]),errors='coerce').fillna(0).iloc[0]); rem=max(oq-done,0)
            rows.append({'Process':proc,'Product Category':cat,'Risk Qty pcs':rem})
    d=pd.DataFrame(rows)
    if not d.empty:d=d.groupby(['Process','Product Category'],as_index=False)['Risk Qty pcs'].sum()
    full=pd.MultiIndex.from_product([procs,cats],names=['Process','Product Category']).to_frame(index=False)
    return full.merge(d,on=['Process','Product Category'],how='left').fillna({'Risk Qty pcs':0})

def _wo_encoded_date(wo):
    """Read controlled WO date token DDMMYY, e.g. PM006A-011125-1 -> 2025-11-01."""
    try:
        m=re.search(r'-(\d{6})(?:-|$)',str(wo).strip())
        if not m:return pd.NaT
        return pd.to_datetime(m.group(1),format='%d%m%y',errors='coerce')
    except Exception:return pd.NaT

def _reporting_order_type(df):
    """Existing planner convention: TEST first; PM/PBM normal work is stock/MPS, remainder MTO."""
    x=df.copy()
    cls=_wo_class_table(x)
    if 'Work Order' in x.columns and not cls.empty:
        x=x.merge(cls[['Work Order','Order Type']],on='Work Order',how='left',suffixes=('','_cls'))
    ot=x.get('Order Type',pd.Series('NORMAL',index=x.index)).fillna('NORMAL').astype(str).str.upper()
    wo=x.get('Work Order',pd.Series('',index=x.index)).astype(str).str.upper().str.strip()
    x['Product Type']=np.where(ot.str.contains('TEST'),'TEST',np.where(wo.str.startswith(('PM','PBM')),'MTS / MPS','MTO'))
    return x

def _backorder_month_category(master):
    """Shared overdue-only month/category series used by all Daily Planner backorder views."""
    d=overdue_month_category(master, bkk_today())
    if d.empty:return d
    d['Weight kg']=pd.to_numeric(d['Weight ton'],errors='coerce').fillna(0)*1000.0
    return d

def _complete_gantt_rows(master, allp, wo_list, start_date):
    """One row for every applicable PPC process: PASSED, CURRENT or WAITING. QC deliberately excluded."""
    procs=['Preparation','Mixing','Forming','Firing','Grinding / เจียร','Cutting / ตัด','Packing']; out=[]
    if master is None or master.empty:return pd.DataFrame()
    mm=master[master['Work Order'].astype(str).isin(set(map(str,wo_list)))].copy()
    ap=allp.copy() if isinstance(allp,pd.DataFrame) else pd.DataFrame()
    for wo,g in mm.groupby(mm['Work Order'].astype(str)):
        r=g.iloc[0]; oq=float(pd.to_numeric(pd.Series([r.get('Order Qty',0)]),errors='coerce').fillna(0).iloc[0]); due=pd.to_datetime(r.get('Due Date'),errors='coerce')
        route=dl.route(r)
        for proc in procs:
            if proc=='Grinding / เจียร' and not str(route).startswith('Grinding'):continue
            if proc=='Cutting / ตัด' and not str(route).startswith('Cutting'):continue
            actkey={'Preparation':'Eff Preparation','Mixing':'Eff Mixing','Forming':'Eff Forming','Firing':'Eff Firing','Packing':'Eff Packing'}.get(proc,'Eff Grinding / Cutting')
            act=float(pd.to_numeric(pd.Series([r.get(actkey,r.get('Grinding / Cutting Actual',0) if proc in ['Grinding / เจียร','Cutting / ตัด'] else r.get(proc+' Actual',0))]),errors='coerce').fillna(0).iloc[0])
            pg=ap[(ap.get('Work Order',pd.Series('',index=ap.index)).astype(str)==str(wo)) & (ap.get('Section',pd.Series('',index=ap.index)).astype(str)==proc)].copy() if not ap.empty else pd.DataFrame()
            pdates=pd.to_datetime(pg.get('Plan Date',pd.Series(dtype='datetime64[ns]')),errors='coerce').dropna() if not pg.empty else pd.Series(dtype='datetime64[ns]')
            exp=pdates.max() if not pdates.empty else pd.NaT
            if oq>0 and act>=oq-1e-9: status='PASSED / ผ่านแล้ว'; end=pd.Timestamp(start_date); begin=end-pd.Timedelta(days=1)
            elif act>0: status='CURRENT / กำลังดำเนินการ'; begin=pd.Timestamp(start_date); end=exp if pd.notna(exp) and exp>=begin else begin+pd.Timedelta(days=1)
            else: status='WAITING / รอ'; begin=pdates.min() if not pdates.empty else pd.Timestamp(start_date); end=exp if pd.notna(exp) and exp>=begin else begin+pd.Timedelta(days=1)
            out.append({'Work Order':str(wo),'Customer':r.get('Customer',''),'Product Category':str(r.get('Category','')),'Process':proc,'Status':status,'Actual pcs':act,'Order pcs':oq,'Expected Finish':exp,'Due Date':due,'Gantt Start':begin,'Gantt End':end})
    return pd.DataFrame(out)

def _dashboard_jpeg(allp,risk,wip,start_date,caps=None,stock=None,master=None):
    """2560x1440 management/shopfloor board. Delivery targets come from Plan2026 Due Date, not generated Packing plan."""
    from datetime import timedelta
    fig=plt.figure(figsize=(25.6,14.4),dpi=100)
    gs=fig.add_gridspec(5,4,height_ratios=[0.68,1.35,1.55,1.55,1.9],hspace=.70,wspace=.30)
    p=allp.copy() if isinstance(allp,pd.DataFrame) else pd.DataFrame()
    rr=risk.copy() if isinstance(risk,pd.DataFrame) else pd.DataFrame()
    ww=wip.copy() if isinstance(wip,pd.DataFrame) else pd.DataFrame()
    mm=master.copy() if isinstance(master,pd.DataFrame) else pd.DataFrame()
    tomorrow=(pd.Timestamp(start_date)+pd.Timedelta(days=1)).date()
    while pd.Timestamp(tomorrow).weekday()==6:
        tomorrow=(pd.Timestamp(tomorrow)+pd.Timedelta(days=1)).date()

    def _master_delivery(day):
        if mm.empty or 'Due Date' not in mm.columns:return pd.DataFrame()
        d=mm.copy();d['_due']=pd.to_datetime(d['Due Date'],errors='coerce').dt.date
        closed=d.get('Overall Closed',pd.Series(False,index=d.index)).fillna(False).astype(bool)
        d=d[d['_due'].eq(day)&~closed].copy()
        if d.empty:return d
        oq=pd.to_numeric(d.get('Order Qty',0),errors='coerce').fillna(0)
        pa=pd.to_numeric(d.get('Packing Actual Qty',d.get('Packing Actual',0)),errors='coerce').fillna(0)
        d['_open']=pd.to_numeric(d.get('Remaining Packing',oq-pa),errors='coerce').fillna(0).clip(lower=0)
        # one row per WO; prevent duplicate process/master rows multiplying delivery.
        agg={'_open':'max'}
        for c in ['Customer','Category','Due Date']:
            if c in d.columns:agg[c]='first'
        d=d.groupby('Work Order',as_index=False).agg(agg)
        return d.sort_values(['Due Date','Work Order'],na_position='last') if 'Due Date' in d.columns else d

    tdue=_master_delivery(start_date); ndue=_master_delivery(tomorrow)
    today_del=int(tdue['_open'].sum()) if not tdue.empty else 0
    tom_del=int(ndue['_open'].sum()) if not ndue.empty else 0

    ax=fig.add_subplot(gs[0,:]);ax.axis('off')
    ax.text(.01,.72,f'SL CARBORUNDUM — PPC DAILY CONTROL BOARD   {start_date:%d %b %Y}',fontsize=30,fontweight='bold')
    ax.text(.01,.32,'Due date first → executable capacity → pull feasible work → linked firing/post-firing/packing flow',fontsize=17)
    planpcs=float(pd.to_numeric(p.get('Plan Qty',0),errors='coerce').fillna(0).sum()) if not p.empty else 0
    planton=float(pd.to_numeric(p.get('Plan ton',0),errors='coerce').fillna(0).sum()) if not p.empty else 0
    high=int((rr.get('Delivery Risk',pd.Series(dtype=str)).astype(str).str.upper()=='HIGH').sum()) if not rr.empty else 0
    openw=int((~mm.get('Overall Closed',pd.Series(False,index=mm.index)).fillna(False).astype(bool)).sum()) if not mm.empty else 0
    kpis=[('PLAN',f'{planpcs:,.0f} pcs / {planton:,.1f} t'),('OPEN WO',f'{openw:,}'),('HIGH RISK',f'{high:,}'),
          ('PLAN2026 DUE TODAY',f'{today_del:,} pcs'),('PLAN2026 DUE NEXT WORKDAY',f'{tom_del:,} pcs')]
    x=.01
    for lab,val in kpis:
        ax.text(x,.04,f'{lab}: {val}',fontsize=15,fontweight='bold',transform=ax.transAxes);x+=.195

    def _borderless_table(ax,d,title):
        ax.axis('off');ax.set_title(title,loc='left',fontweight='bold',fontsize=18,pad=10)
        if d.empty:
            ax.text(.02,.70,'No open Plan2026 WO due on this date.',fontsize=14);return
        rows=[]
        for _,r in d.head(9).iterrows():
            rows.append([str(r.get('Work Order',''))[:16],str(r.get('Customer',''))[:24],
                         f"{float(r.get('_open',0)):,.0f}",str(r.get('Due Date',''))[:10]])
        tab=ax.table(cellText=rows,colLabels=['WO','CUSTOMER','OPEN PCS','DUE DATE'],loc='upper left',
                     cellLoc='left',colLoc='left',bbox=[0,.01,1,.88],colWidths=[.25,.39,.15,.21])
        tab.auto_set_font_size(False);tab.set_fontsize(13);tab.scale(1,1.35)
        for (ri,ci),cell in tab.get_celld().items():
            cell.set_linewidth(0);cell.set_edgecolor('none');cell.PAD=.08
            cell.get_text().set_fontfamily(THAI_FONT_NAME)
            if ri==0:cell.get_text().set_weight('bold')
    _borderless_table(fig.add_subplot(gs[1,0:2]),tdue,'TODAY — PLAN 2026 DUE DELIVERY / OPEN PACKING')
    _borderless_table(fig.add_subplot(gs[1,2:4]),ndue,'NEXT WORKDAY — PLAN 2026 DUE DELIVERY / OPEN PACKING')

    axw=fig.add_subplot(gs[2,0:2]);wl=_wip_long(ww);order=['Preparation Required','Mixing','Forming','Firing','Grinding','Cutting','Packing']
    if not wl.empty:
        tot=wl.groupby('Section',as_index=False)['WIP pcs'].sum();tot['Section']=pd.Categorical(tot['Section'],categories=order,ordered=True);tot=tot.sort_values('Section')
        bars=axw.bar(tot['Section'].astype(str),tot['WIP pcs'])
        for b,v in zip(bars,tot['WIP pcs']):axw.text(b.get_x()+b.get_width()/2,b.get_height(),f'{v:,.0f}',ha='center',va='bottom',fontsize=12)
    axw.set_title('PLAN-2026 PLANNING WIP / QUEUE — PLANNED PCS BY PROCESS',fontweight='bold');axw.tick_params(axis='x',rotation=24);axw.set_ylabel('pcs')

    axc=fig.add_subplot(gs[2,2:4])
    if not p.empty:
        _pdte=pd.to_datetime(p.get('Plan Date'),errors='coerce').dt.date;_td=p[_pdte.eq(start_date)].copy()
        if not _td.empty:
            _td['_qty']=pd.to_numeric(_td.get('Plan Qty',0),errors='coerce').fillna(0)
            _sec=_td.groupby('Section',as_index=False)['_qty'].sum().sort_values('_qty',ascending=False);_major=[]
            for sec in _sec['Section']:
                g=_td[_td['Section'].astype(str).eq(str(sec))].groupby('Customer',as_index=False)['_qty'].sum().sort_values('_qty',ascending=False)
                _major.append(str(g.iloc[0]['Customer'])[:18] if not g.empty else '')
            bars=axc.bar(_sec['Section'].astype(str),_sec['_qty'])
            for b,v,cust in zip(bars,_sec['_qty'],_major):axc.text(b.get_x()+b.get_width()/2,b.get_height(),f'{v:,.0f}\n{cust}',ha='center',va='bottom',fontsize=14)
    axc.set_title("TODAY'S TARGET — ALL SECTIONS (PCS + MAJOR CUSTOMER)",fontweight='bold');axc.tick_params(axis='x',rotation=24);axc.set_ylabel('pcs')

    def _draw_kiln_table(ax,day,title):
        ax.axis('off');ax.set_title(title,loc='left',fontweight='bold',fontsize=17,pad=10)
        if p.empty:return
        _pdte=pd.to_datetime(p.get('Plan Date'),errors='coerce').dt.date;f=p[(_pdte==day)&p['Section'].astype(str).eq('Firing')].copy()
        if f.empty:ax.text(.02,.72,'No kiln load planned.',fontsize=14);return
        f['_qty']=pd.to_numeric(f.get('Plan Qty',0),errors='coerce').fillna(0);rows=[]
        for (kiln,program),g in f.groupby(['Kiln','Program'],dropna=False):
            wos=', '.join(g.sort_values('Due Date',na_position='last')['Work Order'].astype(str).head(5).tolist());due=pd.to_datetime(g.get('Due Date'),errors='coerce').min()
            rows.append([str(kiln),str(program),f"{g['_qty'].sum():,.0f}",str(due.date()) if pd.notna(due) else '',wos[:62]])
        tab=ax.table(cellText=rows,colLabels=['KILN','PROGRAM','PCS','EARLIEST DUE','WORK ORDERS'],loc='upper left',cellLoc='left',colLoc='left',bbox=[0,.01,1,.88],colWidths=[.10,.13,.10,.18,.49])
        tab.auto_set_font_size(False);tab.set_fontsize(12);tab.scale(1,1.35)
        for (ri,ci),cell in tab.get_celld().items():
            cell.set_linewidth(0);cell.set_edgecolor('none');cell.PAD=.08;cell.get_text().set_fontfamily(THAI_FONT_NAME)
            if ri==0:cell.get_text().set_weight('bold')
    _draw_kiln_table(fig.add_subplot(gs[3,0:2]),start_date,'TODAY — KILN LOADING / PROGRAM / DUE / WO')
    _draw_kiln_table(fig.add_subplot(gs[3,2:4]),tomorrow,'NEXT WORKDAY — KILN LOADING / PROGRAM / DUE / WO')

    # ---- Distance-readable TODAY execution summary: one large item per process ----
    axt=fig.add_subplot(gs[4,:])
    axt.set_title('TODAY EXECUTION — PROCESS SUMMARY / เป้าหมายวันนี้',loc='left',fontweight='bold',fontsize=19,pad=12)
    axt.set_ylabel('pcs',fontsize=14)
    if not p.empty:
        pdte=pd.to_datetime(p.get('Plan Date'),errors='coerce').dt.date
        td=p[pdte.eq(start_date)].copy()
        if not td.empty:
            td['_qty']=pd.to_numeric(td.get('Plan Qty',0),errors='coerce').fillna(0)
            sec=td.groupby('Section',as_index=False).agg(PCS=('_qty','sum'),WOs=('Work Order','nunique'))
            sec=sec.sort_values('PCS',ascending=False)
            labels=sec['Section'].astype(str).tolist()
            bars=axt.bar(labels,sec['PCS'])
            for b,(_,r) in zip(bars,sec.iterrows()):
                g=td[td['Section'].astype(str).eq(str(r['Section']))]
                cust=''
                if not g.empty and 'Customer' in g.columns:
                    cg=g.groupby('Customer',as_index=False)['_qty'].sum().sort_values('_qty',ascending=False)
                    cust=str(cg.iloc[0]['Customer'])[:16] if not cg.empty else ''
                axt.text(b.get_x()+b.get_width()/2,b.get_height(),
                         f"{r['PCS']:,.0f} pcs\n{int(r['WOs'])} WO\n{cust}",
                         ha='center',va='bottom',fontsize=13,fontweight='bold')
            axt.tick_params(axis='x',rotation=0,labelsize=13)
            axt.tick_params(axis='y',labelsize=12)
            axt.grid(axis='y',alpha=.18)
        else:
            axt.text(.03,.55,'No execution target for selected date.',transform=axt.transAxes,fontsize=16,fontweight='bold')
    else:
        axt.text(.03,.55,'No calculated daily plan.',transform=axt.transAxes,fontsize=16,fontweight='bold')
    b=io.BytesIO();fig.savefig(b,format='jpg',dpi=100,facecolor='white');plt.close(fig);return b.getvalue()

_daily_cache=Path(os.environ.get('SL_SHARED_ROOT',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA')))/'CACHE'/'daily_result.pkl'
_daily_cache.parent.mkdir(parents=True,exist_ok=True)
_current_daily_sig,_current_daily_inputs,_current_daily_params=_daily_current_signature()
def _same_daily_source_bytes(_saved_inputs,_active_inputs):
    if not isinstance(_saved_inputs,dict) or not isinstance(_active_inputs,dict) or set(_saved_inputs)!=set(_active_inputs):return False
    for _name in _saved_inputs:
        _a=_saved_inputs.get(_name) or {};_b=_active_inputs.get(_name) or {}
        if not isinstance(_a,dict) or not isinstance(_b,dict):return False
        if any(_a.get(_k)!=_b.get(_k) for _k in ('path','bytes','sha256','state')):return False
    return True

if st.session_state.get('daily_result') is not None:
    _meta=st.session_state.get('daily_result_meta') or {}
    if not _meta.get('signature') or _meta.get('signature')!=_current_daily_sig:
        if _same_daily_source_bytes(_meta.get('inputs'),_current_daily_inputs):
            st.session_state.daily_stale_reason='The last calculated plan is retained for review. Planning controls changed; the displayed snapshot is not recalculated until you choose Create Daily Plan.'
        else:
            # Never clear a calculated result merely because the current source revision
            # changed. Keep the last issued plan visible for traceability and explicitly
            # mark it stale until the user calculates against the new source set.
            st.session_state.daily_stale_reason='The last calculated plan is retained for review. Active source contents changed; this is a dated snapshot and must be recalculated before release.'
if st.session_state.get('daily_result') is None and _daily_cache.exists():
    try:
        with _daily_cache.open('rb') as _f:_cached=pickle.load(_f)
        _cache_meta=(_cached.get('meta') or {}) if isinstance(_cached,dict) else {}
        if isinstance(_cached,dict) and _cached.get('schema')=='SL_DAILY_RESULT_V2' and _cached.get('signature')==_current_daily_sig:
            st.session_state.daily_result=_cached['result'];st.session_state.daily_result_meta=_cache_meta;st.session_state.daily_stale_reason=''
        elif isinstance(_cached,dict) and _cached.get('schema')=='SL_DAILY_RESULT_V2' and _same_daily_source_bytes(_cache_meta.get('inputs'),_current_daily_inputs):
            st.session_state.daily_result=_cached['result'];st.session_state.daily_result_meta=_cache_meta
            st.session_state.daily_stale_reason='The previous calculated plan was restored from CENTRAL_DATA/CACHE for the same active source-file bytes. Its saved planning controls differ from this view, so review it as a dated snapshot or press Create Daily Plan to recalculate.'
        elif isinstance(_cached,dict) and _cached.get('schema')=='SL_DAILY_RESULT_V2' and isinstance(_cached.get('result'),dict):
            st.session_state.daily_result=_cached['result'];st.session_state.daily_result_meta=_cache_meta
            st.session_state.daily_stale_reason='The last saved plan was restored from CENTRAL_DATA/CACHE. Active sources differ from its recorded inputs; review its source trace and recalculate before release.'
    except Exception as _cache_err:st.session_state.daily_stale_reason=f'Saved calculation could not be verified ({_cache_err}); source uploads and user entries remain in CENTRAL_DATA.'
# If daily_result.pkl is missing/corrupt, recover the newest complete dated snapshot.
# Snapshots are append-only, so navigation, interrupted writes, or a damaged latest
# pointer cannot erase the last successful calculation.
if st.session_state.get('daily_result') is None:
    try:
        _snapshot_dir=_daily_cache.parent/'DAILY_PLAN_SNAPSHOTS'
        _snapshot_files=sorted(_snapshot_dir.glob('daily_plan_*.pkl'),key=lambda p:p.stat().st_mtime_ns,reverse=True) if _snapshot_dir.is_dir() else []
        for _snapshot_file in _snapshot_files:
            try:
                with _snapshot_file.open('rb') as _snapshot_handle:_snapshot_payload=pickle.load(_snapshot_handle)
                if not (isinstance(_snapshot_payload,dict) and _snapshot_payload.get('schema')=='SL_DAILY_RESULT_V2' and isinstance(_snapshot_payload.get('result'),dict)):
                    continue
                st.session_state.daily_result=_snapshot_payload['result']
                st.session_state.daily_result_meta=_snapshot_payload.get('meta') or {}
                st.session_state.daily_stale_reason=f"Recovered the last successful plan from dated snapshot {_snapshot_file.name}. It is retained for traceability; verify its recorded sources and recalculate before release."
                break
            except Exception:
                continue
    except Exception as _snapshot_recovery_error:
        st.session_state.daily_stale_reason=f'Plan snapshot recovery could not complete ({_snapshot_recovery_error}); dated snapshot files were not deleted.'
res=st.session_state.daily_result
if st.session_state.get('daily_stale_reason'):
    st.error('DATA RECONCILIATION HOLD / หยุดใช้ข้อมูลเก่า: '+st.session_state.daily_stale_reason)
elif res and st.session_state.get('daily_result_meta'):
    _m=st.session_state.daily_result_meta
    st.info(f"Saved plan ID: {_m.get('plan_id',_m.get('signature','')[:16])} · Dashboard snapshot: {_m.get('generated_at','time unavailable')} Thailand local time (Phan Thong, Chonburi) · input fingerprint {_m.get('signature','')[:16]} — export is a frozen copy of this calculation.")
    with st.expander('Snapshot source files / parameter fingerprint'):
        st.dataframe(pd.DataFrame([{'Input':k,**(v if isinstance(v,dict) else {'value':v})} for k,v in (_m.get('inputs') or {}).items()]),use_container_width=True,hide_index=True)
# Daily Status is isolated: parse errors are captured, never raised/displayed outside its own 📡 tab.
# Planning-controlled Daily Status address mapping. Editable because monthly departmental templates can move columns.
def _col0(x):
    x=str(x or '').strip().upper(); n=0
    for ch in re.sub('[^A-Z]','',x): n=n*26+(ord(ch)-64)
    return max(0,n-1)
_ds_shared_root=Path(os.environ.get('SL_SHARED_ROOT',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA')))/'DAILY_STATUS'
_ds_shared_root.mkdir(parents=True,exist_ok=True)
_ds_preloaded=[p for p in list(_ds_shared_root.glob('*.xlsx'))+list(_ds_shared_root.glob('*.xlsm')) if not p.name.startswith('~$')]
with st.expander('📤 Daily Status files (replace only if newer) / สถานะรายวัน',expanded=(str(st.query_params.get('focus','')) in ('closed','status','kpi','wip') and not _ds_preloaded)):
    if _ds_preloaded:
        st.success(f'{len(_ds_preloaded)} Daily Status file(s) already loaded from Home. This box does not ask for Plan-2026 again. Use it only to replace a newer section workbook.')
        st.caption('Already stored: '+', '.join(p.name for p in _ds_preloaded[:8]))
    else:
        st.caption('No Daily Status section workbook on Home yet. Plan-2026 open/closed still works. Production date is the worksheet tab name.')
    st.caption('Production date is read only from each worksheet tab name; date cells inside the workbook are ignored.')
    _ds_start_row=st.number_input('First data row / แถวข้อมูลแรก',1,100,5,key='ds_start_row_cfg')
    _ds_rows=[]
    _defaults={'Preparation':['B','C','D','N','O','Q','R','S','T'],'Mixing':['B','C','D','N','O','Q','R','S','T'],'Forming':['B','C','D','N','O','Q','R','S','T'],'Firing':['B','C','D','O','P','R','S','T','U'],'Grinding':['B','C','D','N','O','Q','R','T','U'],'Packing':['B','C','D','N','O','Q','','S','T']}
    for _sec,_v in _defaults.items(): _ds_rows.append([_sec]+_v)
    _dsm=pd.DataFrame(_ds_rows,columns=['Section','WO','Spec','Customer','Plan','Actual','Category','Plan Weight','Problem','Action'])
    _dsemap=_persistent_data_editor(_dsm,use_container_width=True,hide_index=True,disabled=['Section'],key='daily_status_address_editor')
_ds_fixed={}
for _,_r in _dsemap.iterrows():
    _ds_fixed[str(_r['Section'])]={'wo':_col0(_r['WO']),'spec':_col0(_r['Spec']),'customer':_col0(_r['Customer']),'plan':_col0(_r['Plan']),'actual':_col0(_r['Actual']),'category':_col0(_r['Category']),'plan_weight':_col0(_r['Plan Weight']) if str(_r['Plan Weight']).strip() else None,'problem':_col0(_r['Problem']),'action':_col0(_r['Action'])}
# Controlled shared Daily Status source: one batch upload accepts each section workbook separately.
_ds_history=_ds_shared_root/'history'; _ds_history.mkdir(parents=True,exist_ok=True)
_ds_registry_path=_ds_shared_root/'source_registry.json'
try: _ds_registry=json.loads(_ds_registry_path.read_text(encoding='utf-8')) if _ds_registry_path.exists() else {'records':[]}
except Exception: _ds_registry={'records':[]}
_ds_registry.setdefault('records',[])
class _SharedUpload:
    def __init__(self,p,original_name=None): self._p=Path(p); self.name=self._p.name; self.original_name=original_name or self.name
    def getvalue(self): return self._p.read_bytes()
class _SectionUpload:
    def __init__(self,upload,section): self.upload=upload; self.name=upload.name; self.original_name=upload.name; self.section=section
    def getvalue(self): return self.upload.getvalue()
with st.sidebar.expander('📡 Daily Status source / แหล่งข้อมูลรายวัน',expanded=False):
    st.caption('Upload or replace Daily Status workbooks once in Home → Files → All software inputs, or use the small Update input files link. This planner reads the shared section files automatically; it has no duplicate upload form.')
    st.caption('Daily Status needs one workbook per section. Sheet-tab names provide production dates. Use the Daily Open / Closed page for scan/type manual OPEN or CLOSED entries.')
    _section_uploads=[]
actualu=_section_uploads
_ds_saved=[]; _ds_rejected_upload=[]
for _u in actualu or []:
    try:
        _raw=_u.getvalue(); _sha=hashlib.sha256(_raw).hexdigest()
        _up_xls=pd.ExcelFile(io.BytesIO(_raw))
        _preview=_up_xls.parse(_up_xls.sheet_names[0],header=None,nrows=8,usecols=range(21))
        _section=getattr(_u,'section','') or _status_section_from_file_sheet(_u.name,str(_up_xls.sheet_names[0]),_preview)
        _canon=next((x for x in ['Preparation','Mixing','Forming','Firing','Grinding','Packing'] if _section.startswith(x)),None)
        if not _canon:
            _ds_rejected_upload.append({'File':_u.name,'Reason':'Section was not recognized from the filename or first worksheet. Include the department name in the filename.'}); continue
        # Monthly revisions often arrive with a changed filename suffix. Use the
        # dominant dated-tab month as the stable key so a revised workbook replaces
        # that section/month instead of double-counting the old and new copies.
        _month_counts={};_year_counts={}
        for _sn in _up_xls.sheet_names:
            _dm=re.fullmatch(r'\s*\d{1,2}[-/.]\d{1,2}[-/.](\d{4})\s*',str(_sn))
            if _dm:
                try:
                    _mm=re.fullmatch(r'\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\s*',str(_sn));_mo=int(_mm.group(2));_yr=int(_mm.group(3));_yr=_yr-543 if _yr>2400 else _yr
                    if 1<=_mo<=12 and 2000<=_yr<=2100:_month_counts[(_yr,_mo)]=_month_counts.get((_yr,_mo),0)+1;_year_counts[_yr]=_year_counts.get(_yr,0)+1
                except Exception:pass
        _report_period=''
        if _month_counts:
            _dom=max(_month_counts,key=_month_counts.get)
            _report_period=f'{_dom[0]}-{_dom[1]:02d}' if _month_counts[_dom]/sum(_month_counts.values())>=0.75 else f'{max(_year_counts)}-ALL'
        else:
            _fn_text=Path(_u.name).stem
            _fn_year=re.search(r'(20\d{2}|25\d{2})',_fn_text); _fn_month=next((i for i,n in enumerate(['มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน','กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม'],1) if n in _fn_text),None)
            if _fn_year:
                _yy=int(_fn_year.group(1));_yy=_yy-543 if _yy>2400 else _yy
                _report_period=f'{_yy}-{_fn_month:02d}' if _fn_month else f'{_yy}-ALL'
        _ext=Path(_u.name).suffix.lower() if Path(_u.name).suffix.lower() in {'.xlsx','.xlsm'} else '.xlsx'
        if _report_period:_stored=f'{_canon}__{_report_period}__LATEST{_ext}'
        else:
            _base=re.sub(r'[^A-Za-z0-9._-]+','_',Path(_u.name).stem).strip('._') or 'DailyStatus'
            _stored=f'{_canon}__{_base}{_ext}'
        _dest=_ds_shared_root/_stored
        _stamp=datetime.datetime.now(ZoneInfo('Asia/Bangkok')).strftime('%Y%m%d_%H%M%S')
        for _entry in _ds_registry['records']:
            if not _entry.get('active') or _entry.get('section')!=_canon or not _report_period or _entry.get('report_period')!=_report_period:continue
            _old_path=Path(_entry.get('stored_path',''))
            if _old_path.exists() and _old_path.resolve()!=_dest.resolve():
                _arch=_ds_history/f'{_stamp}_{_old_path.name}'
                try:_old_path.rename(_arch);_entry['archived_path']=str(_arch.resolve())
                except Exception:
                    _arch.write_bytes(_old_path.read_bytes());_old_path.unlink(missing_ok=True);_entry['archived_path']=str(_arch.resolve())
            _entry['active']=False
        _old_sha=hashlib.sha256(_dest.read_bytes()).hexdigest() if _dest.exists() else ''
        if _old_sha==_sha:
            # Preserve one active registry record for identical canonical sources.
            for _entry in _ds_registry['records']:
                if _entry.get('stored_path')==str(_dest.resolve()):_entry['active']=True
            _ds_saved.append({'Section':_canon,'Original File':Path(getattr(_u,'original_name',_u.name)).name,'Stored File':str(_dest.resolve()),'SHA-256':_sha,'Status':'Already current'})
            continue
        if _dest.exists():
            _arch=_ds_history/f'{_stamp}_{_stored}'; _arch.write_bytes(_dest.read_bytes())
            for _entry in _ds_registry['records']:
                if _entry.get('stored_path')==str(_dest.resolve()) and _entry.get('active'):
                    _entry['active']=False; _entry['archived_path']=str(_arch.resolve())
        _dest.write_bytes(_raw)
        _docmod=''
        try:
            with zipfile.ZipFile(io.BytesIO(_raw)) as _z:
                _core=_z.read('docProps/core.xml').decode('utf-8','ignore');_dm=re.search(r'<dcterms:modified[^>]*>([^<]+)',_core)
                if _dm:_docmod=_dm.group(1)
        except Exception:pass
        _meta={'section':_canon,'report_period':_report_period or None,'original_filename':Path(getattr(_u,'original_name',_u.name)).name,'stored_filename':_stored,'stored_path':str(_dest.resolve()),'sha256':_sha,'size_bytes':len(_raw),'excel_document_modified_at':_docmod,'uploaded_by':str(st.session_state.get('sl_user','unknown')),'uploaded_at':datetime.datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds'),'active':True}
        _ds_registry['records'].append(_meta); _ds_saved.append({'Section':_canon,'Original File':Path(getattr(_u,'original_name',_u.name)).name,'Stored File':str(_dest.resolve()),'SHA-256':_sha,'Status':'Saved'})
    except Exception as _up_err: _ds_rejected_upload.append({'File':getattr(_u,'name',''),'Reason':str(_up_err)})
if _ds_saved or _ds_rejected_upload:
    _ds_registry_path.write_text(json.dumps(_ds_registry,ensure_ascii=False,indent=2),encoding='utf-8')
    if _ds_saved: st.sidebar.success(f'{len(_ds_saved)} Daily Status section file(s) checked/saved. Shared source folder: {_ds_shared_root}')
    if _ds_rejected_upload: st.sidebar.error(f'{len(_ds_rejected_upload)} file(s) need attention: '+ '; '.join(x['File']+': '+x['Reason'] for x in _ds_rejected_upload))
_ds_active=list(_ds_shared_root.glob('*.xlsx'))+list(_ds_shared_root.glob('*.xlsm'))
_ds_meta={Path(x.get('stored_path','')).name:x for x in _ds_registry['records'] if x.get('active')}
_ds_inputs=[_SharedUpload(_p,_ds_meta.get(_p.name,{}).get('original_filename',_p.name)) for _p in sorted(_ds_active)]
if _ds_inputs: st.sidebar.caption(f'Using {len(_ds_inputs)} active section workbook(s) from {_ds_shared_root}')
_ds_active_table=[{'Section':_ds_meta.get(p.name,{}).get('section','Unclassified / legacy'),'Report period':_ds_meta.get(p.name,{}).get('report_period','Not inferred'),'Original filename':_ds_meta.get(p.name,{}).get('original_filename',p.name),'Stored server path':str(p.resolve()),'Uploaded at':_ds_meta.get(p.name,{}).get('uploaded_at',datetime.datetime.fromtimestamp(p.stat().st_mtime,ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds')),'Workbook modified at':_ds_meta.get(p.name,{}).get('excel_document_modified_at','Not recorded in workbook'),'Size (MB)':round(p.stat().st_size/1048576,2),'SHA-256':_ds_meta.get(p.name,{}).get('sha256','Not recorded')} for p in sorted(_ds_active)]
try:
    _ds_fingerprint=tuple((str(p.resolve()),int(p.stat().st_mtime_ns),int(p.stat().st_size),
                           str(_ds_meta.get(p.name,{}).get('sha256',''))) for p in sorted(_ds_active))
    _ds_cache_valid,_ds_cache_rejected,_ds_cache_errors=_daily_status_files(_ds_inputs,_ds_fingerprint,_ds_fixed,'R1',int(_ds_start_row))
except Exception as _dse:
    _ds_cache_valid=pd.DataFrame();_ds_cache_rejected=pd.DataFrame();_ds_cache_errors=pd.DataFrame([{'Error':str(_dse)}])
if isinstance(_ds_cache_valid,pd.DataFrame) and not _ds_cache_valid.empty:
    _ds_cache_valid=_cust_lang(_retain_customer_source_cols(_ds_cache_valid),_LANG)
_oc_shown=False
if str(st.query_params.get('focus',''))=='closed':
    from suite.open_closed_view import render as _render_open_closed
    _render_open_closed(st, plan_path=st.session_state.get('plan_path') or str(_resolve_central('Plan-2026-LATEST.xlsx') or ''),
                        daily_status=_ds_cache_valid, job_path=str(_resolve_central('Job-Register-LATEST.xlsx') or ''),
                        cache_dir=str(Path(os.environ.get('SL_SHARED_ROOT',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA')))/'CACHE'),
                        key='daily_oc_focus')
    _oc_shown=True
    if not res:
        st.info('CREATE DAILY PLAN is only for the calculated schedule. Open/Closed above already uses the files loaded on Home.')
if res:
    allp=_common_postfire(res['all']);caps=_collapse_caps(res['capacity_summary'].copy());issues=_common_postfire(res['issues']);wip=res['wip'];risk=res['delivery_risk']
    allp=_cust_lang(allp,_LANG); issues=_cust_lang(issues,_LANG); wip=_cust_lang(wip,_LANG); risk=_cust_lang(risk,_LANG)
    if isinstance(res.get('master'), pd.DataFrame):
        res['master']=_cust_lang(_retain_customer_source_cols(res['master']),_LANG)
    _customer_allowed=bool(_hub_identity and _hub_identity.get('role','').lower() in {'admin','planning','manager','management'})
    if not _customer_allowed:
        def _remove_customer_fields(frame):
            if isinstance(frame,pd.DataFrame):
                cols=[c for c in frame.columns if 'customer' in str(c).lower() or 'ลูกค้า' in str(c)]
                return frame.drop(columns=cols,errors='ignore')
            return frame
        for _key,_value in list(res.items()):
            if isinstance(_value,pd.DataFrame):res[_key]=_remove_customer_fields(_value)
        allp=_remove_customer_fields(allp);issues=_remove_customer_fields(issues);wip=_remove_customer_fields(wip);risk=_remove_customer_fields(risk)
        st.caption('Customer names are restricted to authenticated planning/management users. / ชื่อลูกค้าจะแสดงเฉพาะผู้ใช้ฝ่ายวางแผน/ผู้บริหารที่เข้าสู่ระบบแล้ว')
    # F is an alias for P in every presentation dataset, before graph grouping.
    for _df in [allp,caps,issues,wip,risk,res.get('master',pd.DataFrame())]:
        if isinstance(_df,pd.DataFrame):
            for _col in ['Category','Product Category','Group']:
                if _col in _df.columns:_df[_col]=_df[_col].astype(str).str.strip().str.upper().replace({'F':'P'})
    # Decode Excel serials explicitly before any date formatting/filtering.
    for _date_frame in [allp,caps,wip,risk,res.get('master',pd.DataFrame())]:
        if isinstance(_date_frame,pd.DataFrame):
            for _date_col in _date_frame.columns:
                if _date_col in ['WO Date','Warehouse Target','Due Date','Plan2026 Firing Date','Firing Exit Date','Actual Warehouse Date','Sales Delivery Date','Plan Date','Firing Date','Firing Complete','Projected Finish','Suggested Safe Due Date','Requested New Due Date','Next Required Date']:
                    _date_frame[_date_col]=_date_frame[_date_col].apply(parse_date)
    # FINAL SOURCE RULE: Plan2026 overrides planner-derived quantity/category/due-date fields on any mismatch.
    _auth=res.get('master',pd.DataFrame()).copy()
    if not _auth.empty and 'Work Order' in _auth.columns:
        _auth['_WO']=_auth['Work Order'].astype(str).str.strip()
        _auth=_auth.drop_duplicates('_WO',keep='last').set_index('_WO')
        for _df in [allp,risk]:
            if isinstance(_df,pd.DataFrame) and not _df.empty and 'Work Order' in _df.columns:
                _wo=_df['Work Order'].astype(str).str.strip()
                if 'Due Date' in _auth.columns:_df['Due Date']=_wo.map(_auth['Due Date']).combine_first(_df.get('Due Date'))
                if 'Category' in _auth.columns:_df['Category']=_wo.map(_auth['Category']).combine_first(_df.get('Category'))
        if not risk.empty:
            if 'Order Qty' in _auth.columns:risk['Full Order Qty']=risk['Work Order'].astype(str).str.strip().map(_auth['Order Qty']).combine_first(risk.get('Full Order Qty'))
            if 'Packing Actual' in _auth.columns:risk['Packed Actual Qty']=risk['Work Order'].astype(str).str.strip().map(_auth['Packing Actual']).combine_first(risk.get('Packed Actual Qty'))
            risk['Open Qty']=(pd.to_numeric(risk['Full Order Qty'],errors='coerce').fillna(0)-pd.to_numeric(risk['Packed Actual Qty'],errors='coerce').fillna(0)).clip(lower=0)
    a,b,c,d,e=st.columns(5)
    a.metric('📋 Daily plan rows',len(allp));b.metric('📦 Open unique WOs',wip['Work Order'].astype(str).nunique() if not wip.empty else 0);c.metric('⚠️ WOs with issues',issues['Work Order'].astype(str).nunique() if not issues.empty and 'Work Order' in issues.columns else 0);d.metric('⚖️ Plan ton',f"{pd.to_numeric(allp.get('Plan ton',0),errors='coerce').fillna(0).sum():,.1f}");e.metric('🚨 HIGH delivery risk',int((risk.get('Delivery Risk','')=='HIGH').sum()) if not risk.empty else 0)
    with st.expander('🔎 Work Order part status · Plan-2026 + latest WIP audit',expanded=False):
        _lookup_input=st.text_input('Enter or scan Work Order / พิมพ์หรือสแกนเลขใบสั่งผลิต',key='planner_part_status_lookup',placeholder='e.g. P005-110826')
        if st.button('Show current part status / แสดงสถานะชิ้นงาน',key='planner_part_status_lookup_go'):
            st.session_state['planner_part_status_lookup_value']=_lookup_input.strip()
        _lookup_value=str(st.session_state.get('planner_part_status_lookup_value','')).strip()
        if _lookup_value:
            def _status_wo_key(v):return re.sub(r'[^A-Z0-9]','',str(v or '').upper())
            _lookup_master=res.get('master',pd.DataFrame())
            _lookup_match=pd.DataFrame()
            if isinstance(_lookup_master,pd.DataFrame) and not _lookup_master.empty and 'Work Order' in _lookup_master:
                _lookup_match=_lookup_master[_lookup_master['Work Order'].map(_status_wo_key).eq(_status_wo_key(_lookup_value))].copy()
            if _lookup_match.empty:
                st.warning('Work Order not found in the active Plan-2026 source.')
            else:
                _lookup_row=_lookup_match.iloc[-1];_lookup_wo=str(_lookup_row.get('Work Order',''))
                _status_fields=['Work Order','Product Code','Specification','Category','Due Date','Plan Location','pcs','Order Qty','Packing Actual','Overall Closed']
                _status_record={c:_lookup_row.get(c) for c in _status_fields if c in _lookup_match.columns}
                st.markdown('**Plan-2026 source status / สถานะจาก Plan-2026**')
                st.dataframe(pd.DataFrame([_status_record]),use_container_width=True,hide_index=True)
                _lookup_plan=allp.copy() if isinstance(allp,pd.DataFrame) else pd.DataFrame()
                if not _lookup_plan.empty and 'Work Order' in _lookup_plan:
                    _lookup_plan=_lookup_plan[_lookup_plan['Work Order'].map(_status_wo_key).eq(_status_wo_key(_lookup_wo))].copy()
                    _sched_cols=[c for c in ['Plan Date','Section','Plan Qty','Plan ton','Capacity Basis'] if c in _lookup_plan]
                    if _sched_cols:
                        _lookup_plan['_sort_date']=pd.to_datetime(_lookup_plan.get('Plan Date'),errors='coerce')
                        _lookup_plan=_lookup_plan.sort_values('_sort_date')
                        st.markdown('**Previous and future planned process dates / แผนกระบวนการก่อนหน้าและถัดไป**')
                        st.dataframe(_lookup_plan[_sched_cols],use_container_width=True,hide_index=True)
                _latest_audit=None;_latest_photo=''
                try:
                    from suite.central_paths import db_path as _central_db_path
                    _audit_db=_central_db_path()
                    if _audit_db.is_file():
                        with sqlite3.connect(str(_audit_db),timeout=2) as _ac:
                            _tabs={r[0] for r in _ac.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                            if 'mobile_audits' in _tabs:
                                _audit_cols={r[1] for r in _ac.execute('PRAGMA table_info(mobile_audits)')}
                                _select=[c for c in ['id','physical_status','physical_location','observed_process','verified_qty','qty_unknown','qty_unit','created_at','user_name','notes'] if c in _audit_cols]
                                if 'wo_id' in _audit_cols:
                                    _latest_audit=_ac.execute('SELECT '+','.join('"'+c+'"' for c in _select)+' FROM mobile_audits WHERE upper(wo_id)=upper(?) ORDER BY id DESC LIMIT 1',(_lookup_wo,)).fetchone()
                                    if _latest_audit and 'mobile_audit_photos' in _tabs:
                                        _latest_photo_row=_ac.execute('SELECT filename FROM mobile_audit_photos WHERE audit_id=? ORDER BY id DESC LIMIT 1',(_latest_audit[_select.index('id')],)).fetchone()
                                        _latest_photo=_latest_photo_row[0] if _latest_photo_row else ''
                                    if _latest_audit:_latest_audit=dict(zip(_select,_latest_audit))
                except Exception as _audit_lookup_error:st.caption(f'Latest audit lookup unavailable: {_audit_lookup_error}')
                if _latest_audit:
                    st.markdown('**Latest physical WIP audit / ผลตรวจนับหน้างานล่าสุด**')
                    st.dataframe(pd.DataFrame([{k:_latest_audit.get(k) for k in ['physical_status','observed_process','physical_location','verified_qty','qty_unit','qty_unknown','created_at','user_name','notes']}]),use_container_width=True,hide_index=True)
                    if _latest_photo:
                        _photo_root=Path(os.environ.get('SL_PHOTO_ROOT',str(_central_db_path().parent.parent/'PHOTOS')))/'MOBILE_AUDITS'
                        _photo_path=_photo_root/Path(str(_latest_photo)).name
                        if _photo_path.is_file():st.image(str(_photo_path),caption=f'Latest audit photo · {_latest_photo}',width=360)
                        else:st.caption(f'Latest audit photo record: {_latest_photo} (photo file is not in {_photo_root})')
                else:st.info('No physical audit has been saved for this work order yet.')
                st.caption(f'Plan source: {Path(st.session_state.get("plan_path",str(_shared_plan))).name if "_shared_plan" in globals() else Path(st.session_state.get("plan_path","")).name} · audit source: shared database `{_central_db_path()}`. Mobile detail and desktop Audit Report read the same audit database.')
    st.caption('POSITIVE PPC: 🔥 firing rhythm drives upstream PUSH; downstream QC → Grinding OR Cutting → Packing PULL from firing. Icons are the primary navigation.  |  📺 Dashboard  📅 Daily  🔀 Route  🏭 Capacity  📈 Analysis  📦 WIP  ⚙️ Machine  🧪 Material  🚚 Risk  🗓️ MPS  ⚠️ Issues  🔎 Evidence  🔭 Demand/Capacity  ✅ Validation  💎 Tooling  📡 Daily Status  🧪 Test Work  ⬇️ Download Plan')
    st.caption('Capacity feasibility is evaluated against controlled section capacity. Overload is shown in Capacity / Recovery analysis, not as a material-status message.')
    _ov=caps[pd.to_numeric(caps.get('Utilization %'),errors='coerce')>100.01].copy() if isinstance(caps,pd.DataFrame) and not caps.empty else pd.DataFrame()
    if not _ov.empty:
        _ov['Suggested Action']='SUGGEST OVERTIME / CAPACITY RECOVERY — do not treat overload as normal capacity'
        st.warning(f'Capacity control: {len(_ov)} day/section overload(s) detected. Planner must not silently accept >100% controlled capacity; OT/capacity recovery is suggested and the excess remains a risk.')
        _major=_ov[pd.to_numeric(_ov.get('Utilization %'),errors='coerce')>103.0]
        if not _major.empty: st.error(f'HARD CAPACITY GATE: {len(_major)} day/section load(s) exceed 103%. These are NOT considered normal feasible production; reschedule/rebalance or approve OT before release.')
    _NAV=['📺 Dashboard / แดชบอร์ด','📅 Daily / รายวัน','🔀 Route / เส้นทาง','⚖️ Capacity vs Plan vs Actual / กำลังผลิตเทียบแผนและผลจริง','📈 Analysis / วิเคราะห์','🏭 WIP details (central page) / ดู WIP หน้ากลาง','⚙️ Machine / เครื่องจักร','🧪 Plan Material Check / ตรวจวัตถุดิบตามแผน','🚚 Risk / ความเสี่ยง','🗓️ MPS + Backorder / แผนหลัก + งานค้างส่ง','⚠️ Issues / ปัญหา','🔎 Evidence / หลักฐาน','🔭 Demand-Capacity / อุปสงค์-กำลัง','📦 Packaging / บรรจุภัณฑ์','💎 Tooling / เครื่องมือ','📡 Daily Status Analysis / วิเคราะห์สถานะรายวัน','🧪 Test Work / งานทดสอบ','🗂️ Order Portfolio / กลุ่มงาน','⬇️ Download Plan / ดาวน์โหลดแผน','📈 Weekly Factory Performance Review / รายงานผลงานโรงงานรายสัปดาห์','✅ Validation / ตรวจสอบ','🎯 Department KPI — retained sources / KPI แผนกจากข้อมูลกลาง','📊 Daily Open / Closed WO Report / รายงานใบสั่งเปิด-ปิดรายวัน','⚙️ Mixing Mill Plan vs Actual / แผนโม่เทียบจริง']
    _GROUPS={
      '① 🏭 Daily Planning / การวางแผนรายวัน':[0,1,2,3,6,14,13],
      '② 🧪 Plan Material Check / ตรวจวัตถุดิบตามแผน':[7,8],
      '③ 🗓️ Long-Term Plans / แผนระยะยาว':[9,12,10,4],
      '④ 📋 Work Orders / ใบสั่งผลิต':[17,16],
      '⑤ 📊 Reports & Evidence / รายงานและหลักฐาน':[5,22,15,21,19,11,18,20,23]
    }
    _quick_options=['Browse all modules / ดูทุกโมดูล','🏭 WIP — Planning vs Production (central page)','📊 Daily Open / Closed WO Report / รายงานใบสั่งเปิด-ปิดรายวัน','📡 Daily Status analysis / วิเคราะห์สถานะรายวัน','🎯 Monthly Planning KPI Scorecard / KPI ผลลัพธ์รายเดือน','🎯 Department KPI — retained sources / KPI แผนกจากข้อมูลกลาง','⚙️ Mixing Mill Plan vs Actual / แผนโม่เทียบจริง']
    _quick_options.append('⬇️ Download Complete Daily Plan / ดาวน์โหลดแผนรายวันฉบับเต็ม')
    _quick_options.append('🏭 All-section Plan vs Capacity Graphs / กราฟแผนเทียบกำลังผลิตทุกแผนก')
    _quick_options.append('⚖️ Capacity vs Plan vs Actual / กำลังผลิตเทียบแผนและผลจริง')
    _quick_options.append('📅 Daily plan by section / แผนรายแผนก')
    from suite.daily_navigation import focus_labels
    _focus_to_label=focus_labels(_quick_options)
    if st.session_state.get('daily_quick_access_v13') not in _quick_options:
        st.session_state['daily_quick_access_v13']=_quick_options[0]
    _requested_focus=st.query_params.get('focus','')
    if _requested_focus in _focus_to_label:
        st.session_state['daily_quick_access_v13']=_focus_to_label[_requested_focus]
    def _clear_daily_focus():
        if 'focus' in st.query_params:del st.query_params['focus']
    def _select_daily_module(index,browse_label):
        # Streamlit callbacks run before widgets are instantiated on the next rerun.
        st.session_state['daily_nav_selected']=index
        st.session_state['daily_quick_access_v13']=browse_label
        if 'focus' in st.query_params:del st.query_params['focus']
    _quick_choice=st.sidebar.selectbox('📌 DIRECT ACCESS / เปิดหน้าหลักโดยตรง',_quick_options,key='daily_quick_access_v13',on_change=_clear_daily_focus)
    _quick_idx={'📅 Daily plan by section / แผนรายแผนก':1,'🏭 WIP — Planning vs Production (central page)':5,'📊 Daily Open / Closed WO Report / รายงานใบสั่งเปิด-ปิดรายวัน':22,'📡 Daily Status analysis / วิเคราะห์สถานะรายวัน':15,'🎯 Department KPI — retained sources / KPI แผนกจากข้อมูลกลาง':21,'⚙️ Mixing Mill Plan vs Actual / แผนโม่เทียบจริง':23,'⬇️ Download Complete Daily Plan / ดาวน์โหลดแผนรายวันฉบับเต็ม':18,'🏭 All-section Plan vs Capacity Graphs / กราฟแผนเทียบกำลังผลิตทุกแผนก':3,'⚖️ Capacity vs Plan vs Actual / กำลังผลิตเทียบแผนและผลจริง':3}
    if _quick_choice == _quick_options[4] and st.query_params.get('hub_kpi_url'):
        _kpi_link_label='เปิด KPI รายเดือน' if _LANG=='ไทย' else 'Open monthly KPI'
        st.markdown(f"<a href='{st.query_params.get('hub_kpi_url')}' target='_top' style='font-size:.82rem;color:#0057b8;text-decoration:underline'>↗ {_kpi_link_label}</a>",unsafe_allow_html=True)
        _nav_idx=0;_nav='🎯 Monthly Planning KPI Scorecard'
    elif _quick_choice in _quick_idx:
        _nav_idx=_quick_idx[_quick_choice];_nav=_NAV[_nav_idx]
        # Direct navigation changes the page without a large success banner.
    else:
        with _top_sidebar_nav:
            st.markdown('### 🧭 CONTROL CENTER / ศูนย์ควบคุม')
            st.caption('Open a category to see its pages, then choose the exact page. / เปิดหมวดเพื่อดูหน้าที่อยู่ข้างใน')
            for _gi,(_grp,_group_indices) in enumerate(_GROUPS.items()):
                # Guard bad/stale configured indices so navigation cannot crash at runtime.
                _safe_indices=[i for i in _group_indices if isinstance(i,int) and 0<=i<len(_NAV)]
                with st.expander(_grp,expanded=_gi==0):
                    for _sub_i in _safe_indices:
                        st.button(_NAV[_sub_i],key=f'daily_nav_{_sub_i}',use_container_width=True,type='primary' if st.session_state.get('daily_nav_selected',0)==_sub_i else 'secondary',on_click=_select_daily_module,args=(_sub_i,_quick_options[0]))
                    if len(_safe_indices)!=len(_group_indices):
                        st.caption('One unavailable page link was skipped safely; check the navigation map.')
        _nav_idx=int(st.session_state.get('daily_nav_selected',0))
        if not 0<=_nav_idx<len(_NAV):_nav_idx=0;st.session_state['daily_nav_selected']=0
        _nav=_NAV[_nav_idx]
        if _nav_idx==0:
            with _top_page_nav: st.markdown('<div class="ppc-control-card"><b>📺 MANAGEMENT + PLANNING LIVE VIEW / ภาพรวม</b><br>Choose any page from the expandable hierarchy on the left.</div>',unsafe_allow_html=True)
    if _nav_idx==0:
        st.markdown('<div class="ppc-control-card"><b>📺 MANAGEMENT + PLANNING LIVE VIEW / ภาพรวมบริหารและวางแผน</b><br>Neutral operational status • click modules for detail • selected-period charts auto-fit the screen</div>',unsafe_allow_html=True)
        st.markdown(f'## 📺 SELECTED-DATE FACTORY DASHBOARD — {dashboard_date:%d-%m-%Y}')
        if _hub_sources_url:st.markdown(f"<a href='{html.escape(str(_hub_sources_url),quote=True)}' target='_top' style='font-size:.76rem;color:#0057b8;text-decoration:underline'>↻ {'อัปเดตไฟล์ที่ใช้ในกราฟนี้' if _LANG=='ไทย' else 'Update files used by this analysis'}</a>",unsafe_allow_html=True)
        st.markdown('### 🏭 WIP')
        st.caption('WIP has one central destination in Planning Center: WIP — Planning vs Production. The page labels Plan-2026 planning quantities and department-reported Production snapshots separately with their source and cut-off.')
        _hub_wip_url=st.query_params.get('hub_wip_url','')
        if _hub_wip_url:
            st.markdown(f"<a href='{_hub_wip_url}' target='_top' style='display:inline-block;padding:.55rem .85rem;border:1px solid #0F766E;border-radius:.55rem;background:#ECFDF5;color:#115E59;font-size:.9rem;font-weight:700;text-decoration:none'>🏭 {'เปิดรายงาน WIP เดียวกับเมนูหลัก' if _LANG=='ไทย' else 'Open the same WIP report as the main menu'} →</a>",unsafe_allow_html=True)
        else:
            st.info('Return to Planning Center navigation and select Reports → WIP — Planning vs Production.')

        _sd=allp.copy()
        _sd['_dashboard_date']=pd.to_datetime(_sd['Plan Date'],errors='coerce').dt.date
        _sd=_sd[_sd['_dashboard_date'].eq(dashboard_date)].copy()
        if _sd.empty:
            st.warning('No executable production rows are scheduled for the selected dashboard date.')
        else:
            _secrows=[]
            for _sec,_g in _sd.groupby('Section',sort=False):
                _secrows.append({'Section':_sec,
                    'Plan pcs':round(float(pd.to_numeric(_g.get('Plan Qty',0),errors='coerce').fillna(0).sum())),
                    'Plan kg':round(float(pd.to_numeric(_g.get('Plan kg',0),errors='coerce').fillna(0).sum()),1),
                    'WO Count':_g['Work Order'].astype(str).nunique(),
                    'Peak Resource Load %':round(float(pd.to_numeric(_g.get('Utilization %',0),errors='coerce').fillna(0).max()),1)})
            st.dataframe(pd.DataFrame(_secrows),use_container_width=True,hide_index=True,height=min(360,90+36*len(_secrows)))
            _showcols=[c for c in ['Section','Work Order','Customer','Category','Due Date','Plan Qty','Plan kg','Machine','Kiln','Program','Capacity Basis','Source / Reason'] if c in _sd.columns]
            st.markdown('### Daily executable plan / แผนปฏิบัติการประจำวัน')
            st.dataframe(_sd[_showcols].sort_values(['Section','Due Date','Work Order'],na_position='last'),use_container_width=True,hide_index=True,height=420)
        _dm=res.get('master',pd.DataFrame()).copy()
        if not _dm.empty and 'Due Date' in _dm.columns:
            _dm['_due_dashboard']=pd.to_datetime(_dm['Due Date'],errors='coerce').dt.date
            _closed=_dm.get('Overall Closed',pd.Series(False,index=_dm.index)).fillna(False).astype(bool)
            _protect=_dm[(_dm['_due_dashboard']<=dashboard_date)&~_closed].copy()
            if not _protect.empty:
                _pc=[c for c in ['Work Order','Customer','Category','Due Date','Order Qty','Packing Actual','Remaining Packing'] if c in _protect.columns]
                st.markdown('### 🚨 Due/overdue WOs requiring protection by selected date')
                st.dataframe(_protect[_pc].sort_values(['Due Date','Work Order'],na_position='last'),use_container_width=True,hide_index=True,height=300)

        # Authoritative Plan2026 due-date cross-check for selected dashboard date + next working day.
        _dueview=pd.DataFrame()
        _dm_due=res.get('master',pd.DataFrame()).copy()
        if not _dm_due.empty and 'Due Date' in _dm_due.columns:
            _dm_due['_DueDate']=pd.to_datetime(_dm_due['Due Date'],errors='coerce').dt.date
            _next_due=(pd.Timestamp(dashboard_date)+pd.Timedelta(days=1)).date()
            while pd.Timestamp(_next_due).weekday()==6:
                _next_due=(pd.Timestamp(_next_due)+pd.Timedelta(days=1)).date()
            _closed_due=_dm_due.get('Overall Closed',pd.Series(False,index=_dm_due.index)).fillna(False).astype(bool)
            _dueview=_dm_due[_dm_due['_DueDate'].isin([dashboard_date,_next_due]) & ~_closed_due].copy()
            if not _dueview.empty:
                _dueview['Dashboard Packing Target']=pd.to_numeric(_dueview.get('Remaining Packing',_dueview.get('Order Qty',0)),errors='coerce').fillna(0)
                _pack_day=allp.copy()
                _pack_day['_pd_due']=pd.to_datetime(_pack_day.get('Plan Date'),errors='coerce').dt.date
                _pack_day=_pack_day[_pack_day['Section'].astype(str).eq('Packing') & _pack_day['_pd_due'].isin([dashboard_date,_next_due])]
                _pack_by=_pack_day.groupby('Work Order')['Plan Qty'].sum() if not _pack_day.empty else pd.Series(dtype=float)
                _dueview['Daily Planner Packing Qty']=_dueview['Work Order'].astype(str).map(_pack_by).fillna(0)
                _dueview['Open Packing Qty']=pd.to_numeric(_dueview.get('Remaining Packing',_dueview['Dashboard Packing Target']),errors='coerce').fillna(0)
                _keep=[c for c in ['Due Date','Work Order','Customer','Category','Order Qty','Packing Actual','Open Packing Qty','Dashboard Packing Target','Daily Planner Packing Qty'] if c in _dueview.columns]
                _dueview=_dueview[_keep].sort_values(['Due Date','Work Order'],na_position='last')

        st.markdown('## 🚚 PLAN 2026 DELIVERY TARGET → PACKING / เป้าหมายส่งมอบจาก Plan 2026')
        st.caption('Independent cross-check: every valid OPEN WO due TODAY or TOMORROW in Plan2026 is shown, even when the generated Daily Plan missed it.')
        if _dueview.empty: st.info('No open Plan2026 WO due today/tomorrow, or Due Date is unavailable.')
        else:
            st.dataframe(_dueview,use_container_width=True,hide_index=True,height=min(440,90+36*len(_dueview)),
              column_config={'Customer':st.column_config.TextColumn(width='large'),'Work Order':st.column_config.TextColumn(width='medium'),
               'Dashboard Packing Target':st.column_config.NumberColumn(width='medium',format='%.0f'),
               'Daily Planner Packing Qty':st.column_config.NumberColumn(width='medium',format='%.0f'),
               'Open Packing Qty':st.column_config.NumberColumn(width='medium',format='%.0f')})

        st.markdown('### 🎯 MANAGEMENT RISK VISIBILITY / ภาพรวมความเสี่ยงสำหรับผู้บริหาร')
        _late_n=int((pd.to_datetime(risk.get('Projected Finish'),errors='coerce')>pd.to_datetime(risk.get('Due Date'),errors='coerce')).fillna(False).sum()) if not risk.empty else 0
        _bo_qty=float(pd.to_numeric(risk.get('Open Qty',0),errors='coerce').fillna(0).sum()) if not risk.empty else 0
        _cv0=_capacity_validation(allp,caps)
        _over_n=int((pd.to_numeric(_cv0.get('Load %'),errors='coerce')>100).fillna(False).sum()) if not _cv0.empty else 0
        _fc0=_firing_consistency(allp,st.session_state.firing_override if isinstance(st.session_state.firing_override,pd.DataFrame) else pd.DataFrame())
        _fire_bad=int((_fc0.get('Result',pd.Series(dtype=str))=='FAIL').sum()) if not _fc0.empty else 0
        _k1,_k2,_k3,_k4=st.columns(4)
        _k1.metric('Open qty / Backorder visibility',f'{_bo_qty:,.0f} pcs')
        _k2.metric('Projected late WOs',_late_n)
        _k3.metric('Capacity overload day/sections',_over_n)
        _k4.metric('Firing-plan mismatches',_fire_bad)
        _a1,_a2,_a3,_a4=st.columns(4)
        if _a1.button('📋 Backorder detail / รายละเอียดงานค้าง',use_container_width=True,key='dash_bo_v1935'): st.session_state['dash_detail_v1935']='BACKORDER'
        if _a2.button('🚚 Risk WO detail / รายละเอียด WO เสี่ยง',use_container_width=True,key='dash_risk_v1935'): st.session_state['dash_detail_v1935']='RISK'
        if _a3.button('🏭 Capacity detail / รายละเอียดกำลัง',use_container_width=True,key='dash_cap_v1935'): st.session_state['dash_detail_v1935']='CAPACITY'
        if _a4.button('🔥 Firing mismatch detail / รายละเอียดแผนเผา',use_container_width=True,key='dash_fire_v1935'): st.session_state['dash_detail_v1935']='FIRING'
        _ddet=st.session_state.get('dash_detail_v1935','')
        if _ddet=='RISK':
            _rv=risk.copy(); _cols=[c for c in ['Work Order','Customer','Category','Open Qty','Due Date','Projected Finish','Bottleneck Process','Delivery Risk','Recovery Action'] if c in _rv.columns]
            st.dataframe(_rv[_cols] if _cols else _rv,use_container_width=True,hide_index=True,height=320)
            st.caption('Edit due date, closure, quantity, route or priority in Validation → Planner Decision Layer; recalculation determines whether risk is removed.')
        elif _ddet=='CAPACITY': st.dataframe(_cv0,use_container_width=True,hide_index=True,height=320)
        elif _ddet=='FIRING':
            st.caption('Firing mismatch = Daily Planner firing rows do not reconcile with the uploaded/current Firing Planner output by WO/date/quantity. Review exact evidence before release.')
            st.dataframe(_fc0,use_container_width=True,hide_index=True,height=320)
            if isinstance(st.session_state.firing_override,pd.DataFrame) and not st.session_state.firing_override.empty:
                st.session_state.firing_override=_persistent_data_editor(st.session_state.firing_override,use_container_width=True,height=340,key='dash_fire_editor_v1935')
        elif _ddet=='BACKORDER':
            _bd=_backorder_month_category(res.get('master',pd.DataFrame())); st.dataframe(_bd,use_container_width=True,hide_index=True,height=320)
        st.subheader('📺 MANAGEMENT / SHOPFLOOR TV DASHBOARD')
        st.caption('Built from the uploaded Plan 2026 + calculated daily plan. HD board is designed for TV viewing: large text, Plan2026 due deliveries, kiln loading and process-level execution summary. Detailed WO tables stay in analysis tabs; WIP has one central report.')
        # Compact live dashboard: Today/Tomorrow deliveries + risk + stock + WO status.
        _tom=(pd.Timestamp(dashboard_date)+pd.Timedelta(days=1)).date()
        while pd.Timestamp(_tom).weekday()==6:_tom=(pd.Timestamp(_tom)+pd.Timedelta(days=1)).date()
        _md=res.get('master',pd.DataFrame()).copy()
        def _due_delivery_rows(_day):
            if _md.empty or 'Due Date' not in _md.columns:return pd.DataFrame()
            _x=_md.copy();_x['_due']=pd.to_datetime(_x['Due Date'],errors='coerce').dt.date
            _closed=_x.get('Overall Closed',pd.Series(False,index=_x.index)).fillna(False).astype(bool)
            _x=_x[_x['_due'].eq(_day)&~_closed].copy()
            if _x.empty:return _x
            _oq=pd.to_numeric(_x.get('Order Qty',0),errors='coerce').fillna(0);_pa=pd.to_numeric(_x.get('Packing Actual Qty',_x.get('Packing Actual',0)),errors='coerce').fillna(0)
            _x['PCS']=pd.to_numeric(_x.get('Remaining Packing',_oq-_pa),errors='coerce').fillna(0).clip(lower=0)
            _agg={'PCS':'max'}
            for _c in ['Customer','Category','Specification','Due Date']:
                if _c in _x.columns:_agg[_c]='first'
            return _x.groupby('Work Order',as_index=False).agg(_agg)
        _today_del=_due_delivery_rows(dashboard_date)
        _tom_del=_due_delivery_rows(_tom)
        dc1,dc2=st.columns(2)
        def _delivery_card(col,title,df):
            with col:
                st.markdown(f'### {title}')
                if df.empty: st.success('No planned delivery / packing completion.')
                else:
                    vv=df.copy();vv['PCS']=pd.to_numeric(vv.get('PCS',0),errors='coerce').fillna(0).round().astype(int)
                    show=[c for c in ['Work Order','Customer','Category','Specification','PCS','Due Date'] if c in vv.columns]
                    st.dataframe(vv[show].sort_values('Due Date',na_position='last'),use_container_width=True,height=230,hide_index=True)
        _delivery_card(dc1,'🔵 PLAN2026 DUE TODAY / OPEN PACKING',_today_del)
        _delivery_card(dc2,'🟣 PLAN2026 DUE NEXT WORKDAY / OPEN PACKING',_tom_del)
        st.markdown('### 🚨 DELIVERY RISK — WHAT IS AT RISK AND WHY')
        if risk.empty: st.success('No open delivery risk rows.')
        else:
            rv=risk.copy()
            if 'Open Qty' in rv.columns: rv['Open Qty pcs']=pd.to_numeric(rv['Open Qty'],errors='coerce').fillna(0).round().astype(int)
            rshow=[c for c in ['Delivery Risk','Work Order','Customer','Category','Due Date','Open Qty pcs','Bottleneck Process','Projected Finish','Detailed Reason'] if c in rv.columns]
            st.dataframe(rv[rshow].sort_values(['Delivery Risk','Due Date'],na_position='last'),use_container_width=True,height=280,hide_index=True)
            _rpm0=_process_risk_matrix(res.get('master',pd.DataFrame()),risk)
            if not _rpm0.empty:
                _rpm0=_rpm0[pd.to_numeric(_rpm0['Risk Qty pcs'],errors='coerce').fillna(0)>0].copy()
                if not _rpm0.empty:
                    _fr0=px.bar(_rpm0,x='Process',y='Risk Qty pcs',color='Product Category',barmode='stack',category_orders={'Product Category':['P','R','S','T','M','PB']},title='DASHBOARD RISK — ALL PROCESSES × PRODUCT CATEGORY')
                    for _tr in _fr0.data:_tr.text=None
                    _rt0=_rpm0.groupby('Process',as_index=False)['Risk Qty pcs'].sum()
                    _fr0.add_scatter(x=_rt0['Process'],y=_rt0['Risk Qty pcs'],mode='text',text=[f'{v:,.0f}' for v in _rt0['Risk Qty pcs']],textposition='top center',showlegend=False,hoverinfo='skip')
                    _show_plotly(_fr0,'Dashboard_Risk_All_Processes')
        g1,g2=st.columns(2)
        with g1:
            stock0=res.get('stock',pd.DataFrame())
            st.markdown('### 📦 STOCK IN HAND')
            if isinstance(stock0,pd.DataFrame) and not stock0.empty:
                _tot_stock_col='Balance Stock t' if 'Balance Stock t' in stock0.columns else ('On Hand t' if 'On Hand t' in stock0.columns else None)
                if _tot_stock_col: st.metric('TOTAL STOCK IN HAND / สต็อกรวม',f"{pd.to_numeric(stock0[_tot_stock_col],errors='coerce').fillna(0).sum():,.2f} t")
                scol='Balance Stock t' if 'Balance Stock t' in stock0.columns else ('On Hand t' if 'On Hand t' in stock0.columns else None)
                if scol:
                    ss=stock0.groupby('Stock Source Sheet' if 'Stock Source Sheet' in stock0.columns else 'Material',as_index=False)[scol].sum()
                    xcol=ss.columns[0]
                    fig=px.bar(ss,x=xcol,y=scol,title='Stock in hand / available balance — values on hover only',hover_data={scol:':.3f'})
                    fig.update_traces(text=None,texttemplate=None)
                    _show_plotly(fig,'Dashboard_stock_in_hand')
                else: st.info('Stock quantity field not mapped.')
            else: st.info('Upload Stock on Hand to display stock graph.')
        with g2:
            st.markdown('### 📋 DAILY OPEN / CLOSED REPORT')
            st.caption('Whole-order status is shown once in Reports → Daily Open / Closed WO Report. Section OPEN/CLOSED entries are recorded separately under Production → Update WO Section Status.')
            _hub_reports_url=st.query_params.get('hub_reports_url','')
            if _hub_reports_url:
                st.markdown(f"<a href='{_hub_reports_url}' target='_top' style='font-size:.82rem;color:#0057b8;text-decoration:underline'>↗ {'เปิดรายงานเปิด/ปิดรายวัน' if _LANG=='ไทย' else 'Open daily status report'}</a>",unsafe_allow_html=True)
        st.markdown('### 🌐 Animated bilingual TV dashboard / แดชบอร์ด TV แบบเคลื่อนไหว')
        _tdates=pd.to_datetime(allp.get('Plan Date'),errors='coerce').dropna(); _tvmin=_tdates.min().date() if not _tdates.empty else dashboard_date; _tvmax=_tdates.max().date() if not _tdates.empty else dashboard_date
        _tv1,_tv2=st.columns(2); _tvfrom=_tv1.date_input('TV FROM / TV จากวันที่',value=max(_tvmin,dashboard_date),min_value=_tvmin,max_value=_tvmax,key='tv_from_v1935'); _tvto=_tv2.date_input('TV TO / TV ถึงวันที่',value=min(_tvmax,max(_tvmin,dashboard_date)+timedelta(days=13)),min_value=_tvmin,max_value=_tvmax,key='tv_to_v1935')
        if _tvto<_tvfrom:_tvfrom,_tvto=_tvto,_tvfrom
        _logo=Path(__file__).with_name('SL_LOGO_BANNER.png'); _backorder_master=_active_backorder_master(res.get('master',pd.DataFrame()))
        _html,_tv_audit=_tv_html_v1935(res.get('master',pd.DataFrame()),risk,allp,caps,res.get('stock',pd.DataFrame()),st.session_state.firing_override,_tvfrom,_tvto,_logo,wip,st.session_state.get('daily_result_meta'),{'Plan-2026':st.session_state.get('plan_path'),'Firing plan':st.session_state.get('fire_path'),'Capacity':st.session_state.get('cap_path'),'Stock on hand':st.session_state.get('stock_path')},backorder_master=_backorder_master)
        st.caption(f"HTML parity check — exported TV file: {_tv_audit['today_target_pcs']:,.0f} pcs today · {_tv_audit['next_workday_target_pcs']:,.0f} pcs next workday · {_tv_audit['delivery_risk_wo_count']:,} date-windowed risk WOs · {_tv_audit['overdue_backorder_wo_count']:,} overdue backorders / {_tv_audit['overdue_backorder_pcs']:,.0f} pcs / {_tv_audit['overdue_backorder_ton']:,.2f} ton (all due months; same rule as Backorder Analysis). Snapshot {_tv_audit['generated_at']} · fingerprint {_tv_audit['fingerprint'][:16]}.")
        st.download_button('🌐 DOWNLOAD ANIMATED BILINGUAL TV DASHBOARD / ดาวน์โหลดแดชบอร์ด TV HTML',_html.encode('utf-8'),file_name=f'SL_PPC_TV_{_tvfrom:%Y%m%d}_{_tvto:%Y%m%d}.html',mime='text/html',use_container_width=True,key='tv_html_v1935')
    
        st.markdown('## ⚠️ RISK SUMMARY / สรุปงานเสี่ยง')
        st.caption('TV-style summary: risk quantity, WO count, nearest due date and main bottleneck. Detailed WO evidence remains in Delivery Risk tab.')
        if risk.empty:
            st.success('No open delivery risk rows.')
        else:
            _rs=risk.copy()
            # Resolve legacy shared Plan2026 Grinding/Cutting field to the actual WO route for display.
            if 'Bottleneck Process' in _rs.columns:
                _mm=res.get('master',pd.DataFrame()).copy()
                _route_by_wo={}
                if isinstance(_mm,pd.DataFrame) and not _mm.empty and 'Work Order' in _mm.columns:
                    for _,_mr in _mm.iterrows():
                        try: _route_by_wo[str(_mr.get('Work Order','')).strip()]=dl.route(_mr)
                        except Exception: pass
                def _risk_process(_r):
                    bp=str(_r.get('Bottleneck Process','') or '').strip()
                    if 'GRINDING/CUTTING' in bp.upper() or 'GRINDING / CUTTING' in bp.upper():
                        return _route_by_wo.get(str(_r.get('Work Order','')).strip(),'Grinding / เจียร')
                    return bp
                _rs['Bottleneck Process']=_rs.apply(_risk_process,axis=1)
            _rs['_risk']=_rs.get('Delivery Risk',pd.Series('',index=_rs.index)).astype(str).str.upper()
            _rs['_qty']=pd.to_numeric(_rs.get('Open Qty',0),errors='coerce').fillna(0)
            _rs['_due']=pd.to_datetime(_rs.get('Due Date'),errors='coerce')
            _risky=_rs[_rs['_risk'].isin(['HIGH','LATE','AT RISK','WATCH'])].copy()
            if _risky.empty:
                st.success('No HIGH/LATE/AT RISK/WATCH work orders.')
            else:
                _c1,_c2,_c3,_c4=st.columns(4)
                _c1.metric('RISK WOs',f"{_risky['Work Order'].astype(str).nunique():,}")
                _c2.metric('RISK QTY',f"{_risky['_qty'].sum():,.0f} pcs")
                _nd=_risky['_due'].min()
                _c3.metric('NEAREST DUE',_nd.strftime('%d %b') if pd.notna(_nd) else '-')
                _bn=_risky.get('Bottleneck Process',pd.Series('',index=_risky.index)).fillna('').astype(str)
                _bn=_bn[_bn.str.strip().ne('')]
                _main=_bn.value_counts().index[0] if not _bn.empty else 'CHECK'
                _c4.metric('MAIN BOTTLENECK',str(_main)[:24])
                _sum=_risky.groupby('_risk',as_index=False).agg(WOs=('Work Order','nunique'),PCS=('_qty','sum'))
                _sum=_sum.sort_values('PCS',ascending=False)
                _fig=px.bar(_sum,x='_risk',y='PCS',text='PCS',hover_data=['WOs'],title='Risk quantity by status')
                _fig.update_traces(texttemplate='%{text:,.0f} pcs',textposition='outside')
                _fig.update_layout(height=360,font=dict(size=18),xaxis_title='',yaxis_title='pcs',showlegend=False,
                                   margin=dict(l=40,r=30,t=65,b=40))
                _show_plotly(_fig,'Dashboard_Risk_Summary')
                _top=_risky.sort_values(['_due','_qty'],ascending=[True,False]).head(6).copy()
                _top['DUE']=_top['_due'].dt.strftime('%d %b')
                _top['PCS']=_top['_qty'].round().astype(int)
                _show=[c for c in ['Work Order','Customer','Category','PCS','DUE','Bottleneck Process'] if c in _top.columns]
                st.dataframe(_top[_show],use_container_width=True,hide_index=True,height=250)
        # V1.9.33: removed single-process 'Bottleneck slide'. Risk/bottleneck evidence is shown in Pareto/detail views where all affected processes remain visible.

    if _nav_idx==1:
        st.caption('Planning-start rule: ALL existing Plan 2026 WIP buckets (Preparation, Mixing, Forming, Firing-ready, Grinding OR Cutting, Packing) are evaluated from the selected start date. New output moves only on the next working day; Firing follows the uploaded Firing Planner.')
        # Hard start-date audit: no silent date drift. If a process has existing WIP but cannot
        # be scheduled on the selected date, show it immediately as a planning exception.
        srcw=res.get('wip',pd.DataFrame()).copy()
        audit=[]
        if not srcw.empty:
            post=pd.to_numeric(srcw.get('WIP Grinding / Cutting',0),errors='coerce').fillna(0)
            _routes=srcw.apply(dl.route,axis=1)
            source_qty={
              'Preparation':pd.to_numeric(srcw.get('WIP Preparation',0),errors='coerce').fillna(0).sum(),
              'Mixing':pd.to_numeric(srcw.get('WIP Mixing',0),errors='coerce').fillna(0).sum(),
              'Forming':pd.to_numeric(srcw.get('WIP Forming',0),errors='coerce').fillna(0).sum(),
              'Firing':pd.to_numeric(srcw.get('WIP Firing',0),errors='coerce').fillna(0).sum(),
              'Grinding / เจียร':post[_routes.astype(str).str.startswith('Grinding')].sum(),
              'Cutting / ตัด':post[_routes.astype(str).str.startswith('Cutting')].sum(),
              'Packing':pd.to_numeric(srcw.get('WIP Packing',0),errors='coerce').fillna(0).sum()}
            for sec,q0 in source_qty.items():
                qstart=0.0
                if not allp.empty:
                    mask=(allp['Section'].eq(sec)) & (pd.to_datetime(allp['Plan Date'],errors='coerce').dt.date.eq(start))
                    qstart=pd.to_numeric(allp.loc[mask,'Plan Qty'],errors='coerce').fillna(0).sum()
                status='STARTS ON SELECTED DATE' if qstart>0 else ('NO EXISTING WIP' if q0<=0 else 'HOLD / CHECK RESOURCE-MATCH OR INPUT')
                audit.append({'Process':sec,'Existing WIP pcs':round(float(q0),2),'Planned on selected start pcs':round(float(qstart),2),'Start-date status':status})
        if audit:
            adf=pd.DataFrame(audit); st.markdown('**🔒 START-DATE LOCK AUDIT / ตรวจสอบวันเริ่มแผน**');st.dataframe(adf,use_container_width=True,hide_index=True)
            bad=adf[(adf['Existing WIP pcs']>0)&(adf['Planned on selected start pcs']<=0)]
            if not bad.empty: st.error('Selected planning date is NOT being silently shifted. Processes with existing WIP but zero executable plan on the selected date are explicitly shown above and must have their resource/input mismatch corrected.')
        if not allp.empty:
            cols=[c for c in ['Plan Date','Section','Work Order','Customer','Specification','Category','Due Date','Plan Qty','Plan kg','Plan ton','Post-Firing Route','QC Required','Machine','Bottleneck Machine','Kiln','Program','NCR Qty','NCR Disposition','Capacity Basis','Source / Reason'] if c in allp.columns]
            _requested_section=st.query_params.get('section','')
            _sections=['All sections / ทุกแผนก']+sorted(allp['Section'].dropna().astype(str).unique())
            _default=next((i for i,x in enumerate(_sections) if _requested_section and x.startswith(_requested_section)),0)
            _section=st.selectbox('แผนแผนก / Section plan',_sections,index=_default,key='daily_section62_'+_requested_section)
            _section_plan=allp if _section==_sections[0] else allp[allp['Section'].eq(_section)]
            st.dataframe(_section_plan[cols],use_container_width=True,height=650)
        # explicit start-date proof
        if not allp.empty:
            first_by=allp.groupby('Section',as_index=False)['Plan Date'].min().rename(columns={'Plan Date':'First Planned Date'})
            st.markdown('**Start-date evidence / หลักฐานวันเริ่มแผน**');st.dataframe(first_by,use_container_width=True,hide_index=True)
    if _nav_idx==2:
        st.subheader('🔀 Work Order route + NCR manager / เส้นทางกระบวนการ + NCR')
        st.info('Select a WO, review the complete route, and change the post-firing branch or QC/NCR control. These are planning-layer overrides only; Plan 2026 is not overwritten.')
        master=res.get('master',pd.DataFrame()).copy()
        if master.empty:
            st.info('No WO master loaded.')
        else:
            master=master.drop_duplicates(subset=['Work Order'],keep='first')
            wolist=master['Work Order'].astype(str).sort_values().tolist()
            sel=st.selectbox('Work Order / ใบสั่งผลิต',wolist,key='route_wo')
            rr=master[master['Work Order'].astype(str).eq(sel)].iloc[0]
            default_rt=dl.route(rr)
            saved=st.session_state.plan_overrides
            sov=saved[saved['Work Order'].astype(str).eq(sel)].iloc[0] if isinstance(saved,pd.DataFrame) and not saved.empty and 'Work Order' in saved.columns and saved['Work Order'].astype(str).eq(sel).any() else None
            cur_rt=str(sov.get('Post-Firing Route')) if sov is not None and pd.notna(sov.get('Post-Firing Route')) and str(sov.get('Post-Firing Route')).strip() else 'AUTO'
            cur_qc=str(sov.get('QC Required')) if sov is not None and pd.notna(sov.get('QC Required')) and str(sov.get('QC Required')).strip() else 'YES'
            cur_nq=float(pd.to_numeric(pd.Series([sov.get('NCR Qty') if sov is not None else 0]),errors='coerce').fillna(0).iloc[0])
            cur_ns=str(sov.get('NCR Stage')) if sov is not None and pd.notna(sov.get('NCR Stage')) and str(sov.get('NCR Stage')).strip() else 'QC'
            cur_nd=str(sov.get('NCR Disposition')) if sov is not None and pd.notna(sov.get('NCR Disposition')) and str(sov.get('NCR Disposition')).strip() else 'HOLD'
            c1,c2,c3=st.columns(3);c1.metric('Customer',str(rr.get('Customer','')));c2.metric('Specification',str(rr.get('Specification','')));c3.metric('Default post-fire route',default_rt)
            route_options=['AUTO','Grinding / เจียร','Cutting / ตัด','Direct Packing / บรรจุโดยตรง']
            if cur_rt not in route_options:cur_rt='AUTO'
            qccol,rtcol=st.columns([1,2])
            qcval=qccol.selectbox('QC after new kiln output?',options=['YES','NO'],index=0 if cur_qc.upper()!='NO' else 1,key='route_qc')
            rtval=rtcol.selectbox('Post-firing route / เส้นทางหลังเผา',route_options,index=route_options.index(cur_rt),key='route_post')
            n1,n2,n3=st.columns(3)
            nq=n1.number_input('NCR quantity pcs',min_value=0.0,value=cur_nq,step=1.0,key='route_ncr_qty')
            nstages=['Firing','QC','Grinding','Cutting','Packing']; ns=n2.selectbox('NCR stage',nstages,index=nstages.index(cur_ns) if cur_ns in nstages else 1,key='route_ncr_stage')
            ndisps=['HOLD','REWORK','SCRAP / REJECT','ACCEPT / USE']; nd=n3.selectbox('NCR disposition',ndisps,index=ndisps.index(cur_nd) if cur_nd in ndisps else 0,key='route_ncr_disp')
            resolved=default_rt if rtval=='AUTO' else rtval
            full=['Preparation','Mixing','Forming','Firing']+(['QC'] if qcval=='YES' else [])
            if not resolved.startswith('Direct Packing'):full.append(resolved.split(' / ')[0])
            full.append('Packing')
            st.markdown('**Complete process route / เส้นทางกระบวนการทั้งหมด**')
            st.success('  →  '.join(full))
            note=st.text_input('Route/NCR note (optional)',value=str(sov.get('Route Note','')) if sov is not None else '',key='route_note')
            if st.button('💾 SAVE WO ROUTE / NCR',use_container_width=True):
                row={'Work Order':sel,'Post-Firing Route':rtval,'QC Required':qcval,'NCR Qty':nq,'NCR Stage':ns,'NCR Disposition':nd,'Route Note':note}
                st.session_state.plan_overrides=_merge_override_row(st.session_state.plan_overrides,row)
                st.success('Saved. Click CREATE DAILY PLAN to recalculate from the same Plan 2026 + firing data.')
            st.markdown('**Current WO planned process rows**')
            wr=allp[allp['Work Order'].astype(str).eq(sel)].copy() if not allp.empty else pd.DataFrame()
            st.dataframe(wr[[c for c in ['Plan Date','Section','Plan Qty','Machine','Kiln','Program','Source / Reason'] if c in wr.columns]],use_container_width=True,height=320)
    if _nav_idx==3:
        st.subheader('📊 Daily Capacity vs Planned vs Actual / กำลังการผลิต - แผน - ผลิตจริง')
        st.caption('Capacity, plan and actual use the same selected daily-plan calculation and section. Grinding and Cutting stay separate; Mixing stays in mill units. Missing actual evidence is blank, not treated as zero.')
        if st.query_params.get('hub_capacity_actual_url'):
            st.markdown(f"<a href='{st.query_params.get('hub_capacity_actual_url')}' target='_top' style='font-size:.78rem;color:#0057b8;text-decoration:underline'>↗ Open this same Capacity vs Plan vs Actual report in the main menu</a>",unsafe_allow_html=True)
        st.markdown('### All-section plan vs controlled capacity / แผนเทียบกำลังผลิตทุกแผนก')
        # Capacity summary is keyed to the engine's source process names. Do not
        # split/rename Grinding and Cutting here before joining capacity rows.
        _capacity_plan_rows=res.get('all',allp) if isinstance(res,dict) else allp
        _all_cv=_capacity_validation(_capacity_plan_rows,caps)
        if _all_cv.empty:
            st.info('Create/load the current daily schedule first. The charts below use that saved calculation; this page will not silently rebuild it.')
        else:
            _ton_cv=_all_cv[_all_cv['Basis'].eq('ton') & ~_all_cv['Section'].astype(str).str.contains('Mixing',case=False)].copy()
            if not _ton_cv.empty:
                _ton_long=_ton_cv.melt(id_vars=['Date','Section'],value_vars=['Capacity ton','Plan ton'],var_name='Measure',value_name='Tonnes per day')
                _ton_fig=px.bar(_ton_long,x='Date',y='Tonnes per day',color='Measure',barmode='group',facet_row='Section',
                    title='SECTION PLAN vs CONTROLLED CAPACITY · tonnes/day · each process kept separate')
                _ton_fig.update_layout(height=max(480,190*_ton_cv['Section'].nunique()),xaxis_title='Plan date',yaxis_title='Metric tonnes/day',legend_title='')
                _show_plotly(_ton_fig,'All_sections_plan_vs_capacity_tonnes')
            _pcs_cv=_all_cv[_all_cv['Basis'].eq('pcs')].copy()
            if not _pcs_cv.empty:
                _pcs_long=_pcs_cv.melt(id_vars=['Date','Section'],value_vars=['Capacity pcs','Plan pcs'],var_name='Measure',value_name='Pieces per day')
                _pcs_fig=px.bar(_pcs_long,x='Date',y='Pieces per day',color='Measure',barmode='group',facet_row='Section',
                    title='SECTION PLAN vs CONTROLLED CAPACITY · pieces/day · only compatible pcs-rated sections')
                _pcs_fig.update_layout(height=max(380,190*_pcs_cv['Section'].nunique()),xaxis_title='Plan date',yaxis_title='Pieces/day',legend_title='')
                _show_plotly(_pcs_fig,'All_sections_plan_vs_capacity_pcs')
            st.markdown("<a href='?page=daily&amp;focus=mixing' target='_top' style='font-size:.84rem;color:#0057b8;text-decoration:underline'>↗ Mixing capacity is shown separately in its native units: mills/day and mill batches</a>",unsafe_allow_html=True)
            _unrated=_all_cv[_all_cv['Basis'].eq('not directly comparable')]
            if not _unrated.empty:
                st.caption('Sections without a controlled comparable daily capacity remain ungraphed as feasible capacity; see the table below for their CHECK rows.')
        _ds_valid,_ds_rejected,_ds_errors=_ds_cache_valid,_ds_cache_rejected,_ds_cache_errors
        seed=_ds_valid.rename(columns={'Production Actual Qty':'Actual Qty'})[['Date','Section','Work Order','Actual Qty']].copy() if not _ds_valid.empty else pd.DataFrame()
        if seed.empty:seed=pd.DataFrame(columns=['Date','Section','Work Order','Actual Qty','Actual ton'])
        actual_edit=_persistent_data_editor(_actual_table(seed,res.get('master',pd.DataFrame()),allp),num_rows='dynamic',use_container_width=True,height=260,key='actual_editor')
        actualagg=_aggregate_actual(actual_edit,res.get('master',pd.DataFrame()),allp)
        capshow=caps.merge(actualagg,on=['Plan Date','Section'],how='left')
        for _actual_col in ['Actual pcs','Actual ton','Actual WOs']:
            capshow[_actual_col]=pd.to_numeric(capshow.get(_actual_col,pd.Series(np.nan,index=capshow.index)),errors='coerce')
        # Work-order count and plan pcs are essential operational measures; ton alone is not sufficient for many sections.
        if not allp.empty:
            woct=allp.groupby(['Plan Date','Section'],as_index=False)['Work Order'].nunique().rename(columns={'Work Order':'Planned WOs'});capshow=capshow.merge(woct,on=['Plan Date','Section'],how='left')
        capshow['Planned WOs']=pd.to_numeric(capshow.get('Planned WOs',0),errors='coerce').fillna(0)
        # Equivalent pcs capacity uses the day's planned product mix average weight; it is shown as equivalent, not a universal machine rating.
        avg_g=(pd.to_numeric(capshow.get('Plan ton',0),errors='coerce').fillna(0)*1e6/pd.to_numeric(capshow.get('Plan pcs',0),errors='coerce').replace(0,pd.NA));capshow['Capacity pcs (equiv)']=(pd.to_numeric(capshow.get('Capacity ton',0),errors='coerce').fillna(0)*1e6/avg_g).fillna(0)
        if not capshow.empty:
            if actualagg.empty:st.info('No Daily Status actual rows are loaded for this period. Actual bars are left blank; missing is not treated as zero.')
            sec=st.selectbox('🏭 Section for graph',sorted(capshow['Section'].dropna().unique()),key='cap_sec')
            g=capshow[capshow['Section']==sec].copy().sort_values('Plan Date')
            fig,ax=plt.subplots(figsize=(12,4.8));x=range(len(g));w=.26
            ax.bar([i-w for i in x],g['Capacity ton'],width=w,label='Capacity ton');ax.bar(list(x),g['Plan ton'],width=w,label='Planned ton');ax.bar([i+w for i in x],g['Actual ton'],width=w,label='Actual ton')
            ax.set_xticks(list(x));ax.set_xticklabels([str(v) for v in g['Plan Date']],rotation=45,ha='right');ax.set_ylabel('ton');ax.set_title(f'{sec} — Capacity vs Plan vs Actual ');ax.legend();fig.tight_layout();_show_mpl(fig,'SL_PPC_graph_01')
            fig,ax=plt.subplots(figsize=(12,4.8));x=range(len(g));w=.25;ax.bar([i-w for i in x],g['Capacity pcs (equiv)'],width=w,label='Capacity pcs (equiv)');ax.bar(list(x),g['Plan pcs'],width=w,label='Plan pcs');ax.bar([i+w for i in x],g['Actual pcs'],width=w,label='Actual pcs');ax.set_xticks(list(x));ax.set_xticklabels([str(v) for v in g['Plan Date']],rotation=45,ha='right');ax.set_title(f'{sec} — CAPACITY / PLAN / ACTUAL PCS ');ax.legend();fig.tight_layout();_show_mpl(fig,'SL_PPC_graph_02')
            fig,ax=plt.subplots(figsize=(12,4.2));x=range(len(g));w=.32;ax.bar([i-w/2 for i in x],g['Planned WOs'],width=w,label='Planned WOs');ax.bar([i+w/2 for i in x],g['Actual WOs'],width=w,label='Actual WOs');ax.set_xticks(list(x));ax.set_xticklabels([str(v) for v in g['Plan Date']],rotation=45,ha='right');ax.set_title(f'{sec} — WORK ORDERS: PLAN vs ACTUAL');ax.legend();fig.tight_layout();_show_mpl(fig,'SL_PPC_graph_03')
            st.dataframe(capshow,use_container_width=True,height=500)
    if _nav_idx==4:
        st.subheader('📈 PLAN vs ACTUAL ANALYSIS / วิเคราะห์แผนเทียบผลจริง')
        st.caption("Uses ALL rows, including fully/sectionwise closed rows. When dated Daily Actual is not uploaded, a due-date cohort means orders are grouped by their customer Due Date month/week—not by the actual day that each process ran. Cumulative Actual quantities are never plotted into future due-date periods; future Actual is shown as zero unless dated Daily Actual evidence exists.")
        src=res.get('master',pd.DataFrame()).copy()
        if src.empty:
            st.info('No Plan 2026 data.')
        else:
            secs=['Preparation','Mixing','Forming','Firing','Grinding','Packing']
            rec=[]
            for sec in secs:
                pc=f'{sec} Plan'; ac=f'{sec} Actual'
                if pc in src.columns and ac in src.columns:
                    for _,rr in src.iterrows():
                        _disp=sec
                        if sec=='Grinding':_disp=('Cutting / ตัด' if str(dl.route(rr)).startswith('Cutting') else 'Grinding / เจียร')
                        rec.append({'Due Date':rr.get('Due Date'),'Section':_disp,'Category':eng.normcat(rr.get('Category')),'Plan Qty':float(pd.to_numeric(rr.get(pc,0),errors='coerce') or 0),'Actual Qty':float(pd.to_numeric(rr.get(ac,0),errors='coerce') or 0),'Net Weight g/pc':float(pd.to_numeric(rr.get('Net Weight g/pc',0),errors='coerce') or 0),'Work Order':rr.get('Work Order','')})
            pa=pd.DataFrame(rec)
            if pa.empty: st.warning('Plan/Actual quantity columns are not available under the current mapping.')
            else:
                pa['Due Date']=pd.to_datetime(pa['Due Date'],errors='coerce')
                _pvalid=pa['Due Date'].dropna(); _pmin=_pvalid.min().date() if not _pvalid.empty else pd.Timestamp(start).date(); _pmax=_pvalid.max().date() if not _pvalid.empty else pd.Timestamp(start).date()
                _pc1,_pc2=st.columns(2); _pfrom=_pc1.date_input('Graph FROM / กราฟจากวันที่',value=_pmin,min_value=_pmin,max_value=_pmax,key='pa_from_v1935'); _pto=_pc2.date_input('Graph TO / กราฟถึงวันที่',value=min(_pmax,_pfrom+timedelta(days=27)),min_value=_pmin,max_value=_pmax,key='pa_to_v1935')
                if _pto<_pfrom:_pfrom,_pto=_pto,_pfrom
                pa=pa[(pa['Due Date'].dt.date>=_pfrom)&(pa['Due Date'].dt.date<=_pto)].copy()
                period=st.selectbox('Period tab / แท็บช่วงเวลา',['Daily','Weekly','Monthly','Quarterly'],index=1,key='pa_period_v1935')
                if period=='Daily': pa['Period']=pa['Due Date'].dt.strftime('%Y-%m-%d')
                elif period=='Weekly': pa['Period']=pa['Due Date'].dt.to_period('W-SAT').astype(str)
                elif period=='Monthly': pa['Period']=pa['Due Date'].dt.to_period('M').astype(str)
                else: pa['Period']=pa['Due Date'].dt.to_period('Q').astype(str)
                pa=pa.dropna(subset=['Period'])
                # Plan2026 process Actual fields are cumulative quantities, not dated production history.
                # Therefore a WO due in Oct/Nov must NEVER create an Oct/Nov 'Actual' bar in September.
                # Future due-date cohorts are suppressed from Actual unless a dated Daily Actual source is used.
                _cut=pd.Timestamp(start)
                pa['_Future Due Cohort']=pa['Due Date']>_cut
                pa.loc[pa['_Future Due Cohort'],'Actual Qty']=0.0
                overall=pa.groupby('Period',as_index=False)[['Plan Qty','Actual Qty']].sum()
                fig=go.Figure();fig.add_bar(x=overall['Period'],y=overall['Plan Qty'],name='Plan pcs');fig.add_bar(x=overall['Period'],y=overall['Actual Qty'],name='Actual pcs (reported through planning date only)');fig.update_layout(barmode='group',title=f'{period} Plan vs Actual — future Actual suppressed after {start}',xaxis_title=period,yaxis_title='pcs',hovermode='x unified');_show_plotly(fig,'SL_PPC_plot_01')
                bys=pa.groupby(['Period','Section'],as_index=False)[['Plan Qty','Actual Qty']].sum();st.dataframe(bys,use_container_width=True,height=280)
                cat=pa.groupby(['Period','Category'],as_index=False)[['Plan Qty','Actual Qty']].sum()
                _catlong=pd.concat([cat[['Period','Category','Plan Qty']].rename(columns={'Plan Qty':'Qty'}).assign(Measure='Plan / แผน'),cat[['Period','Category','Actual Qty']].rename(columns={'Actual Qty':'Qty'}).assign(Measure='Actual / ผลจริง')],ignore_index=True)
                fig=px.bar(_catlong,x='Period',y='Qty',color='Category',facet_row='Measure',barmode='stack',category_orders={'Category':['P','R','S','T','M','PB']},title=f'{period} PLAN AND ACTUAL OUTPUT BY PRODUCT CATEGORY');fig.update_xaxes(title='Period / ช่วงเวลา');fig.update_yaxes(title='Quantity (pcs) / จำนวน (ชิ้น)');fig.update_layout(legend_title='Product category / กลุ่มสินค้า');_show_plotly(fig,'SL_PPC_plot_02')
                pa['Plan kg']=pa['Plan Qty']*pd.to_numeric(pa.get('Net Weight g/pc',0),errors='coerce').fillna(0)/1000; pa['Actual kg']=pa['Actual Qty']*pd.to_numeric(pa.get('Net Weight g/pc',0),errors='coerce').fillna(0)/1000
                _wg=pa.groupby('Period',as_index=False)[['Plan kg','Actual kg']].sum(); _fw=go.Figure();_fw.add_bar(x=_wg['Period'],y=_wg['Plan kg'],name='Plan / แผน');_fw.add_bar(x=_wg['Period'],y=_wg['Actual kg'],name='Actual / ผลจริง');_fw.update_layout(barmode='group',title=f'{period} PLAN vs ACTUAL — WEIGHT',xaxis_title='Period / ช่วงเวลา',yaxis_title='Weight (kg) / น้ำหนัก (กก.)',legend_title='Measure / ตัวชี้วัด');_show_plotly(_fw,'PlanActual_weight_v1935')
                _wrows=[]
                for _per,_gg in pa.groupby('Period'):_wrows.append({'Period':_per,'Plan WOs':_gg.loc[_gg['Plan Qty']>0,'Work Order'].astype(str).nunique(),'Actual WOs':_gg.loc[_gg['Actual Qty']>0,'Work Order'].astype(str).nunique()})
                _wg2=pd.DataFrame(_wrows); _fwo=go.Figure();_fwo.add_bar(x=_wg2['Period'],y=_wg2['Plan WOs'],name='Plan WOs / WO แผน');_fwo.add_bar(x=_wg2['Period'],y=_wg2['Actual WOs'],name='Actual WOs / WO จริง');_fwo.update_layout(barmode='group',title=f'{period} PLAN vs ACTUAL — WORK ORDERS',xaxis_title='Period / ช่วงเวลา',yaxis_title='Unique WOs / จำนวน WO',legend_title='Measure / ตัวชี้วัด');_show_plotly(_fwo,'PlanActual_WO_v1935')
                st.markdown('### Past-due backorders / งานค้างส่งเกินกำหนด — by original due month')
                bg=_monthly_open_closed(src)
                if bg.empty:
                    st.info('No due-date status data available.')
                else:
                    # The shared overdue-only helper already excludes every future due date.
                    curm=pd.Period(pd.Timestamp(bkk_today()),freq='M')
                    st.caption(f"Backorder definition shared with Home: open balance due before {bkk_today():%d %b %Y}; future orders are demand, not backorders.")
                    _bd=pd.to_datetime(bg['Due Month'].astype(str)+'-01',errors='coerce') if not bg.empty else pd.Series(dtype='datetime64[ns]')
                    if not bg.empty and _bd.notna().any():
                        _bmin=_bd.min().date(); _bmax=(pd.Timestamp(_bd.max())+pd.offsets.MonthEnd(0)).date()
                        _bc1,_bc2=st.columns(2)
                        _bfrom=_bc1.date_input('Backorder FROM / งานค้างส่งจากวันที่',value=_bmin,min_value=_bmin,max_value=_bmax,key='backorder_from_v1936')
                        _bto=_bc2.date_input('Backorder TO / งานค้างส่งถึงวันที่',value=_bmax,min_value=_bmin,max_value=_bmax,key='backorder_to_v1936')
                        if _bto<_bfrom:_bfrom,_bto=_bto,_bfrom
                        _bfromp=pd.Period(pd.Timestamp(_bfrom),freq='M'); _btop=pd.Period(pd.Timestamp(_bto),freq='M')
                        _bper=pd.PeriodIndex(bg['Due Month'],freq='M'); bg=bg[(_bper>=_bfromp)&(_bper<=_btop)].copy()
                    # V1.9.18: management backorder must retain product-category evidence.
                    bc=_backorder_month_category(src)
                    if not bc.empty:
                        if '_bfromp' in locals() and '_btop' in locals():
                            _bp2=pd.PeriodIndex(bc['Due Month'],freq='M'); bc=bc[(_bp2>=_bfromp)&(_bp2<=_btop)].copy()
                        _bcq=bc.groupby(['Due Month','Product Category'],as_index=False)['Qty pcs'].sum()
                        fig=px.bar(_bcq,x='Due Month',y='Qty pcs',color='Product Category',barmode='stack',category_orders={'Product Category':['P','R','S','T','M','PB']},title='Past-due OPEN backorders — product-category stack by due month')
                        fig.update_layout(xaxis_title='Original due month / เดือนกำหนดส่งเดิม',yaxis_title='Quantity (pcs) / จำนวน (ชิ้น)',legend_title='Product category / กลุ่มสินค้า')
                        _show_plotly(fig,'Backorder_month_open_closed_category_stack_v1935')
                        st.dataframe(bc.sort_values(['Due Month','Status','Product Category']),use_container_width=True,hide_index=True)
                    else:
                        st.info('No category-mapped backorder rows.')

    if _nav_idx==5:
        st.header('🏭 WIP — Planning vs Production / WIP แผนเทียบฝ่ายผลิต')
        st.caption('WIP values are shown in the central Planning Center page. Planning queues and Production snapshots have separate definitions and are never added together.')
        _hub_wip_url=st.query_params.get('hub_wip_url','')
        if _hub_wip_url:
            st.markdown(f"<a href='{_hub_wip_url}' target='_top' style='display:inline-block;padding:.55rem .85rem;border:1px solid #0F766E;border-radius:.55rem;background:#ECFDF5;color:#115E59;font-size:.9rem;font-weight:700;text-decoration:none'>🏭 {'เปิดรายงาน WIP เดียวกับเมนูหลัก' if _LANG=='ไทย' else 'Open the same WIP report as the main menu'} →</a>",unsafe_allow_html=True)
        else:
            st.caption('Return to Planning Center navigation → Reports → WIP — Planning vs Production.')
    if _nav_idx==6:
        st.subheader('🌀 Mixer / 🏗️ Forming / 🛠️ Post-firing resources')
        for sec in ['Mixing','Forming','Grinding / เจียร','Cutting / ตัด']:
            d0=res['plans'].get(sec,pd.DataFrame())
            st.markdown(f'**{sec}**')
            if d0 is None or d0.empty:st.caption('No plan rows.')
            else:st.dataframe(d0,use_container_width=True,height=250)
    if _nav_idx==7:
        st.subheader('🧪 DAILY PLAN MATERIAL CHECK — STOCK / BOM / ALTERNATIVES')
        _stock=res.get('stock',pd.DataFrame()).copy()
        if not _stock.empty:
            # Show ALL materials, highest shortage/gap first; no top-N truncation. Exact source columns are retained in hover.
            _numcols=[c for c in _stock.columns if pd.api.types.is_numeric_dtype(_stock[c])]
            _matcol=next((c for c in _stock.columns if 'material' in str(c).lower() or 'วัตถุดิบ' in str(c)),_stock.columns[0])
            if _numcols:
                _sg=_stock.copy();_availcols=[c for c in _numcols if any(k in str(c).lower() for k in ['on hand','stock','physical','receive','waiting','test'])]
                if not _availcols:_availcols=_numcols
                _sg['_StockTotal']=_sg[_availcols].apply(pd.to_numeric,errors='coerce').fillna(0).sum(axis=1)
                _reqcol=next((c for c in _numcols if any(k in str(c).lower() for k in ['order on hand','require','demand','order qty','need'])),None)
                _sg['_OrderOnHand']=pd.to_numeric(_sg[_reqcol],errors='coerce').fillna(0) if _reqcol else 0.0
                _sg['_Gap']=(_sg['_OrderOnHand']-_sg['_StockTotal']).clip(lower=0)
                _sg=_sg.sort_values(['_Gap','_OrderOnHand'],ascending=[False,False])
                fm=px.bar(_sg,x=_matcol,y='_Gap',hover_data=[c for c in _stock.columns if c!=_matcol]+['_OrderOnHand','_StockTotal'],title='ALL materials — shortage gap descending (Order on hand − available stock/receiving/test)')
                fm.update_layout(xaxis={'categoryorder':'array','categoryarray':_sg[_matcol].astype(str).tolist()});_show_plotly(fm,'Material_All_Gap_Descending')
        stock=res.get('stock',pd.DataFrame())
        if stock.empty:
            st.warning('Stock file not uploaded/verified. Required sheets: Abrasive (Balance column N), ทรายบด-ล้างR (Balance column E), ทรายบด-ล้างSPB (Balance column E).')
        else:
            st.success('Controlled stock source verified: Abrasive=N, ทรายบด-ล้างR=E, ทรายบด-ล้างSPB=E. No other stock sheet is used.')
            viewcols=[c for c in ['Stock Source Sheet','Material','Material Name','Type','Order on Hand g','Physical Stock g','Waiting to Receive g','Under Test g','Balance Stock g','Stock Status','Movement','Remark'] if c in stock.columns]
            st.dataframe(stock[viewcols],use_container_width=True,height=430,hide_index=True)
            c1,c2,c3,c4=st.columns(4)
            c1.metric('Balance stock',f"{stock['Balance Stock t'].sum():,.2f} t")
            c2.metric('Shortage materials',int((stock['Balance Stock g']<0).sum()))
            c3.metric('Zero + open order',int(((stock['Balance Stock g']==0)&(stock['Order on Hand g']>0)).sum()))
            c4.metric('Waiting receipt',f"{stock['Waiting to Receive g'].sum()/1e6:,.2f} t")
            # Interactive controlled-stock graph: separate Order-on-Hand bar vs stacked supply/pipeline bar.
            by=stock.groupby('Stock Source Sheet',as_index=False)[['Physical Stock g','Order on Hand g','Waiting to Receive g','Under Test g','Balance Stock g']].sum()
            fig=go.Figure()
            fig.add_bar(x=by['Stock Source Sheet'],y=by['Order on Hand g']/1e6,name='Order on Hand',offsetgroup='order',hovertemplate='%{x}<br>Order on Hand: %{y:.3f} t<extra></extra>')
            for c,nm in [('Physical Stock g','Stock in Hand'),('Waiting to Receive g','Under Receiving'),('Under Test g','Under Test')]:
                fig.add_bar(x=by['Stock Source Sheet'],y=by[c]/1e6,name=nm,offsetgroup='supply',hovertemplate='%{x}<br>'+nm+': %{y:.3f} t<extra></extra>')
            _supply_total=(by['Physical Stock g']+by['Waiting to Receive g']+by['Under Test g'])/1e6
            fig.add_scatter(x=by['Stock Source Sheet'],y=_supply_total,mode='text',text=[f'{v:.2f} t' for v in _supply_total],textposition='top center',showlegend=False,hoverinfo='skip')
            fig.update_layout(barmode='stack',title='Order on Hand vs Stock + Receiving + Under Test — TOTAL above stack',yaxis_title='ton',hovermode='x unified',uniformtext_minsize=11,uniformtext_mode='show')
            _show_plotly(fig,'SL_PPC_plot_04')
            _show_all=st.toggle('Show all materials / แสดงวัตถุดิบทั้งหมด',value=False,key='stock_show_all_v1934')
            sm=stock.copy();sm['Display']=sm['Material'].astype(str)+' | '+sm['Material Name'].astype(str)
            sm['Shortage g']=(-pd.to_numeric(sm['Balance Stock g'],errors='coerce').fillna(0)).clip(lower=0)
            sm=sm.sort_values(['Shortage g','Order on Hand g'],ascending=[False,False])
            if not _show_all: sm=sm[sm['Shortage g']>0].copy()
            if sm.empty: sm=stock.copy().head(0)
            st.caption('Default = shortage only, maximum shortage → minimum shortage. Turn on Show all for the complete slidable stock list.')
            f2=go.Figure();f2.add_bar(x=sm['Display'],y=sm['Order on Hand g']/1e6,name='Order on Hand',offsetgroup='order')
            for c,nm in [('Physical Stock g','Stock in Hand'),('Waiting to Receive g','Under Receiving'),('Under Test g','Under Test')]:
                f2.add_bar(x=sm['Display'],y=sm[c]/1e6,name=nm,offsetgroup='supply',
                           hovertemplate='%{x}<br>'+nm+': %{y:.3f} t<extra></extra>')
            _tot2=(sm['Physical Stock g']+sm['Waiting to Receive g']+sm['Under Test g'])/1e6
            f2.add_scatter(x=sm['Display'],y=_tot2,mode='text',text=[f'{v:.3f} t' for v in _tot2],
                           textposition='top center',name='Total Supply',hoverinfo='skip')
            f2.update_layout(barmode='stack',title='Material-level stock position — hover for exact values',yaxis_title='ton',xaxis_tickangle=-55,hovermode='x unified')
            _show_plotly(f2,'SL_PPC_plot_05')
            urgent=stock[(stock['Balance Stock g']<0)|((stock['Balance Stock g']==0)&(stock['Order on Hand g']>0))].copy().sort_values('Balance Stock g').head(40)
            st.markdown('### 🔁 Alternative material decision / การตัดสินใจวัตถุดิบทดแทน')
            _short=stock[pd.to_numeric(stock['Balance Stock g'],errors='coerce').fillna(0)<0].copy()
            _alts=[]
            if not _short.empty:
                _all=stock.copy(); _all['_desc']=(_all['Material'].astype(str)+' '+_all['Material Name'].astype(str)+' '+_all.get('Type',pd.Series('',index=_all.index)).astype(str)).str.upper()
                for _,_r in _short.iterrows():
                    _tokens=[t for t in re.findall(r'[A-Z]+\d+',str(_r.get('Material',''))+' '+str(_r.get('Material Name','')).upper()) if len(t)>=2]
                    for _tok in dict.fromkeys(_tokens):
                        _cand=_all[_all['_desc'].str.contains(r'(?<![A-Z0-9])'+re.escape(_tok)+r'(?![A-Z0-9])',regex=True,na=False)&(_all.index!=_r.name)&(pd.to_numeric(_all['Balance Stock g'],errors='coerce').fillna(0)>0)]
                        for _,_a in _cand.iterrows():
                            _alts.append({'Approve':False,'Required Material':_r.get('Material',''),'Required Name':_r.get('Material Name',''),'Shortage kg':abs(float(_r.get('Balance Stock g',0) or 0))/1000,'Match Token':_tok,'Alternative Material':_a.get('Material',''),'Alternative Name':_a.get('Material Name',''),'Available kg':float(_a.get('Balance Stock g',0) or 0)/1000,'Planner Reason':'Same controlled material token; planner approval required'})
            _adf=pd.DataFrame(_alts)
            if _adf.empty: st.info('No automatic same-token alternatives found. This does not prove no substitute exists; Planner may review the complete stock list.')
            else:
                _aed=_persistent_data_editor(_adf,use_container_width=True,hide_index=True,height=min(360,80+34*len(_adf)),disabled=[c for c in _adf.columns if c not in ['Approve','Planner Reason']],key='material_alt_approval_v1934')
                _approved=_aed[_aed['Approve'].fillna(False)].copy(); st.session_state['approved_material_alternatives_v1934']=_approved.to_dict('records')
                st.caption(f'Approved alternatives affecting planner analysis: {len(_approved)}. Recommendation alone never changes shortage; only checked approvals are effective.')
            st.markdown('### 🚨 STOCK SHORTAGE / URGENCY REMINDER')
            if urgent.empty: st.success('No negative/zero balance with open order in the controlled stock sheets.')
            else: st.dataframe(urgent[viewcols],use_container_width=True,hide_index=True,height=330)
    if _nav_idx==8:
        st.subheader('🚚 DELIVERY RISK / ความเสี่ยงการส่งมอบ')
        if risk.empty: st.success('No open delivery risk rows.')
        else:
            _rd=pd.to_datetime(risk.get('Due Date'),errors='coerce')
            _rmin=_rd.dropna().min().date() if _rd.notna().any() else start
            _rmax=_rd.dropna().max().date() if _rd.notna().any() else start+timedelta(days=30)
            _dc1,_dc2=st.columns(2)
            _rf=_dc1.date_input('Risk FROM / ความเสี่ยงจากวันที่',value=max(_rmin,start) if _rmin<=_rmax else start,key='risk_from_v1933')
            _rtod=_dc2.date_input('Risk TO / ความเสี่ยงถึงวันที่',value=min(_rmax,start+timedelta(days=30)) if _rmax>=start else _rmax,key='risk_to_v1933')
            if _rf>_rtod:_rf,_rtod=_rtod,_rf
            _risk_view=risk[(_rd.dt.date>=_rf)&(_rd.dt.date<=_rtod)].copy()
            st.caption(f'Risk analysis period / ช่วงวิเคราะห์ความเสี่ยง: {_rf:%d-%m-%Y} → {_rtod:%d-%m-%Y}. Only this period is included below.')
            _rv=_risk_view.copy();_rv['Product Category']=_rv.get('Category','').astype(str).str.strip().str.upper()
            _rv=_rv[_rv['Product Category'].isin(['P','R','S','T','M','PB'])]
            rc=_rv.groupby(['Delivery Risk','Product Category'],as_index=False)['Work Order'].nunique().rename(columns={'Work Order':'WOs'})
            fig=px.bar(rc,x='Delivery Risk',y='WOs',color='Product Category',barmode='stack',
                       category_orders={'Product Category':['P','R','S','T','M','PB']},
                       title='Delivery risk — product category wise',hover_data=['WOs'])
            _rt=rc.groupby('Delivery Risk',as_index=False)['WOs'].sum()
            fig.add_scatter(x=_rt['Delivery Risk'],y=_rt['WOs'],mode='text',text=[f'{v:,.0f}' for v in _rt['WOs']],textposition='top center',showlegend=False,hoverinfo='skip')
            _show_plotly(fig,'SL_PPC_plot_06')
            _rq=_process_risk_matrix(res.get('master',pd.DataFrame()),_risk_view)
            if not _rq.empty:
                fig=px.bar(_rq,x='Process',y='Risk Qty pcs',color='Product Category',barmode='stack',
                           category_orders={'Product Category':['P','R','S','T','M','PB']},
                           title='Delivery risk quantity — product category × process',hover_data={'Risk Qty pcs':':,.0f'})
                _rqt=_rq.groupby('Process',as_index=False)['Risk Qty pcs'].sum()
                fig.add_scatter(x=_rqt['Process'],y=_rqt['Risk Qty pcs'],mode='text',text=[f'{v:,.0f}' for v in _rqt['Risk Qty pcs']],textposition='top center',showlegend=False,hoverinfo='skip')
                _show_plotly(fig,'Delivery_risk_category_process')
            st.caption('Suggested Safe Due Date = scheduled Packing completion + selected working-day protection buffer. If schedule coverage is incomplete or a blocking resource/route issue remains, the planner intentionally does NOT invent a date.')
            show=[c for c in ['Work Order','Customer','Category','Due Date','Suggested Safe Due Date','Extension vs Current Due (calendar days)','Sales New Due Date Requested','Requested New Due Date','Sales Due-Date Action','Safe-Date Confidence','Full Order Qty','Packed Actual Qty','Open Qty','Planned Packing Qty','Schedule Coverage %','Current Status / WIP','Bottleneck Process','Projected Finish','Packing Completion','Delivery Risk','Safe Due-Date Basis','Detailed Reason'] if c in risk.columns]
            st.dataframe(_risk_view[show],use_container_width=True,height=560,hide_index=True)
        st.markdown('### 📅 WORK ORDER GANTT — PLAN / ACTUAL PROGRESS / SUGGESTED NEW DUE DATE')
        _woopts=sorted(res.get('master',pd.DataFrame()).get('Work Order',pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
        _sel=st.multiselect('Select one or many Work Orders',_woopts,default=_woopts[:1] if _woopts else [],key='wo_gantt_select')
        if _sel:
            _gp=allp[allp['Work Order'].astype(str).isin(_sel)].copy()
            _gm=res.get('master',pd.DataFrame()).copy();_gm=_gm[_gm['Work Order'].astype(str).isin(_sel)] if not _gm.empty else _gm
            _rows=[]
            # Grinding and Cutting are distinct routes. Never display them together as one status.
            _secmap={
                'Preparation':('Preparation Plan','Preparation Actual','Preparation Status'),
                'Mixing':('Mixing Plan','Mixing Actual','Mixing Status'),
                'Forming':('Forming Plan','Forming Actual','Forming Status'),
                'Firing':('Firing Plan','Firing Actual','Firing Status'),
                'Grinding / เจียร':('Grinding / Cutting Plan','Grinding / Cutting Actual','Grinding / Cutting Status'),
                'Cutting / ตัด':('Grinding / Cutting Plan','Grinding / Cutting Actual','Grinding / Cutting Status'),
                'Packing':('Packing Plan','Packing Actual','Packing Status')
            }
            for _wo in _sel:
                _mrow=_gm[_gm['Work Order'].astype(str).eq(_wo)].iloc[0] if not _gm.empty and _gm['Work Order'].astype(str).eq(_wo).any() else pd.Series(dtype=object)
                _wp=_gp[_gp['Work Order'].astype(str).eq(_wo)].copy()
                for _sec,_sg in _wp.groupby('Section',sort=False):
                    _ds=pd.to_datetime(_sg['Plan Date'],errors='coerce').dropna()
                    if _ds.empty:continue
                    _pc,_ac,_sc=_secmap.get(_sec,(None,None,None))
                    _plan=float(pd.to_numeric(pd.Series([_mrow.get(_pc,0) if _pc else 0]),errors='coerce').fillna(0).iloc[0])
                    _act=float(pd.to_numeric(pd.Series([_mrow.get(_ac,0) if _ac else 0]),errors='coerce').fillna(0).iloc[0])
                    _progress=min((_act/_plan*100) if _plan>0 else 0,100)
                    _status=str(_mrow.get(_sc,'') if _sc else '').strip()
                    if not _status:
                        _status='Completed / เสร็จ' if _progress>=100 else ('In progress / กำลังดำเนินการ' if _progress>0 else 'Not started / ยังไม่เริ่ม')
                    _pqty=float(pd.to_numeric(_sg['Plan Qty'],errors='coerce').fillna(0).sum())
                    _aqty=min(_act,_pqty) if _pqty>0 else _act
                    _rows.append({
                        'Work Order':_wo,'Process':_sec,'Start':_ds.min(),
                        'Finish':_ds.max()+pd.Timedelta(days=1),
                        'Plan Status':f"Plan {_ds.min().date()} → {_ds.max().date()}",
                        'Current Status':_status,'Actual Progress %':_progress,
                        'Planned Qty pcs':_pqty,'Finished Qty pcs':_aqty,
                        'Due Date':pd.to_datetime(_mrow.get('Due Date'),errors='coerce')
                    })
                # Explicit curing/oven gate, with project-specific drying/check durations when sourced.
                _cat=eng.normcat(_mrow.get('Category',''));_off=lt.applied_offsets(_mrow);_cw=int(_off.get('Curing/Oven Gate WD',0) or 0)
                _dry=int(_off.get('Drying Gate Calendar Days',_cw) or 0);_pre=int(_off.get('Pre-firing Check Calendar Days',0) or 0)
                _form=_wp[_wp['Section'].astype(str).eq('Forming')]
                if _dry>0 and not _form.empty:
                    _fd=pd.to_datetime(_form['Plan Date'],errors='coerce').max()
                    if pd.notna(_fd):
                        _has_override=bool(_off.get('Process Time Override Source'))
                        _dry_label='Drying / อบแห้ง' if _has_override else 'Curing/Oven TIME GATE'
                        _rows.append({'Work Order':_wo,'Process':_dry_label,
                                      'Start':_fd+pd.Timedelta(days=1),'Finish':_fd+pd.Timedelta(days=1+_dry),
                                      'Plan Status':f"{_dry} calendar day(s); {_off.get('Process Time Override Source') or 'capacity workbook category lead time'}",'Current Status':'Time gate / ระยะเวลารอ',
                                      'Actual Progress %':0,'Planned Qty pcs':0,'Finished Qty pcs':0,'Due Date':pd.to_datetime(_mrow.get('Due Date'),errors='coerce')})
                        if _has_override and _pre>0:
                            _rows.append({'Work Order':_wo,'Process':'Pre-firing check / ตรวจสอบก่อนเผา',
                                          'Start':_fd+pd.Timedelta(days=1+_dry),'Finish':_fd+pd.Timedelta(days=1+_dry+_pre),
                                          'Plan Status':f"{_pre} calendar day(s); {_off.get('Process Time Override Source')}",'Current Status':'Readiness check / ตรวจความพร้อมก่อนเข้าเตา',
                                          'Actual Progress %':0,'Planned Qty pcs':0,'Finished Qty pcs':0,'Due Date':pd.to_datetime(_mrow.get('Due Date'),errors='coerce')})
            _gd=pd.DataFrame(_rows)
            if not _gd.empty:
                _gd=_gd.sort_values(['Work Order','Start','Finish']).copy()
                _gd['Stage State']='FUTURE'
                for _wo,_ix in _gd.groupby('Work Order').groups.items():
                    _sub=_gd.loc[list(_ix)].sort_values('Start')
                    _done=_sub['Actual Progress %'].fillna(0)>=99.999
                    _gd.loc[_sub.index[_done],'Stage State']='DONE'
                    _open=_sub.index[~_done]
                    if len(_open)>0:_gd.loc[_open[0],'Stage State']='CURRENT'
                _gd['WO / Process']=_gd['Work Order']+' | '+_gd['Process']
                # Do not draw raw datetime/duration numbers on bars. Show named information in hover/table.
                fig=px.timeline(
                    _gd,x_start='Start',x_end='Finish',y='WO / Process',color='Process',
                    hover_name='Work Order',
                    hover_data={'Work Order':False,'Process':True,'Start':True,'Finish':True,
                                'Plan Status':True,'Stage State':True,'Current Status':True,'Actual Progress %':':.0f',
                                'Planned Qty pcs':':,.0f','Finished Qty pcs':':,.0f','Due Date':True},
                    title='Selected WO Gantt — PLAN / CURRENT ACTUAL STATUS / EXPECTED DELIVERY'
                )
                # IMPORTANT: Process = planned process represented by the bar.
                # Current Status = latest status from the production/master data.
                # Do not display raw internal bar duration values.
                fig.update_traces(text=[],texttemplate='',textposition='none')
                fig.update_yaxes(autorange='reversed')
                # Current process is highlighted with a large marker; due/expected dates are vertical milestones.
                _cur=_gd[_gd['Stage State'].eq('CURRENT')]
                if not _cur.empty:
                    fig.add_scatter(x=_cur['Start'],y=_cur['WO / Process'],mode='markers',marker={'size':15,'symbol':'diamond'},
                                    name='CURRENT PROCESS / กระบวนการปัจจุบัน',
                                    customdata=np.stack([_cur['Current Status'].astype(str),_cur['Finished Qty pcs'].fillna(0)],axis=-1),
                                    hovertemplate='CURRENT PROCESS<br>Status: %{customdata[0]}<br>Finished: %{customdata[1]:,.0f} pcs<extra></extra>')
                _due_dates=pd.to_datetime(_gd['Due Date'],errors='coerce').dropna().unique()
                for _dd in _due_dates[:5]:fig.add_vline(x=pd.Timestamp(_dd).timestamp()*1000,line_dash='dash',annotation_text='DUE DATE')
                _rr=risk[risk['Work Order'].astype(str).isin(_sel)] if not risk.empty else pd.DataFrame()
                if not _rr.empty and 'Suggested Safe Due Date' in _rr.columns:
                    for _ed in pd.to_datetime(_rr['Suggested Safe Due Date'],errors='coerce').dropna().unique()[:5]:
                        fig.add_vline(x=pd.Timestamp(_ed).timestamp()*1000,line_dash='dot',annotation_text='EST. DELIVERY')
                _show_plotly(fig,'WO_Gantt_plan_actual_revised_due')
            st.caption('Hover meaning: PROCESS = the planned process represented by the colored bar; CURRENT STATUS = the latest actual/status field from the production master. They are different. Gantt Start = first planned date of that process; for Preparation it is the first production-process start, not WO creation date.')
            if not _gd.empty:
                _status_cols=['Work Order','Process','Stage State','Start','Finish','Due Date','Plan Status','Current Status','Planned Qty pcs','Finished Qty pcs','Actual Progress %']
                st.dataframe(_gd[_status_cols].sort_values(['Work Order','Start','Process']),use_container_width=True,hide_index=True,height=340)
            _due=risk[risk['Work Order'].astype(str).isin(_sel)][[c for c in ['Work Order','Customer','Due Date','Suggested Safe Due Date','Projected Finish','Packing Completion','Sales New Due Date Requested','Requested New Due Date','Safe-Date Confidence','Delivery Risk','Bottleneck Process'] if c in risk.columns]]
            if not _due.empty:
                _due=_due.rename(columns={'Suggested Safe Due Date':'Suggested New Expected Delivery Date'})
                st.markdown('#### Expected delivery / กำหนดส่งคาดการณ์ใหม่')
                st.dataframe(_due,use_container_width=True,hide_index=True)
            if not _gd.empty:
                _gxl=_gantt_excel_bytes(_gd,_due)
                st.download_button('⬇️ DOWNLOAD SELECTED WO GANTT — EXCEL',_gxl,file_name=f'SL_PPC_WO_GANTT_{pd.Timestamp(start).strftime("%Y%m%d")}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='download_selected_wo_gantt_excel')
    # Product-code / production-number classification from controlled factory rules.
    _masterx=res.get('master',pd.DataFrame()).copy()
    if not _masterx.empty:
        _masterx['Product Code']=_masterx.get('Product Code','').astype(str).str.strip()
        _masterx['Production Number']=_masterx.get('Work Order','').astype(str).str.strip().str.upper()
        _masterx['Order Class']=np.select([_masterx['Production Number'].str.startswith('PBM'),_masterx['Production Number'].str.startswith('PM'),_masterx['Production Number'].str.startswith('PBS'),_masterx['Production Number'].str.startswith('PS'),_masterx['Production Number'].str.startswith('PB')],['MAKE TO STOCK / CONTINUOUS RESIN','MAKE TO STOCK / CONTINUOUS VITRIFIED','MONTHLY MADE TO ORDER / RESIN','MONTHLY MADE TO ORDER / VITRIFIED','MADE TO ORDER / RESIN'],default='MADE TO ORDER / VITRIFIED')
        # Test Work is inherited from the CURRENT FIRING PLANNER OUTPUT by Work Order.
        # Fallback only when an old firing file lacks Work Type: Product Code first character 1 = TEST.
        _pcu=_masterx['Product Code'].astype(str).str.strip().str.upper()
        _fs=res.get('firing_source',pd.DataFrame()).copy()
        _fmap={}
        if isinstance(_fs,pd.DataFrame) and not _fs.empty and 'Work Order' in _fs.columns:
            _wcol=next((c for c in ['Work Type / ประเภทงาน','Work Type','Test Work'] if c in _fs.columns),None)
            _ocol=next((c for c in ['Test Work Override','Test Override'] if c in _fs.columns),None)
            if _wcol:
                for _,_r in _fs.iterrows():
                    _w=str(_r.get('Work Order','')).strip();_v=str(_r.get(_wcol,'')).upper()
                    if _w:_fmap[_w]=('YES' if 'TEST' in _v or 'งานทดสอบ' in _v else 'NO')
        _daily_override=st.session_state.get('test_override_daily',{}) or {}
        _masterx['Test Work']=[_daily_override.get(str(w).strip(),_fmap.get(str(w).strip(),('YES' if pc[:1]=='1' else 'NO'))) for w,pc in zip(_masterx['Work Order'],_pcu)]
        _is_test=_masterx['Test Work'].eq('YES')
        _masterx['Work Type']=np.where(_is_test,'TEST / งานทดสอบ','NORMAL / งานปกติ')
        _masterx['Test Type']=np.where(_is_test,'TEST / CONTROLLED BY FIRING PLANNER','NORMAL / SALE PRODUCT')
        _masterx['Test Rule Source']=[('FIRING PLANNER WO SELECTION' if str(w).strip() in _fmap else 'FALLBACK: PRODUCT CODE STARTS 1') for w in _masterx['Work Order']]
    if _nav_idx==23:
        st.markdown('## ⚙️ Mixing Mill Plan vs Actual / แผนโม่เทียบผลจริง')
        st.caption('Reads every active Mixing daily-status workbook. The sheet-tab name is the production date. Mill-batch plan comes from Plan(โม่); actual active mills are distinct M/C values with actual output. Capacity uses the controlled CAP ผสม sheet and is counted once per assigned mill per day.')
        _mix_capacity=APP_DIR/'CAPACITY_DATABASE.xlsx'
        _mix_paths=[getattr(x,'_p',None) for x in _ds_inputs if getattr(x,'_p',None) and 'MIXING' in Path(getattr(x,'name','')).name.upper()]
        if not _mix_paths:
            _mix_paths=[p for p in _ds_active if 'MIXING' in p.name.upper()]
        if not _mix_paths:
            st.warning(f'No active Mixing daily workbook is loaded. Upload the Mixing file under the six section-specific Daily Status uploaders. Target: {_ds_shared_root}')
        elif not _mix_capacity.exists():
            st.error(f'Controlled mill capacity source is missing: {_mix_capacity}')
        else:
            try:
                _mix_daily,_mix_detail,_mix_diag=mixcap.build_mixing_daily(_mix_paths,_mix_capacity)
                if _mix_daily.empty:
                    st.warning('No valid date-tab Mixing rows were found. Confirm date tab names and the supplied Mixing template columns.')
                else:
                    _last=_mix_daily.sort_values('Date').iloc[-1]
                    _m1,_m2,_m3,_m4=st.columns(4)
                    _m1.metric('Planned mill batches',f"{_last['Planned mill batches']:,.0f}" if pd.notna(_last['Planned mill batches']) else '—')
                    _m2.metric('Assigned batch capacity',f"{_last['Available batch capacity on assigned mills']:,.0f}" if pd.notna(_last['Available batch capacity on assigned mills']) else '—')
                    _m3.metric('Actual mills active',f"{_last['Actual mills active']:,.0f}")
                    _m4.metric('Actual kg capacity use',f"{_last['Actual kg capacity utilization %']:.1f}%" if pd.notna(_last['Actual kg capacity utilization %']) else '—')
                    _show_plotly(px.bar(_mix_daily,x='Date',y=['Planned mills assigned','Actual mills active','Available mills/day'],barmode='group',title='MIXING CAPACITY — MILL COUNT / MILLS PER DAY',labels={'value':'Number of mills','variable':'Measure'}),'Mixing_Mills_Plan_Actual_Capacity')
                    _show_plotly(px.bar(_mix_daily,x='Date',y=['Planned mill batches','Available batch capacity on assigned mills'],barmode='group',title='Mixing mill-batch plan vs assigned-mill batch capacity'),'Mixing_Mill_Batches_Plan_Capacity')
                    _kg=_mix_daily.melt(id_vars='Date',value_vars=['Plan kg (calculated from source kg/pc)','Actual kg (source)','Available kg capacity on assigned mills'],var_name='Measure',value_name='kg')
                    _show_plotly(px.bar(_kg,x='Date',y='kg',color='Measure',barmode='group',title='Mixing plan/actual kg vs capacity'),'Mixing_Kg_Plan_Actual_Capacity')
                    st.markdown('### Daily mill plan, active machines and capacity')
                    _plan_over=_mix_daily[pd.to_numeric(_mix_daily['Batch capacity utilization %'],errors='coerce')>100.0]
                    _actual_over=_mix_daily[pd.to_numeric(_mix_daily['Actual kg capacity utilization %'],errors='coerce')>100.0]
                    if not _plan_over.empty:st.error(f"Plan exceeds assigned mill-batch capacity on {_plan_over['Date'].nunique()} production day(s).")
                    if not _actual_over.empty:st.warning(f"Actual kg exceeds assigned mills' nominal daily capacity on {_actual_over['Date'].nunique()} production day(s). Review product/machine eligibility, shifts and approved overtime.")
                    st.dataframe(_mix_daily,use_container_width=True,hide_index=True,height=420)
                    with st.expander('Work-order detail and source rows',expanded=False):
                        st.dataframe(_mix_detail,use_container_width=True,hide_index=True,height=500)
                    st.download_button('⬇️ Download Mixing mill plan vs actual with row traceability',_mix_detail.to_csv(index=False).encode('utf-8-sig'),'Mixing_Mill_Plan_Actual_Trace.csv','text/csv',key='mix_mill_trace_download')
                    st.caption(f"Mixing source(s): {'; '.join(str(Path(p).resolve()) for p in _mix_paths)} · Capacity source: {_mix_capacity.resolve()} · Capacity values: CAP ผสม, source rows 3 onward. Plan kg is derived only from the source workbook's total kg/order qty × planned pcs; actual kg is read from the daily source. Actual mill batch count is not present in the supplied daily template, so the report shows actual active machine count instead.")
                    if _mix_diag:st.warning('Source checks: '+str(_mix_diag))
                    if int(_mix_daily['Unmapped machine rows'].sum()):st.warning(f"{int(_mix_daily['Unmapped machine rows'].sum())} assigned machine row(s) did not map to CAP ผสม; these are excluded from capacity totals.")
            except Exception as _mix_error:st.error(f'Mixing plan/actual capacity report failed safely: {_mix_error}')

    if _nav_idx==19:
        st.subheader('🧯 Backorder & risk recovery plan / แผนกู้คืนงานค้างและความเสี่ยง')
        st.caption('Separate recovery analysis · reconciled to the saved daily schedule once, with per-date and per-section capacity checks.')
        try:
            from suite.recovery_actions import build_recovery_daily_allocation as _recovery_reconcile
            from suite.recovery_actions import build_recovery_actions
            _recovery_asof=datetime.datetime.now(ZoneInfo('Asia/Bangkok')).date()
            _recovery_action_base=build_recovery_actions(res.get('master',pd.DataFrame()),risk,_recovery_asof)
            _recovery_store=Path(os.environ.get('SL_SHARED_ROOT',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA')))/'RECOVERY'/'ACTIONS'
            _recovery_store.mkdir(parents=True,exist_ok=True)
            _latest_action_file=max(_recovery_store.glob('Recovery_Action_*.csv'),key=lambda p:p.stat().st_mtime,default=None)
            _editable_action_cols=[c for c in ['Sales Priority — confirm','Sales Confirmed Customer Due Date','Production Capacity / Bottleneck — confirm','Production Earliest Feasible Finish — confirm','Jointly Agreed Recovery Date','Action Owner','Agreement Status','Next Review Date','Comments / Evidence','Recovery Action'] if c in _recovery_action_base.columns]
            if _latest_action_file and not _recovery_action_base.empty:
                try:
                    _saved_actions=pd.read_csv(_latest_action_file,keep_default_na=False)
                    if 'Work Order' in _saved_actions:
                        _action_map=_saved_actions.drop_duplicates('Work Order',keep='last').set_index('Work Order')
                        for _field in _editable_action_cols:
                            if _field in _action_map:
                                _recovery_action_base[_field]=_recovery_action_base.apply(lambda _r:_action_map.at[_r['Work Order'],_field] if _r['Work Order'] in _action_map.index and str(_action_map.at[_r['Work Order'],_field]).strip() else _r[_field],axis=1)
                except Exception as _load_action_error:st.warning(f'Previous recovery action edits were kept; could not load the latest edit snapshot: {_load_action_error}')
            if _latest_action_file and not _recovery_action_base.empty:
                st.session_state['recovery_action_edits']=_recovery_action_base.copy()
            if not _recovery_action_base.empty:
                with st.expander('✏️ Edit Sales / Production recovery commitments',expanded=False):
                    st.caption('Edit priorities, owners, agreed dates, review dates and actions. This saves an append-only CSV revision in CENTRAL_DATA/RECOVERY/ACTIONS; it does not rewrite Plan-2026 or approve a customer-date change.')
                    _action_edit=_persistent_data_editor(_recovery_action_base,num_rows='dynamic',use_container_width=True,height=330,key='recovery_action_editor_rc2911',disabled=[c for c in ['Work Order','Customer','Product Code','Category','Due Date','Open quantity (pcs)','Recovery Priority'] if c in _recovery_action_base.columns])
                    if st.button('💾 Save recovery actions to central data',key='save_recovery_actions_rc2911',type='primary'):
                        _action_stamp=datetime.datetime.now(ZoneInfo('Asia/Bangkok')).strftime('%Y%m%d_%H%M%S')
                        _action_user=re.sub(r'[^A-Za-z0-9_-]+','_',str(st.session_state.get('sl_user','unknown')))
                        _action_path=_recovery_store/f'Recovery_Action_{_action_stamp}_{_action_user}.csv'
                        _action_out=_action_edit.copy();_action_out['Edited By']=st.session_state.get('sl_user','unknown');_action_out['Edited At Thailand']=datetime.datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds')
                        _action_tmp=_action_path.with_suffix('.csv.tmp');_action_out.to_csv(_action_tmp,index=False,encoding='utf-8-sig');os.replace(_action_tmp,_action_path)
                        st.session_state['recovery_action_edits']=_action_out
                        st.success(f'Saved recovery action revision: {_action_path.name}')
            _recovery_summary,_recovery_detail=_recovery_reconcile(
                res.get('master',pd.DataFrame()),risk,allp,
                caps,_recovery_asof)
            if _recovery_summary.empty:
                st.info('No open urgent/high-risk recovery work order was found in the current Plan-2026/risk source. Check the source date and daily plan window.')
            else:
                st.info('How recovery enters the daily plan: this page does not append a second backorder quantity. It matches overdue / urgent WOs against the existing unified daily schedule. “Recovery allocation” is the portion already scheduled; whole-day plan and capacity include all WOs for that section/date. A WO marked NOT SCHEDULED has not been inserted and needs an explicit feasible plan revision.')
                _plan_source_display=st.session_state.get('plan_path','Not recorded')
                _capacity_source_display=st.session_state.get('cap_path','Not recorded')
                st.caption(f"Plan source: {_plan_source_display} · Controlled capacity source: {_capacity_source_display} · As-of date: {_recovery_asof:%d %b %Y} (Phan Thong, Chonburi).")
                _r1,_r2,_r3=st.columns(3)
                _r1.metric('Recovery WOs',f"{_recovery_summary['Work Order'].nunique():,}")
                _r2.metric('On-time in current plan',f"{_recovery_summary['Due Date Result'].astype(str).str.startswith('ON TIME').sum():,}")
                _r3.metric('Capacity exceptions',f"{_recovery_summary['Capacity Result'].astype(str).str.contains('NOT FEASIBLE|HARD GATE|UNVERIFIED',regex=True).sum():,}")
                _scheduled_recovery=pd.to_numeric(_recovery_summary.get('Scheduled Qty pcs',pd.Series(dtype=float)),errors='coerce').fillna(0).sum()
                _open_recovery=pd.to_numeric(_recovery_summary.get('Open quantity (pcs)',pd.Series(dtype=float)),errors='coerce').fillna(0).sum()
                st.caption(f"Already scheduled: {_scheduled_recovery:,.0f} / {_open_recovery:,.0f} recovery pcs. Counts are reconciled to the saved schedule; no extra load is added.")
                _recovery_chart=_recovery_summary.copy()
                if 'Category' not in _recovery_chart:_recovery_chart['Category']='UNKNOWN'
                _recovery_chart['Category']=_recovery_chart['Category'].fillna('UNKNOWN').astype(str).replace({'F':'P','':'UNKNOWN','nan':'UNKNOWN'})
                _recovery_chart['Open pcs']=pd.to_numeric(_recovery_chart.get('Open quantity (pcs)',0),errors='coerce').fillna(0)
                _recovery_chart['Scheduled pcs']=pd.to_numeric(_recovery_chart.get('Scheduled Qty pcs',0),errors='coerce').fillna(0).clip(lower=0)
                _recovery_chart['Not scheduled pcs']=(_recovery_chart['Open pcs']-_recovery_chart['Scheduled pcs']).clip(lower=0)
                _recovery_cat=_recovery_chart.groupby('Category',as_index=False)[['Scheduled pcs','Not scheduled pcs']].sum()
                if not _recovery_cat.empty:
                    _recovery_fig=px.bar(_recovery_cat,x='Category',y=['Scheduled pcs','Not scheduled pcs'],barmode='stack',
                        title='Recovery quantity: already in daily plan vs still unallocated',color_discrete_map={'Scheduled pcs':'#0F766E','Not scheduled pcs':'#D97706'})
                    _show_plotly(_recovery_fig,'Recovery_Scheduled_vs_Unallocated')
                st.dataframe(_recovery_summary,use_container_width=True,hide_index=True,height=340)
                with st.expander('Daily section allocation and capacity evidence / รายละเอียดแผนรายวันและหลักฐานกำลังการผลิต',expanded=True):
                    if _recovery_detail.empty:
                        st.warning('No daily allocation rows exist for these urgent work orders. They have NOT been inserted into the plan; review the available capacity below, then create a feasible dated allocation in the Daily Plan before treating recovery as committed.')
                        _open_capacity=caps.copy() if isinstance(caps,pd.DataFrame) else pd.DataFrame()
                        if not _open_capacity.empty and {'Plan Date','Section'}.issubset(_open_capacity.columns):
                            _open_capacity['Plan Date']=pd.to_datetime(_open_capacity['Plan Date'],errors='coerce')
                            _open_capacity=_open_capacity[_open_capacity['Plan Date'].dt.date.ge(_recovery_asof)].copy()
                            if 'Plan ton' in _open_capacity and 'Capacity ton' in _open_capacity:
                                _open_capacity['Remaining capacity ton']=pd.to_numeric(_open_capacity['Capacity ton'],errors='coerce')-pd.to_numeric(_open_capacity['Plan ton'],errors='coerce')
                            if 'Mixing Plan MO' in _open_capacity and 'Mixing Capacity MO' in _open_capacity:
                                _open_capacity['Remaining mixing mills']=pd.to_numeric(_open_capacity['Mixing Capacity MO'],errors='coerce')-pd.to_numeric(_open_capacity['Mixing Plan MO'],errors='coerce')
                            _avail_cols=[c for c in ['Plan Date','Section','Plan pcs','Capacity pcs','Plan ton','Capacity ton','Remaining capacity ton','Utilization %','Mixing Plan MO','Mixing Capacity MO','Remaining mixing mills','Capacity Basis','Reason / Limiting Factor'] if c in _open_capacity.columns]
                            if not _open_capacity.empty and _avail_cols:
                                st.caption('Unassigned normal-capacity outlook from the current Daily Plan window. Values are section/date totals; a free slot is not assigned to a WO until its route and process sequence are checked.')
                                st.dataframe(_open_capacity[_avail_cols].sort_values(['Plan Date','Section']),use_container_width=True,hide_index=True,height=360)
                    else:
                        _cap_graph=_recovery_detail.copy()
                        if {'Plan Date','Section'}.issubset(_cap_graph.columns):
                            _cap_graph=_cap_graph.drop_duplicates(['Plan Date','Section']).copy()
                            _cap_graph['Plan Date']=pd.to_datetime(_cap_graph['Plan Date'],errors='coerce')
                            _rated_ton=_cap_graph[~_cap_graph['Section'].astype(str).str.contains('Mixing|ผสม|QC|Quality|Cleaning',case=False,regex=True)].copy()
                            _ton_cols=['Whole-day plan ton (includes listed recovery WOs)','Recovery allocation ton this day/section','Controlled capacity ton']
                            if not _rated_ton.empty and all(c in _rated_ton.columns for c in _ton_cols):
                                for _col in _ton_cols:_rated_ton[_col]=pd.to_numeric(_rated_ton[_col],errors='coerce')
                                _rated_ton=_rated_ton.dropna(subset=['Whole-day plan ton (includes listed recovery WOs)','Controlled capacity ton'])
                                if not _rated_ton.empty:
                                    _rated_ton['Other scheduled load ton']=(_rated_ton['Whole-day plan ton (includes listed recovery WOs)']-_rated_ton['Recovery allocation ton this day/section']).clip(lower=0)
                                    _sections=sorted(_rated_ton['Section'].astype(str).unique())
                                    _selected_section=st.selectbox('Capacity comparison section / เลือกกระบวนการเทียบกำลังการผลิต',_sections,key='recovery_capacity_section_rc2919')
                                    _one=_rated_ton[_rated_ton['Section'].astype(str).eq(_selected_section)].sort_values('Plan Date')
                                    _cf2=go.Figure()
                                    _cf2.add_bar(x=_one['Plan Date'],y=_one['Other scheduled load ton'],name='Other daily plan (ton)')
                                    _cf2.add_bar(x=_one['Plan Date'],y=_one['Recovery allocation ton this day/section'],name='Listed recovery WOs already in plan (ton)')
                                    _cf2.add_scatter(x=_one['Plan Date'],y=_one['Controlled capacity ton'],name='Controlled capacity (ton)',mode='lines+markers',line={'color':'#dc2626','width':3})
                                    _cf2.update_layout(barmode='stack',title=f'{_selected_section}: daily plan composition vs controlled capacity',yaxis_title='Metric tonnes per day',xaxis_title='Plan date')
                                    _show_plotly(_cf2,'Recovery_plan_vs_capacity_rc2919')
                                    st.caption('The recovery portion is already included in the stacked total. “Implied headroom before listed recovery” is calculated as capacity minus the other scheduled load; it is a reconciliation, not proof that the schedule was originally built without the WO.')
                                    _compare_cols=['Plan Date','Section','Recovery WOs in this day/section','Recovery allocation pcs this day/section','Recovery allocation ton this day/section','Whole-day plan ton (includes listed recovery WOs)','Controlled capacity ton','Implied headroom before listed recovery ton','Headroom after current plan ton','Over-capacity ton','Capacity Check','Capacity Basis / Limiting Factor']
                                    st.dataframe(_one[[c for c in _compare_cols if c in _one.columns]],use_container_width=True,hide_index=True)
                            _mix_rows=_cap_graph[_cap_graph['Section'].astype(str).str.contains('Mixing|ผสม',case=False,regex=True)]
                            _rated_rows=_cap_graph[~_cap_graph['Section'].astype(str).str.contains('Mixing|ผสม',case=False,regex=True)]
                            if not _rated_rows.empty and 'Section Utilization %' in _rated_rows:
                                _rated_rows['Section Utilization %']=pd.to_numeric(_rated_rows['Section Utilization %'],errors='coerce')
                                _rated_rows=_rated_rows.dropna(subset=['Section Utilization %'])
                                if not _rated_rows.empty:
                                    _cf=px.bar(_rated_rows,x='Plan Date',y='Section Utilization %',color='Section',barmode='group',title='Whole-day section load on recovery dates · capacity %')
                                    _cf.add_hline(y=100,line_dash='dash',line_color='#d97706',annotation_text='100% normal capacity')
                                    _cf.add_hline(y=103,line_dash='dot',line_color='#b91c1c',annotation_text='103% hard gate')
                                    _show_plotly(_cf,'Recovery_whole_day_capacity')
                            if not _mix_rows.empty and {'Mixing Plan mills','Mixing Capacity mills'}.issubset(_mix_rows.columns):
                                _mg=_mix_rows[['Plan Date','Mixing Plan mills','Mixing Capacity mills']].copy()
                                _mg['Mixing Plan mills']=pd.to_numeric(_mg['Mixing Plan mills'],errors='coerce')
                                _mg['Mixing Capacity mills']=pd.to_numeric(_mg['Mixing Capacity mills'],errors='coerce')
                                _mg=_mg.dropna(subset=['Mixing Plan mills','Mixing Capacity mills'])
                                if not _mg.empty:
                                    _mf=px.bar(_mg,x='Plan Date',y=['Mixing Plan mills','Mixing Capacity mills'],barmode='group',title='Mixing · mills per day (not tonnes)')
                                    _show_plotly(_mf,'Recovery_mixing_mills_capacity')
                                    st.caption('Mixing plan mills/day and capacity mills/day are whole-section totals from the controlled capacity comparison. They include every scheduled WO; the system does not invent a separate mill count for individual backorder pieces.')
                        st.dataframe(_recovery_detail,use_container_width=True,hide_index=True,height=420)
                        _ot_all=res.get('ot_suggestion',pd.DataFrame())
                        if isinstance(_ot_all,pd.DataFrame) and not _ot_all.empty:
                            _recovery_dates=set(pd.to_datetime(_recovery_detail.get('Plan Date'),errors='coerce').dt.date.dropna()) if 'Plan Date' in _recovery_detail else set()
                            _ot_cols=[c for c in ['Plan Date','Section','Plan Qty pcs','Indicative Normal Capacity pcs','Load %','Suggested OT hours','OT Action'] if c in _ot_all.columns]
                            _ot_show=_ot_all[_ot_all['Plan Date'].map(lambda v:pd.to_datetime(v,errors='coerce').date() in _recovery_dates if pd.notna(pd.to_datetime(v,errors='coerce')) else False)]
                            if not _ot_show.empty:
                                st.markdown('#### Overtime / capacity recovery by date and section')
                                st.caption('Indicative hours from the current total section load and normal hours; this is not approval or recovery-WO-only OT. Confirm shift, resource and OT authorization before release.')
                                st.dataframe(_ot_show[_ot_cols],use_container_width=True,hide_index=True)
                        _rx=io.BytesIO()
                        with pd.ExcelWriter(_rx,engine='xlsxwriter') as _rw:
                            _recovery_summary.to_excel(_rw,index=False,sheet_name='Recovery Feasibility')
                            _recovery_detail.to_excel(_rw,index=False,sheet_name='Daily Capacity Evidence')
                            _recovery_actions_for_export=st.session_state.get('recovery_action_edits',_recovery_action_base)
                            _recovery_actions_for_export.to_excel(_rw,index=False,sheet_name='Sales Production Actions')
                        st.download_button('⬇️ Download recovery + capacity evidence / ดาวน์โหลดหลักฐานแผนกู้คืน',_rx.getvalue(),
                            file_name=f'SL_RECOVERY_CAPACITY_{_recovery_asof:%Y%m%d}.xlsx',
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='daily_recovery_feasibility_export')
                st.caption('The result is “on time in current plan” only when scheduled quantity covers the open quantity and the planned finish is on/before the due date. Any >100% load is infeasible as normal capacity; >103% is a hard gate. QC/Cleaning have no rated capacity and remain timing-only. Production/Sales confirmation is still required; this is not a delivery guarantee.')
        except Exception as _re:
            st.error(f'Recovery-to-daily-plan reconciliation stopped safely: {_re}')
        st.info('📺 WEEKLY MEETING VIEW / รายงานประชุมประจำสัปดาห์: enable TV text in the sidebar. Use the graph toolbar for SVG, or open each graph’s offline HTML to export 4K PNG. All numbers remain linked to the current selected source and Production-confirmed data.')
        jobs50.render(st,APP_DIR)
        st.caption('Mixing Mill Plan vs Actual is available as its own direct page in the Daily Planning module.')
        mdreport.render(st,allp,risk,caps,res.get('master',pd.DataFrame()),start,APP_DIR,daily_status=_ds_cache_valid,stock_df=res.get('stock',pd.DataFrame()),firing_df=st.session_state.firing_override,planning_wip=wip,source_paths={'Plan-2026':st.session_state.get('plan_path'),'Firing Plan':st.session_state.get('fire_path'),'Capacity Database':st.session_state.get('cap_path'),'Stock on hand':st.session_state.get('stock_path')})
        with st.expander('📊 DOWNLOAD WEEKLY / MONTHLY / MID-YEAR / YEARLY MEETING POWERPOINT',expanded=False):
            meeting52.render(st,res.get('master',pd.DataFrame()),risk,st.session_state.get('prod_wip_review'),st.session_state.get('job_register_review'),start)
        with st.expander('📚 Process-sheet actual evidence / หลักฐานการผลิตจากชีต',expanded=False):ss48.render(st)
        with st.expander('🔎 CLICKABLE TRACEABLE DATA STUDIO / ข้อมูลที่แก้ไขได้',expanded=False):
            _ds=st.selectbox('Choose analysis / เลือกข้อมูล',['Delivery risks','Process schedule','WO master'],key='trace48_choice')
            _td={'Delivery risks':risk,'Process schedule':allp,'WO master':res.get('master',pd.DataFrame())}[_ds]
            tv48.interactive(st,_td,_ds,source='Current uploaded source + planner calculation; reviewed edits remain display-only')
        st.divider()
        st.subheader('📊 WEEKLY REPORTING / รายงานประจำสัปดาห์')
        st.caption('Factory Manager meeting view: Incoming vs delivery • OPEN/CLOSED • WIP/output matching • bottleneck • recovery plan. / มุมมองสำหรับประชุมประจำสัปดาห์')
        st.info('PLANNING PRINCIPLE / หลักการวางแผน: Protect the committed due date first and minimize due-date revisions. Due date never overrides physical feasibility. Firing Plan is the first currently controlled release layer; other process plans remain Planning responsibility but must be treated as provisional until their data/capacity logic reaches release-level reliability. / ปกป้องกำหนดส่งก่อน ลดการเลื่อนกำหนดส่ง และไม่วางแผนเกินความเป็นจริงทางกายภาพ')
        st.caption('Decision hierarchy / ลำดับการตัดสินใจ: 1) Due-date protection  2) Capacity feasibility  3) Resource utilization  4) Smooth workload. MTS also protects safety stock; TEST work receives explicit trust/new-customer visibility.')
        _rm=res.get('master',pd.DataFrame()).copy()
        if _rm.empty or 'Work Order' not in _rm.columns:
            st.warning('Plan2026 master is required for Reporting / ต้องใช้ข้อมูลหลัก Plan2026')
        else:
            _rm['WO Date']=_rm['Work Order'].map(_wo_encoded_date)
            _rm['Due Date']=pd.to_datetime(_rm.get('Due Date'),errors='coerce')
            _rm['Product Category']=_rm.get('Category','').astype(str).str.upper().str.strip().replace('F','P')
            _rm=_rm[_rm['Product Category'].isin(['P','R','S','T','M','PB'])].copy()
            _rm=_reporting_order_type(_rm)
            _closed=_rm.get('Overall Closed',pd.Series(False,index=_rm.index)).fillna(False).astype(bool)
            _rm['Closure Status']=np.where(_closed,'CLOSED / ปิดใบสั่ง','OPEN / ยังไม่ปิด')
            # Planning-control classification: due-date protection first; do not turn missing data into confirmed delay.
            _now=pd.Timestamp(start).normalize()
            _rm['_open_qty']=pd.to_numeric(_rm.get('Remaining Packing',_rm.get('Order Qty',0)),errors='coerce').fillna(0).clip(lower=0)
            _rm['_days_to_due']=(_rm['Due Date']-_now).dt.days
            _rm['Planning Priority']=np.select([
                (~_closed)&_rm['Due Date'].notna()&(_rm['Due Date']<_now),
                (~_closed)&_rm['Due Date'].notna()&(_rm['_days_to_due'].between(0,3)),
                (~_closed)&_rm['Due Date'].isna(),
            ],['1 BACK ORDER / งานค้างส่ง','2 DUE <=3 DAYS / กำหนดส่ง ≤3 วัน','6 DATA/STATUS CHECK / ตรวจข้อมูล'],default='5 FUTURE / อนาคต')
            _today=pd.Timestamp(start).normalize(); _mon=_today-pd.Timedelta(days=_today.weekday()); _sun=_mon+pd.Timedelta(days=6)
            _rc1,_rc2=st.columns(2)
            _rf=pd.Timestamp(_rc1.date_input('Week FROM / จากวันที่',value=_mon.date(),key='report_week_from'))
            _rt=pd.Timestamp(_rc2.date_input('Week TO / ถึงวันที่',value=_sun.date(),key='report_week_to'))
            st.markdown('### 0. Due-date protection & planning control / การปกป้องกำหนดส่งและการควบคุมแผน')
            _pr=_rm[~_closed].groupby(['Planning Priority','Product Category'],as_index=False).agg(WOs=('Work Order','nunique'),**{'Open Qty pcs':('_open_qty','sum')})
            if not _pr.empty:
                _show_plotly(px.bar(_pr,x='Planning Priority',y='WOs',color='Product Category',barmode='stack',title='Open WOs by delivery urgency (current status; not production closure)'),'Weekly_Due_Date_Protection')
                st.dataframe(_pr,use_container_width=True,hide_index=True)
            st.caption('Firing is the first controlled detailed release. Preparation/Mixing/Forming/Grinding/Cutting/Packing plans shown by the system must still be capacity-feasible, but remain provisional recommendations until validated for release. / Firing เป็นแผนรายละเอียดที่ควบคุมก่อน ส่วนกระบวนการอื่นต้องแม่นยำและผ่านการตรวจสอบก่อนปล่อยใช้งาน')
            st.markdown('### 1. Actual job opening & closure / เปิดและปิดใบสั่งผลิตจริง')
            st.caption('Use the editable monthly register above. WO encoded dates are not a substitute for actual issued/closed register dates.')
            st.markdown('#### By process: bottleneck and recovery / ตามกระบวนการ: คอขวดและแผนกู้คืน')
            _rr=risk.copy() if isinstance(risk,pd.DataFrame) else pd.DataFrame()
            if not _rr.empty and 'Work Order' in _rr.columns:
                _rr['Bottleneck Process']=_rr.get('Bottleneck Process','UNKNOWN').fillna('UNKNOWN').astype(str)
                _rr['Risk Qty']=pd.to_numeric(_rr.get('Open Qty',0),errors='coerce').fillna(0)
                _rp=_rr.groupby('Bottleneck Process',as_index=False).agg(**{'Risk WOs':('Work Order','nunique'),'Risk Qty pcs':('Risk Qty','sum')}).sort_values('Risk Qty pcs',ascending=False)
                _rp['Recovery Plan / แผนกู้คืน']=_rp['Bottleneck Process'].map(lambda z:f'Protect due-date WOs; rebalance {z} capacity; approve OT/recovery only when controlled capacity is exceeded.')
                _show_plotly(px.bar(_rp,x='Bottleneck Process',y='Risk Qty pcs',hover_data=['Risk WOs'],title='Bottleneck process — risk quantity / กระบวนการคอขวด — จำนวนเสี่ยง'),'Weekly_Bottleneck')
                st.dataframe(_rp,use_container_width=True,hide_index=True,height=280)
            st.markdown('### 2. Status and WIP reports / รายงานสถานะและ WIP')
            st.info('Whole-order OPEN/CLOSED counts are maintained in Reports → Daily Open / Closed WO Report. Section events are listed there but do not close the whole order.')
            _hub_reports_url=st.query_params.get('hub_reports_url','')
            _hub_wip_url=st.query_params.get('hub_wip_url','')
            if _hub_reports_url:
                st.markdown(f"<a href='{_hub_reports_url}' target='_top' style='font-size:.82rem;color:#0057b8;text-decoration:underline'>↗ {'เปิดรายงานงานเปิด/ปิด' if _LANG=='ไทย' else 'Open Daily Open / Closed report'}</a>",unsafe_allow_html=True)
            if _hub_wip_url:
                st.markdown(f"<a href='{_hub_wip_url}' target='_top' style='font-size:.82rem;color:#b45309;text-decoration:underline'>↗ {'เปิด WIP กลาง' if _LANG=='ไทย' else 'Open central WIP'}</a>",unsafe_allow_html=True)
    if _nav_idx==9:
        st.subheader('🗓️ Long-Term Plans / แผนระยะยาว — MPS + Backorder / MPS + งานค้างส่ง')
        st.markdown('### 🚨 Backorder Analysis / การวิเคราะห์งานค้างส่ง')
        if _hub_sources_url:st.markdown(f"<a href='{html.escape(str(_hub_sources_url),quote=True)}' target='_top' style='font-size:.76rem;color:#0057b8;text-decoration:underline'>↻ {'อัปเดต Plan-2026 / Stock / Forecast' if _LANG=='ไทย' else 'Update Plan-2026 / Stock / Forecast'}</a>",unsafe_allow_html=True)
        st.caption(f"Past-due open orders only, using the same Home definition as of {bkk_today():%d %b %Y}; MPS future demand is shown separately. / แสดงเฉพาะงานเปิดที่เกินกำหนด โดยใช้นิยามเดียวกับหน้าหลัก")
        _recent_bo=recent_open_closed_month_category(res.get('master',pd.DataFrame()),bkk_today(),months=3)
        if not _recent_bo.empty:
            st.markdown('#### Last 3 due months · current open and closed / 3 เดือนกำหนดส่งล่าสุด')
            st.caption('IMPORTANT: these figures cover ONLY the last 3 due months, not all open WOs or all backorders. Each month has adjacent OPEN and CLOSED bars stacked by product category. Current status by due month is NOT historical month-end opening/closure activity. Closed uses ordered pcs; open uses remaining pcs.')
            _recent_bo['_month']=pd.to_datetime(_recent_bo['Due Month'].astype(str)+'-01',errors='coerce')
            _recent_bo['Month']=_recent_bo['_month'].dt.strftime('%b %Y')
            _recent_bo['Month / Status']=_recent_bo['Month']+' · '+_recent_bo['Status']
            _last_months=sorted(_recent_bo['Month'].unique(),key=lambda _m:pd.to_datetime(_m,format='%b %Y',errors='coerce'))
            _last_orders={'Month':_last_months,'Product Category':['P','R','S','T','M','PB','UNKNOWN'],'Status':['OPEN','CLOSED']}
            _recent_charts=[('Qty pcs','pcs','Recent_Status_Qty'),('Weight ton','ton','Recent_Status_Weight'),('WOs','WO','Recent_Status_WOs')]
            for _v,_unit,_key in _recent_charts:
                _rg=_recent_bo.groupby(['Month / Status','Status','Product Category'],as_index=False)[_v].sum()
                _ordered=[f'{m} · {status}' for m in _last_months for status in ('OPEN','CLOSED')]
                _fig_recent=px.bar(_rg,x='Month / Status',y=_v,color='Product Category',barmode='stack',category_orders={'Month / Status':_ordered,'Product Category':['P','R','S','T','M','PB','UNKNOWN']},
                    color_discrete_map={'P':'#2563EB','R':'#16A34A','S':'#DC2626','T':'#7C3AED','M':'#0891B2','PB':'#EAB308','UNKNOWN':'#9CA3AF'},
                    title=f'Current open / closed by due month and category · {_unit}')
                _show_plotly(_fig_recent,_key)
            _rc1,_rc2,_rc3=st.columns(3)
            _open_recent=_recent_bo[_recent_bo['Status'].eq('OPEN')]
            _rc1.metric('Open pcs (3 due months only)',f"{_open_recent['Qty pcs'].sum():,.0f} pcs")
            _rc2.metric('Open WOs (3 due months only)',f"{_open_recent['WOs'].sum():,.0f} WO")
            _rc3.metric('Open tons (3 due months only)',f"{_open_recent['Weight ton'].sum():,.2f} t")
        _ltbc=_backorder_month_category(res.get('master',pd.DataFrame()))
        if not _ltbc.empty:
            _ltbc['_m']=pd.to_datetime(_ltbc['Due Month'].astype(str).str[:7]+'-01',errors='coerce')
            _ltbc['Month / Status']=_ltbc['_m'].dt.strftime('%b-%y')+' '+_ltbc['Status'].astype(str).str.upper()
            st.caption('One shared definition with Home: overdue open balance only, grouped by original due month and product category. Future open orders stay in MPS demand. / ใช้นิยามเดียวกับหน้าหลัก: เฉพาะยอดคงเหลือที่เปิดและเกินกำหนด')
            for _metric,_ttl,_nm in [
                ('Qty pcs','PAST-DUE BACKORDER QTY — MONTH × PRODUCT CATEGORY / จำนวนงานค้างส่ง','LongTerm_Backorder_QTY_reference'),
                ('Weight ton','PAST-DUE BACKORDER TON — MONTH × PRODUCT CATEGORY / น้ำหนักงานค้างส่ง','LongTerm_Backorder_TON_reference'),
                ('WOs','PAST-DUE BACKORDER WORK ORDERS — MONTH × PRODUCT CATEGORY / จำนวนใบงานค้างส่ง','LongTerm_Backorder_WO_reference')]:
                _ltg=_ltbc.groupby(['Month / Status','Product Category'],as_index=False)[_metric].sum()
                with st.expander(f'📝 Related data / ข้อมูลที่เกี่ยวข้อง — {_metric}  • click to review/edit graph source',expanded=False):
                    st.caption('Edits are planner-session corrections for analysis only; Plan2026 source is not overwritten. / การแก้ไขใช้เฉพาะการวิเคราะห์ในเซสชัน ไม่เขียนทับ Plan2026')
                    _ltg=_persistent_data_editor(_ltg,use_container_width=True,hide_index=True,num_rows='dynamic',key=f'bo_edit_{_nm}')
                    _ltg[_metric]=pd.to_numeric(_ltg[_metric],errors='coerce').fillna(0)
                _ltf=px.bar(_ltg,x='Month / Status',y=_metric,color='Product Category',barmode='stack',category_orders={'Product Category':['P','R','S','T','M','PB']},title=_ttl,color_discrete_map={'P':'#2563EB','R':'#16A34A','S':'#DC2626','T':'#7C3AED','M':'#0891B2','PB':'#EAB308'})
                _ltt=_ltg.groupby('Month / Status',as_index=False)[_metric].sum()
                _labs=[f'{v:.2f} t' if _metric=='Weight ton' else (f'{v:,.0f} WO' if _metric=='WOs' else f'{v:,.0f}') for v in _ltt[_metric]]
                _ltf.add_scatter(x=_ltt['Month / Status'],y=_ltt[_metric],mode='text',text=_labs,textposition='top center',showlegend=False,hoverinfo='skip')
                _ltf.update_xaxes(type='category',tickangle=-30)
                _show_plotly(_ltf,_nm)
            _lc1,_lc2,_lc3=st.columns(3); _lc1.metric('PAST-DUE OPEN / งานค้างเปิด',f"{_ltbc['Qty pcs'].sum():,.0f} pcs"); _lc2.metric('PAST-DUE WOs / จำนวน WO',f"{_ltbc['WOs'].sum():,.0f}"); _lc3.metric('PAST-DUE WEIGHT / น้ำหนักค้าง',f"{_ltbc['Weight ton'].sum():,.2f} t")
            # Bottleneck view for overdue OPEN backorder, using the shared Home definition.
            try:
                _mbo=res.get('master',pd.DataFrame()).copy(); _rbo=risk.copy() if isinstance(risk,pd.DataFrame) else pd.DataFrame()
                if not _mbo.empty and not _rbo.empty and 'Work Order' in _mbo.columns and 'Work Order' in _rbo.columns and 'Bottleneck Process' in _rbo.columns:
                    _ow=set(overdue_backorders(_mbo,bkk_today()).get('Work Order',pd.Series(dtype=str)).astype(str))
                    _rbo=_rbo[_rbo['Work Order'].astype(str).isin(_ow)].copy(); _rbo['_qty']=pd.to_numeric(_rbo.get('Open Qty',0),errors='coerce').fillna(0)
                    _bpg=_rbo.groupby('Bottleneck Process',as_index=False)['_qty'].sum().sort_values('_qty',ascending=False)
                    if not _bpg.empty:
                        with st.expander('📝 Related data / ข้อมูลที่เกี่ยวข้อง — Backorder bottleneck • click to review/edit',expanded=False):
                            _bpg=_persistent_data_editor(_bpg,use_container_width=True,hide_index=True,num_rows='dynamic',key='bo_edit_bottleneck_process')
                            _bpg['_qty']=pd.to_numeric(_bpg['_qty'],errors='coerce').fillna(0)
                        _fbp=px.bar(_bpg,x='_qty',y='Bottleneck Process',orientation='h',color='Bottleneck Process',title='OPEN BACKORDER BOTTLENECK PROCESS / กระบวนการคอขวดของงานค้างเปิด')
                        _show_plotly(_fbp,'LongTerm_Backorder_Bottleneck_Process')
            except Exception as _be: st.caption(f'Backorder bottleneck diagnostic: {_be}')
        else:
            st.info('No category-mapped backorder data available from current Plan 2026. / ไม่พบข้อมูลงานค้างส่งที่จับคู่กลุ่มสินค้า')
        st.subheader('🗓️ MPS + BACKORDER / แผนการผลิตหลัก + งานค้างส่ง → MRP → Purchase → Capacity → Risk')
        st.caption('MPS = long-term executable production schedule: month × product category × process requirement × controlled capacity × bottleneck/risk. It is not only a demand forecast.')
        if not _masterx.empty:
            _test=_masterx[_masterx['Test Work'].eq('YES')].copy()
            if not _test.empty:
                st.markdown('### 🧪 Test-work delivery risk / ความเสี่ยงงานทดสอบ')
                st.caption('TEST work is tracked separately because successful new/test work supports customer trust and future business; protect its committed date without overriding physical feasibility. / แยกติดตามงานทดสอบเพื่อความเชื่อมั่นลูกค้า โดยไม่วางแผนเกินความเป็นจริง')
                _tr=risk[risk['Work Order'].astype(str).isin(_test['Work Order'].astype(str))].copy() if not risk.empty else pd.DataFrame()
                if not _tr.empty:
                    _tr=_tr.merge(_test[['Work Order','Product Code','Work Type','Test Type','Test Rule Source']].drop_duplicates('Work Order'),on='Work Order',how='left')
                    st.dataframe(_tr[[c for c in ['Work Order','Product Code','Work Type','Test Type','Test Rule Source','Customer','Category','Due Date','Open Qty','Current Status / WIP','Bottleneck Process','Projected Finish','Delivery Risk'] if c in _tr.columns]],use_container_width=True,hide_index=True,height=300)
                    _tg=_tr.groupby(['Category','Delivery Risk'],as_index=False)['Open Qty'].sum()
                    ft=px.bar(_tg,x='Category',y='Open Qty',color='Delivery Risk',barmode='stack',title='Test-work delivery risk by category');_show_plotly(ft,'Test_Work_Delivery_Risk')
            _mts=_masterx[_masterx['Order Class'].str.startswith('MAKE TO STOCK')].copy()
            if not _mts.empty:
                st.markdown('### 🏪 Make-to-stock / continuous production identification')
                st.caption('Factory production-number rule from supplied reference: PM = continuous monthly Vitrified; PBM = continuous monthly Resin. PS/PBS remain monthly made-to-order.')
                _mtsw=wip[wip['Work Order'].astype(str).isin(_mts['Work Order'].astype(str))].copy() if isinstance(wip,pd.DataFrame) else pd.DataFrame()
                if not _mtsw.empty:
                    _mtsw=_mtsw.merge(_mts[['Work Order','Order Class','Product Code']].drop_duplicates('Work Order'),on='Work Order',how='left')
                    st.dataframe(_mtsw,use_container_width=True,hide_index=True,height=280)
                    st.markdown('#### 🛡️ MTS safety-stock protection / การปกป้อง Safety Stock')
                    _ssbase=_mts[['Product Code']].dropna().drop_duplicates().copy()
                    _ssbase['Safety Stock pcs']=0.0
                    _ssbase['Available FG Stock pcs']=0.0
                    if 'mts_safety_stock_control' in st.session_state and isinstance(st.session_state['mts_safety_stock_control'],pd.DataFrame):
                        _old=st.session_state['mts_safety_stock_control'].copy()
                        _ssbase=_ssbase.merge(_old,on='Product Code',how='left',suffixes=('','_old'))
                        for _c in ['Safety Stock pcs','Available FG Stock pcs']:
                            if _c+'_old' in _ssbase.columns:_ssbase[_c]=pd.to_numeric(_ssbase[_c+'_old'],errors='coerce').combine_first(pd.to_numeric(_ssbase[_c],errors='coerce')).fillna(0)
                        _ssbase=_ssbase[['Product Code','Safety Stock pcs','Available FG Stock pcs']]
                    _ssbase=_persistent_data_editor(_ssbase,use_container_width=True,hide_index=True,key='mts_safety_stock_editor')
                    st.session_state['mts_safety_stock_control']=_ssbase.copy()
                    _mtsw2=_mtsw.copy(); _mtsw2['WIP pcs']=pd.to_numeric(_mtsw2['WIP pcs'],errors='coerce').fillna(0) if 'WIP pcs' in _mtsw2.columns else pd.Series(0.0,index=_mtsw2.index)
                    _wipprod=_mtsw2.groupby('Product Code',as_index=False)['WIP pcs'].sum() if 'Product Code' in _mtsw2.columns else pd.DataFrame(columns=['Product Code','WIP pcs'])
                    _ss=_ssbase.merge(_wipprod,on='Product Code',how='left').fillna({'WIP pcs':0})
                    _ss['Safety Stock Gap pcs']=(pd.to_numeric(_ss['Safety Stock pcs'],errors='coerce').fillna(0)-pd.to_numeric(_ss['Available FG Stock pcs'],errors='coerce').fillna(0)).clip(lower=0)
                    _ss['Coverage incl. WIP pcs']=pd.to_numeric(_ss['Available FG Stock pcs'],errors='coerce').fillna(0)+pd.to_numeric(_ss['WIP pcs'],errors='coerce').fillna(0)
                    _ss['Projected Gap after WIP pcs']=(pd.to_numeric(_ss['Safety Stock pcs'],errors='coerce').fillna(0)-_ss['Coverage incl. WIP pcs']).clip(lower=0)
                    _ss['Status']=np.where(_ss['Projected Gap after WIP pcs']>0,'MTS REPLENISHMENT REQUIRED','SAFETY STOCK PROTECTED')
                    st.dataframe(_ss,use_container_width=True,hide_index=True,height=300)
                    _show_plotly(px.bar(_ss,x='Product Code',y=['Safety Stock pcs','Available FG Stock pcs','WIP pcs'],barmode='group',title='MTS safety stock vs FG stock vs WIP / Safety Stock เทียบสต็อกและ WIP'),'MTS_Safety_Stock_WIP')
        # Operational MRP: all open WO material requirements with real need dates.
        # Need Date = scheduled Preparation date where available; otherwise customer Due Date minus controlled internal lead.
        try:
            pm0,bom0,fm0,meta0=lm.parse_product_capacity(Path(st.session_state.cap_path).read_bytes())
            mw=res.get('master',pd.DataFrame()).copy()
            if not bom0.empty and not mw.empty:
                _leadmap=meta0.get('Internal Lead Days by Group',{}) or {}
                _prep=allp[allp['Section'].astype(str).eq('Preparation')].copy() if not allp.empty else pd.DataFrame()
                _prepdate={}
                if not _prep.empty:
                    _prep['_d']=pd.to_datetime(_prep['Plan Date'],errors='coerce')
                    _prepdate=_prep.dropna(subset=['_d']).groupby(_prep['Work Order'].astype(str))['_d'].min().to_dict()
                rows=[]
                for _,_r in mw.iterrows():
                    _wo=str(_r.get('Work Order','')).strip(); _item=str(_r.get('Product Code','')).strip()
                    _q=float(pd.to_numeric(pd.Series([_r.get('WIP Preparation',0)]),errors='coerce').fillna(0).iloc[0])
                    if _q<=0 or not _item: continue
                    _cat=eng.normcat(_r.get('Category','')); _due=pd.to_datetime(_r.get('Due Date'),errors='coerce')
                    _need=_prepdate.get(_wo,pd.NaT)
                    if pd.isna(_need) and pd.notna(_due): _need=_due-pd.Timedelta(days=float(_leadmap.get(_cat,0) or 0))
                    if pd.isna(_need): _need=pd.Timestamp(start)
                    _bg=bom0[bom0['Item'].astype(str).eq(_item)]
                    for _,_b in _bg.iterrows():
                        rows.append({'Work Order':_wo,'Customer':_r.get('Customer',''),'Category':_cat,'Item':_item,'Material':_b['Material'],'Need Qty pcs':_q,'g per pc':_b['g per pc'],'Need Date':pd.Timestamp(_need)})
                om=pd.DataFrame(rows)
                if not om.empty:
                    om['Gross Requirement t']=pd.to_numeric(om['Need Qty pcs'],errors='coerce').fillna(0)*pd.to_numeric(om['g per pc'],errors='coerce').fillna(0)/1e6
                    om['Need Year']=om['Need Date'].dt.year;om['Need Month']=om['Need Date'].dt.strftime('%Y-%m')
                    gross=om.groupby(['Material','Need Year','Need Month','Need Date'],as_index=False).agg({'Gross Requirement t':'sum','Work Order':'nunique','Need Qty pcs':'sum'}).rename(columns={'Work Order':'WOs'})
                    stk=res.get('stock',pd.DataFrame());stock_verified=isinstance(stk,pd.DataFrame) and not stk.empty and 'Material' in stk.columns
                    _stock=stk.groupby('Material',as_index=False)['On Hand t'].sum() if stock_verified else pd.DataFrame(columns=['Material','On Hand t'])
                    gross=gross.merge(_stock,on='Material',how='left')
                    if not stock_verified:gross['On Hand t']=float('nan')
                    gross['Source Type']=gross['Material'].astype(str).str.upper().apply(lambda x:'IMPORT' if ('RENWA' in x or x.strip()=='ART') else 'DOMESTIC')
                    gross['Lead Time days']=gross['Source Type'].map({'IMPORT':int(import_lead),'DOMESTIC':int(domestic_lead)})
                    gross=gross.sort_values(['Material','Need Date'])
                    gross['_Cum Gross']=gross.groupby('Material')['Gross Requirement t'].cumsum()
                    gross['_Prior Cum']=gross.groupby('Material')['_Cum Gross'].shift(fill_value=0)
                    _oh=pd.to_numeric(gross['On Hand t'],errors='coerce')
                    gross['_Cum Short']=(_oh.rsub(gross['_Cum Gross'])).clip(lower=0) if stock_verified else float('nan')
                    gross['_Prior Short']=(_oh.rsub(gross['_Prior Cum'])).clip(lower=0) if stock_verified else float('nan')
                    gross['Net Need t']=(gross['_Cum Short']-gross['_Prior Short']).clip(lower=0) if stock_verified else float('nan')
                    gross['Recommended PO Date']=gross.apply(lambda r:(pd.Timestamp(r['Need Date'])-pd.Timedelta(days=int(r['Lead Time days']))).date(),axis=1)
                    gross['Expected Receipt Date']=gross.apply(lambda r:(pd.Timestamp(r['Recommended PO Date'])+pd.Timedelta(days=int(r['Lead Time days']))).date(),axis=1)
                    gross['Expected Receipt if PO Initiated Today']=gross.apply(lambda r:(pd.Timestamp(start)+pd.Timedelta(days=int(r['Lead Time days']))).date(),axis=1)
                    gross['Receipt Risk Days if Ordered Today']=gross.apply(lambda r:max((pd.Timestamp(r['Expected Receipt if PO Initiated Today'])-pd.Timestamp(r['Need Date'])).days,0),axis=1)
                    gross['Action']=gross.apply(lambda r:('STOCK DATA REQUIRED' if pd.isna(r['On Hand t']) else ('ORDER / EXPEDITE' if r['Net Need t']>0 else 'STOCK COVERS')),axis=1)
                    st.markdown('### 🧪 OPERATIONAL MRP — ALL MATERIALS / ALL NEED DATES')
                    st.caption('Structured from the supplied MRP/MPS reference concept: finished-product demand → BOM/material usage → gross requirement → stock → net need → purchase timing. / โครงสร้างอ้างอิง: ความต้องการสินค้า → BOM/การใช้วัตถุดิบ → ความต้องการรวม → สต็อก → ความต้องการสุทธิ → เวลาในการสั่งซื้อ')
                    st.caption('Need Date comes from the scheduled Preparation date where available; otherwise Due Date minus the controlled internal production lead time. No single common date is forced.')
                    show=['Material','Need Year','Need Month','Need Date','WOs','Need Qty pcs','Gross Requirement t','On Hand t','Net Need t','Source Type','Lead Time days','Recommended PO Date','Expected Receipt Date','Expected Receipt if PO Initiated Today','Receipt Risk Days if Ordered Today','Action']
                    st.dataframe(gross[show],use_container_width=True,height=390,hide_index=True)
                    gmon=gross.groupby(['Need Month','Material'],as_index=False)['Gross Requirement t'].sum()
                    fig=px.bar(gmon,x='Need Month',y='Gross Requirement t',color='Material',barmode='stack',title='Operational MRP — ALL materials by need month',hover_data={'Gross Requirement t':':.3f'})
                    _gt=gmon.groupby('Need Month',as_index=False)['Gross Requirement t'].sum()
                    fig.add_scatter(x=_gt['Need Month'],y=_gt['Gross Requirement t'],mode='text',text=[f'{v:.2f} t' for v in _gt['Gross Requirement t']],textposition='top center',showlegend=False,hoverinfo='skip')
                    _show_plotly(fig,'Operational_MRP_all_materials_months')
                    _tl=gross.copy();_tl['Recommended PO Date']=pd.to_datetime(_tl['Recommended PO Date'],errors='coerce')
                    _tl['Start = Recommended PO Date']=_tl['Recommended PO Date']
                    _tl['End = Expected Material Receipt Date']=pd.to_datetime(_tl['Expected Receipt Date'],errors='coerce')
                    figt=px.timeline(
                        _tl,x_start='Recommended PO Date',x_end='Expected Receipt Date',y='Material',color='Source Type',
                        hover_data={'Start = Recommended PO Date':True,'End = Expected Material Receipt Date':True,
                                    'Need Month':True,'Gross Requirement t':':.3f','Net Need t':':.3f',
                                    'WOs':True,'Action':True},
                        title='Operational MRP — PO INITIATION → EXPECTED MATERIAL RECEIPT'
                    )
                    figt.update_traces(text=None,texttemplate=None,hovertemplate=None)
                    figt.update_yaxes(autorange='reversed')
                    _show_plotly(figt,'Operational_MRP_all_material_timing')
                    st.caption('Horizontal bar START = Recommended PO Initiation Date. END = Expected Material Receipt Date based on the controlled import/domestic lead time. Material Need Date remains shown in hover/table; Receipt Risk Days shows whether ordering today would already be late. Raw epoch/date numbers are intentionally not printed on the bars; move the cursor to see named dates.')
                else: st.warning('No current Preparation material demand could be matched to BOM. Check Product Code/BOM mapping or WIP Preparation quantities.')
            else:st.warning('Operational MRP requires BOM/product-material data in Capacity Database and current Plan2026.')
        except Exception as e:st.warning(f'Operational MRP diagnostic: {e}')
        st.markdown('---')
        st.markdown('### 🗓️ OPERATIONAL MASTER PRODUCTION SCHEDULE — MONTH × CATEGORY × CAPACITY × RISK')
        st.caption('Reference logic from the supplied historical MPS: monthly demand by item/customer/category, then compare required production with executable schedule and controlled capacity. / อ้างอิงแนวคิด MPS เดิม: ความต้องการรายเดือนตามสินค้า/ลูกค้า/กลุ่มสินค้า แล้วเทียบกับแผนที่ทำได้และกำลังการผลิต')
        _om=res.get('master',pd.DataFrame()).copy();_op=allp.copy()
        if not _om.empty and 'Due Date' in _om.columns:
            _om['Due Date']=pd.to_datetime(_om['Due Date'],errors='coerce');_om=_om.dropna(subset=['Due Date'])
            _om['Month']=_om['Due Date'].dt.to_period('M').astype(str);_om['Product Category']=_om.get('Category','').astype(str).str.strip().str.upper();_om=_om[_om['Product Category'].isin(['P','R','S','T','M','PB'])]
            _om['Demand pcs']=pd.to_numeric(_om.get('Order Qty',0),errors='coerce').fillna(0)-pd.to_numeric(_om.get('Packing Actual Qty',_om.get('Packing Actual',0)),errors='coerce').fillna(0);_om['Demand pcs']=_om['Demand pcs'].clip(lower=0)
            _dm=_om.groupby(['Month','Product Category'],as_index=False)['Demand pcs'].sum()
            if not _op.empty:
                _op['Plan Date']=pd.to_datetime(_op.get('Plan Date'),errors='coerce');_op['Month']=_op['Plan Date'].dt.to_period('M').astype(str);_op['Product Category']=_op.get('Category','').astype(str).str.strip().str.upper()
                _pk=_op[_op.get('Section','').astype(str).eq('Packing')].groupby(['Month','Product Category'],as_index=False)['Plan Qty'].sum().rename(columns={'Plan Qty':'Scheduled pcs'})
                _dm=_dm.merge(_pk,on=['Month','Product Category'],how='left')
            _dm['Scheduled pcs']=pd.to_numeric(_dm.get('Scheduled pcs',0),errors='coerce').fillna(0);_dm['Risk pcs']=(_dm['Demand pcs']-_dm['Scheduled pcs']).clip(lower=0)
            fig=go.Figure()
            for _cat in ['P','R','S','T','M','PB']:
                _z=_dm[_dm['Product Category'].eq(_cat)].groupby('Month',as_index=False)[['Demand pcs','Scheduled pcs','Risk pcs']].sum()
                fig.add_bar(x=_z['Month'],y=_z['Scheduled pcs'],name=f'{_cat} scheduled')
            _tot=_dm.groupby('Month',as_index=False)[['Demand pcs','Scheduled pcs','Risk pcs']].sum()
            fig.add_scatter(x=_tot['Month'],y=_tot['Demand pcs'],name='Required demand',mode='lines+markers')
            fig.add_scatter(x=_tot['Month'],y=_tot['Risk pcs'],name='Uncovered / risk',mode='lines+markers')
            fig.update_layout(barmode='stack',title='Operational MPS — monthly scheduled production by category vs required demand and uncovered risk',yaxis_title='pcs',hovermode='x unified')
            _show_plotly(fig,'Operational_MPS_month_category_capacity_risk')
            # Monthly capacity evidence from the same daily capacity calendar used by the planner.
            _cp=caps.copy() if isinstance(caps,pd.DataFrame) else pd.DataFrame()
            if not _cp.empty and 'Plan Date' in _cp.columns:
                _cp['Plan Date']=pd.to_datetime(_cp['Plan Date'],errors='coerce');_cp['Month']=_cp['Plan Date'].dt.to_period('M').astype(str)
                _cm=_cp.groupby(['Month','Section'],as_index=False)[['Capacity ton','Plan ton']].sum()
                _cm['Load %']=np.where(_cm['Capacity ton']>0,_cm['Plan ton']/_cm['Capacity ton']*100,np.nan)
                _cm['Month / Process']=_cm['Month'].astype(str)+' | '+_cm['Section'].astype(str)
                fig=go.Figure();fig.add_bar(x=_cm['Month / Process'],y=_cm['Plan ton'],name='Planned load ton');fig.add_bar(x=_cm['Month / Process'],y=_cm['Capacity ton'],name='Controlled capacity ton')
                fig.update_layout(barmode='group',title='MPS PROCESS SCHEDULE — PLAN vs CONTROLLED CAPACITY',yaxis_title='ton',xaxis_title='Month | Process')
                _show_plotly(fig,'Operational_MPS_monthly_process_capacity')
                _cm['Focus / Resource Action']=np.where(_cm['Load %']>100,'CAPACITY SHORTFALL — OT / alternate resource / reschedule excess',np.where(_cm['Load %']>=90,'WATCH — protect due-date work and prepare recovery resource','AVAILABLE — pull next-due executable work'))
                st.dataframe(_cm.sort_values('Load %',ascending=False),use_container_width=True,hide_index=True,height=340)
            st.dataframe(_dm.sort_values(['Month','Product Category']),use_container_width=True,hide_index=True,height=320)
        else:
            st.info('No valid due-date demand available for operational MPS.')

        st.markdown('### 🏭 MASTER PRODUCTION SCHEDULE (MPS) → MATERIAL REQUIREMENTS (MRP)')
        st.caption('MPS answers WHAT finished products must be produced, HOW MANY, and WHEN — by month, product, category, size and customer — while comparing required production load with available capacity. MRP is then calculated FROM the MPS to answer what materials must be purchased and when.')
        if not st.session_state.sales_path or not Path(st.session_state.sales_path).exists():
            st.info('Upload Sales Forecast for long-term MPS. Operational MRP above remains available from Plan2026.')
        else:
            policy=st.session_state.policy.copy() if isinstance(st.session_state.policy,pd.DataFrame) else pd.DataFrame()
            if not policy.empty:policy=_persistent_data_editor(policy,use_container_width=True,hide_index=True,key='matpolicy',column_config={'Source Type':st.column_config.SelectboxColumn('Source Type',options=['IMPORT','DOMESTIC'])});st.session_state.policy=policy
            if st.button('🔄 BUILD / REFRESH MPS-MRP',use_container_width=True):
                try:
                    sales_base,sales_long=lm.parse_sales(Path(st.session_state.sales_path).read_bytes());pmaster,bom,formmeta,meta=lm.parse_product_capacity(Path(st.session_state.cap_path).read_bytes());stock=(lm.parse_stock(Path(st.session_state.stock_path).read_bytes()) if st.session_state.stock_path and Path(st.session_state.stock_path).exists() else pd.DataFrame(columns=['Material','On Hand t']));planlt=lm.parse_plan2026(Path(st.session_state.plan_path).read_bytes())
                    pol=policy.copy();pol.loc[pol['Source Type'].eq('IMPORT'),'Lead Time days']=int(import_lead);pol.loc[pol['Source Type'].eq('DOMESTIC'),'Lead Time days']=int(domestic_lead)
                    model=lm.build_model(sales_long,sales_base,pmaster,bom,stock,planlt,formmeta,meta,start.year,start.month,'Higher of Sales Forecast or Firm Open Orders',26,8.0,pol,as_of=bkk_today());st.session_state.long_result={'model':model,'sales_base':sales_base,'master':pmaster,'bom':bom,'stock':stock,'policy':pol,'meta':meta}
                except Exception as e:st.error(str(e));st.code(traceback.format_exc())
            lr=st.session_state.long_result
            if lr:
                model=lr['model'];mps=model.get('mps',pd.DataFrame());mrp=model.get('mrp',pd.DataFrame());pur=model.get('purchase',pd.DataFrame());capm=model.get('capacity',pd.DataFrame());rr=model.get('risk',pd.DataFrame())
                if not mps.empty:
                    st.markdown('### 📈 MASTER PRODUCTION SCHEDULE — WHAT / HOW MANY / WHEN')
                    st.caption('Construction: explicit backorder recovery + higher of Sales Forecast or firm open-order demand. Capacity is a feasibility check; due/open demand is not deleted merely because capacity is tight.')
                    _months=list(mps['Month'].dropna().astype(str).unique())
                    _mselect=st.selectbox('MPS month detail',_months,key='mps_month_detail') if _months else None
                    _mv=mps[mps['Month'].astype(str).eq(str(_mselect))].copy() if _mselect else mps.copy()
                    if not _mv.empty:
                        _top=_mv.groupby(['Item','Group'],dropna=False,as_index=False)[['MPS Pcs','MPS t']].sum().sort_values('MPS Pcs',ascending=False).head(25)
                        fig=px.bar(_top,x='Item',y='MPS Pcs',color='Group',text='MPS Pcs',
                                   hover_data={'Group':True,'MPS Pcs':':,.0f','MPS t':':.3f'},title=f'MPS product schedule — {_mselect}')
                        _show_plotly(fig,'MPS_product_detail')
                        _cust=_mv.groupby('Customer',as_index=False)[['MPS Pcs','MPS t']].sum().sort_values('MPS Pcs',ascending=False).head(20)
                        if not _cust.empty:
                            fig=px.bar(_cust,x='Customer',y='MPS Pcs',text='MPS Pcs',hover_data={'MPS t':':.3f'},title=f'MPS by customer — {_mselect}')
                            _show_plotly(fig,'MPS_customer_detail')
                        st.dataframe(_mv[[c for c in ['Month','Item','Customer','Group','Size Range','Forecast Pcs','Firm Future Pcs','Backorder Recovery Pcs','MPS Pcs','MPS t','Demand Basis'] if c in _mv.columns]],use_container_width=True,height=330,hide_index=True)
                    st.markdown('### 📈 MPS — SALES FORECAST vs CAPACITY vs POSSIBLE PLAN')
                    mg=model.get('mps_monthly',pd.DataFrame()).copy()
                    if mg.empty: mg=mps.groupby(['Month No','Month'],as_index=False)[['Forecast Pcs','Firm Future Pcs','Backorder Recovery Pcs','MPS Pcs','MPS t']].sum().sort_values('Month No')
                    if not mg.empty and {'Forecast Pcs','MPS Pcs','Possible Plan Pcs'}.issubset(mg.columns):
                        _fg=go.Figure();_fg.add_bar(x=mg['Month'],y=mg['Forecast Pcs'],name='Sales Forecast pcs');_fg.add_scatter(x=mg['Month'],y=mg['MPS Pcs'],name='Aggregate Demand / MPS pcs',mode='lines+markers');_fg.add_scatter(x=mg['Month'],y=mg['Possible Plan Pcs'],name='Capacity-feasible Possible Plan pcs',mode='lines+markers');_fg.update_layout(title='Master Production Schedule — forecast vs aggregate demand vs possible plan',yaxis_title='pcs');_show_plotly(_fg,'MPS_forecast_capacity_possible_plan_pcs')
                        _tg=go.Figure();_tg.add_bar(x=mg['Month'],y=mg['MPS t'],name='Required production ton');_tg.add_scatter(x=mg['Month'],y=mg['Possible Plan t'],name='Possible production ton',mode='lines+markers');_tg.add_scatter(x=mg['Month'],y=mg['Mixing Capacity t'],name='Normal mixing capacity ton',mode='lines+markers');_tg.update_layout(title='MPS weight feasibility — required vs possible vs normal mixing capacity',yaxis_title='ton');_show_plotly(_tg,'MPS_weight_feasibility')
                        st.dataframe(mg[[c for c in ['Month','Forecast Pcs','Firm Future Pcs','Backorder Recovery Pcs','MPS Pcs','MPS t','Possible Plan Pcs','Possible Plan t','Capacity Shortfall Pcs','Capacity Shortfall t','Mixing Load %','Forming Load %','Aggregate Feasibility','Primary Constraint','MPS Risk','Suggested Capacity Action'] if c in mg.columns]],use_container_width=True,height=330,hide_index=True)
                    st.markdown('### 📈 MPS — MONTHWISE PCS / TON / WORK ORDERS')
                    _firm=model.get('firm',pd.DataFrame()).copy()
                    if not _firm.empty:
                        _firm['Due Date']=pd.to_datetime(_firm['Due Date'],errors='coerce');_firm['Month No']=_firm['Due Date'].dt.month
                        _woc=_firm.groupby('Month No')['WO'].nunique() if 'WO' in _firm.columns else pd.Series(dtype=float)
                        mg['Firm Open WOs']=mg['Month No'].map(_woc).fillna(0).astype(int)
                    else:mg['Firm Open WOs']=0
                    c1,c2,c3=st.columns(3)
                    with c1:
                        fig=px.bar(mg,x='Month',y='MPS Pcs',text='MPS Pcs',hover_data=['Forecast Pcs','Firm Future Pcs','Backorder Recovery Pcs'],title='MPS quantity — pcs');_show_plotly(fig,'MPS_monthly_pcs')
                    with c2:
                        fig=px.bar(mg,x='Month',y='MPS t',text='MPS t',hover_data=['MPS Pcs'],title='MPS production weight — ton');_show_plotly(fig,'MPS_monthly_ton')
                    with c3:
                        fig=px.bar(mg,x='Month',y='Firm Open WOs',text='Firm Open WOs',hover_data=['MPS Pcs','MPS t'],title='Firm open Work Orders by due month');_show_plotly(fig,'MPS_monthly_workorders')
                    st.dataframe(mps,use_container_width=True,height=320)
                    # Sales Forecast representation: category/group and size range, not only total ton.
                    mgp=model.get('group',pd.DataFrame());msz=model.get('size',pd.DataFrame())
                    if not mgp.empty:
                        st.markdown('### 🧩 MPS ANALYSIS — PRODUCT CATEGORY WISE')
                        _cv=mgp.copy();_cy='Possible Plan Pcs' if 'Possible Plan Pcs' in _cv.columns else 'MPS Pcs'
                        fig=px.bar(_cv,x='Month',y=_cy,color='Group',barmode='stack',title='Capacity-feasible possible production plan — category wise',hover_data=[c for c in ['Forecast Pcs','MPS Pcs','MPS t','Possible Plan Pcs','Possible Plan t','Feasibility','Capacity Factor'] if c in _cv.columns]);_ct=_cv.groupby('Month',as_index=False)[_cy].sum();fig.add_scatter(x=_ct['Month'],y=_ct[_cy],mode='text',text=[f'{v:,.0f}' if 'Pcs' in _cy else f'{v:.2f} t' for v in _ct[_cy]],textposition='top center',showlegend=False,hoverinfo='skip');_show_plotly(fig,'MPS_category_possible_plan')
                        st.dataframe(_cv[[c for c in ['Month','Group','Forecast Pcs','Firm Future Pcs','Backorder Recovery Pcs','MPS Pcs','MPS t','Possible Plan Pcs','Possible Plan t','Capacity Shortfall Pcs','Required Forming hr','Shared Available Forming hr/month','Feasibility','Capacity Factor'] if c in _cv.columns]],use_container_width=True,height=300,hide_index=True)
                    if not msz.empty:
                        st.markdown('### 📏 MPS ANALYSIS — PRODUCT SIZE WISE')
                        _sv=msz.copy();_sy='Possible Plan Pcs' if 'Possible Plan Pcs' in _sv.columns else 'MPS Pcs'
                        fig=px.bar(_sv,x='Month',y=_sy,color='Size Range',barmode='stack',title='Capacity-feasible possible production plan — size wise',hover_data=[c for c in ['Group','Forecast Pcs','MPS Pcs','MPS t','Possible Plan Pcs','Possible Plan t','Feasibility','Capacity Factor'] if c in _sv.columns]);_st=_sv.groupby('Month',as_index=False)[_sy].sum();fig.add_scatter(x=_st['Month'],y=_st[_sy],mode='text',text=[f'{v:,.0f}' if 'Pcs' in _sy else f'{v:.2f} t' for v in _st[_sy]],textposition='top center',showlegend=False,hoverinfo='skip');_show_plotly(fig,'MPS_size_possible_plan')
                        st.dataframe(_sv[[c for c in ['Month','Group','Size Range','Forecast Pcs','Firm Future Pcs','Backorder Recovery Pcs','MPS Pcs','MPS t','Possible Plan Pcs','Possible Plan t','Capacity Shortfall Pcs','Required Forming hr','Feasibility','Capacity Factor'] if c in _sv.columns]],use_container_width=True,height=320,hide_index=True)
                if not mrp.empty:
                    st.markdown('### 🧪 MRP — Material Requirement / ความต้องการวัตถุดิบ')
                    mcols=[c for c in ['Month No','Month','Material','Gross Requirement t'] if c in mrp.columns]
                    if 'Gross Requirement t' in mrp.columns and 'Month' in mrp.columns:
                        rg=mrp.groupby(['Month No','Month'],as_index=False)['Gross Requirement t'].sum().sort_values('Month No')
                        fig,ax=plt.subplots(figsize=(11,4.5));ax.bar(rg['Month'],rg['Gross Requirement t']);ax.set_ylabel('Gross requirement ton');ax.set_title('Monthly MRP gross requirement');ax.tick_params(axis='x',rotation=35);fig.tight_layout();_show_mpl(fig,'SL_PPC_graph_08')
                        # ALL materials, ALL months: no top-N truncation.
                        _mall=mrp.groupby(['Month No','Month','Material'],as_index=False)['Gross Requirement t'].sum().sort_values(['Month No','Material'])
                        fig=px.bar(_mall,x='Month',y='Gross Requirement t',color='Material',barmode='stack',hover_data={'Gross Requirement t':':.3f'},title='MRP — ALL materials by month');_mt=_mall.groupby('Month',as_index=False)['Gross Requirement t'].sum();fig.add_scatter(x=_mt['Month'],y=_mt['Gross Requirement t'],mode='text',text=[f'{v:.2f} t' for v in _mt['Gross Requirement t']],textposition='top center',showlegend=False,hoverinfo='skip')
                        _show_plotly(fig,'MRP_all_materials_all_months')
                    st.dataframe(mrp,use_container_width=True,height=280)
                    if 'Material' in mrp.columns and 'Gross Requirement t' in mrp.columns:
                        mm=mrp.groupby('Material',as_index=False)['Gross Requirement t'].sum().sort_values('Gross Requirement t',ascending=False)
                        fig,ax=plt.subplots(figsize=(12,5));ax.bar(mm['Material'].astype(str),mm['Gross Requirement t'],color=plt.cm.tab20(range(len(mm))));ax.set_ylabel('Gross requirement ton');ax.set_title('MRP by material');ax.tick_params(axis='x',rotation=55);fig.tight_layout();_show_mpl(fig,'SL_PPC_graph_10')
                    stk=lr.get('stock',pd.DataFrame())
                    if isinstance(stk,pd.DataFrame) and not stk.empty and 'Material' in stk.columns:
                        qtycol=next((c for c in ['On Hand t','Stock t','Qty t','On Hand','Stock'] if c in stk.columns),None)
                        if qtycol:
                            ss=stk[['Material',qtycol]].copy();ss[qtycol]=pd.to_numeric(ss[qtycol],errors='coerce').fillna(0);ss=ss.groupby('Material',as_index=False)[qtycol].sum().sort_values(qtycol,ascending=False)
                            fig,ax=plt.subplots(figsize=(12,5));ax.bar(ss['Material'].astype(str),ss[qtycol],color=plt.cm.tab20(range(len(ss))));ax.set_ylabel('Stock on hand');ax.set_title('Stock on hand by material');ax.tick_params(axis='x',rotation=55);fig.tight_layout();_show_mpl(fig,'SL_PPC_graph_11')
                st.markdown('### 🛒 WHAT — WHEN — HOW MUCH / ซื้ออะไร เมื่อไร เท่าไร')
                if pur.empty:st.success('No purchase action generated from current MRP/stock/policy.')
                else:
                    show=[c for c in ['Material','Supplier','Need Month','Required Receipt Date','Recommended PO Date','Gross Requirement t','Beginning Stock t','Safety Stock t','Recommended Order Qty t','Action','Data Warning'] if c in pur.columns]
                    st.dataframe(pur[show],use_container_width=True,height=340)
                    pg=pur.groupby('Need Month',as_index=False)['Recommended Order Qty t'].sum() if 'Need Month' in pur.columns else pd.DataFrame()
                    if not pg.empty:
                        fig,ax=plt.subplots(figsize=(11,4.5));ax.bar(pg['Need Month'],pg['Recommended Order Qty t']);ax.set_ylabel('Recommended order ton');ax.set_title('Purchase quantity by need month');ax.tick_params(axis='x',rotation=35);fig.tight_layout();_show_mpl(fig,'SL_PPC_graph_12')
                if not capm.empty:
                    st.markdown('### 🏭 MPS Capacity Outlook / แนวโน้มกำลังการผลิต')
                    fig,ax=plt.subplots(figsize=(11,4.5));x=range(len(capm));
                    if 'MPS t' in capm.columns:ax.plot(list(x),capm['MPS t'],marker='o',label='MPS ton')
                    if 'Mixing Capacity t' in capm.columns:ax.plot(list(x),capm['Mixing Capacity t'],marker='o',label='Mixing capacity ton')
                    ax.set_xticks(list(x));ax.set_xticklabels(capm['Month'],rotation=35,ha='right');ax.set_ylabel('ton');ax.set_title('MPS vs monthly capacity');ax.legend();fig.tight_layout();_show_mpl(fig,'SL_PPC_graph_13')
                    st.dataframe(capm,use_container_width=True,height=260)
                # V1.7.8 detailed long-term control views
                bo=model.get('backorder_detail',pd.DataFrame()); bos=model.get('backorder_summary',pd.DataFrame()); cc=model.get('capacity_category',pd.DataFrame()); cs=model.get('capacity_size',pd.DataFrame()); mg2=model.get('mps_monthly',pd.DataFrame())
                st.markdown('### 🚨 PAST-DUE BACKORDERS — MONTHWISE OPEN')
                st.caption(f"Same Plan-2026 rule as Home, as of {bkk_today():%d %b %Y} in Phan Thong, Chonburi: revised due date (E; initial C only when E is blank), open pcs = QTY − Packing Actual, and whole-WO closed by EU or FC. Due today/future and unknown-date orders are not counted as overdue.")
                _boc=_monthly_open_closed(res.get('master',pd.DataFrame()))
                if not _boc.empty:
                    _boc['Due Month']=_boc['Due Month'].astype(str).str[:7]
                    fig=px.bar(_boc,x='Due Month',y='Qty pcs',color='Status',barmode='group',
                               hover_data={'Qty pcs':':,.0f','WOs':True},
                               title='Past-due open quantity by due month — same definition as Home')
                    _show_plotly(fig,'LongTerm_backorder_open_closed_monthwise')
                    st.dataframe(_boc,use_container_width=True,hide_index=True)
                st.markdown('### 🚨 BACKORDER RECOVERY LOAD — OPEN QTY TO RECOVER')
                st.caption('Recovery demand is split from in-year firm future demand; one WO cannot be in both buckets. 2027 due orders are excluded from a 2026 MPS horizon and remain future demand. Capacity comparison below uses the calculated MPS load and the controlled capacity source.')
                if bo.empty: st.success('No overdue open orders in current Plan 2026 source.')
                else:
                    c1,c2=st.columns(2);c1.metric('Backorder WOs',bo['WO'].astype(str).nunique());c2.metric('Backorder Qty',f"{pd.to_numeric(bo['Open Qty'],errors='coerce').fillna(0).sum():,.0f} pcs")
                    if not bos.empty:
                        fig=px.bar(bos,x='Group',y='Backorder Pcs',color='Size Range',barmode='group',hover_data=['Backorder WOs'],title='Backorder by product category and size');_show_plotly(fig,'Backorder_by_category_size')
                    # Detailed recovery analysis for management: age, current stage, recovery timing and lateness.
                    _bo=bo.copy()
                    if not _bo.empty:
                        _today=pd.Timestamp(start)
                        if 'Due Date' in _bo.columns:
                            _bo['Due Date']=pd.to_datetime(_bo['Due Date'],errors='coerce')
                            _bo['Backorder Age days']=(_today-_bo['Due Date']).dt.days.clip(lower=0)
                        _rmap=risk.drop_duplicates('Work Order').set_index(risk['Work Order'].astype(str)) if not risk.empty and 'Work Order' in risk.columns else pd.DataFrame()
                        if not isinstance(_rmap,pd.DataFrame) or _rmap.empty:
                            _bo['Current Stage']='';_bo['Projected Finish']=pd.NaT;_bo['Recovery Risk']='CHECK';_bo['Recovery Action']='Review current WIP and capacity.'
                        else:
                            _bo['Current Stage']=_bo['WO'].astype(str).map(_rmap.get('Current Status / WIP',pd.Series(dtype=object)))
                            _bo['Projected Finish']=pd.to_datetime(_bo['WO'].astype(str).map(_rmap.get('Projected Finish',pd.Series(dtype=object))),errors='coerce')
                            _bo['Recovery Risk']=_bo['WO'].astype(str).map(_rmap.get('Delivery Risk',pd.Series(dtype=object)))
                            _bo['Recovery Action']=_bo['WO'].astype(str).map(_rmap.get('Detailed Reason',pd.Series(dtype=object)))
                        _bo['Projected Additional Late days']=np.where(_bo['Projected Finish'].notna()&_bo['Due Date'].notna(),(_bo['Projected Finish']-_bo['Due Date']).dt.days.clip(lower=0),np.nan)
                        st.markdown('### 🔎 BACKORDER RECOVERY — ORDER-BY-ORDER ROOT VISIBILITY')
                        _bc=[c for c in ['WO','Customer','Group','Size Range','Open Qty','Due Date','Backorder Age days','Current Stage','Projected Finish','Projected Additional Late days','Recovery Risk','Recovery Action'] if c in _bo.columns]
                        st.dataframe(_bo[_bc].sort_values(['Backorder Age days','Open Qty'],ascending=[False,False]),use_container_width=True,height=420,hide_index=True)
                        _age=_bo.groupby('Group',as_index=False).agg(**{'Backorder pcs':('Open Qty','sum'),'Average age days':('Backorder Age days','mean'),'WOs':('WO','nunique')})
                        fage=px.scatter(_age,x='Average age days',y='Backorder pcs',size='WOs',color='Group',hover_data=['WOs'],title='Backorder severity — quantity vs age')
                        _show_plotly(fage,'Backorder_severity_age_qty')
                    # MD backorder analysis: bottleneck process -> category -> WO/customer/qty + complete route/status.
                    if '_bo' in locals() and isinstance(_bo,pd.DataFrame) and not _bo.empty:
                        _bo['Bottleneck Process']=_bo['WO'].astype(str).map(_rmap.get('Bottleneck Process',pd.Series(dtype=object))) if isinstance(_rmap,pd.DataFrame) and not _rmap.empty else ''
                        _bpg=_bo.groupby(['Bottleneck Process','Group'],dropna=False,as_index=False)['Open Qty'].sum()
                        if not _bpg.empty:
                            _fbo=px.bar(_bpg,x='Bottleneck Process',y='Open Qty',color='Group',barmode='stack',title='BACKORDER QTY BY BOTTLENECK PROCESS + PRODUCT CATEGORY')
                            _bpt=_bpg.groupby('Bottleneck Process',as_index=False)['Open Qty'].sum();_fbo.add_scatter(x=_bpt['Bottleneck Process'],y=_bpt['Open Qty'],mode='text',text=[f'{v:,.0f}' for v in _bpt['Open Qty']],textposition='top center',showlegend=False,hoverinfo='skip')
                            _show_plotly(_fbo,'Backorder_bottleneck_process_category')
                        _bplan=allp[allp['Work Order'].astype(str).isin(_bo['WO'].astype(str))].copy()
                        _broutes=[]
                        for _wo,_gg in _bplan.groupby('Work Order'):
                            _broutes.append({'WO':str(_wo),'Complete Plan':' → '.join(_gg.sort_values('Plan Date')['Section'].astype(str).drop_duplicates().tolist()),'Next Planned Date':pd.to_datetime(_gg['Plan Date'],errors='coerce').min(),'Last Planned Date':pd.to_datetime(_gg['Plan Date'],errors='coerce').max()})
                        _routes=pd.DataFrame(_broutes)
                        _boexp=_bo.merge(_routes,on='WO',how='left') if not _routes.empty else _bo.copy()
                        st.markdown('### 📋 BACKORDER BOTTLENECK + COMPLETE PLAN DETAIL')
                        _boexp['Due Month']=pd.to_datetime(_boexp.get('Due Date'),errors='coerce').dt.strftime('%Y-%m')
                        _boexp['Required Recovery pcs']=pd.to_numeric(_boexp.get('Open Qty',0),errors='coerce').fillna(0)
                        _boexp['Positive Recovery Signal']=_boexp.apply(lambda r:f"PRODUCE {float(r.get('Required Recovery pcs',0)):,.0f} pcs; protect {r.get('WO','')} through {r.get('Bottleneck Process','CHECK PROCESS')} to packing",axis=1)
                        _bc2=[c for c in ['WO','Customer','Group','Open Qty','Due Date','Due Month','Backorder Age days','Current Stage','Bottleneck Process','Required Recovery pcs','Projected Finish','Recovery Risk','Complete Plan','Next Planned Date','Last Planned Date','Positive Recovery Signal','Recovery Action'] if c in _boexp.columns]
                        st.dataframe(_boexp[_bc2],use_container_width=True,hide_index=True,height=430)
                        _bio=io.BytesIO()
                        with pd.ExcelWriter(_bio,engine='xlsxwriter') as _bw:
                            _boexp.to_excel(_bw,index=False,sheet_name='Backorder Risk Detail')
                            if not _bpg.empty:_bpg.to_excel(_bw,index=False,sheet_name='Bottleneck Summary')
                            if not _bplan.empty:_bplan.to_excel(_bw,index=False,sheet_name='Complete Production Plan')
                        st.download_button('⬇️ DOWNLOAD BACKORDER BOTTLENECK ANALYSIS — EXCEL',_bio.getvalue(),file_name='SL_PPC_BACKORDER_BOTTLENECK_ANALYSIS.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='backorder_bottleneck_excel')
                    # V1.9.16: category x month OPEN/CLOSED + complete-process Gantt.
                    _bmc=_backorder_month_category(res.get('master',pd.DataFrame()))
                    if not _bmc.empty:
                        st.markdown('### 📊 PAST-DUE BACKORDER — PRODUCT CATEGORY × MONTH / งานค้างส่งเกินกำหนด')
                        _bmc['Period / Status']=_bmc['Due Month'].astype(str)+'  '+_bmc['Status'].astype(str)
                        for _metric,_title,_nm,_fmt in [
                            ('Qty pcs','PAST-DUE BACKORDER QUANTITY × PRODUCT CATEGORY','Backorder_qty_category_stack',',.0f'),
                            ('Weight ton','PAST-DUE BACKORDER WEIGHT × PRODUCT CATEGORY','Backorder_weight_category_stack','.2f'),
                            ('WOs','PAST-DUE BACKORDER WORK ORDERS × PRODUCT CATEGORY','Backorder_wo_category_stack',',.0f')]:
                            _bc=_bmc.groupby(['Period / Status','Product Category'],as_index=False)[_metric].sum()
                            _fbmc=px.bar(_bc,x='Period / Status',y=_metric,color='Product Category',barmode='stack',category_orders={'Product Category':['P','R','S','T','M','PB']},title=_title)
                            _bct=_bc.groupby('Period / Status',as_index=False)[_metric].sum()
                            _labs=[(f'{v:.2f} t' if _metric=='Weight ton' else (f'{v:,.0f} WO' if _metric=='WOs' else f'{v:,.0f} pcs')) for v in _bct[_metric]]
                            _fbmc.add_scatter(x=_bct['Period / Status'],y=_bct[_metric],mode='text',text=_labs,textposition='top center',showlegend=False,hoverinfo='skip')
                            _show_plotly(_fbmc,_nm)
                        st.dataframe(_bmc.sort_values(['Due Month','Status','Product Category']),use_container_width=True,hide_index=True,height=300)
                    if '_bo' in locals() and isinstance(_bo,pd.DataFrame) and not _bo.empty:
                        _bgantt=_complete_gantt_rows(res.get('master',pd.DataFrame()),allp,_bo['WO'].astype(str).unique(),start)
                        if not _bgantt.empty:
                            st.markdown('### 🗓️ BACKORDER COMPLETE PROCESS GANTT / แกนต์ทุกกระบวนการ')
                            _gb=px.timeline(_bgantt,x_start='Gantt Start',x_end='Gantt End',y='Work Order',color='Status',hover_data=['Customer','Product Category','Process','Actual pcs','Order pcs','Expected Finish','Due Date'],title='ALL PPC PROCESSES — PASSED / CURRENT / WAITING + EXPECTED FINISH')
                            _gb.update_yaxes(autorange='reversed');_gb.update_layout(height=max(520,min(1100,180+34*_bgantt['Work Order'].nunique())))
                            _show_plotly(_gb,'Backorder_complete_process_Gantt')
                            st.dataframe(_bgantt[['Work Order','Customer','Product Category','Process','Status','Actual pcs','Order pcs','Expected Finish','Due Date']],use_container_width=True,hide_index=True,height=420)
                    st.dataframe(bo,use_container_width=True,height=260)
                if not mg2.empty:
                    st.markdown('### 📊 MPS DEMAND CONSTRUCTION + CAPACITY')
                    fig=go.Figure();fig.add_bar(x=mg2['Month'],y=mg2['Forecast Pcs'],name='Forecast pcs');fig.add_bar(x=mg2['Month'],y=mg2['Firm Future Pcs'],name='Future firm pcs');fig.add_bar(x=mg2['Month'],y=mg2['Backorder Recovery Pcs'],name='Backorder recovery pcs');fig.add_scatter(x=mg2['Month'],y=mg2['MPS Pcs'],name='Final MPS pcs',mode='lines+markers');fig.update_layout(barmode='group',title='MPS = forecast / firm demand + explicit backorder recovery',yaxis_title='pcs');_show_plotly(fig,'MPS_demand_construction')
                    fig=go.Figure();fig.add_bar(x=mg2['Month'],y=mg2['MPS t'],name='MPS ton');fig.add_scatter(x=mg2['Month'],y=mg2['Mixing Capacity t'],name='Mixing capacity ton',mode='lines+markers');fig.update_layout(title='MPS ton vs Mixing capacity',yaxis_title='ton');_show_plotly(fig,'MPS_vs_Mixing_capacity')
                    fig=go.Figure();fig.add_bar(x=mg2['Month'],y=mg2['Required Forming hr'],name='Required forming hr');fig.add_scatter(x=mg2['Month'],y=mg2['Available Forming hr'],name='Available forming hr',mode='lines+markers');fig.update_layout(title='MPS forming hours vs shared machine-hour capacity',yaxis_title='hours');_show_plotly(fig,'MPS_vs_Forming_capacity')
                    fig=go.Figure();fig.add_bar(x=mg2['Month'],y=mg2['Mixing Load %'],name='Mixing load %');fig.add_bar(x=mg2['Month'],y=mg2['Forming Load %'],name='Forming load %');fig.add_hline(y=100,line_dash='dash',annotation_text='100% normal capacity');fig.update_layout(barmode='group',title='Monthly capacity load %',yaxis_title='%');_show_plotly(fig,'Monthly_capacity_load_percent')
                if not cc.empty:
                    st.markdown('### 🧩 CAPACITY LOAD BY PRODUCT CATEGORY')
                    fig=px.bar(cc,x='Month',y='Required Forming hr',color='Group',barmode='group',hover_data=['MPS Pcs','MPS t','Rate pcs/hr','Shared Available Forming hr/month','Category Share of Forming Capacity %'],title='Required forming hours by category');_show_plotly(fig,'Capacity_load_by_category');st.dataframe(cc,use_container_width=True,height=260)
                if not cs.empty:
                    st.markdown('### 📏 CAPACITY LOAD BY PRODUCT CATEGORY + SIZE')
                    cats=sorted([str(x) for x in cs['Group'].dropna().unique()]);sc=st.selectbox('Select category for size-capacity analysis',options=['ALL']+cats,key='capacity_size_category');sv=cs if sc=='ALL' else cs[cs['Group'].astype(str).eq(sc)]
                    fig=px.bar(sv,x='Month',y='Required Forming hr',color='Size Range',barmode='group',hover_data=['Group','MPS Pcs','MPS t','Rate pcs/hr','Size Share of Forming Capacity %'],title='Required forming hours by size');_show_plotly(fig,'Capacity_load_by_size');st.dataframe(sv,use_container_width=True,height=280)
                    st.caption('Shared machines are not double-counted as separate dedicated size capacities. The graph shows each category/size required load against the common forming machine-hour pool.')
                if not pur.empty:
                    st.markdown('### 🛒 MRP PURCHASE TIMING — WHAT / WHEN / HOW MUCH')
                    show=[c for c in ['Material','Supplier','Need Month','Material Need Date','Required Receipt Date','Recommended PO Date','Lead Time days','Gross Requirement t','Beginning Stock t','Safety Stock t','Recommended Order Qty t','Action','Data Warning'] if c in pur.columns];st.dataframe(pur[show],use_container_width=True,height=320)
                    pm=pur.groupby('Material',as_index=False)['Recommended Order Qty t'].sum().sort_values('Recommended Order Qty t',ascending=False);fig=px.bar(pm,x='Material',y='Recommended Order Qty t',title='Recommended purchase quantity by material');_show_plotly(fig,'MRP_purchase_by_material')
                if not rr.empty:
                    st.markdown('### ⚠️ Long-term Risk Register');st.dataframe(rr,use_container_width=True,height=280)
                try:
                    longxls=lm.export_excel(model,lr['sales_base'],lr['master'],lr['bom'],lr['stock'],lr['policy'],lr['meta']);st.download_button('⬇️ DOWNLOAD COMPLETE LONG-TERM MPS/MRP/BACKORDER EXCEL',longxls,file_name='SL_PPC_LONG_TERM_MPS_MRP_V1_8_1.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
                except Exception as ex: st.warning(f'Long-term Excel export diagnostic: {ex}')
    if _nav_idx==10:
        st.subheader('⚠️ HOLD / ISSUE MANAGER — by unique Work Order')
        im=eng.issue_management(issues)
        if im.empty:st.success('No current planning issues.')
        else:
            c1,c2,c3=st.columns(3);c1.metric('Unique WOs affected',im['Work Order'].astype(str).nunique());c2.metric('Raw issue rows',len(issues));c3.metric('Affected qty',f"{im['Affected Qty'].sum():,.0f} pcs")
            st.dataframe(im,use_container_width=True,height=360)
            bad=set(im['Work Order'].astype(str));master=res.get('master',pd.DataFrame()).copy();ed=master[master['Work Order'].astype(str).isin(bad)].copy() if not master.empty else pd.DataFrame()
            if 'Forced Forming Machine' not in ed.columns:ed['Forced Forming Machine']=''
            if 'Forced Forming Capacity pcs/day' not in ed.columns:ed['Forced Forming Capacity pcs/day']=None
            if 'Lead Time Profile' not in ed.columns:ed['Lead Time Profile']=''
            keep=[c for c in ['Work Order','Customer','Category','Specification','Product Code','Shape','D','T','H','Net Weight g/pc','Gross Weight g/pc','Forced Forming Machine','Forced Forming Capacity pcs/day','Lead Time Profile','Post-Firing Route','QC Required','NCR Qty','NCR Stage','NCR Disposition'] if c in ed.columns]
            if keep:
                corrected=_persistent_data_editor(ed[keep].drop_duplicates(subset=['Work Order'],keep='first'),use_container_width=True,height=360,disabled=['Work Order','Customer'] if 'Customer' in keep else ['Work Order'],key='hold_fix_editor')
                if st.button('💾 SAVE ISSUE CORRECTIONS',use_container_width=True):
                    base=st.session_state.plan_overrides.copy() if isinstance(st.session_state.plan_overrides,pd.DataFrame) else pd.DataFrame()
                    for _,r0 in corrected.iterrows():base=_merge_override_row(base,r0.to_dict())
                    st.session_state.plan_overrides=base;st.success('Saved. Click CREATE DAILY PLAN to recalculate.')
            st.markdown('**Raw evidence**');st.dataframe(issues,use_container_width=True,height=300)
    if _nav_idx==11:
        st.subheader('🔎 Evidence + export')
        wm=res.get('master',pd.DataFrame())
        if not wm.empty:
            nw=pd.to_numeric(wm.get('Net Weight g/pc',0),errors='coerce');gw=pd.to_numeric(wm.get('Gross Weight g/pc',0),errors='coerce');c1,c2,c3=st.columns(3);c1.metric('WO rows',len(wm));c2.metric('Net weight available',f'{int((nw>0).sum()):,} / {len(wm):,}');c3.metric('Gross weight available',f'{int((gw>0).sum()):,} / {len(wm):,}')
        st.dataframe(res.get('capacity_evidence',pd.DataFrame()),use_container_width=True)
        st.markdown('#### Controlled manpower from Capacity Database')
        st.dataframe(pd.DataFrame([{'Department':k,'Current People':v} for k,v in CAP_MANPOWER.items()]),use_container_width=True,hide_index=True)
        st.markdown('#### Lead Time master from attached Capacity Database')
        st.dataframe(res.get('lead_time_master',pd.DataFrame()),use_container_width=True,height=340)
        st.markdown('### ⏱️ Lead Time Control / เวลานำที่ใช้ในการวางแผน')
        st.caption('Source = Delivery Control Process image supplied 9-Sep-2026. If Capacity Database firing days are higher, the Firing Planner/Capacity Database remains authoritative for kiln running days. The selected AUTO profile for every WO is exported for cross-check.')
        st.dataframe(res.get('lead_time_master',lt.master_table()),use_container_width=True,height=300)
        st.markdown('**WO Lead Time Applied / Lead time ที่ใช้ราย Work Order**');st.dataframe(res.get('lead_time_applied',pd.DataFrame()),use_container_width=True,height=300)
        out=io.BytesIO()
        with pd.ExcelWriter(out,engine='xlsxwriter') as w:
            allp.to_excel(w,index=False,sheet_name='Daily Plan');caps.to_excel(w,index=False,sheet_name='Capacity vs Plan');_wip_long(wip).to_excel(w,index=False,sheet_name='WIP Stage Category');wip.to_excel(w,index=False,sheet_name='WIP Snapshot');risk.to_excel(w,index=False,sheet_name='Delivery Risk');risk[[c for c in ['Work Order','Customer','Category','Due Date','Suggested Safe Due Date','Extension vs Current Due (calendar days)','Sales New Due Date Requested','Requested New Due Date','Sales Due-Date Action','Safe-Date Confidence','Open Qty','Planned Packing Qty','Schedule Coverage %','Packing Completion','Bottleneck Process','Safe Due-Date Basis'] if c in risk.columns]].to_excel(w,index=False,sheet_name='Sales Due Date Request');issues.to_excel(w,index=False,sheet_name='Issues');res.get('stock',pd.DataFrame()).to_excel(w,index=False,sheet_name='Stock Used');res.get('bom',pd.DataFrame()).to_excel(w,index=False,sheet_name='BOM Used');res.get('lead_time_master',lt.master_table()).to_excel(w,index=False,sheet_name='Lead Time Master');res.get('lead_time_applied',pd.DataFrame()).to_excel(w,index=False,sheet_name='WO Lead Time Applied');res.get('ab_pair_audit',pd.DataFrame()).to_excel(w,index=False,sheet_name='AB Pair Synchronization');res.get('ot_suggestion',pd.DataFrame()).to_excel(w,index=False,sheet_name='OT Suggestion')
            # Snapshot Plan-vs-Actual and back-order evidence; closed rows are retained.
            _m=res.get('master',pd.DataFrame()).copy();_pa=[]
            if not _m.empty:
                for _sec in ['Preparation','Mixing','Forming','Firing','Grinding','Packing']:
                    _pc=f'{_sec} Plan';_ac=f'{_sec} Actual'
                    if _pc in _m.columns and _ac in _m.columns:
                        _g=_m.groupby(_m['Category'].apply(eng.normcat),as_index=False)[[_pc,_ac]].sum();_g.insert(0,'Section',_sec);_g=_g.rename(columns={'Category':'Product Category',_pc:'Plan Qty',_ac:'Actual Qty'});_pa.append(_g)
                if _pa:pd.concat(_pa,ignore_index=True).to_excel(w,index=False,sheet_name='Plan vs Actual Snapshot')
                _b=_m.copy();_b['Due Date']=pd.to_datetime(_b.get('Due Date'),errors='coerce');_b['Open Qty']=pd.to_numeric(_b.get('Open Qty',0),errors='coerce').fillna(0);_today_bkk=pd.Timestamp(datetime.datetime.now(ZoneInfo('Asia/Bangkok')).date());_b=_b[(_b['Due Date']<_today_bkk)&(_b['Open Qty']>0)]
                if not _b.empty:_b.to_excel(w,index=False,sheet_name='Back Order Detail')
            if isinstance(st.session_state.plan_overrides,pd.DataFrame) and not st.session_state.plan_overrides.empty:st.session_state.plan_overrides.to_excel(w,index=False,sheet_name='WO Route NCR Overrides')
            if isinstance(_ds_cache_valid,pd.DataFrame) and not _ds_cache_valid.empty:
                _dsex=_crosscheck_ppc_production_actual(_ds_cache_valid,allp,res.get('master',pd.DataFrame()));_dsex.to_excel(w,index=False,sheet_name='Daily Status Analysis')
            if not _masterx.empty:
                _masterx[_masterx['Order Class'].str.startswith('MAKE TO STOCK')].to_excel(w,index=False,sheet_name='Make To Stock')
                _masterx[_masterx['Test Work'].eq('YES')].to_excel(w,index=False,sheet_name='Test Work')
            for sec,d0 in res['plans'].items():
                if d0 is not None and not d0.empty:d0.to_excel(w,index=False,sheet_name=sec.replace('/','-')[:31])
        _daily_plan_export_bytes=out.getvalue()
        st.download_button('⬇️ DOWNLOAD DAILY PLAN EXCEL',_daily_plan_export_bytes,file_name='SL_PPC_DAILY_OUTPUT_V1_9_24.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='evidence_daily_plan_download')

    if _nav_idx==12:
        st.subheader('🔭 DEMAND–CAPACITY–RISK VISIBILITY — WEEK / MONTH / CUSTOM PERIOD')
        st.caption('Management visibility for weekly/monthly/management review: compare demand by product group and department with capacity and delivery dates, identify bottlenecks, backorder recovery and mitigation. Detailed Gantt uses the same product-category colors as the summary.')

        _wm=res.get('master',pd.DataFrame()).copy()
        _wp=allp.copy()
        if _wm.empty or _wp.empty:
            st.warning('Create the daily plan first. Weekly report requires the current Plan 2026 master and calculated complete plan.')
        else:
            _dates=pd.to_datetime(_wp.get('Plan Date'),errors='coerce')
            _min_d=_dates.min().date() if _dates.notna().any() else pd.Timestamp(start).date()
            _max_d=_dates.max().date() if _dates.notna().any() else (pd.Timestamp(start)+pd.Timedelta(days=28)).date()
            _default_to=min(_max_d,_min_d+pd.Timedelta(days=27))
            _c1,_c2=st.columns(2)
            _from=_c1.date_input('Visibility — FROM started/planned date',value=_min_d,min_value=_min_d,max_value=_max_d,key='weekly_from')
            _to=_c2.date_input('Visibility — TO started/planned date',value=_default_to,min_value=_min_d,max_value=_max_d,key='weekly_to')
            if _to<_from:
                st.error('TO date must be on or after FROM date.')
            else:
                _wp['_D']=pd.to_datetime(_wp.get('Plan Date'),errors='coerce').dt.date
                _wr=_wp[(_wp['_D']>=_from)&(_wp['_D']<=_to)].copy()
                _wr['Category']=_wr.get('Category','').astype(str).str.upper().replace({'':'UNKNOWN'})
                _wr['Plan Qty']=pd.to_numeric(_wr.get('Plan Qty',0),errors='coerce').fillna(0)
                _wr['Plan ton']=pd.to_numeric(_wr.get('Plan ton',0),errors='coerce').fillna(0)

                # Fixed category color map used by BOTH summary and Gantt.
                _cat_order=['P','R','S','T','PB','M','UNKNOWN']
                _palette=['#4C78A8','#F58518','#54A24B','#E45756','#72B7B2','#B279A2','#9D9D9D']
                _cat_colors={c:_palette[i] for i,c in enumerate(_cat_order)}
                for _c in sorted(set(_wr['Category'])-_cat_colors.keys()):
                    _cat_colors[_c]='#9D9D9D'

                st.markdown('### 1. Product-group demand / capacity / delivery-risk summary')
                _sum_rows=[]
                _wm2=_wm.copy()
                _wm2['Category']=_wm2.get('Category','').astype(str).str.upper().replace({'':'UNKNOWN'})
                _wm2['_WODate']=pd.to_datetime(_wm2.get('WO Date',pd.NaT),errors='coerce')
                _wm2['_Due']=pd.to_datetime(_wm2.get('Due Date',pd.NaT),errors='coerce')
                _wm2['_Order']=pd.to_numeric(_wm2.get('Order Qty',0),errors='coerce').fillna(0)
                _wm2['_Pack']=pd.to_numeric(_wm2.get('Packing Actual Qty',_wm2.get('Packing Actual',0)),errors='coerce').fillna(0)
                _wm2['_Remain']=(_wm2['_Order']-_wm2['_Pack']).clip(lower=0)
                _wm2['_Closed']=_wm2.get('Overall Closed',pd.Series(False,index=_wm2.index)).fillna(False).astype(bool)
                _incoming=_wm2[(~_wm2['_Closed']) & (_wm2['_WODate'].dt.date>=_from) & (_wm2['_WODate'].dt.date<=_to)].copy()
                _open_due=_wm2[(~_wm2['_Closed']) & (_wm2['_Due'].dt.date<=_to)].copy()

                # Department capacity is taken from calculated capacity rows in the selected window.
                _capw=caps.copy()
                if not _capw.empty:
                    _capw['_D']=pd.to_datetime(_capw.get('Plan Date'),errors='coerce').dt.date
                    _capw=_capw[(_capw['_D']>=_from)&(_capw['_D']<=_to)].copy()

                _riskmap={}
                if not risk.empty and 'Work Order' in risk.columns:
                    _riskmap=risk.drop_duplicates('Work Order').set_index(risk['Work Order'].astype(str))['Delivery Risk'].astype(str).to_dict()

                for _cat in sorted(set(_wr['Category']).union(set(_incoming['Category']))):
                    _cg=_wr[_wr['Category'].eq(_cat)]
                    _inc=_incoming[_incoming['Category'].eq(_cat)]
                    _od=_open_due[_open_due['Category'].eq(_cat)]
                    _wo_list=set(_cg.get('Work Order',pd.Series(dtype=str)).astype(str))
                    _high=sum(1 for w in _wo_list if str(_riskmap.get(w,'')).upper()=='HIGH')
                    _med=sum(1 for w in _wo_list if str(_riskmap.get(w,'')).upper() in {'MEDIUM','YELLOW'})

                    # Process load ratio from calculated plan vs calculated available capacity.
                    _proc_stats=[]
                    for _sec,_sg in _cg.groupby('Section'):
                        _plan=float(pd.to_numeric(_sg.get('Plan ton',0),errors='coerce').fillna(0).sum())
                        if _plan<=0:
                            _plan=float(pd.to_numeric(_sg.get('Plan Qty',0),errors='coerce').fillna(0).sum())
                        _cap=0.0
                        if not _capw.empty and 'Section' in _capw.columns:
                            _cc=_capw[_capw['Section'].astype(str).eq(str(_sec))]
                            for _cn in ['Capacity ton','Capacity t','Capacity pcs','Capacity']:
                                if _cn in _cc.columns:
                                    _cap=float(pd.to_numeric(_cc[_cn],errors='coerce').fillna(0).sum())
                                    if _cap>0: break
                        _load=(_plan/_cap*100) if _cap>0 else None
                        _proc_stats.append((str(_sec),_plan,_cap,_load))
                    _valid=[x for x in _proc_stats if x[3] is not None]
                    _b=max(_valid,key=lambda x:x[3]) if _valid else ('Not resolved',0,0,None)
                    _loadpct=_b[3]
                    if _loadpct is None:
                        _risk_level='CHECK'
                        _mit='Capacity unit/source not directly comparable — review department capacity evidence.'
                    elif _loadpct>100:
                        _risk_level='HIGH'
                        _mit=f'Bottleneck {_b[0]} at {_loadpct:.0f}% load: prioritize earliest due WOs; use approved OT/rebalance/alternate resource where feasible; review delivery date only after recovery options.'
                    elif _loadpct>=90:
                        _risk_level='WATCH'
                        _mit=f'{_b[0]} near capacity at {_loadpct:.0f}%: protect due-date sequence and prepare OT/rebalance if slippage occurs.'
                    else:
                        _risk_level='OK' if _high==0 else 'DELIVERY RISK'
                        _mit='Capacity is feasible: issue the required daily quantities as production commitments, protect due-date sequence, and use remaining capacity to pull the next-earliest executable work.' if _high==0 else 'Capacity may be feasible overall, but HIGH-risk WOs require order-level recovery follow-up.'
                    _sum_rows.append({
                        'Product Group':_cat,
                        'Incoming WOs':_inc['Work Order'].astype(str).nunique() if not _inc.empty else 0,
                        'Incoming Qty pcs':float(_inc['_Remain'].sum()) if not _inc.empty else 0,
                        'Open Due WOs':_od['Work Order'].astype(str).nunique() if not _od.empty else 0,
                        'Open Due Qty pcs':float(_od['_Remain'].sum()) if not _od.empty else 0,
                        'Planned WOs in Window':len(_wo_list),
                        'Planned Qty pcs':float(_cg['Plan Qty'].sum()),
                        'Planned ton':float(_cg['Plan ton'].sum()),
                        'Bottleneck Department':_b[0],
                        'Bottleneck Load %':round(_loadpct,1) if _loadpct is not None else None,
                        'HIGH Delivery Risk WOs':_high,
                        'WATCH WOs':_med,
                        'Management Status':_risk_level,
                        'Production Mitigation Plan':_mit
                    })
                _summary=pd.DataFrame(_sum_rows)
                if not _summary.empty:
                    st.dataframe(_summary,use_container_width=True,hide_index=True,height=320)
                    # MD view: process on horizontal axis; product category remains the color dimension.
                    _chart=_wr.groupby(['Section','Category'],as_index=False)['Plan Qty'].sum().rename(columns={'Section':'Process','Category':'Product Group','Plan Qty':'Planned Qty pcs'})
                    figsum=px.bar(_chart,x='Process',y='Planned Qty pcs',color='Product Group',barmode='stack',
                                  color_discrete_map=_cat_colors,text_auto='.3s',
                                  title=f'Product-group demand by process — {_from} to {_to}')
                    _tot=_chart.groupby('Process',as_index=False)['Planned Qty pcs'].sum()
                    figsum.add_scatter(x=_tot['Process'],y=_tot['Planned Qty pcs'],mode='text',
                                       text=[f'{v:,.0f}' for v in _tot['Planned Qty pcs']],
                                       textposition='top center',showlegend=False,hoverinfo='skip')
                    figsum.update_layout(showlegend=True,xaxis_title='PROCESS / DEPARTMENT',yaxis_title='DEMAND PCS')
                    _show_plotly(figsum,'Weekly_product_group_summary')

                st.markdown('### 2. Department demand vs capacity / bottleneck')
                _dept=[]
                for _sec,_sg in _wr.groupby('Section'):
                    _pq=float(pd.to_numeric(_sg.get('Plan Qty',0),errors='coerce').fillna(0).sum())
                    _pt=float(pd.to_numeric(_sg.get('Plan ton',0),errors='coerce').fillna(0).sum())
                    _cap_qty=_cap_ton=0.0
                    if not _capw.empty and 'Section' in _capw.columns:
                        _cc=_capw[_capw['Section'].astype(str).eq(str(_sec))]
                        if 'Capacity pcs' in _cc.columns:_cap_qty=float(pd.to_numeric(_cc['Capacity pcs'],errors='coerce').fillna(0).sum())
                        for _cn in ['Capacity ton','Capacity t']:
                            if _cn in _cc.columns:_cap_ton=float(pd.to_numeric(_cc[_cn],errors='coerce').fillna(0).sum());break
                    if _cap_ton>0 and _pt>0:
                        _util=_pt/_cap_ton*100;_basis='ton'
                    elif _cap_qty>0:
                        _util=_pq/_cap_qty*100;_basis='pcs'
                    else:
                        _util=None;_basis='capacity source not directly comparable'
                    _dept.append({'Department':_sec,'Demand pcs':_pq,'Demand ton':_pt,
                                  'Available Capacity pcs':_cap_qty,'Available Capacity ton':_cap_ton,
                                  'Load %':round(_util,1) if _util is not None else None,'Comparison Basis':_basis,
                                  'Status':('BOTTLENECK' if _util is not None and _util>100 else ('WATCH' if _util is not None and _util>=90 else ('OK' if _util is not None else 'CHECK')))})
                _deptdf=pd.DataFrame(_dept).sort_values('Load %',ascending=False,na_position='last') if _dept else pd.DataFrame()
                st.dataframe(_deptdf,use_container_width=True,hide_index=True,height=300)
                if not _deptdf.empty:
                    _dc=_deptdf.copy()
                    _dc['Demand']=np.where(_dc['Comparison Basis'].eq('ton'),_dc['Demand ton'],_dc['Demand pcs'])
                    _dc['Capacity']=np.where(_dc['Comparison Basis'].eq('ton'),_dc['Available Capacity ton'],_dc['Available Capacity pcs'])
                    _dcl=_dc.melt(id_vars=['Department','Comparison Basis'],value_vars=['Demand','Capacity'],var_name='Measure',value_name='Value')
                    _fdc=px.bar(_dcl,x='Department',y='Value',color='Measure',barmode='group',text='Value',title='DEMAND vs AVAILABLE CAPACITY — SAME GRAPH')
                    _fdc.update_traces(texttemplate='%{text:,.1f}',textposition='outside')
                    _show_plotly(_fdc,'Demand_vs_Capacity_Same_Graph')

                st.markdown('### 3. BOTTLENECK → AT-RISK ORDERS / คอขวด → งานที่เสี่ยง')
                _br=[]
                _rbase=risk.copy() if isinstance(risk,pd.DataFrame) else pd.DataFrame()
                if not _rbase.empty:
                    for _,_rr in _rbase.iterrows():
                        _wo=str(_rr.get('Work Order','')); _bp=str(_rr.get('Bottleneck Process','')).strip()
                        if not _wo or not _bp: continue
                        _pw=_wp[_wp.get('Work Order',pd.Series(dtype=str)).astype(str).eq(_wo)]
                        _qty=float(pd.to_numeric(_rr.get('Open Qty',_rr.get('Remaining Qty',0)),errors='coerce') or 0)
                        _br.append({'Bottleneck Process':_bp,'Work Order':_wo,'Customer':_rr.get('Customer',''),'Product Category':_rr.get('Category',''),'At Risk Qty pcs':_qty,'Due Date':_rr.get('Due Date'),'Due Month':pd.to_datetime(_rr.get('Due Date'),errors='coerce').strftime('%Y-%m') if pd.notna(pd.to_datetime(_rr.get('Due Date'),errors='coerce')) else '', 'Projected Finish':_rr.get('Projected Finish'),'Delivery Risk':_rr.get('Delivery Risk',''),'Current Status':_rr.get('Current Status / WIP',''),'Complete Plan': ' → '.join(_pw.sort_values('Plan Date')['Section'].astype(str).drop_duplicates().tolist()) if not _pw.empty else '', 'Next Required Process':str(_pw.sort_values('Plan Date')['Section'].iloc[0]) if not _pw.empty else _bp, 'Next Required Date':pd.to_datetime(_pw.sort_values('Plan Date')['Plan Date'].iloc[0],errors='coerce') if not _pw.empty else pd.NaT, 'Required Production pcs':float(pd.to_numeric(_pw.get('Plan Qty',0),errors='coerce').fillna(0).sum()) if not _pw.empty else _qty, 'Positive Recovery Signal':f'PRODUCE {_qty:,.0f} pcs / protect WO {_wo} at {_bp}; follow complete process plan to due date', 'Planning Commitment':'ACHIEVE AS PLANNED if required process load is within available capacity; escalate only the quantified excess/late portion'})
                _brdf=pd.DataFrame(_br)
                if _brdf.empty:
                    st.info('No bottleneck-at-risk order detail resolved for this window.')
                else:
                    st.dataframe(_brdf.sort_values(['Bottleneck Process','Due Date']),use_container_width=True,hide_index=True,height=380)
                    _bg=_brdf.groupby(['Bottleneck Process','Product Category'],as_index=False)['At Risk Qty pcs'].sum()
                    _fb=px.bar(_bg,x='Bottleneck Process',y='At Risk Qty pcs',color='Product Category',barmode='stack',color_discrete_map=_cat_colors,title='AT-RISK QUANTITY BY BOTTLENECK PROCESS')
                    _bt=_bg.groupby('Bottleneck Process',as_index=False)['At Risk Qty pcs'].sum()
                    _fb.add_scatter(x=_bt['Bottleneck Process'],y=_bt['At Risk Qty pcs'],mode='text',text=[f'{v:,.0f}' for v in _bt['At Risk Qty pcs']],textposition='top center',showlegend=False,hoverinfo='skip')
                    _show_plotly(_fb,'Bottleneck_at_risk_orders')
                    # ALL constrained processes Pareto: a WO may face more than one process constraint.
                    _pcap=caps.copy() if isinstance(caps,pd.DataFrame) else pd.DataFrame()
                    if not _pcap.empty:
                        _pcap['Load %']=pd.to_numeric(_pcap.get('Utilization %',0),errors='coerce').fillna(0)
                        _pcap['Plan pcs']=pd.to_numeric(_pcap.get('Plan pcs',0),errors='coerce').fillna(0)
                        _par=_pcap.groupby('Section',as_index=False).agg(**{'Risk / Load pcs':('Plan pcs','sum'),'Peak Load %':('Load %','max')})
                        _par=_par[(_par['Risk / Load pcs']>0)|(_par['Peak Load %']>=90)].sort_values(['Risk / Load pcs','Peak Load %'],ascending=[False,False]).reset_index(drop=True)
                        if not _par.empty:
                            _par['Pareto Basis']=np.where(_par['Peak Load %']>100,'OVER CAPACITY',np.where(_par['Peak Load %']>=90,'NEAR CAPACITY','ACTIVE LOAD'))
                            _par['Cumulative %']=_par['Risk / Load pcs'].cumsum()/max(_par['Risk / Load pcs'].sum(),1)*100
                            _fp=go.Figure();_fp.add_bar(x=_par['Section'],y=_par['Risk / Load pcs'],name='Affected / planned pcs');_fp.add_scatter(x=_par['Section'],y=_par['Cumulative %'],name='Cumulative %',mode='lines+markers',yaxis='y2')
                            _fp.update_layout(title='ALL BOTTLENECK / CONSTRAINED PROCESSES — PARETO',yaxis_title='pcs',yaxis2=dict(title='Cumulative %',overlaying='y',side='right',range=[0,105]))
                            _show_plotly(_fp,'All_bottleneck_process_pareto')
                            st.dataframe(_par,use_container_width=True,hide_index=True)
                    _bm=_brdf.groupby(['Due Month','Bottleneck Process','Product Category'],as_index=False)['At Risk Qty pcs'].sum()
                    if not _bm.empty:
                        _fm=px.bar(_bm,x='Due Month',y='At Risk Qty pcs',color='Product Category',facet_row='Bottleneck Process',barmode='stack',color_discrete_map=_cat_colors,title='AT-RISK QTY BY DUE MONTH × PROCESS × PRODUCT CATEGORY')
                        _fm.update_layout(height=max(650,220*_bm['Bottleneck Process'].nunique()))
                        _show_plotly(_fm,'Bottleneck_due_month_process_category')

                _rpm=_process_risk_matrix(res.get('master',pd.DataFrame()),risk)
                if not _rpm.empty:
                    st.markdown('### ⚠️ RISK QUANTITY — ALL PRODUCT CATEGORIES × ALL PROCESSES')
                    _frp=px.bar(_rpm,x='Process',y='Risk Qty pcs',color='Product Category',barmode='stack',category_orders={'Product Category':['P','R','S','T','M','PB']},title='RISK / REMAINING QUANTITY BY PROCESS — P, R, S, T, M, PB')
                    _show_plotly(_frp,'Risk_all_categories_all_processes')
                st.markdown('### 4. Detailed order-by-order COMPLETE PLAN Gantt')
                st.caption('Included WOs = WOs with calculated work starting/planned inside the selected FROM–TO window. The complete calculated route for each selected WO is then shown, even when later process dates extend beyond TO.')
                _started=set(_wr.get('Work Order',pd.Series(dtype=str)).astype(str))
                _g=_wp[_wp.get('Work Order',pd.Series(dtype=str)).astype(str).isin(_started)].copy()
                if _g.empty:
                    st.info('No planned WOs start in the selected date range.')
                else:
                    _g['_PD']=pd.to_datetime(_g.get('Plan Date'),errors='coerce')
                    _g['Category']=_g.get('Category','').astype(str).str.upper().replace({'':'UNKNOWN'})
                    _grow=[]
                    for (_wo,_sec,_cat),_sg in _g.dropna(subset=['_PD']).groupby(['Work Order','Section','Category'],dropna=False):
                        _ds=_sg['_PD'].dropna()
                        if _ds.empty: continue
                        _grow.append({'Work Order':str(_wo),'Process':str(_sec),'Product Group':str(_cat),
                                      'Start':_ds.min(),'Finish':_ds.max()+pd.Timedelta(days=1),
                                      'Plan Qty pcs':float(pd.to_numeric(_sg.get('Plan Qty',0),errors='coerce').fillna(0).sum()),
                                      'Customer':str(_sg.get('Customer',pd.Series([''])).iloc[0]) if 'Customer' in _sg.columns else '',
                                      'Due Date':pd.to_datetime(_sg.get('Due Date',pd.Series([pd.NaT])).iloc[0],errors='coerce') if 'Due Date' in _sg.columns else pd.NaT})
                    _gantt=pd.DataFrame(_grow)
                    if not _gantt.empty:
                        _gantt['WO / Process']=_gantt['Work Order']+' | '+_gantt['Process']
                        fg=px.timeline(_gantt,x_start='Start',x_end='Finish',y='WO / Process',color='Product Group',
                                       color_discrete_map=_cat_colors,
                                       hover_name='Work Order',
                                       hover_data={'Process':True,'Product Group':True,'Customer':True,'Due Date':True,
                                                   'Start':True,'Finish':True,'Plan Qty pcs':':,.0f'},
                                       title=f'Order-by-order complete production plan — WOs starting {_from} to {_to}')
                        fg.update_traces(text=[],texttemplate='',textposition='none')
                        fg.update_yaxes(autorange='reversed')
                        fg.update_layout(height=max(650,min(1800,32*len(_gantt)+180)))
                        _show_plotly(fg,'Weekly_complete_order_Gantt')
                        st.dataframe(_gantt[['Work Order','Customer','Product Group','Process','Start','Finish','Due Date','Plan Qty pcs']],
                                     use_container_width=True,hide_index=True,height=420)

                st.markdown('### 5. Order-level delivery risk and mitigation')
                _rshow=risk[risk.get('Work Order',pd.Series(dtype=str)).astype(str).isin(_started)].copy() if not risk.empty else pd.DataFrame()
                if not _rshow.empty:
                    _cols=[c for c in ['Work Order','Customer','Category','Due Date','Projected Finish','Packing Completion',
                                       'Delivery Risk','Bottleneck Process','Suggested Safe Due Date','Sales New Due Date Requested'] if c in _rshow.columns]
                    st.dataframe(_rshow[_cols],use_container_width=True,hide_index=True,height=320)

                # Cross-functional recovery actions are built from the master and risk data without changing due dates.
                from suite.recovery_actions import build_recovery_actions
                _asof_recovery=datetime.datetime.now(ZoneInfo('Asia/Bangkok')).date()
                _recovery_actions=build_recovery_actions(_rm,risk,_asof_recovery)
                # Weekly Excel pack: summary + department + complete plan + risk + Sales/Production recovery confirmations.
                _bout=io.BytesIO()
                with pd.ExcelWriter(_bout,engine='xlsxwriter') as _w:
                    if not _summary.empty:_summary.to_excel(_w,index=False,sheet_name='Weekly Summary')
                    if not _deptdf.empty:_deptdf.to_excel(_w,index=False,sheet_name='Dept Capacity')
                    if '_brdf' in locals() and isinstance(_brdf,pd.DataFrame) and not _brdf.empty:_brdf.to_excel(_w,index=False,sheet_name='Bottleneck Risk Orders')
                    if '_gantt' in locals() and isinstance(_gantt,pd.DataFrame) and not _gantt.empty:_gantt.to_excel(_w,index=False,sheet_name='WO Complete Gantt')
                    if not _rshow.empty:_rshow.to_excel(_w,index=False,sheet_name='Delivery Risk')
                    if not _recovery_actions.empty:
                        _recovery_actions.to_excel(_w,index=False,sheet_name='Recovery Actions')
                        _wa=_w.sheets['Recovery Actions']; _wa.freeze_panes(1,0); _wa.autofilter(0,0,len(_recovery_actions),len(_recovery_actions.columns)-1)
                        _wa.set_row(0,34); _wa.set_column(0,len(_recovery_actions.columns)-1,22)
                        _w.sheets['Recovery Actions'].write_comment(0,0,'System-generated draft from current Plan-2026 and delivery-risk calculations. Sales and Production must confirm priority, capacity, and date. Do not change a customer commitment without Sales/customer approval.')
                    else:
                        pd.DataFrame([{'Status':'No open order met the current overdue / due-within-3-days / high-risk / missing-date filter. Verify source coverage before concluding there is no recovery work.'}]).to_excel(_w,index=False,sheet_name='Recovery Actions')
                    _plan_source=Path(str(st.session_state.get('plan_path') or ''))
                    _src_info=[{'Item':'Generated at (Thailand local time — Phan Thong, Chonburi)','Value':datetime.datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds')},
                               {'Item':'Active Plan-2026 source','Value':str(_plan_source.resolve()) if _plan_source.exists() else 'Not available in session state'},
                               {'Item':'Plan-2026 SHA-256','Value':hashlib.sha256(_plan_source.read_bytes()).hexdigest() if _plan_source.is_file() else 'Not available'},
                               {'Item':'As-of date for urgent filter','Value':_asof_recovery.isoformat()},
                               {'Item':'Recovery filter','Value':'OPEN only; due date missing, due within 3 days, overdue, or delivery risk HIGH/LATE/OVERDUE/AT RISK'},
                               {'Item':'Approval rule','Value':'No customer due-date change is made by this export; Sales/Production confirmation is required.'},
                               {'Item':'Workbook rule','Value':'Other source workbooks and live records are not edited by this report.'}]
                    pd.DataFrame(_src_info).to_excel(_w,index=False,sheet_name='Recovery Traceability')
                    _wr.drop(columns=['_D'],errors='ignore').to_excel(_w,index=False,sheet_name='Window Plan Detail')
                if not _recovery_actions.empty:
                    st.caption(f"Recovery Actions sheet contains {_recovery_actions['Work Order'].astype(str).nunique()} open urgent/high-risk WOs. It is a draft for Sales and Production confirmation; customer dates are not changed by this export.")
                st.download_button('⬇️ DOWNLOAD WEEKLY + RECOVERY ACTION PACK — EXCEL',_bout.getvalue(),
                                   file_name=f'SL_PPC_DEMAND_CAPACITY_RISK_{_from}_{_to}.xlsx',
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                   use_container_width=True,key='weekly_report_excel')

    if _nav_idx==16:
        st.subheader('🧪 TEST WORK CONTROL & RISK / ควบคุมและวิเคราะห์งานทดสอบ')
        st.caption('Daily Planner can override TEST/NORMAL by WO without changing the Firing Planner file. Candidate selector shows Product Code starting 1 or 4 only; 1 defaults TEST, 4 defaults NORMAL unless selected.')
        if _masterx.empty:
            st.warning('No Plan2026 master rows are available for Test Work classification.')
        else:
            _cand=_masterx[_masterx['Product Code'].astype(str).str.strip().str[:1].isin(['1','4'])].copy()
            _cand['Due Date']=pd.to_datetime(_cand.get('Due Date'),errors='coerce')
            _valid_due=_cand['Due Date'].dropna()
            _tw_min=_valid_due.min().date() if not _valid_due.empty else start
            _tw_max=_valid_due.max().date() if not _valid_due.empty else (pd.Timestamp(start)+pd.Timedelta(days=90)).date()
            c1,c2=st.columns(2)
            _tw_from=c1.date_input('Test Work due FROM / กำหนดส่งจาก',value=max(_tw_min,start) if _tw_min<=_tw_max else start,key='tw_due_from_v1929')
            _tw_to=c2.date_input('Test Work due TO / กำหนดส่งถึง',value=_tw_max,key='tw_due_to_v1929')
            _cand=_cand[(_cand['Due Date'].dt.date>=_tw_from)&(_cand['Due Date'].dt.date<=_tw_to)].copy()
            _saved=st.session_state.get('test_override_daily',{}) or {}
            _cand['TEST? / งานทดสอบ']=[(_saved.get(str(w).strip(),t)=='YES') for w,t in zip(_cand['Work Order'],_cand['Test Work'])]
            _editcols=[c for c in ['TEST? / งานทดสอบ','Work Order','Product Code','Customer','Category','Due Date','Order Qty'] if c in _cand.columns]
            _ed=_persistent_data_editor(_cand[_editcols],use_container_width=True,hide_index=True,height=min(500,110+34*max(len(_cand),1)),disabled=[c for c in _editcols if c!='TEST? / งานทดสอบ'],column_config={'Due Date':st.column_config.DateColumn('Due Date / กำหนดส่ง',format='DD-MM-YYYY')},key='daily_test_selector_v1930')
            if not _ed.empty:
                for _,_r in _ed.iterrows():
                    _saved[str(_r['Work Order']).strip()]='YES' if bool(_r['TEST? / งานทดสอบ']) else 'NO'
                st.session_state.test_override_daily=_saved
                _masterx['Test Work']=[_saved.get(str(w).strip(),v) for w,v in zip(_masterx['Work Order'],_masterx['Test Work'])]
                _masterx['Work Type']=np.where(_masterx['Test Work'].eq('YES'),'TEST / งานทดสอบ','NORMAL / งานปกติ')
            _tw=_masterx[_masterx['Test Work'].eq('YES')].copy()
            _tw['Due Date']=pd.to_datetime(_tw.get('Due Date'),errors='coerce')
            _tw=_tw[(_tw['Due Date'].dt.date>=_tw_from)&(_tw['Due Date'].dt.date<=_tw_to)].copy()
            if _tw.empty:
                st.info('No Test Work in the selected due-date window.')
            else:
                _tw_wo=set(_tw['Work Order'].astype(str))
                _tw_risk=risk[risk['Work Order'].astype(str).isin(_tw_wo)].copy() if isinstance(risk,pd.DataFrame) and not risk.empty else pd.DataFrame()
                if not _tw_risk.empty:
                    _riskcols=[c for c in ['Work Order','Open Qty','Current Status / WIP','Bottleneck Process','Projected Finish','Delivery Risk','Suggested Safe Due Date'] if c in _tw_risk.columns]
                    _tw=_tw.merge(_tw_risk[_riskcols].drop_duplicates('Work Order'),on='Work Order',how='left')
                    _bp=_tw_risk.copy(); _bp['Open Qty']=pd.to_numeric(_bp.get('Open Qty',0),errors='coerce').fillna(0)
                    _bp=_bp.groupby('Bottleneck Process',as_index=False).agg(**{'WO Count':('Work Order','nunique'),'Risk Qty':('Open Qty','sum')}).sort_values(['Risk Qty','WO Count'],ascending=False)
                    if not _bp.empty:
                        _fig=px.bar(_bp,x='Bottleneck Process',y='WO Count',text='WO Count',hover_data={'Risk Qty':':,.0f'},title='TEST WORK — BOTTLENECK WORK ORDERS BY PROCESS / งานทดสอบติดคอขวดตามกระบวนการ')
                        _fig.update_traces(textposition='outside');_show_plotly(_fig,'TestWork_Bottleneck_WO_Count')
                _showcols=[c for c in ['Work Order','Product Code','Customer','Category','Due Date','Order Qty','Open Qty','Current Status / WIP','Bottleneck Process','Projected Finish','Delivery Risk','Suggested Safe Due Date'] if c in _tw.columns]
                st.metric('Test Work WOs shown',_tw['Work Order'].astype(str).nunique())
                with st.expander('📋 OPEN TEST-WORK DETAIL / เปิดรายละเอียดงานทดสอบ',expanded=False):
                    _tw_show=_tw[_showcols].sort_values(['Due Date','Work Order'],na_position='last').copy(); _tw_show['Due Date']=pd.to_datetime(_tw_show['Due Date'],errors='coerce').dt.date
                    st.dataframe(_tw_show,use_container_width=True,hide_index=True,height=480)
                _tb=io.BytesIO()
                with pd.ExcelWriter(_tb,engine='xlsxwriter') as _w:_tw[_showcols].sort_values(['Due Date','Work Order'],na_position='last').to_excel(_w,index=False,sheet_name='Test Work')
                st.download_button('⬇️ DOWNLOAD TEST WORK — EXCEL',_tb.getvalue(),file_name=f'SL_PPC_TEST_WORK_{_tw_from}_{_tw_to}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='download_test_work_excel')

    if _nav_idx==17:
        st.subheader('🗂️ ORDER PORTFOLIO / กลุ่มงาน — TEST • MASS/MTO • MAKE TO STOCK')
        st.caption('Planner control view: every open WO is classified into a planning group and shown categorywise with current bottleneck, delivery risk, controlled-capacity evidence and suggested revised due date. TEST classification has priority over production-number class.')
        if _masterx.empty:
            st.warning('No Plan2026 master rows are available for order classification.')
        else:
            _pf=_masterx.copy()
            _pf['Planning Group']=np.where(_pf['Test Work'].eq('YES'),'TEST WORK / งานทดสอบ',
                np.where(_pf['Order Class'].str.startswith('MAKE TO STOCK'),'MAKE TO STOCK / ผลิตเพื่อสต็อก','MASS / MADE TO ORDER / ผลิตตามคำสั่ง'))
            _pf['Due Date']=pd.to_datetime(_pf.get('Due Date'),errors='coerce')
            _open_col='Open Qty' if 'Open Qty' in _pf.columns else None
            _pfwo=set(_pf['Work Order'].astype(str))
            if isinstance(risk,pd.DataFrame) and not risk.empty:
                _rk=[c for c in ['Work Order','Open Qty','Current Status / WIP','Bottleneck Process','Projected Finish','Delivery Risk','Suggested Safe Due Date','Safe-Date Confidence','Detailed Reason'] if c in risk.columns]
                if _rk: _pf=_pf.merge(risk[_rk].drop_duplicates('Work Order'),on='Work Order',how='left')
            _pf['Suggested Revised Due Date']=pd.to_datetime(_pf.get('Suggested Safe Due Date'),errors='coerce') if 'Suggested Safe Due Date' in _pf.columns else pd.NaT
            # Capacity evidence is attached to each WO through its current bottleneck and planned dates.
            _cap_ev=_capacity_validation(allp,caps) if isinstance(allp,pd.DataFrame) else pd.DataFrame()
            _sec_cap={}
            if not _cap_ev.empty:
                for _sec,_cg in _cap_ev.groupby('Section'):
                    _sec_cap[str(_sec)]={'Max Load %':float(pd.to_numeric(_cg['Load %'],errors='coerce').max()),
                                        'Overload Days':int((pd.to_numeric(_cg['Load %'],errors='coerce')>100.0001).sum()),
                                        'Capacity Basis':', '.join(sorted(set(_cg['Basis'].dropna().astype(str))))}
            _pf['Bottleneck Capacity Max Load %']=_pf.get('Bottleneck Process',pd.Series('',index=_pf.index)).astype(str).map(lambda x:_sec_cap.get(x,{}).get('Max Load %',np.nan))
            _pf['Bottleneck Overload Days']=_pf.get('Bottleneck Process',pd.Series('',index=_pf.index)).astype(str).map(lambda x:_sec_cap.get(x,{}).get('Overload Days',0))
            _pf['Capacity Basis']=_pf.get('Bottleneck Process',pd.Series('',index=_pf.index)).astype(str).map(lambda x:_sec_cap.get(x,{}).get('Capacity Basis','CHECK'))
            _groups=['ALL']+sorted(_pf['Planning Group'].dropna().astype(str).unique().tolist())
            _cats=['ALL']+sorted(_pf.get('Category',pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
            _c1,_c2=st.columns(2)
            _gsel=_c1.selectbox('Planning group / กลุ่มงาน',_groups,key='portfolio_group')
            _csel=_c2.selectbox('Product category / ประเภทสินค้า',_cats,key='portfolio_category')
            _pv=_pf.copy()
            if _gsel!='ALL': _pv=_pv[_pv['Planning Group'].eq(_gsel)]
            if _csel!='ALL': _pv=_pv[_pv['Category'].astype(str).eq(_csel)]
            _pv=_pv.sort_values(['Due Date','Planning Group','Category','Work Order'],na_position='last')
            _pc=[c for c in ['Planning Group','Work Order','Product Code','Customer','Category','Due Date','Order Qty','Open Qty','Current Status / WIP','Bottleneck Process','Bottleneck Capacity Max Load %','Bottleneck Overload Days','Capacity Basis','Projected Finish','Suggested Revised Due Date','Safe-Date Confidence','Delivery Risk','Detailed Reason'] if c in _pv.columns]
            _m1,_m2,_m3=st.columns(3); _m1.metric('WOs',_pv['Work Order'].astype(str).nunique()); _m2.metric('Categories',_pv['Category'].astype(str).nunique()); _m3.metric('At-risk WOs',int(_pv.get('Delivery Risk',pd.Series('',index=_pv.index)).astype(str).str.contains('RISK|LATE|OVERDUE',case=False,regex=True).sum()))
            if not _pv.empty:
                _qtycol='Open Qty' if 'Open Qty' in _pv.columns else ('Order Qty' if 'Order Qty' in _pv.columns else None)
                if _qtycol:
                    _pg=_pv.groupby(['Planning Group','Category'],as_index=False)[_qtycol].sum()
                    _fig=px.bar(_pg,x='Category',y=_qtycol,color='Planning Group',barmode='group',title='Open demand by planning group × product category')
                    _show_plotly(_fig,'Order_Portfolio_Category')
                _bn=_pv.groupby(['Bottleneck Process','Planning Group'],dropna=False,as_index=False).size().rename(columns={'size':'WO Count'}) if 'Bottleneck Process' in _pv.columns else pd.DataFrame()
                if not _bn.empty:
                    _fbn=px.bar(_bn,x='Bottleneck Process',y='WO Count',color='Planning Group',barmode='group',title='Bottleneck WOs by planning group')
                    _show_plotly(_fbn,'Order_Portfolio_Bottleneck')
                st.dataframe(_pv[_pc],use_container_width=True,hide_index=True,height=540)
                _pb=io.BytesIO()
                with pd.ExcelWriter(_pb,engine='xlsxwriter') as _w:
                    _pv[_pc].to_excel(_w,index=False,sheet_name='Portfolio Detail')
                    for _grp,_gg in _pv.groupby('Planning Group'):
                        _sn={'TEST WORK / งานทดสอบ':'Test Work','MAKE TO STOCK / ผลิตเพื่อสต็อก':'Make To Stock','MASS / MADE TO ORDER / ผลิตตามคำสั่ง':'Mass-MTO'}.get(_grp,'Other')
                        _gg[_pc].to_excel(_w,index=False,sheet_name=_sn[:31])
                    if not _cap_ev.empty:_cap_ev.to_excel(_w,index=False,sheet_name='Capacity Evidence')
                st.download_button('⬇️ DOWNLOAD ORDER PORTFOLIO — EXCEL',_pb.getvalue(),file_name=f'SL_PPC_ORDER_PORTFOLIO_{pd.Timestamp(start).strftime("%Y%m%d")}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='download_order_portfolio')
            else:
                st.info('No WOs match the selected planning group/category.')

    if _nav_idx==18:
        st.subheader('⬇️ DOWNLOAD PLAN / ดาวน์โหลดแผน')
        st.caption('This button builds the Excel workbook from the current calculated plan, then downloads it to your computer. No extra upload is needed.')
        if isinstance(allp,pd.DataFrame) and not allp.empty:
            try:
                from daily_plan_export import build_daily_plan_workbook as _build_daily_export
                _export_result=dict(res)
                try:
                    from suite.recovery_actions import build_recovery_daily_allocation as _recovery_reconcile_export
                    from suite.recovery_actions import build_recovery_actions as _recovery_actions_export
                    _recovery_asof_export=datetime.datetime.now(ZoneInfo('Asia/Bangkok')).date()
                    _export_result['recovery_feasibility'],_export_result['recovery_capacity_evidence']=_recovery_reconcile_export(
                        res.get('master',pd.DataFrame()),risk,allp,caps,_recovery_asof_export)
                    _export_result['recovery_actions']=_recovery_actions_export(res.get('master',pd.DataFrame()),risk,_recovery_asof_export)
                except Exception as _recovery_export_error:
                    st.warning(f'Recovery sheets unavailable: {_recovery_export_error}')
                _export_bytes=_build_daily_export(allp,caps,wip,risk,issues,_export_result)
                st.download_button('⬇️ DOWNLOAD COMPLETE DAILY PLAN — EXCEL',_export_bytes,file_name=f'SL_PPC_DAILY_OUTPUT_{pd.Timestamp(start).strftime("%Y%m%d")}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='main_daily_plan_download')
                st.success('Workbook includes the daily schedule, capacity, planning WIP, delivery risk, issues, source-backed master tables and section plans when available.')
            except Exception as _export_error:
                st.error(f'Daily Plan export could not be built: {_export_error}')
        else:
            st.warning('Create the Daily Plan first. Confirm Plan-2026 and Current Firing Planner Output are loaded, then choose Create Daily Plan.')

    if _nav_idx==20:
        st.subheader('✅ PLAN ACCURACY / VALIDATION — SOFTWARE ACCEPTANCE EVIDENCE')
        st.caption('This tab proves the plan rule-by-rule. FAIL is more important than a cosmetic overall percentage.')
        st.markdown('### ✏️ PLANNER DECISION LAYER / ชั้นการตัดสินใจของฝ่ายวางแผน')
        _pm=res.get('master',pd.DataFrame()).copy()
        if not _pm.empty and 'Work Order' in _pm.columns:
            _pm=_pm.drop_duplicates('Work Order',keep='last')
            _ec=[c for c in ['Work Order','Customer','Product Code','Category','Due Date','Order Qty','Shape','D','T','H','Overall Closed'] if c in _pm.columns]
            _pe=_persistent_data_editor(_pm[_ec],use_container_width=True,hide_index=True,height=380,disabled=[c for c in ['Work Order','Customer','Product Code'] if c in _ec],key='planner_decision_editor_v1933')
            if st.button('💾 SAVE PLANNER DECISIONS / บันทึกการตัดสินใจ',key='save_planner_decisions_v1933'):
                _base=st.session_state.plan_overrides.copy() if isinstance(st.session_state.plan_overrides,pd.DataFrame) else pd.DataFrame()
                for _,_r in _pe.iterrows():
                    _base=_merge_override_row(_base,_r.to_dict())
                st.session_state.plan_overrides=_base
                st.success('Saved as planning-layer overrides. Click CREATE DAILY PLAN to recalculate. Original Plan2026 remains unchanged.')
        st.divider()

        # Daily Status parsing/errors are intentionally isolated to the 📡 Daily Status tab.
        fire_df=st.session_state.firing_override if isinstance(st.session_state.firing_override,pd.DataFrame) else pd.DataFrame()
        fv=_firing_consistency(allp,fire_df)
        cv=_capacity_validation(allp,caps)
        bv=_pull_balance_validation(allp,caps)

        checks=[]
        # Firing exact consistency is a hard gate.
        if fv.empty: checks.append({'Check':'Daily Firing = Firing Planner','Result':'CHECK','Evidence':'No mapped firing comparison available.'})
        else:
            bad=int((fv['Result']=='FAIL').sum())
            checks.append({'Check':'Daily Firing = Firing Planner','Result':'PASS' if bad==0 else 'FAIL','Evidence':f'{len(fv)-bad}/{len(fv)} WO firing date+qty matches; {bad} mismatch.'})
        # Capacity hard gate.
        if cv.empty:checks.append({'Check':'Capacity compliance','Result':'CHECK','Evidence':'No comparable daily capacity rows.'})
        else:
            bad=int((cv['Result']=='FAIL').sum());checks.append({'Check':'Capacity compliance','Result':'PASS' if bad==0 else 'FAIL','Evidence':f'{bad} day/section overload(s) above controlled capacity.'})
        # Due date.
        if risk.empty:checks.append({'Check':'Due-date adherence','Result':'CHECK','Evidence':'No delivery-risk table.'})
        else:
            _late=pd.to_datetime(risk.get('Projected Finish'),errors='coerce')>pd.to_datetime(risk.get('Due Date'),errors='coerce')
            checks.append({'Check':'Due-date adherence','Result':'PASS' if int(_late.fillna(False).sum())==0 else 'WARNING',
                           'Evidence':f"{int(_late.fillna(False).sum())} open WO(s) project after due date; each requires unavoidable-vs-avoidable reason review."})
        # Lead sequence.
        _seq_fail=0
        for wo,g in allp.groupby('Work Order'):
            gg=g.copy();gg['_d']=pd.to_datetime(gg['Plan Date'],errors='coerce')
            mins=gg.groupby('Section')['_d'].min().to_dict()
            order=['Preparation','Mixing','Forming','Firing']
            last=None
            for sec in order:
                if sec in mins and pd.notna(mins[sec]):
                    if last is not None and mins[sec].date()<=last.date():_seq_fail+=1
                    last=mins[sec]
        checks.append({'Check':'Process sequence / next-working-day rule','Result':'PASS' if _seq_fail==0 else 'FAIL','Evidence':f'{_seq_fail} same-day/reversed core-process sequence violation(s).'})
        # Pull/work balance.
        _low=bv[(pd.to_numeric(bv.get('Load %'),errors='coerce')<60)] if not bv.empty else pd.DataFrame()
        checks.append({'Check':'Work balance / pull utilization','Result':'PASS' if _low.empty else 'WARNING',
                       'Evidence':f'{len(_low)} low-load day/section rows below 60%. Review whether executable future WIP existed before calling these avoidable idle days.'})
        # Long-term reconciliation presence.
        lr=st.session_state.get('long_result')
        checks.append({'Check':'Sales Forecast → MPS → MRP chain','Result':'PASS' if isinstance(lr,dict) and lr else 'CHECK',
                       'Evidence':'Long-term model built and available for reconciliation.' if isinstance(lr,dict) and lr else 'Build MPS/MRP with Sales Forecast to validate forecast→plan→material chain.'})
        vdf=pd.DataFrame(checks)
        c1,c2,c3=st.columns(3);c1.metric('PASS',int((vdf['Result']=='PASS').sum()));c2.metric('WARNING / CHECK',int(vdf['Result'].isin(['WARNING','CHECK']).sum()));c3.metric('FAIL',int((vdf['Result']=='FAIL').sum()))
        st.dataframe(vdf,use_container_width=True,hide_index=True)
        st.markdown('### 🔥 Daily Planner vs Firing Planner — exact WO/date/quantity comparison')
        st.dataframe(fv,use_container_width=True,hide_index=True,height=330)
        st.markdown('### 🏭 Capacity compliance — every day × section')
        st.dataframe(cv,use_container_width=True,hide_index=True,height=360)
        st.markdown('### ⚖️ Work balance / pull visibility')
        st.dataframe(bv,use_container_width=True,hide_index=True,height=360)
        if not bv.empty:
            _bvg=bv.copy(); _bvg['Date']=pd.to_datetime(_bvg['Date'],errors='coerce')
            fbal=px.bar(_bvg.sort_values(['Date','Section']),x='Date',y='Load %',color='Section',barmode='group',
                        hover_data={'Plan pcs':':,.0f','Plan ton':':.3f','Capacity pcs':':,.0f','Capacity ton':':.3f','Basis':True,'Unused Capacity %':':.1f'},
                        title='Daily section load / pull evidence — planned load vs controlled capacity')
            fbal.add_hline(y=100,line_dash='dash',annotation_text='CONTROLLED CAPACITY = 100%')
            fbal.update_layout(yaxis_title='Load vs controlled capacity (%)',xaxis_title='Plan date',hovermode='closest')
            _show_plotly(fbal,'Validation_daily_balance')
        st.warning('Validation principle: a low-load day is NOT automatically a pull failure. It becomes a planning failure only when executable future demand existed and controlled capacity was left idle.')

    if _nav_idx==13:
        st.subheader('📦 PACKAGING PLAN / แผนบรรจุภัณฑ์')
        preq,ptabs=_packaging_requirement(res.get('master',pd.DataFrame()),allp,st.session_state.packaging_path)
        if '_error' in ptabs:st.error('Packaging database read error: '+ptabs['_error'])
        elif 'Packaging standard' in ptabs:
            _pack_frame=ptabs['Packaging standard'];st.success(f"Packaging source loaded: {len(_pack_frame):,} product rows · sheet {_pack_frame.attrs.get('source_sheet','Packaging standard')} · header row {_pack_frame.attrs.get('header_row','legacy mapping')}")
        if preq.empty:
            st.warning('No packaging requirement could be calculated from the current Packing plan.')
        else:
            c1,c2,c3=st.columns(3)
            c1.metric('Packaging requirement lines',len(preq))
            c2.metric('Exact product matches',int(preq['Match Method'].astype(str).str.startswith('EXACT PRODUCT CODE').sum()))
            c3.metric('Fallback / unresolved',int((~preq['Match Method'].astype(str).str.startswith('EXACT PRODUCT CODE')).sum()))
            st.dataframe(preq.sort_values(['Packing Plan Date','Risk','Work Order']),use_container_width=True,hide_index=True,height=430)
            st.markdown('### Requirement by packaging material / ความต้องการตามวัสดุบรรจุภัณฑ์')
            pm=preq.dropna(subset=['Required Qty']).groupby('Packaging Material',as_index=False)['Required Qty'].sum().sort_values('Required Qty',ascending=False)
            if not pm.empty:
                fp=px.bar(pm.head(30),x='Packaging Material',y='Required Qty',title='Packaging requirement — top materials')
                _show_plotly(fp,'Packaging_requirement')
        fr=ptabs.get('Final report',pd.DataFrame())
        if not fr.empty:
            st.markdown('### Existing packaging control — overdue / requirement / reservation')
            st.caption('This is read from the supplied Packaging Final report; original source fields are preserved.')
            st.dataframe(fr,use_container_width=True,hide_index=True,height=380)
        st.info('Thai approved standard: exact Product Code only; box counts are rounded up and component quantities use the standard per box. A missing product match is reported separately from a missing file. Legacy English usage data may show a size fallback requiring review.')

    if _nav_idx==14:
        st.subheader('💎 TOOLING / DIAMOND PLAN / แผนไดมอนด์')
        dp=_diamond_plan(st.session_state.diamond_path,st.session_state.diamond_issue_path)
        if dp.empty:
            st.warning('Diamond/tooling history could not be mapped.')
        else:
            st.caption('Current planning basis = historical monthly consumption + current Diamond stock from the supplied files. No product-to-diamond rule is invented where the source does not provide one.')
            c1,c2,c3=st.columns(3);c1.metric('Tool codes',len(dp));c2.metric('Urgent replenish',int(dp['Recommended Action'].eq('URGENT REPLENISH').sum()));c3.metric('Plan replenish',int(dp['Recommended Action'].eq('PLAN REPLENISH').sum()))
            st.dataframe(dp,use_container_width=True,hide_index=True,height=450)
            _dplot=dp[pd.to_numeric(dp['Months Cover'],errors='coerce').notna()].sort_values('Months Cover').head(30)
            if not _dplot.empty:
                fd=px.bar(_dplot,x='Code',y='Months Cover',hover_data=['Tool','Stock','Avg Monthly','Recommended Action'],title='Diamond/tooling stock coverage — months')
                fd.add_hline(y=1,line_dash='dash',annotation_text='1 month')
                _show_plotly(fd,'Diamond_months_cover')

    if _nav_idx==15:
        st.subheader('📡 PLAN CONTROL & FACTORY EXECUTION / ควบคุมแผนและผลการผลิตจริง')
        st.caption('Traceable chain: PPC Issued Plan → Production Daily Plan → Production Actual. Production date comes only from the worksheet tab name. HARD RULE: blank/invalid WO rows are excluded from every KPI and shown only as rejected evidence.')
        st.caption(f'Active departmental source files are stored in {_ds_shared_root}; one upload accepts separate files for Preparation, Mixing, Forming, Firing, Grinding, and Packing.')
        if _ds_active_table:
            st.markdown('#### Active Department Workbooks / ไฟล์แผนกที่กำลังใช้งาน')
            st.dataframe(pd.DataFrame(_ds_active_table),use_container_width=True,hide_index=True,height=min(360,90+len(_ds_active_table)*42))
        _sv,_sr,_se=_ds_cache_valid,_ds_cache_rejected,_ds_cache_errors
        st.markdown('### 🎯 Customer delivery & section completion / ส่งมอบลูกค้าและปิดงานรายแผนก')
        st.caption('Plan-2026 C = initial warehouse due date, E = revised due date, EV = actual warehouse date. Section completion is derived from the section workbook date tab when cumulative actual reaches required quantity or balance is zero. Section-vs-customer-date is a comparison proxy because the source has no separate section due dates.')
        _pt_path=Path(st.session_state.get('plan_path',''))
        _pt=_plan_delivery_trace(str(_pt_path),_pt_path.stat().st_mtime if _pt_path.is_file() else 0) if _pt_path.is_file() else pd.DataFrame()
        _sections_detail=pd.DataFrame();_delivery_detail=pd.DataFrame()
        if not _pt.empty:
            _delivery_detail=_pt.copy()
            _delivery_detail['Actual Delivery Date']=_delivery_detail['Actual Warehouse Date (EV)']
            for _tag,_duecol in [('Initial','Initial Due Date (C)'),('Revised','Revised Due Date (E)')]:
                _delivery_detail[f'{_tag} Result']=np.select([
                    _delivery_detail['Actual Delivery Date'].notna()&_delivery_detail[_duecol].notna()&(_delivery_detail['Actual Delivery Date'].dt.normalize()<=_delivery_detail[_duecol].dt.normalize()),
                    _delivery_detail['Actual Delivery Date'].notna()&_delivery_detail[_duecol].notna()],['ON TIME','LATE'],'NOT SCORED — DATE MISSING')
                _delivery_detail[f'{_tag} On-time Qty']=np.where(_delivery_detail[f'{_tag} Result'].eq('ON TIME'),_delivery_detail['Order Qty'],0)
            _delivery_detail=_delivery_detail.sort_values(['Customer','Work Order'])
            _delivered=_delivery_detail[_delivery_detail['Actual Delivery Date'].notna()].copy()
            _dm1,_dm2,_dm3,_dm4,_dm5=st.columns(5)
            _dm1.metric('Actual warehouse dates recorded',f"{len(_delivered):,} WOs")
            _initial_eval=_delivered[_delivered['Initial Due Date (C)'].notna()]
            _revised_eval=_delivered[_delivered['Revised Due Date (E)'].notna()]
            _dm2.metric('On time vs initial due',f"{(_initial_eval['Initial Result'].eq('ON TIME').mean()*100 if len(_initial_eval) else 0):.1f}%",f"{_initial_eval['Initial Result'].eq('ON TIME').sum():,}/{len(_initial_eval):,} scored")
            _dm3.metric('On time vs revised due',f"{(_revised_eval['Revised Result'].eq('ON TIME').mean()*100 if len(_revised_eval) else 0):.1f}%",f"{_revised_eval['Revised Result'].eq('ON TIME').sum():,}/{len(_revised_eval):,} scored")
            _dm4.metric('Revised due date missing',f"{_delivery_detail['Revised Due Date (E)'].isna().sum():,} WOs")
            _dm5.metric('On-time parts vs revised',f"{_delivery_detail['Revised On-time Qty'].sum():,.0f} pcs",f"of {_revised_eval['Order Qty'].sum():,.0f} scored pcs")
            if not _delivered.empty:
                _cust=_delivered.groupby('Customer',dropna=False).agg(Delivered_WOs=('Work Order','nunique'),Delivered_Pcs=('Order Qty','sum'),On_time_Initial_WOs=('Initial Result',lambda s:s.eq('ON TIME').sum()),On_time_Revised_WOs=('Revised Result',lambda s:s.eq('ON TIME').sum()),On_time_Initial_Pcs=('Initial On-time Qty','sum'),On_time_Revised_Pcs=('Revised On-time Qty','sum')).reset_index()
                _cust['Initial On-time %']=np.where(_cust.Delivered_WOs>0,_cust.On_time_Initial_WOs/_cust.Delivered_WOs*100,0)
                _cust['Revised On-time %']=np.where(_cust.Delivered_WOs>0,_cust.On_time_Revised_WOs/_cust.Delivered_WOs*100,0)
                _cust['Initial On-time pcs %']=np.where(_cust.Delivered_Pcs>0,_cust.On_time_Initial_Pcs/_cust.Delivered_Pcs*100,0)
                _cust['Revised On-time pcs %']=np.where(_cust.Delivered_Pcs>0,_cust.On_time_Revised_Pcs/_cust.Delivered_Pcs*100,0)
                st.markdown('#### Customer satisfaction — actual warehouse date vs promised dates')
                st.dataframe(_cust.sort_values('Delivered_WOs',ascending=False),use_container_width=True,hide_index=True,height=230)
        if not _sv.empty:
            _sx=_sv.copy()
            _sx['Date']=pd.to_datetime(_sx['Date'],errors='coerce')
            for _c in ['Section Required Qty','Cumulative Actual Qty','Balance Qty']:_sx[_c]=pd.to_numeric(_sx[_c],errors='coerce')
            _sx['_WO_KEY']=_sx['Work Order'].astype(str).str.upper().str.replace(r'[^A-Z0-9]','',regex=True)
            _daily_group=_sx.dropna(subset=['Date']).groupby(['_WO_KEY','Work Order','Section','Date'],as_index=False).agg(
                **{'Required Qty':('Section Required Qty','sum'),'Cumulative Qty':('Cumulative Actual Qty','sum'),'Balance Qty':('Balance Qty','sum'),
                   'Production Actual Qty':('Production Actual Qty','sum'),'Source File':('Source File','first'),'Source Sheet':('Source Sheet','first'),
                   'Source Rows':('Source Row',lambda s:', '.join(map(str,s.tolist()))),'Date Source':('Date Source','first')})
            _daily_group['_complete']=(_daily_group['Required Qty']>0)&((_daily_group['Balance Qty']<=0)|(_daily_group['Cumulative Qty']>=_daily_group['Required Qty']))
            _latest=_daily_group.sort_values('Date').drop_duplicates(['_WO_KEY','Section'],keep='last')
            _closed=_daily_group[_daily_group['_complete']].sort_values('Date').drop_duplicates(['_WO_KEY','Section'],keep='first').rename(columns={'Date':'Section Close Date','Source File':'Close Source File','Source Sheet':'Close Source Sheet','Source Rows':'Close Source Rows','Date Source':'Close Date Basis'})
            _sections_detail=_latest[['Work Order','_WO_KEY','Section','Date','Required Qty','Cumulative Qty','Balance Qty','Production Actual Qty','Source File','Source Sheet','Source Rows','Date Source']].rename(columns={'Date':'Latest Status Date','Source File':'Latest Source File','Source Sheet':'Latest Source Sheet','Source Rows':'Latest Source Rows','Date Source':'Latest Date Basis'}).merge(
                _closed[['_WO_KEY','Section','Section Close Date','Close Source File','Close Source Sheet','Close Source Rows','Close Date Basis']],on=['_WO_KEY','Section'],how='left')
            if not _pt.empty:
                _sections_detail=_sections_detail.merge(_pt[['_WO_KEY','Customer','Product Code','Order Qty','Initial Due Date (C)','Revised Due Date (E)','Plan Source Row']],on='_WO_KEY',how='left')
                for _tag,_duecol in [('Initial','Initial Due Date (C)'),('Revised','Revised Due Date (E)')]:
                    _sections_detail[f'{_tag} On-time']=np.where(_sections_detail['Section Close Date'].notna()&_sections_detail[_duecol].notna(),np.where(_sections_detail['Section Close Date'].dt.normalize()<=_sections_detail[_duecol].dt.normalize(),'ON TIME','LATE'),'NOT SCORED')
                _sumrows=[]
                for _sec in ['Preparation','Mixing','Forming','Firing','Grinding','Packing']:
                    _q=_sections_detail[_sections_detail['Section'].astype(str).str.startswith(_sec)]
                    _done=_q[_q['Section Close Date'].notna()]
                    _ie=_done[_done['Initial Due Date (C)'].notna()] if 'Initial Due Date (C)' in _done else pd.DataFrame()
                    _re=_done[_done['Revised Due Date (E)'].notna()] if 'Revised Due Date (E)' in _done else pd.DataFrame()
                    _qtycol='Order Qty' if 'Order Qty' in _q else None
                    _totalpcs=pd.to_numeric(_q[_qtycol],errors='coerce').fillna(0).sum() if _qtycol else np.nan
                    _donepcs=pd.to_numeric(_done[_qtycol],errors='coerce').fillna(0).sum() if _qtycol else np.nan
                    _iepcs=_ie[pd.to_numeric(_ie[_qtycol],errors='coerce').notna()] if _qtycol else pd.DataFrame()
                    _repcs=_re[pd.to_numeric(_re[_qtycol],errors='coerce').notna()] if _qtycol else pd.DataFrame()
                    _sumrows.append({'Section':_sec,'Tracked WOs':_q['_WO_KEY'].nunique(),'Completed WOs':_done['_WO_KEY'].nunique(),'Completion coverage %':100*_done['_WO_KEY'].nunique()/max(_q['_WO_KEY'].nunique(),1),'Tracked parts':_totalpcs,'Completed parts':_donepcs,'Completion coverage (parts) %':100*_donepcs/max(_totalpcs,1) if pd.notna(_totalpcs) else np.nan,'Initial due scored WOs':len(_ie),'On time vs initial %':100*_ie['Initial On-time'].eq('ON TIME').mean() if len(_ie) else np.nan,'On time vs initial (parts) %':100*pd.to_numeric(_iepcs.loc[_iepcs['Initial On-time'].eq('ON TIME'),_qtycol],errors='coerce').sum()/max(pd.to_numeric(_iepcs[_qtycol],errors='coerce').sum(),1) if len(_iepcs) else np.nan,'Revised due scored WOs':len(_re),'On time vs revised %':100*_re['Revised On-time'].eq('ON TIME').mean() if len(_re) else np.nan,'On time vs revised (parts) %':100*pd.to_numeric(_repcs.loc[_repcs['Revised On-time'].eq('ON TIME'),_qtycol],errors='coerce').sum()/max(pd.to_numeric(_repcs[_qtycol],errors='coerce').sum(),1) if len(_repcs) else np.nan})
                _section_summary=pd.DataFrame(_sumrows)
                st.markdown('#### Section closure by date tab — completion and due-date comparison')
                _gc1,_gc2=st.columns(2)
                with _gc1:
                    _g1=px.bar(_section_summary,x='Section',y=['Tracked WOs','Completed WOs'],barmode='group',title='Work orders with section closure evidence')
                    st.plotly_chart(_g1,use_container_width=True)
                with _gc2:
                    _g2=px.bar(_section_summary,x='Section',y=['On time vs initial %','On time vs revised %'],barmode='group',title='Section completion by customer due date (proxy)')
                    _g2.update_yaxes(range=[0,100],title='Percent of completed WOs with a valid due date')
                    st.plotly_chart(_g2,use_container_width=True)
                st.dataframe(_section_summary,use_container_width=True,hide_index=True)
                st.caption('Section closure evidence rule: first dated tab where cumulative actual quantity ≥ required quantity OR remaining balance ≤ 0. Rows without enough quantity/balance evidence remain unclosed / not scored; source date is always the worksheet tab.')
                _showcols=[c for c in ['Work Order','Customer','Product Code','Section','Required Qty','Cumulative Qty','Balance Qty','Latest Status Date','Section Close Date','Initial Due Date (C)','Initial On-time','Revised Due Date (E)','Revised On-time','Production Actual Qty','Latest Source File','Latest Source Sheet','Latest Source Rows','Close Source File','Close Source Sheet','Close Source Rows','Close Date Basis','Plan Source Row'] if c in _sections_detail.columns]
                st.markdown('#### Traceable section-by-work-order detail')
                st.dataframe(_sections_detail[_showcols].sort_values(['Work Order','Section']),use_container_width=True,hide_index=True,height=380)
            else:
                st.info('Upload Plan-2026 to compare section completions with original/revised customer dates.')
        if not _delivery_detail.empty:
            _dc=[c for c in ['Work Order','Customer','Product Code','Order Qty','Initial Due Date (C)','Initial Result','Revised Due Date (E)','Revised Result','Actual Delivery Date','Plan Source Row'] if c in _delivery_detail]
            with st.expander('Traceable delivery-by-work-order detail',expanded=False):st.dataframe(_delivery_detail[_dc],use_container_width=True,hide_index=True,height=400)
            st.download_button('⬇️ Download delivery and section traceability workbook',_delivery_detail.to_csv(index=False).encode('utf-8-sig'),'Plan2026_OnTime_Delivery_Trace.csv','text/csv',key='on_time_delivery_trace')
        if _sv.empty:
                    st.warning('Problem / corrective-action analysis is empty because no readable Daily Status section rows are loaded. Use Home → Files → All software inputs, or the Update input files link above; upload one workbook per section. Each workbook stays separate, and its worksheet tabs provide the dates.')
        else:
            _cx=_crosscheck_ppc_production_actual(_sv,allp,res.get('master',pd.DataFrame()))
            _sm=_daily_status_summary(_cx)
            _date_series=pd.to_datetime(_sv['Date'],errors='coerce').dropna()
            if _date_series.empty:
                st.warning('Daily Status dates could not be parsed / ไม่สามารถอ่านวันที่ Daily Status ได้')
                st.stop()
            _mind=_date_series.min().date();_maxd=_date_series.max().date()
            d1,d2=st.columns(2)
            _df=d1.date_input('Performance FROM / จากวันที่',value=_mind,min_value=_mind,max_value=_maxd,key='status_from')
            _dt=d2.date_input('Performance TO / ถึงวันที่',value=_maxd,min_value=_mind,max_value=_maxd,key='status_to')
            _f=_cx[(pd.to_datetime(_cx['Date'],errors='coerce').dt.date>=_df)&(pd.to_datetime(_cx['Date'],errors='coerce').dt.date<=_dt)].copy()
            _fsm=_daily_status_summary(_f)

            _prod_plan=float(_f['Production Plan Qty'].sum());_act=float(_f['Production Actual Qty'].sum())
            _ppc=float(_f['PPC Issued Plan Qty'].fillna(0).sum())
            _miss=int((_f['Miss Qty']>0).sum())
            _reason_cov=100*(1-(((_f['Miss Qty']>0)&_f['Problem'].astype(str).str.strip().eq('')).sum()/max(_miss,1)))
            _action_cov=100*(1-(((_f['Miss Qty']>0)&_f['Production Action'].astype(str).str.strip().eq('')).sum()/max(_miss,1)))
            k1,k2,k3,k4,k5,k6=st.columns(6)
            k1.metric('Production Plan',f'{_prod_plan:,.0f} pcs')
            k2.metric('Actual',f'{_act:,.0f} pcs')
            k3.metric('Achievement',f'{(_act/_prod_plan*100 if _prod_plan else 0):.1f}%')
            k4.metric('PPC→Production',f'{(_prod_plan/_ppc*100 if _ppc else 0):.1f}%' if _ppc else 'N/A')
            k5.metric('Reason coverage',f'{_reason_cov:.1f}%')
            k6.metric('Action coverage',f'{_action_cov:.1f}%')

            st.markdown('### Department × Product Category performance / ผลงานตามหน่วยงานและกลุ่มสินค้า')
            st.dataframe(_fsm,use_container_width=True,hide_index=True,height=380)
            # Selected-period total Plan vs Actual, each bar stacked by product category. One total label per stack.
            _pva=_f.groupby('Category',as_index=False).agg(**{'Plan':('Production Plan Qty','sum'),'Actual':('Production Actual Qty','sum')})
            _pval=_pva.melt(id_vars='Category',value_vars=['Plan','Actual'],var_name='Measure',value_name='Qty pcs')
            _fpva=px.bar(_pval,x='Measure',y='Qty pcs',color='Category',barmode='stack',category_orders={'Category':['P','R','S','T','M','PB','UNCLASSIFIED']},color_discrete_map=CATEGORY_COLORS,title=f'TOTAL PLAN vs ACTUAL BY PRODUCT CATEGORY — {_df} to {_dt}')
            _pvat=_pval.groupby('Measure',as_index=False)['Qty pcs'].sum()
            _fpva.add_scatter(x=_pvat['Measure'],y=_pvat['Qty pcs'],mode='text',text=[f'{v:,.0f}' for v in _pvat['Qty pcs']],textposition='top center',showlegend=False,hoverinfo='skip')
            _show_plotly(_fpva,'DailyStatus_Total_Plan_Actual_Category_Stack')
            if not _fsm.empty:
                _plot=_fsm.copy()
                fp=px.bar(_plot,x='Section',y='Qty Achievement %',color='Product Category',barmode='group',
                          category_orders={'Product Category':['P','R','S','T','M','PB','UNCLASSIFIED']},
                          color_discrete_map=CATEGORY_COLORS,title='Quantity achievement % by department and product category')
                fp.add_hline(y=100,line_dash='dash',annotation_text='100% plan')
                _show_plotly(fp,'DailyStatus_Category_Achievement')

            st.markdown('### DAILY STATUS — PLAN BY PRODUCT CATEGORY vs CAPACITY / แผนรายวันเทียบกำลังการผลิต')
            # One clear chart: Production Plan is stacked by product category; controlled capacity is a line.
            # Only the TOTAL plan is labelled above each stack. Segment values stay in hover.
            _cat=_f.groupby(['Date','Section','Category'],as_index=False).agg(**{'Plan pcs':('Production Plan Qty','sum'),'Actual pcs':('Production Actual Qty','sum')})
            _capday=caps.copy() if isinstance(caps,pd.DataFrame) else pd.DataFrame()
            if not _cat.empty:
                _cat['Date']=pd.to_datetime(_cat['Date'],errors='coerce').dt.normalize()
                _fs=px.bar(_cat,x='Date',y='Plan pcs',color='Category',facet_row='Section',barmode='stack',
                           category_orders={'Category':['P','R','S','T','M','PB','UNCLASSIFIED']},color_discrete_map=CATEGORY_COLORS,
                           hover_data={'Plan pcs':':,.0f','Actual pcs':':,.0f'},title='DAILY STATUS — PRODUCTION PLAN BY CATEGORY vs CONTROLLED CAPACITY')
                for _tr in _fs.data:_tr.text=None
                _tot=_cat.groupby(['Date','Section'],as_index=False)['Plan pcs'].sum()
                # Add total labels and capacity line process-by-process so facets remain readable.
                _secs=list(dict.fromkeys(_cat['Section'].astype(str).tolist()))
                for _i,_sec in enumerate(_secs, start=1):
                    _tt=_tot[_tot['Section'].astype(str).eq(_sec)]
                    _fs.add_scatter(x=_tt['Date'],y=_tt['Plan pcs'],mode='text',text=[f'{v:,.0f}' for v in _tt['Plan pcs']],textposition='top center',showlegend=False,hoverinfo='skip',row=_i,col=1)
                if not _capday.empty:
                    _capday['Date']=pd.to_datetime(_capday.get('Plan Date'),errors='coerce').dt.normalize()
                    _capday['Capacity pcs']=pd.to_numeric(_capday.get('Plan pcs',0),errors='coerce').fillna(0)/(pd.to_numeric(_capday.get('Utilization %',0),errors='coerce').replace(0,np.nan)/100.0)
                    _cg=_capday.groupby(['Date','Section'],as_index=False)['Capacity pcs'].sum()
                    for _i,_sec in enumerate(_secs, start=1):
                        _cc=_cg[_cg['Section'].astype(str).eq(_sec)]
                        if not _cc.empty:_fs.add_scatter(x=_cc['Date'],y=_cc['Capacity pcs'],mode='lines+markers',name='Controlled Capacity',line=dict(dash='dash'),showlegend=(_i==1),row=_i,col=1)
                _fs.update_layout(height=max(700,220*len(_secs)))
                _show_plotly(_fs,'DailyStatus_Plan_Category_vs_Capacity')
                # Selected-period Plan and Actual by process: each bar is a PRODUCT-CATEGORY stack.
                _pa=_f.groupby(['Section','Category'],as_index=False).agg(**{'Plan pcs':('Production Plan Qty','sum'),'Actual pcs':('Production Actual Qty','sum')})
                _pal=_pa.melt(id_vars=['Section','Category'],value_vars=['Plan pcs','Actual pcs'],var_name='Measure',value_name='pcs')
                _pal['Process / Measure']=_pal['Section'].astype(str)+' — '+_pal['Measure'].astype(str)
                _fa=px.bar(_pal,x='Process / Measure',y='pcs',color='Category',barmode='stack',category_orders={'Category':['P','R','S','T','M','PB','UNCLASSIFIED']},color_discrete_map=CATEGORY_COLORS,title='SELECTED PERIOD — PLAN vs ACTUAL BY PROCESS × PRODUCT CATEGORY')
                _pat=_pal.groupby('Process / Measure',as_index=False)['pcs'].sum()
                _fa.add_scatter(x=_pat['Process / Measure'],y=_pat['pcs'],mode='text',text=[f'{v:,.0f}' for v in _pat['pcs']],textposition='top center',showlegend=False,hoverinfo='skip')
                _show_plotly(_fa,'DailyStatus_Process_Plan_Actual_Category_Stack')
            st.dataframe(_f[['Date','Section','Work Order','Category','PPC Issued Plan Qty','Production Plan Qty','Production Actual Qty',
                             'PPC→Production Variance','Production→Actual Variance','PPC Plan Adherence %','Production Achievement %',
                             'Problem English','Reason Quality','Action English','Action Quality','PPC Recommended Action',
                             'Due Date','Source File','Source Sheet','Source Row']],
                         use_container_width=True,hide_index=True,height=470)

            st.markdown('### Problem / action quality and recovery visibility')
            _missdf=_f[_f['Miss Qty']>0].copy()
            if _missdf.empty:st.success('No under-plan records in selected period.')
            else:
                _edit_pa=_missdf[['Date','Section','Work Order','Category','Production Plan Qty','Production Actual Qty','Miss Qty','Problem','Production Action','PPC Recommended Action','Due Date','Source File','Source Sheet','Source Row']].copy()
                _edit_pa['Due Date']=pd.to_datetime(_edit_pa['Due Date'],errors='coerce').dt.date
                st.caption('Original factory Problem/Reason and Action are shown. Edit the text here when you want English/Thai management wording; source workbook is not overwritten.')
                _persistent_data_editor(_edit_pa,use_container_width=True,hide_index=True,height=400,disabled=[c for c in _edit_pa.columns if c not in ['Problem','Production Action']],key='problem_action_editor_v1930')

            if not _missdf.empty:
                _pa=_missdf.copy();_pa['Problem English']=_pa['Problem English'].replace('', 'No reason provided')
                _pg=_pa.groupby(['Section','Problem English'],as_index=False)['Miss Qty'].sum().sort_values('Miss Qty',ascending=False)
                _pg=_pg.groupby('Section',group_keys=False).head(8)
                if not _pg.empty:
                    fpa=px.bar(_pg,x='Miss Qty',y='Problem English',color='Section',orientation='h',hover_data=['Section'],title='Major production problems by section — missed quantity (pcs)')
                    _show_plotly(fpa,'DailyStatus_Major_Problems_Actions')
                _as=_pa.groupby(['Section','Action English'],as_index=False)['Miss Qty'].sum().sort_values('Miss Qty',ascending=False)
                _as=_as[_as['Action English'].astype(str).str.strip().ne('')].groupby('Section',group_keys=False).head(8)
                if not _as.empty:
                    faa=px.bar(_as,x='Miss Qty',y='Action English',color='Section',orientation='h',title='Major recovery actions by section — quantity gap addressed')
                    _show_plotly(faa,'DailyStatus_Major_Actions')
            st.markdown('### Data integrity / คุณภาพข้อมูล')
            q1,q2,q3=st.columns(3)
            q1.metric('Valid WO source rows',len(_sv))
            q2.metric('Rejected invalid/blank WO rows',len(_sr))
            q3.metric('Workbook/sheet read errors',len(_se))
            st.caption('Rejected rows NEVER contribute quantity, WO count, category, weight, problem/action or any other KPI.')
            if not _sr.empty:
                st.dataframe(_sr[['Date','Section','Work Order','Production Plan Qty','Production Actual Qty','Product Category','Problem','Production Action',
                                  'Reject Reason','Source File','Source Sheet','Source Row']],
                             use_container_width=True,hide_index=True,height=300)
            if not _se.empty:st.dataframe(_se,use_container_width=True,hide_index=True)

            # Traceable Excel export.
            _bout=io.BytesIO()
            with pd.ExcelWriter(_bout,engine='xlsxwriter') as _w:
                _fsm.to_excel(_w,index=False,sheet_name='Performance Summary')
                _f.to_excel(_w,index=False,sheet_name='Traceable Detail')
                _missdf.to_excel(_w,index=False,sheet_name='Miss Reason Action')
                _sr.to_excel(_w,index=False,sheet_name='Rejected Invalid WO')
                _se.to_excel(_w,index=False,sheet_name='Read Errors')
            st.download_button('⬇️ DOWNLOAD TRACEABLE PRODUCTION PERFORMANCE',_bout.getvalue(),
                               file_name=f'SL_PPC_PRODUCTION_PERFORMANCE_{_df}_{_dt}.xlsx',
                               mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                               use_container_width=True,key='status_export')


    if _nav_idx==22:
        from suite.kpi_workspace import render_open_close as _shared_open_close55
        from suite.central_paths import db_path as _central_db55
        _shared_open_close55(st,_central_db55())

    if _nav_idx==21:
        from suite.production_analysis_page import render_department as _shared_department55
        from suite.central_paths import db_path as _central_db55
        _shared_department55(st,_central_db55(),can_edit=bool(st.session_state.get('sl_authenticated')),user=st.session_state.get('sl_user','VIEWER'))

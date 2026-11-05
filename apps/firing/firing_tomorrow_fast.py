import os
import traceable_views as tv48
import io
import time, os, traceback, threading, subprocess, sys
from pathlib import Path
from datetime import date, timedelta
import streamlit as st
import pandas as pd
import numpy as np
import re
import math
import plotly.express as px
import plotly.graph_objects as go
import ppc_desktop_core_v1_9 as coremap
_ROOT=Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path: sys.path.insert(0,str(_ROOT))
from suite.central_paths import resolve_file as _resolve_central, missing_plan_message as _missing_plan_message

import sl_ppc_fast_store_v4_6 as store
import ppc_fast_core_v4_6 as fc
import firing_engine_desktop_v2 as fire
import fast_stage4_v15 as fast4
import pattern_on_demand_v16 as pat16
import operator_print_v19 as opprint
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

st.set_page_config(page_title='SL PPC Firing Planner F12U', layout='wide', page_icon='🔥')
st.markdown('''<style>.stMetric{background:#f7f9fc;border:1px solid #e5e7eb;border-radius:14px;padding:10px}.block-container{padding-top:1.2rem}</style>''',unsafe_allow_html=True)
st.title('🔥 SL PPC FIRING PLANNER / โปรแกรมวางแผนการเผา')
st.markdown('### FIRING PLANNING')
st.info('Central inputs are loaded automatically from Active Files. Select test work if needed → Create Firing Plan → Review release → Pattern Loading → Download operator plan.')

work = Path.home()/'SL_PPC_DATA'
work.mkdir(parents=True, exist_ok=True)
class _CentralUpload:
    def __init__(self,p): self.p=Path(p); self.name=self.p.name
    def getbuffer(self): return self.p.read_bytes()
    def getvalue(self): return self.p.read_bytes()
    def read(self): return self.p.read_bytes()
    def seek(self,*a,**k): return 0

if 'fr' not in st.session_state: st.session_state.fr=None
if 'plan_path' not in st.session_state: st.session_state.plan_path=''
if 'test_work_override_by_wo' not in st.session_state: st.session_state.test_work_override_by_wo={}
if 'firing_data_override_by_wo' not in st.session_state: st.session_state.firing_data_override_by_wo={}
if 'cap_path' not in st.session_state: st.session_state.cap_path=str(Path(__file__).with_name('CAPACITY_DATABASE.xlsx'))
if 'db_path' not in st.session_state: st.session_state.db_path=str(work/'SL_PPC_FAST_DATA.db')

def _safe_graph_name(s):
    return ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in str(s))[:80] or 'FIRING_GRAPH'

def _show_plotly_fire(fig,name):
    """Downloadable Plotly graph with visible values. Daily kiln schedule is the
    one exception: show only the number of planned kiln starts above each day,
    never the word TOTAL and never segment labels."""
    _nm=str(name)
    _is_stack=str(getattr(fig.layout,'barmode','') or '').lower() in {'stack','relative'}
    _kiln_daily=(_nm=='All_kilns_daily_stack')
    _kiln_timeline=(_nm=='Kiln_schedule_timeline')
    for tr in fig.data:
        try:
            if getattr(tr,'type','')=='bar':
                if _kiln_daily or _kiln_timeline or _is_stack:
                    tr.text=[];tr.texttemplate='';tr.textposition='none'
                else:
                    vals=getattr(tr,'y',None) if getattr(tr,'orientation',None)!='h' else getattr(tr,'x',None)
                    nums=[float(v) for v in vals if pd.notna(v)] if vals is not None else []
                    whole=bool(nums) and all(abs(v-round(v))<1e-9 for v in nums)
                    fmt=',.0f' if whole else ',.2f'
                    tr.texttemplate=('%{y:'+fmt+'}' if getattr(tr,'orientation',None)!='h' else '%{x:'+fmt+'}')
                    tr.textposition='outside';tr.cliponaxis=False
            elif getattr(tr,'type','')=='scatter' and not _kiln_daily:
                _yv=getattr(tr,'y',None)
                if _yv is not None:
                    _mode=str(getattr(tr,'mode','') or 'lines')
                    tr.mode=('lines+markers+text' if 'lines' in _mode else 'markers+text')
                    tr.text=[(f'{float(v):,.0f}' if pd.notna(v) and abs(float(v)-round(float(v)))<1e-9 else (f'{float(v):,.2f}' if pd.notna(v) else '')) for v in _yv]
                    tr.textposition='top center'
        except Exception: pass
    if _is_stack and not _kiln_daily:
        try:
            totals={}
            for tr in fig.data:
                if getattr(tr,'type','')!='bar' or getattr(tr,'orientation',None)=='h':continue
                for xx,yy in zip(list(getattr(tr,'x',[]) or []),list(getattr(tr,'y',[]) or [])):
                    try:totals[xx]=totals.get(xx,0.0)+float(yy or 0)
                    except:pass
            for xx,tt in totals.items():fig.add_annotation(x=xx,y=tt,text=f'{tt:,.0f}' if abs(tt-round(tt))<1e-9 else f'{tt:,.2f}',showarrow=False,yshift=10)
        except Exception:pass
    fig.update_layout(hovermode='closest',margin=dict(t=75,b=70))
    st.plotly_chart(fig,use_container_width=True,config={'displaylogo':False,'responsive':True,'modeBarButtonsToAdd':['toImage'],'toImageButtonOptions':{'format':'png','filename':_safe_graph_name(name),'scale':2}})
    st.download_button('⬇️ Download interactive graph HTML',fig.to_html(full_html=True,include_plotlyjs='cdn').encode('utf-8'),file_name=_safe_graph_name(name)+'.html',mime='text/html',key='fire_html_'+_safe_graph_name(name))




def _full_demand_process_pull(prepared, loads, plan_start):
    """Plan visibility for every open WO. Firing allocation stays physically gated,
    but upstream required process/date is shown so missing readiness is actionable."""
    if prepared is None or prepared.empty:return pd.DataFrame()
    p=prepared.copy()
    for c in ['Effective Qty','Verified Ready for Firing Qty','Candidate Ready Qty','Remaining Qty']:
        if c in p.columns:p[c]=pd.to_numeric(p[c],errors='coerce').fillna(0)
    open_col='Effective Qty' if 'Effective Qty' in p.columns else 'Remaining Qty'
    ready_col='Verified Ready for Firing Qty' if 'Verified Ready for Firing Qty' in p.columns else ('Candidate Ready Qty' if 'Candidate Ready Qty' in p.columns else open_col)
    p['_open']=p[open_col].clip(lower=0);p['_ready']=p[ready_col].clip(lower=0);p['_need']=(p['_open']-p['_ready']).clip(lower=0)
    p['_due']=pd.to_datetime(p.get('Due Date'),errors='coerce')
    rows=[]
    for _,r in p[p['_open']>0].sort_values(['_due','Program','Work Order'],na_position='last').iterrows():
        due=r['_due']; need=float(r['_need']); ready=float(r['_ready'])
        # Back-schedule required upstream completion from due date, using a conservative
        # next-day process chain. This is an action signal, not a false firing release.
        fire_need=(due-pd.Timedelta(days=7)).date() if pd.notna(due) else plan_start
        form_need=(pd.Timestamp(fire_need)-pd.Timedelta(days=1)).date()
        mix_need=(pd.Timestamp(form_need)-pd.Timedelta(days=1)).date()
        prep_need=(pd.Timestamp(mix_need)-pd.Timedelta(days=1)).date()
        if need>0:
            proc='Forming / upstream readiness'
            action=f'Produce {need:,.0f} pcs upstream; target Forming ready by {form_need}'
        else:
            proc='Firing ready'
            action=f'{ready:,.0f} pcs ready; combine/allocate by due date and kiln capacity'
        rows.append({'Due Date':due.date() if pd.notna(due) else None,'Work Order':r.get('Work Order',''),
          'Program':r.get('Program',''),'Open Demand pcs':round(float(r['_open'])),'Firing Ready pcs':round(ready),
          'Need Upstream pcs':round(need),'Preparation Needed By':prep_need,'Mixing Needed By':mix_need,
          'Forming Needed By':form_need,'Firing Needed By':fire_need,'Current Required Process':proc,
          'Required Action':action})
    return pd.DataFrame(rows)

def _all_program_upstream_pull(prepared, loads, target):
    """Show P1/P2/P3/P6/etc even when no releasable load exists yet.
    This is an upstream production signal, NOT a firing release quantity.
    """
    if prepared is None or prepared.empty:return pd.DataFrame()
    p=prepared.copy()
    p['Program']=p.get('Program',pd.Series('',index=p.index)).astype(str).str.strip()
    p=p[p['Program'].ne('')].copy()
    if p.empty:return pd.DataFrame()
    p['_open']=pd.to_numeric(p.get('Effective Qty',0),errors='coerce').fillna(0).clip(lower=0)
    ready_col='Verified Ready for Firing Qty' if 'Verified Ready for Firing Qty' in p.columns else ('Candidate Ready Qty' if 'Candidate Ready Qty' in p.columns else 'Remaining Qty')
    p['_ready']=pd.to_numeric(p.get(ready_col,0),errors='coerce').fillna(0).clip(lower=0)
    p['_notready']=(p['_open']-p['_ready']).clip(lower=0)
    p['_due']=pd.to_datetime(p.get('Due Date'),errors='coerce')
    rows=[]
    l=loads if isinstance(loads,pd.DataFrame) else pd.DataFrame()
    for prog,g in p.groupby('Program'):
        gl=l[l.get('Program',pd.Series('',index=l.index)).astype(str).eq(prog)] if not l.empty else pd.DataFrame()
        under=gl[pd.to_numeric(gl.get('Geometric Occupancy Util',pd.Series(0,index=gl.index)),errors='coerce').fillna(0)<float(target)] if not gl.empty else pd.DataFrame()
        ready=float(g['_ready'].sum()); openq=float(g['_open'].sum()); notready=float(g['_notready'].sum())
        need=0
        if not under.empty:
            # strongest current gap for this program
            vals=[]
            for _,r in under.iterrows():
                occ=float(pd.to_numeric(pd.Series([r.get('Geometric Occupancy Util',0)]),errors='coerce').fillna(0).iloc[0])
                q=float(pd.to_numeric(pd.Series([r.get('Qty pcs',0)]),errors='coerce').fillna(0).iloc[0])
                if occ>0 and q>0: vals.append(max(math.ceil(q*float(target)/occ)-math.floor(q),0))
            need=max(vals) if vals else 0
        elif ready<=0 and notready>0:
            need=min(notready,openq)
        earliest=g['_due'].min()
        rows.append({
            'Program':prog,'Open Demand pcs':round(openq),'Ready for Firing pcs':round(ready),
            'Not Yet Ready / Upstream pcs':round(notready),'Additional pcs needed for current target':round(need) if need else 0,
            'Under-target loads':len(under),'Earliest Due':earliest.date() if pd.notna(earliest) else None,
            'Required Production Action':(
                'EXPEDITE FORMING / upstream output for '+prog if (need>0 or (ready<=0 and notready>0))
                else ('COMBINE READY SAME-PROGRAM WOs' if len(under)>0 else 'NO UPSTREAM EXPEDITE SIGNAL')
            )
        })
    return pd.DataFrame(rows).sort_values(['Under-target loads','Earliest Due','Program'],ascending=[False,True,True],na_position='last')


def _integrated_support_plan(fr):
    loads=fr.get('loads',pd.DataFrame()).copy() if isinstance(fr,dict) else pd.DataFrame()
    det=fr.get('details',pd.DataFrame()).copy() if isinstance(fr,dict) else pd.DataFrame()
    up=fr.get('upstream_plan',pd.DataFrame()).copy() if isinstance(fr,dict) else pd.DataFrame()
    if det.empty:return pd.DataFrame()
    d=det.copy()
    if 'Load Date' not in d.columns and not loads.empty and 'Load ID' in d.columns:
        cols=[c for c in ['Load ID','Load Date','Kiln','Program'] if c in loads.columns]
        d=d.merge(loads[cols].drop_duplicates('Load ID'),on='Load ID',how='left',suffixes=('',' Load'))
    qtyc=next((c for c in ['Planned Firing Qty','Qty','Qty pcs'] if c in d.columns),None)
    d['_fq']=pd.to_numeric(d[qtyc],errors='coerce').fillna(0) if qtyc else 0
    rows=[]
    for _,r in d.iterrows():
        wo=str(r.get('Work Order','')); fd=pd.to_datetime(r.get('Load Date'),errors='coerce')
        ug=up[up.get('Work Order',pd.Series('',index=up.index)).astype(str).eq(wo)].copy() if not up.empty else pd.DataFrame()
        dates={}
        for sec in ['Preparation','Mixing','Forming']:
            sg=ug[ug.get('Section',pd.Series('',index=ug.index)).astype(str).eq(sec)] if not ug.empty else pd.DataFrame()
            if not sg.empty:
                dc=next((c for c in ['Plan Date','Date'] if c in sg.columns),None)
                if dc:dates[sec]=pd.to_datetime(sg[dc],errors='coerce').max()
        rows.append({'Firing Date':fd.date() if pd.notna(fd) else None,'Load ID':r.get('Load ID',''),
          'Kiln':r.get('Kiln',r.get('Kiln Load','')),'Program':r.get('Program',r.get('Program Load','')),
          'Work Order':wo,'Firing Qty':round(float(r['_fq'])),
          'Preparation Complete By':dates.get('Preparation',pd.NaT).date() if pd.notna(dates.get('Preparation',pd.NaT)) else None,
          'Mixing Complete By':dates.get('Mixing',pd.NaT).date() if pd.notna(dates.get('Mixing',pd.NaT)) else None,
          'Forming Complete By':dates.get('Forming',pd.NaT).date() if pd.notna(dates.get('Forming',pd.NaT)) else None,
          'Current Ready pcs':round(float(pd.to_numeric(pd.Series([r.get('Ready Now pcs',r.get('Current Ready Portion pcs',0))]),errors='coerce').fillna(0).iloc[0])),
          'MAKE pcs':round(float(pd.to_numeric(pd.Series([r.get('MAKE pcs',r.get('Future Hard-Pull Portion pcs',0))]),errors='coerce').fillna(0).iloc[0])),
          'Preparation Required By':r.get('Preparation Required By',dates.get('Preparation',None)),
          'Mixing Required By':r.get('Mixing Required By',dates.get('Mixing',None)),
          'Forming Required By':r.get('Forming Required By',dates.get('Forming',None)),
          'Status':r.get('Planning Status',r.get('Shop-floor Release Status',r.get('Release Gate','')))})
    return pd.DataFrame(rows).sort_values(['Firing Date','Load ID','Work Order'],na_position='last')

def _daily_vitrified_balance(loads, starts_target=3):
    if loads is None or loads.empty:return pd.DataFrame()
    x=loads.copy();x=x[x.get('Program',pd.Series('',index=x.index)).astype(str).str.upper().isin(['P1','P2','P3','P6'])]
    if x.empty:return pd.DataFrame()
    x['_d']=pd.to_datetime(x['Load Date'],errors='coerce').dt.date;rows=[]
    for d,g in x.groupby('_d'):
        rel=g if 'Release Gate' not in g.columns else g[~g['Release Gate'].astype(str).str.upper().str.startswith('HOLD')]
        n=len(rel);occ=pd.to_numeric(rel.get('Geometric Occupancy Util',0),errors='coerce').fillna(0).mean()*100 if n else 0
        rows.append({'Load Date':d,'Vitrified Starts Planned':n,'Target Starts':int(starts_target),
                     'Average Volume Utilization %':round(float(occ),1),
                     'Balance Status':'TARGET MET' if n>=int(starts_target) else 'PULL MORE / CHECK CAPACITY-COMPATIBILITY'})
    return pd.DataFrame(rows).sort_values('Load Date')
def _waiting_for_parts(loads,prepared,target):
    """Build upstream-pull signal for underfilled HOLD/COMBINE loads.
    Additional qty is a same-mix geometric estimate, not a physical release quantity.
    """
    if loads is None or loads.empty:return pd.DataFrame()
    _gate=loads.get('Release Gate',pd.Series('',index=loads.index)).astype(str)
    _occ=pd.to_numeric(loads.get('Geometric Occupancy Util',pd.Series(0,index=loads.index)),errors='coerce').fillna(0)
    # Benchmark fix: the utilization graph can contain released loads below the selected
    # occupancy target (for example delivery/weight exceptions). Such loads must also
    # appear in the waiting/remaining table. HOLD status is not the only criterion.
    _waiting_mask=_gate.str.contains('HOLD',case=False,na=False) | (_occ < float(target)-1e-9)
    h=loads[_waiting_mask].copy()
    rows=[]
    for _,r in h.iterrows():
        occ=float(pd.to_numeric(pd.Series([r.get('Geometric Occupancy Util',0)]),errors='coerce').fillna(0).iloc[0])
        qty=float(pd.to_numeric(pd.Series([r.get('Qty pcs',0)]),errors='coerce').fillna(0).iloc[0])
        wt=float(pd.to_numeric(pd.Series([r.get('Weight Util',0)]),errors='coerce').fillna(0).iloc[0])
        hu=pd.to_numeric(pd.Series([r.get('Height Util',None)]),errors='coerce').iloc[0]
        if occ>0 and qty>0:
            target_qty=math.ceil(qty*float(target)/occ)
            need=max(target_qty-math.floor(qty),0)
        else:
            target_qty=None;need=None
        prog=str(r.get('Program','')).strip()
        pp=prepared[prepared.get('Program',pd.Series('',index=prepared.index)).astype(str).str.strip().eq(prog)].copy() if isinstance(prepared,pd.DataFrame) and not prepared.empty else pd.DataFrame()
        # prioritize same-program WOs nearest to firing; show the actual process signal rather than inventing readiness.
        if not pp.empty:
            pp['_q']=pd.to_numeric(pp.get('Qty at Current Process / Ready Next',0),errors='coerce').fillna(0)
            pp=pp[pp['_q']>0].copy()
            proc=pp.groupby('Calculated Current Process')['_q'].sum().sort_values(ascending=False)
            process_signal='; '.join(f'{k}: {v:,.0f} pcs' for k,v in proc.head(3).items()) if not proc.empty else 'No quantified upstream WIP trace'
            wo_signal=', '.join(pp.sort_values(['Due Date','Priority Rank'],na_position='last')['Work Order'].astype(str).head(6).tolist())
        else:
            process_signal='No same-program upstream candidate found';wo_signal=''
        rows.append({
            'Load Date':r.get('Load Date'),'Kiln':r.get('Kiln'),'Program':prog,
            'Release Gate':str(r.get('Release Gate','')),
            'Current Qty pcs':int(round(qty)),
            'Current Volume %':round(occ*100,1),'Target Volume %':round(float(target)*100,1),
            'Occupancy Gap %':round(max(float(target)-occ,0)*100,1),
            'Estimated Qty Needed to Target pcs':(int(need) if need is not None else None),
            'Estimated Target Qty pcs':(int(target_qty) if target_qty is not None else None),
            'Weight %':round(wt*100,1),'Height %':(round(float(hu)*100,1) if pd.notna(hu) else None),
            'Upstream WIP / Process Signal':process_signal,'Candidate WOs':wo_signal,
            'Planning Action':'PULL SAME-PROGRAM PARTS FOR COMBINATION' if need is not None and need>0 else 'REVIEW PHYSICAL / CAPACITY CONSTRAINT',
            'Calculation Note':'Qty-to-target is same-mix geometric estimate; exact release still requires physical pattern/furniture/weight validation.'
        })
    return pd.DataFrame(rows)

with st.sidebar:
    st.header('INPUT / ข้อมูล')
    _central=Path(os.environ.get('SL_COMPANY_DATA',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA'/'COMPANY_DATA')))
    _central_plan=_resolve_central('Plan-2026-LATEST.xlsx') or (_central/'Plan-2026-LATEST.xlsx')
    _central_prev=_resolve_central('Firing-Plan-LATEST.xlsx') or (_central/'Firing-Plan-LATEST.xlsx')
    pu=None
    prevu=[_CentralUpload(_central_prev)] if _central_prev.exists() else []
    if _central_plan.exists():
        _sel_plan=work/'PLAN_2026_ACTIVE.xlsx'; _sel_plan.write_bytes(_central_plan.read_bytes()); st.session_state.plan_path=str(_sel_plan)
        st.success(f'✅ Plan-2026: {_central_plan.name}')
    else: st.error(_missing_plan_message())
    if _central_prev.exists(): st.success(f'✅ Previous issued Firing Plan: {_central_prev.name}')
    else: st.warning('No previous issued Firing Plan is stored yet. First plan can still be created; continuity protection starts after the first saved firing plan.')
    st.success('🗄️ Capacity Database auto-loaded / โหลดฐานกำลังการผลิตอัตโนมัติ')
    tomorrow=date.today()+timedelta(days=1)
    start=st.date_input('First firing date / วันเริ่มเผา', value=tomorrow)
    planning_days=st.number_input('Planning days / จำนวนวันที่วางแผน', min_value=1, max_value=365, value=60, step=1,
                                  help='Default 60 days. All open Plan2026 demand supports future balanced kiln planning; due date and upstream capacity control sequence.')
    st.caption('🔒 CUTOVER: before First Firing Date = previous issued plan/actual execution. From First Firing Date = new optimized plan. Previous released/running kiln cycles remain protected.')
    st.caption('🎯 POSITIVE PPC: due date first → upstream capacity commitment → best compatible/smaller kiln → height/volume/program-weight utilization → balanced daily workload. Missing parts may be planned only when Preparation/Mixing/Forming capacity can produce them before firing.')
    target=st.slider('Target occupancy / เป้าหมายการใช้พื้นที่เตา',0.50,0.95,0.80,0.05)
    maxv=st.slider('Maximum occupancy / การใช้พื้นที่สูงสุด',0.70,1.00,0.95,0.01)
    starts=st.number_input('Maximum normal vitrified starts/day T1-T12/T14 / จำนวนเตา vitrified ปกติสูงสุดต่อวัน',min_value=1,max_value=2,value=2,step=1,key='f12u_vitrified_max_2',help='HARD RULE: maximum 2 normal vitrified starts/day. T0 is excluded. Resin R4/R5/R6 are separate.')
    strict=st.checkbox('Strict forming close / ต้องปิดงานขึ้นรูปก่อน',False,help='Default OFF: physically formed/ready quantity can be planned even when the whole WO Forming status is not formally closed. Enable only when management requires full WO closure before firing.')
    st.markdown('''<style>
.big-step{font-size:24px;font-weight:800;padding:10px 14px;border-radius:10px;background:#F3E8FF;margin:8px 0;color:#4C1D95}.big-note{font-size:17px;font-weight:650}
div[data-testid="stButton"] button{font-size:18px!important;font-weight:750!important;min-height:48px}
</style>''',unsafe_allow_html=True)
    st.markdown('<div class="big-note">🧪 TEST WORK / งานทดสอบ: Product Code starting with <b>1</b> = TEST by default. Use the large TEST WORK SELECTION panel in the MAIN PAGE after the input sidebar.</div>',unsafe_allow_html=True)
    # Save Plan2026 immediately so the main-page Test Work selector can read it before plan creation.
    if pu is not None:
        _bytes=pu.getbuffer(); _sel_plan=work/'PLAN_2026_ACTIVE.xlsx'; _sel_plan.write_bytes(_bytes); st.session_state.plan_path=str(_sel_plan)
        try:
            _shared=Path(os.environ.get('SL_COMPANY_DATA',str(Path(__file__).resolve().parents[2]/'company_data')))/'Plan-2026-LATEST.xlsx'; _shared.write_bytes(_bytes)
            st.sidebar.success('Shared Plan-2026 updated for Daily + QR / อัปเดตไฟล์ส่วนกลางแล้ว')
            try: subprocess.run([sys.executable,str(Path(__file__).resolve().parents[2]/'sync_mobile_plan.py')],cwd=Path(__file__).resolve().parents[2],timeout=90,capture_output=True)
            except Exception: pass
        except Exception as _e: st.sidebar.warning(f'Shared Plan update failed: {_e}')
    st.divider();st.caption('Plan 2026 column mapping — revised defaults 10-Sep-2026; editable for future layout changes.')
    def_mapping={k:v for k,v in coremap.DEFAULT_MAP.items() if k not in {'sheet','data_start_row'}}
    mapdf=pd.DataFrame([{'Field':k,'Excel Column':v} for k,v in def_mapping.items()])
    with st.expander('🧭 Plan 2026 column mapping',expanded=False):
        sheet_name=st.text_input('Plan sheet',value=str(coremap.DEFAULT_MAP.get('sheet','แผนการเผา')),key='fire_sheet_map')
        data_row=st.number_input('First data row',1,100,int(coremap.DEFAULT_MAP.get('data_start_row',4)),key='fire_data_row')
        edited_map=st.data_editor(mapdf,use_container_width=True,hide_index=True,disabled=['Field'],key='fire_mapping_editor')

    st.markdown('''<style>
@keyframes fireGlow{0%,100%{box-shadow:0 0 0 rgba(249,115,22,0)}50%{box-shadow:0 0 20px rgba(249,115,22,.20)}}
@keyframes fireTicker{0%{transform:translateX(100%)}100%{transform:translateX(-100%)}}
.fire-card{border:1px solid #e2e8f0;border-radius:18px;padding:14px;background:linear-gradient(135deg,#fff,#fff7ed);box-shadow:0 5px 16px rgba(15,23,42,.06)}
.fire-ticker{overflow:hidden;white-space:nowrap;border-radius:14px;padding:10px 0;background:linear-gradient(90deg,#1f2937,#7c2d12,#1f2937);color:white;font-weight:800;margin:8px 0 16px}.fire-ticker span{display:inline-block;padding-left:100%;animation:fireTicker 32s linear infinite}
div[data-testid="stSidebar"] div[role="radiogroup"] label{border:1px solid #e2e8f0;border-radius:15px;padding:11px;margin:6px 0;background:white;font-weight:800}div[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){border:2px solid #f97316;background:#fff7ed;animation:fireGlow 3s ease-in-out infinite}
div[data-testid="stPlotlyChart"]{background:white;border:1px solid #e2e8f0;border-radius:18px;padding:10px;margin:12px 0 26px;box-shadow:0 6px 18px rgba(15,23,42,.07)}
</style>''',unsafe_allow_html=True)
    st.divider()
    st.markdown('### 🧭 NAVIGATION / เมนู')
    _NAV=['✏️ Planning Data Editor / แก้ไขข้อมูลแผน','🧪 Test Selector / เลือกงานทดสอบ','📅 Kiln Schedule / ตารางเตา','🧪 Test Work / งานทดสอบ','📊 Utilization + Pull / การใช้เตา','🔥 Loads / โหลด','🧱 Pattern Loading / รูปแบบการจัดเรียง','📋 WO Detail / รายละเอียด WO','✅ PL Validation / ตรวจสอบ','⚠️ Exceptions / ข้อยกเว้น','🎯 Candidates / งานผู้สมัคร','🔗 Mapping / การเชื่อมโยง','🔎 Traceable Data / ข้อมูลตรวจสอบ']
    _FGROUPS={
      '① 📋 Planning Data / ข้อมูลการวางแผน':[0,7,10,1,3,11],
      '② 🔥 Kiln Utilization / การใช้เตา':[2,4,5],
      '③ 🧱 Pattern Loading / รูปแบบการจัดเตา':[6],
      '④ ✅ Validation / การตรวจสอบ':[8,9],
      '⑤ 🔎 Data Studio / ตรวจสอบข้อมูล':[12]
    }
    _fgrp=st.radio('Main module / โมดูลหลัก',list(_FGROUPS),index=0,key='f12w_group_nav',label_visibility='collapsed')

_fsubidx=_FGROUPS[_fgrp]
_fsub=[_NAV[i] for i in _fsubidx]
st.markdown(f'<div class="fire-card"><b>{_fgrp}</b><br><span style="font-size:.88rem">Select function / เลือกฟังก์ชัน</span></div>',unsafe_allow_html=True)
_nav=st.selectbox('TAB / แท็บ — select firing page / เลือกหน้าแผนเผา',options=_fsub,index=0,key='f12z_tab_select')

# F12Y Planner Decision Layer: editable WO-level source overrides.
# Original Plan2026 remains untouched; approved values are applied only to this firing calculation.
if st.session_state.get('plan_path') and Path(st.session_state.plan_path).exists() and _fgrp.startswith('①'):
    try:
        _pd_src=coremap.read_plan2026(st.session_state.plan_path,mapping={'sheet':sheet_name,'data_start_row':int(data_row),**{str(r.get('Field','')).strip():str(r.get('Excel Column','')).strip().upper() for _,r in edited_map.iterrows() if str(r.get('Field','')).strip() and str(r.get('Excel Column','')).strip()}})
        _pd_cols=[c for c in ['Work Order','Customer','Product Code','Category','Due Date','Order Qty','Shape','D','T','H','Packing Status','WO Closure','Overall Closed'] if c in _pd_src.columns]
        _pd=_pd_src[_pd_cols].copy().drop_duplicates('Work Order',keep='last')
        _pd['Planner Closed Override']=_pd.get('Overall Closed',False)
        _pd['TEST? / งานทดสอบ']=[st.session_state.test_work_override_by_wo.get(str(w).strip(),('TEST' if str(pc).strip()[:1]=='1' else 'NORMAL'))=='TEST' for w,pc in zip(_pd['Work Order'],_pd.get('Product Code',''))]
        st.markdown('### ✏️ Planning Data Editor / แก้ไขข้อมูลการวางแผน')
        st.caption('Planner-layer only: edit due date, quantity, shape/dimensions, closure and TEST/NORMAL. Original Plan2026 values remain the evidence source.')
        _editable=[c for c in ['Work Order','Customer','Product Code','Category','Due Date','Order Qty','Shape','D','T','H','Planner Closed Override','TEST? / งานทดสอบ'] if c in _pd.columns]
        _ped=st.data_editor(_pd[_editable],use_container_width=True,hide_index=True,height=420,disabled=[c for c in ['Work Order','Customer','Product Code','Category'] if c in _editable],key='f12x_planning_data_editor')
        if st.button('💾 APPLY PLANNER DATA OVERRIDES / ใช้ค่าที่แก้ไข',key='f12x_apply_data'):
            _ov={}; _tw=dict(st.session_state.test_work_override_by_wo)
            for _,_r in _ped.iterrows():
                _wo=str(_r.get('Work Order','')).strip()
                if not _wo: continue
                _ov[_wo]={k:_r.get(k) for k in ['Due Date','Order Qty','Shape','D','T','H','Planner Closed Override'] if k in _r.index}
                _tw[_wo]='TEST' if bool(_r.get('TEST? / งานทดสอบ',False)) else 'NORMAL'
            st.session_state.firing_data_override_by_wo=_ov; st.session_state.test_work_override_by_wo=_tw
            st.success('Planner overrides saved. CREATE FIRING PLAN will use these effective values; Plan2026 file is unchanged.')
    except Exception as _e:
        st.warning(f'Planning Data editor could not load: {_e}')

mapping={'sheet':sheet_name,'data_start_row':int(data_row)}
for _,_r in edited_map.iterrows():
    _f=str(_r.get('Field','')).strip();_c=str(_r.get('Excel Column','')).strip().upper()
    if _f and _c:mapping[_f]=_c

# F12V: fast Test Work selector with due-date range and bulk actions.
# CLOSED means EU Packing Status OR FC Overall WO Closure. Closed WOs are excluded by default.
st.markdown('---')
st.markdown('### 🧪 Test Work Selection / เลือกงานทดสอบ')
st.caption('Fast control: ALL WOs can be selected. Filter by Due Date or search WO/Customer/Product Code. Closed WOs are excluded by default. Product Code 1 = TEST by default; all others = NORMAL until manually selected.')
# Shared Plan-2026: use common SL Planning Center source when no local firing override was uploaded.
_shared_plan=_resolve_central('Plan-2026-LATEST.xlsx') or Path(os.environ.get('SL_COMPANY_DATA',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA'/'COMPANY_DATA')))/'Plan-2026-LATEST.xlsx'
if not st.session_state.get('plan_path') and _shared_plan.exists():
    st.session_state.plan_path=str(_shared_plan)
    st.sidebar.info('Using shared Plan-2026 from SL Planning Center / ใช้ Plan-2026 ส่วนกลาง')
_selector_path=st.session_state.get('plan_path')
if _selector_path and Path(_selector_path).exists():
    try:
        _tp_sel=coremap.read_plan2026(_selector_path,mapping=mapping)
        _cols_sel=[c for c in ['Work Order','Product Code','Customer','Category','Due Date','Packing Status','WO Closure','Overall Closed'] if c in _tp_sel.columns]
        _te_all=_tp_sel[_cols_sel].copy()
        _te_all['Work Order']=_te_all['Work Order'].fillna('').astype(str).str.strip()
        _te_all['Product Code']=_te_all.get('Product Code','').fillna('').astype(str).str.strip()
        _te_all=_te_all[_te_all['Work Order'].ne('')].copy()
        _te_all['Due Date']=pd.to_datetime(_te_all.get('Due Date'),errors='coerce').dt.date
        if 'Category' in _te_all.columns:
            _te_all['Category']=_te_all['Category'].apply(lambda v: ('PB' if str(v).strip().upper().startswith('PB') else (str(v).strip().upper()[:1] if str(v).strip().upper()[:1] in {'P','R','S','T','M'} else 'UNCLASSIFIED')))
        _te_all=_te_all.drop_duplicates('Work Order',keep='first').reset_index(drop=True)
        _valid_due=[d for d in _te_all['Due Date'].tolist() if d is not None and not pd.isna(d)]
        _dmin=min(_valid_due) if _valid_due else date.today()
        _dmax=max(_valid_due) if _valid_due else date.today()+timedelta(days=90)
        _c1,_c2,_c3=st.columns([1,1,1])
        with _c1: _tw_from=st.date_input('Due Date FROM / กำหนดส่งจาก',value=_dmin,key='f12v_tw_due_from')
        with _c2: _tw_to=st.date_input('Due Date TO / กำหนดส่งถึง',value=_dmax,key='f12v_tw_due_to')
        with _c3: _show_closed=st.checkbox('Show CLOSED / แสดงงานปิดแล้ว',False,key='f12v_tw_show_closed')
        _tw_search=st.text_input('Search WO / Customer / Product Code / ค้นหา WO ลูกค้า หรือรหัสสินค้า',value='',key='f12v_tw_search').strip().lower()
        if _tw_from>_tw_to: _tw_from,_tw_to=_tw_to,_tw_from
        _te_sel=_te_all[_te_all['Due Date'].apply(lambda d: d is not None and _tw_from<=d<=_tw_to)].copy()
        if not _show_closed and 'Overall Closed' in _te_sel.columns:
            _te_sel=_te_sel[~_te_sel['Overall Closed'].fillna(False).astype(bool)].copy()
        if _tw_search:
            _sm=pd.Series(False,index=_te_sel.index)
            for _sc in ['Work Order','Customer','Product Code']:
                if _sc in _te_sel.columns: _sm |= _te_sel[_sc].fillna('').astype(str).str.lower().str.contains(_tw_search,regex=False)
            _te_sel=_te_sel[_sm].copy()
        _saved=dict(st.session_state.get('test_work_override_by_wo',{}))
        _b1,_b2,_b3=st.columns([1,1,2])
        _select_all=_b1.button('☑️ Select all visible / เลือกทั้งหมด',use_container_width=True,key='f12v_tw_all')
        _clear_all=_b2.button('⬜ Clear all visible / ยกเลิกทั้งหมด',use_container_width=True,key='f12v_tw_none')
        _b3.caption(f'Visible WOs / WO ที่แสดง: {len(_te_sel):,}')
        if _select_all:
            for _wo in _te_sel['Work Order'].astype(str): _saved[_wo]='TEST'
        if _clear_all:
            for _wo in _te_sel['Work Order'].astype(str): _saved[_wo]='NORMAL'
        _te_sel.insert(0,'TEST? / งานทดสอบ',[(_saved.get(wo,('TEST' if pc[:1].upper()=='1' else 'NORMAL'))=='TEST') for wo,pc in zip(_te_sel['Work Order'],_te_sel['Product Code'])])
        _te_sel['Status / สถานะ']=_te_sel.get('Overall Closed',False).map(lambda x:'CLOSED / ปิดแล้ว' if bool(x) else 'OPEN / เปิด') if 'Overall Closed' in _te_sel.columns else 'OPEN / เปิด'
        _display_cols=[c for c in ['TEST? / งานทดสอบ','Work Order','Product Code','Customer','Category','Due Date','Status / สถานะ'] if c in _te_sel.columns]
        _edit_sel=st.data_editor(_te_sel[_display_cols],use_container_width=True,hide_index=True,
            disabled=[c for c in _display_cols if c!='TEST? / งานทดสอบ'],
            column_config={'TEST? / งานทดสอบ':st.column_config.CheckboxColumn('TEST? / งานทดสอบ',default=False,width='small'),
                           'Due Date':st.column_config.DateColumn('Due Date / กำหนดส่ง',format='DD/MM/YYYY')},
            key='firing_test_work_F12V_editor',height=min(560,max(180,42*(len(_te_sel)+1))))
        # Preserve overrides outside the visible filter; update only visible WOs.
        for _,_r in _edit_sel.iterrows():
            _saved[str(_r['Work Order']).strip()]=('TEST' if bool(_r['TEST? / งานทดสอบ']) else 'NORMAL')
        st.session_state.test_work_override_by_wo=_saved
        _n_test=sum(v=='TEST' for v in _saved.values())
        st.success(f'🧪 Selected Test Work / งานทดสอบที่เลือก: {_n_test:,} WO | Visible / แสดง: {len(_te_sel):,}')
    except Exception as _e_sel:
        st.error('Cannot load Test Work selection / ไม่สามารถโหลดรายการงานทดสอบ: '+str(_e_sel))
else:
    st.warning('⬅️ Upload Latest Plan 2026 first. / กรุณาอัปโหลด Plan 2026 ก่อน')
st.markdown('---')

def _cut_txt(v): return fc.txt(v)
def _cut_num(v,d=0.0): return fc.num(v,d)
def _cut_date(v): return fc.safe_date(v)
def _cut_next(d): return fc._next_workday_after(d,{0,1,2,3,4,5})

def _previous_issued_kiln_blocks(files, planning_start):
    """Read full or operator-print-only issued plans for cutover protection."""
    from apps.firing.previous_issued import previous_kiln_blocks
    return previous_kiln_blocks(files, planning_start)

def _apply_previous_kiln_blocks(fr, blocks, planning_start, starts_per_day=2):
    """Shift new loads only when they conflict with a kiln cycle already committed before cutover."""
    if not blocks:return fr
    loads=fr.get('loads',pd.DataFrame()).copy(); details=fr.get('details',pd.DataFrame()).copy()
    if loads.empty:return fr
    # Stable chronological pass; retain optimizer choices unless prior issued cycle makes them impossible.
    normal={}; resin=set(); t0={}; kiln_next=dict(blocks)
    for idx in loads.sort_values(['Load Date','Load ID'],kind='stable').index:
        r=loads.loc[idx]; lid=str(r.get('Load ID','')); k=_cut_txt(r.get('Kiln','')).upper(); d=_cut_date(r.get('Load Date')) or planning_start
        d=max(d,planning_start,kiln_next.get(k,d)); d=d if d==planning_start else _cut_next(d)  # selected start date is never shifted
        typ='RESIN' if k in {'R4','R5','R6'} else ('T0' if k=='T0' else 'NORMAL')
        while (typ=='NORMAL' and normal.get(d,0)>=int(starts_per_day)) or (typ=='T0' and t0.get(d,0)>=1) or (typ=='RESIN' and (d,k) in resin):
            d=_cut_next(d+timedelta(days=1))
        run=max(int(round(_cut_num(r.get('Running Days',1),1))),1); fin=d+timedelta(days=run)
        if typ=='NORMAL':normal[d]=normal.get(d,0)+1
        elif typ=='T0':t0[d]=t0.get(d,0)+1
        else:resin.add((d,k))
        kiln_next[k]=fin+timedelta(days=1)
        old=_cut_date(r.get('Load Date'))
        loads.at[idx,'Load Date']=d; loads.at[idx,'Program Finish Date']=fin; loads.at[idx,'Firing Complete']=fin
        if old and d>old: loads.at[idx,'Cutover / Previous Plan Protection']=f'SHIFTED {old} → {d}: previous issued {k} cycle protected'
        else: loads.at[idx,'Cutover / Previous Plan Protection']='NEW PLAN FROM SELECTED START'
        if not details.empty and 'Load ID' in details.columns:
            m=details['Load ID'].astype(str)==lid
            details.loc[m,'Load Date']=d; details.loc[m,'Program Finish Date']=fin; details.loc[m,'Firing Complete']=fin
            details.loc[m,'Cutover / Previous Plan Protection']=loads.at[idx,'Cutover / Previous Plan Protection']
    fr['loads']=loads; fr['details']=details; return fr

def _layer_key(wo):
    m=re.match(r'^(.*?)([AB])-([0-9]{6})(.*)$',str(wo).strip().upper())
    return (m.group(1),m.group(3),m.group(4)) if m else None

def _combine_two_layer_for_firing(df):
    """A/B two-layer WOs become one conservative final-part firing candidate.
    Upstream readiness uses the weaker layer; gross weight/thickness combine.
    """
    if df is None or df.empty:return df,pd.DataFrame()
    x=df.copy();x['_lk']=x['Work Order'].astype(str).map(_layer_key);used=set();out=[];audit=[]
    for i,r in x.iterrows():
        if i in used:continue
        lk=r['_lk']
        if not lk:out.append(r.drop(labels=['_lk']));used.add(i);continue
        g=x[x['_lk'].map(lambda z:z==lk)].copy();wos=sorted(g['Work Order'].astype(str).unique());hasA=any(re.match(r'^.*A-[0-9]{6}',w.upper()) for w in wos);hasB=any(re.match(r'^.*B-[0-9]{6}',w.upper()) for w in wos)
        if not (hasA and hasB):out.append(r.drop(labels=['_lk']));used.add(i);continue
        used.update(g.index.tolist()); ga=g[g['Work Order'].astype(str).str.upper().str.match(r'^.*A-[0-9]{6}')];gb=g[g['Work Order'].astype(str).str.upper().str.match(r'^.*B-[0-9]{6}')]
        base=g.sort_values('Due Date',na_position='last').iloc[0].copy();label=f'{lk[0]}A/B-{lk[1]}{lk[2]}'
        base['Work Order']=label;base['Layer Source WOs']=' | '.join(wos);base['Overall Closed']=bool(g['Overall Closed'].fillna(False).all())
        # final part quantity is limited by the layer with the lower cumulative quantity
        for sec in ['Preparation','Mixing','Forming']:
            ap=float(pd.to_numeric(ga.get(f'{sec} Actual',0),errors='coerce').fillna(0).sum());bp=float(pd.to_numeric(gb.get(f'{sec} Actual',0),errors='coerce').fillna(0).sum());base[f'{sec} Actual']=min(ap,bp)
            apl=float(pd.to_numeric(ga.get(f'{sec} Plan',0),errors='coerce').fillna(0).sum());bpl=float(pd.to_numeric(gb.get(f'{sec} Plan',0),errors='coerce').fillna(0).sum());base[f'{sec} Plan']=min(apl,bpl) if apl and bpl else max(apl,bpl)
        for sec in ['Firing','Grinding / Cutting','Packing']:
            av=float(pd.to_numeric(g.get(f'{sec} Actual',0),errors='coerce').fillna(0).max());pl=float(pd.to_numeric(g.get(f'{sec} Plan',0),errors='coerce').fillna(0).max());base[f'{sec} Actual']=av;base[f'{sec} Plan']=pl
        oqA=float(pd.to_numeric(ga.get('Order Qty',0),errors='coerce').fillna(0).sum());oqB=float(pd.to_numeric(gb.get('Order Qty',0),errors='coerce').fillna(0).sum());base['Order Qty']=min(oqA,oqB) if oqA and oqB else max(oqA,oqB)
        wa=float(pd.to_numeric(ga.get('Gross Weight g/pc',0),errors='coerce').replace(0,pd.NA).dropna().median() or 0);wb=float(pd.to_numeric(gb.get('Gross Weight g/pc',0),errors='coerce').replace(0,pd.NA).dropna().median() or 0);base['Gross Weight g/pc']=wa+wb
        try: base['T']=float(pd.to_numeric(ga.get('T',0),errors='coerce').dropna().median())+float(pd.to_numeric(gb.get('T',0),errors='coerce').dropna().median())
        except: pass
        base['Overall Closed']=bool(g['Overall Closed'].fillna(False).all());out.append(base.drop(labels=['_lk']))
        audit.append({'Combined WO':label,'Source WOs':' | '.join(wos),'Rule':'A/B two-layer: final firing candidate; readiness=min(A,B), gross weight=sum(A,B), thickness=sum when numeric'})
    y=pd.DataFrame(out).reset_index(drop=True);y=store.calculate(y)
    return y,pd.DataFrame(audit)

if pu is not None:
    p=work/'PLAN_2026_ACTIVE.xlsx'; p.write_bytes(pu.getbuffer()); st.session_state.plan_path=str(p)

# WO-level Test Work source of truth comes from the visible INPUT-sidebar selector above.
_test_override_by_wo=dict(st.session_state.get('test_work_override_by_wo',{}))

if st.button('▶ CREATE FIRING PLAN / สร้างแผนเผา', type='primary', use_container_width=True):
    plan=st.session_state.plan_path
    cap=st.session_state.cap_path
    if not plan or not Path(plan).exists(): st.error('Please upload latest Plan 2026 first.'); st.stop()
    if not prevu: st.info('No previous issued Firing Plan found: creating the first controlled firing plan without rollover history.')
    if not Path(cap).exists(): st.error('Capacity database not found.'); st.stop()

    progress=st.progress(0)
    msg=st.empty()
    timings=[]
    t0=time.time()

    # V1.9.5 keeps the confirmed factory decision rules, but Stage 4 uses a bounded
    # priority-preserving candidate window and progressively widens only when needed.
    # This prevents hundreds of irrelevant WOs from being tested against every physical placement.
    original_build=fire.build_plan
    def limited_build(prepared,kilns,settings):
        settings.max_planning_days=int(planning_days)
        t=time.time(); msg.warning('Stage 4A/6 — Fast physical screening + kiln cycle control / ตรวจสอบทางกายภาพและรอบการทำงานของเตา')
        out=fast4.build_plan_fast(prepared,kilns,settings)
        timings.append(('Fast physical kiln allocation',time.time()-t))
        progress.progress(78)
        return out
    fire.build_plan=limited_build

    try:
        t=time.time(); msg.info('Stage 1/6 — Import Plan 2026 / นำเข้า Plan 2026')
        n=store.full_sync(plan,st.session_state.db_path,mapping=mapping)
        timings.append(('Plan 2026 import',time.time()-t)); progress.progress(18)

        t=time.time(); msg.info('Stage 2/6 — Load WIP / โหลดข้อมูล WIP')
        df=store.load(st.session_state.db_path)
        # Case-insensitive canonical product categories. There is no F category.
        if 'Category' in df.columns:
            df['Category']=df['Category'].apply(lambda v: ('PB' if str(v).strip().upper().startswith('PB') else (str(v).strip().upper()[:1] if str(v).strip().upper()[:1] in {'P','R','S','T','M'} else 'UNCLASSIFIED')))
        # F12Y apply Planner Decision Layer before firing calculation.
        _fov=st.session_state.get('firing_data_override_by_wo',{}) or {}
        if _fov and 'Work Order' in df.columns:
            for _i,_r in df.iterrows():
                _wo=str(_r.get('Work Order','')).strip(); _o=_fov.get(_wo)
                if not _o: continue
                for _c in ['Due Date','Order Qty','Shape','D','T','H']:
                    if _c in df.columns and _c in _o and pd.notna(_o[_c]): df.at[_i,_c]=_o[_c]
                if 'Planner Closed Override' in _o and bool(_o['Planner Closed Override']):
                    if 'Overall Closed' in df.columns: df.at[_i,'Overall Closed']=True

        # Test-work source of truth = WO-level selection above.
        if 'Product Code' in df.columns:
            _pc=df['Product Code'].fillna('').astype(str).str.strip()
            _wo=df['Work Order'].fillna('').astype(str).str.strip()
            df['Test Work Override']=['TEST' if pc[:1]=='1' else 'NORMAL' for pc in _pc]
            for _i,_w in _wo.items():
                if _w in _test_override_by_wo:
                    df.at[_i,'Test Work Override']=_test_override_by_wo[_w]
        df,layer_audit=_combine_two_layer_for_firing(df)
        timings.append(('Load local WIP database + two-layer combine',time.time()-t)); progress.progress(28)

        t=time.time(); msg.info('Stage 3/6 — WIP + readiness check / ตรวจ WIP และความพร้อม')
        # run_firing_fast internally applies the same V4.6 queue, capacity and release rules.
        starts=min(2,max(1,int(starts)))  # F12U hard safety guard; T0/resin handled separately by engine
        fr=fc.run_firing_fast(df,cap,start,float(target),float(maxv),False,True,int(starts),bool(strict),
                              hard_pull=True,pull_horizon_days=int(planning_days),balance_target=.90,
                              validate_upstream=True,prep_capacity=1200.0,plan2026_path=plan)
        _prev_blocks,_prev_audit=_previous_issued_kiln_blocks(prevu,start)
        fr=_apply_previous_kiln_blocks(fr,_prev_blocks,start,int(starts))
        # The user-selected date is the authoritative NEW PLAN CUTOVER date. It must
        # never be silently rewritten to the first feasible kiln load date. A load may
        # occur later only for a documented physical/capacity/cycle reason.
        for _k in ['loads','details','upstream_plan','pm_validation']:
            if isinstance(fr.get(_k),pd.DataFrame):
                fr[_k]['Selected Planning Start / วันเริ่มแผน']=start
        fr['previous_plan_cutover_audit']=_prev_audit
        try:
            from plan_integrity import check_firing_result as _chk
            fr['integrity_check']=_chk(fr,start,int(starts),float(target),float(maxv))
            from plan_integrity import day1_explanation as _d1
            fr['day1_explanation']=_d1(fr,start)
            _ic=fr['integrity_check']
            if (_ic['Status']=='FAIL').any(): msg.error('PLAN INTEGRITY: FAIL - '+'; '.join(_ic[_ic['Status']=='FAIL']['Check'])+' (see Plan integrity table)')
        except Exception as _e: fr['integrity_check']=pd.DataFrame([{'Check':'Integrity checker','Status':'WARN','Detail':str(_e)}])
        _ld=fr.get('loads',pd.DataFrame())
        _first=pd.to_datetime(_ld.get('Load Date'),errors='coerce').min() if isinstance(_ld,pd.DataFrame) and not _ld.empty and 'Load Date' in _ld.columns else pd.NaT
        fr['plan_control']=pd.DataFrame([{
            'Planning Start / วันเริ่มแผน':start,
            'Rule / กฎ':'New planning horizon begins on selected date; previous issued execution is protected before this date.',
            'First Feasible Firing Load / โหลดเผาแรกที่เป็นไปได้':(_first.date() if pd.notna(_first) else ''),
            'Start-Date Note / หมายเหตุ':('Firing starts on selected date' if pd.notna(_first) and _first.date()==start else 'No firing load is forced onto the cutover date when previous kiln cycle, readiness, upstream lead-time, or capacity makes it infeasible.')
        }])
        timings.append(('Total firing engine (incl. validation)',time.time()-t)); progress.progress(96)
        fr['two_layer_audit']=layer_audit;fr['plan2026_mapping']=pd.DataFrame([{'Field':k,'Excel Column':v} for k,v in mapping.items()])
        # Authoritative execution snapshot: current quantities, process statuses and WO closure come from Latest Plan 2026 only.
        _snap_cols=[c for c in ['Work Order','Customer','Product Category','Due Date','Order Qty','Preparation Actual','Preparation Status','Mixing Actual','Mixing Status','Forming Actual','Forming Status','Firing Actual','Firing Status','Grinding / Cutting Actual','Grinding / Cutting Status','Packing Actual','Packing Status','WO Closure','Overall Closed'] if c in df.columns]
        fr['plan2026_status_snapshot']=df[_snap_cols].copy() if _snap_cols else pd.DataFrame()
        st.session_state.fr=fr
        progress.progress(100); msg.success('Finished / เสร็จสิ้น')
    except Exception as e:
        msg.error('Calculation stopped with an error. / การคำนวณหยุดเนื่องจากข้อผิดพลาด')
        _tb=traceback.format_exc()
        try:
            _lg=Path(__file__).resolve().parent.parent.parent/'logs'; _lg.mkdir(exist_ok=True)
            _lf=_lg/('firing_error_'+time.strftime('%Y%m%d_%H%M%S')+'.txt'); _lf.write_text(_tb,encoding='utf-8')
            st.error(f'{type(e).__name__}: {e}  -  full details saved to: {_lf}')
        except Exception: st.error(f'{type(e).__name__}: {e}')
        with st.expander('Technical details (send this to the developer)'): st.code(_tb)
    finally:
        fire.build_plan=original_build

    timings.append(('TOTAL',time.time()-t0))

fr=st.session_state.fr
if fr is not None:
    loads=fr.get('loads',pd.DataFrame()).copy()
    details=fr.get('details',pd.DataFrame()).copy()
    validation=fr.get('pm_validation',pd.DataFrame()).copy()
    exc=fr.get('exceptions',pd.DataFrame()).copy()
    _ic=fr.get('integrity_check')
    if isinstance(_ic,pd.DataFrame) and not _ic.empty:
        with st.expander('Plan integrity check / ตรวจความถูกต้องของแผน  -  '+('FAIL' if (_ic['Status']=='FAIL').any() else ('WARN' if (_ic['Status']=='WARN').any() else 'ALL PASS')),expanded=bool((_ic['Status']=='FAIL').any())):
            st.dataframe(_ic,use_container_width=True,hide_index=True)
            _d1=fr.get('day1_explanation')
            if isinstance(_d1,pd.DataFrame) and not _d1.empty:
                st.markdown('**Day-1 explanation / ทำไมไม่เริ่มเผาในวันที่เลือก** - loads moved later than the selected start date:')
                st.dataframe(_d1,use_container_width=True,hide_index=True)
    _dry=fr.get('drying_check')
    if isinstance(_dry,pd.DataFrame) and not _dry.empty:
        _held=int(_dry['Timing status'].eq('HOLD').sum())
        st.warning(f'Drying / curing review: {_held} held WO-load rows. No load is execution-approved until drying evidence and drier resources are confirmed. / ตรวจสอบการอบก่อนปล่อยแผน')
        with st.expander('🌬️ Drying readiness / ความพร้อมการอบ',expanded=bool(_held)):
            st.dataframe(_dry,use_container_width=True,hide_index=True)
            st.download_button('⬇ Download doubtful loads / ดาวน์โหลดโหลดที่ต้องตรวจสอบ',_dry.to_csv(index=False).encode('utf-8-sig'),'Firing_Drying_Review.csv','text/csv',key='drying_review_csv')
    prepared=fr.get('prepared',pd.DataFrame()).copy()
    if not prepared.empty and 'Due Date' in prepared.columns:
        _dd=pd.to_datetime(prepared['Due Date'],errors='coerce').dt.date
        prepared['Delivery Status']=['BACK ORDER / OVERDUE' if (d is not None and pd.notna(d) and d < start) else ('DUE TODAY' if (d is not None and pd.notna(d) and d == start) else 'FUTURE / NO DATE') for d in _dd]

    st.divider()
    a,b,c,d=st.columns(4)
    a.metric('Loads',len(loads))
    b.metric('WO detail lines',len(details))
    if not loads.empty and 'Release Gate' in loads.columns:
        c.metric('Release loads',int(loads['Release Gate'].astype(str).str.startswith('RELEASE').sum()))
        d.metric('Hold/Combine',int(loads['Release Gate'].astype(str).str.contains('HOLD',case=False,na=False).sum()))
    else:
        c.metric('Release loads',0); d.metric('Hold/Combine',0)

    overdue_count=int((prepared.get('Delivery Status',pd.Series(dtype=str))=='BACK ORDER / OVERDUE').sum()) if not prepared.empty else 0
    st.caption(f'Back-order firing candidates / งานค้างส่งในคิวเผา: {overdue_count:,} WO — overdue executable work is sorted before future due dates.')

    _LEGACY_NAV_INDEX={_NAV[0]:0,_NAV[1]:0,_NAV[2]:1,_NAV[3]:2,_NAV[4]:3,_NAV[5]:4,_NAV[6]:5,_NAV[7]:6,_NAV[8]:7,_NAV[9]:8,_NAV[10]:9,_NAV[11]:10,_NAV[12]:11}
    _nav_idx=_LEGACY_NAV_INDEX.get(_nav,1)

    if _nav_idx==11:
        _src=st.selectbox('Inspect / ตรวจสอบ',['Prepared firing candidates','Kiln loads','WO firing details'],key='fire48_data_choice')
        _df={'Prepared firing candidates':prepared,'Kiln loads':loads,'WO firing details':details}[_src]
        tv48.interactive(st,_df,_src,source='Current Firing Planner run; display-only review, never bypass release gates')
    if _nav_idx==0:
        st.markdown('## 🧪 SELECT / UNSELECT TEST WORK / เลือกหรือยกเลิกงานทดสอบ')
        st.warning('Changes here apply to the NEXT plan creation. After changing a checkbox, click CREATE FIRING PLAN again. / การเปลี่ยนแปลงมีผลเมื่อสร้างแผนเผาใหม่อีกครั้ง')
        _sp=st.session_state.get('plan_path')
        if _sp and Path(_sp).exists():
            try:
                _tt=coremap.read_plan2026(_sp,mapping=mapping)
                _cc=[c for c in ['Work Order','Product Code','Customer','Category','Due Date'] if c in _tt.columns]
                _tt=_tt[_cc].copy(); _tt['Work Order']=_tt['Work Order'].fillna('').astype(str).str.strip(); _tt['Product Code']=_tt.get('Product Code','').fillna('').astype(str).str.strip()
                # All WOs must be selectable manually; Product Code 1 only supplies the default TEST state.
                _tt=_tt.copy()
                if 'Category' in _tt.columns:
                    _tt['Category']=_tt['Category'].apply(lambda v: ('PB' if str(v).strip().upper().startswith('PB') else (str(v).strip().upper()[:1] if str(v).strip().upper()[:1] in {'P','R','S','T','M'} else 'UNCLASSIFIED')))
                _tt=_tt[_tt['Work Order'].ne('')].drop_duplicates('Work Order').reset_index(drop=True)
                _sv=dict(st.session_state.get('test_work_override_by_wo',{}))
                _tt.insert(0,'TEST? / งานทดสอบ',[(_sv.get(w,('TEST' if pc[:1].upper()=='1' else 'NORMAL'))=='TEST') for w,pc in zip(_tt['Work Order'],_tt['Product Code'])])
                _ed=st.data_editor(_tt,use_container_width=True,hide_index=True,disabled=[c for c in _tt.columns if c!='TEST? / งานทดสอบ'],column_config={'TEST? / งานทดสอบ':st.column_config.CheckboxColumn('TEST? / งานทดสอบ',default=False,width='small')},key='firing_test_work_TAB_editor',height=560)
                st.session_state.test_work_override_by_wo={str(r['Work Order']).strip():('TEST' if bool(r['TEST? / งานทดสอบ']) else 'NORMAL') for _,r in _ed.iterrows()}
                st.success(f"Selected Test Work / งานทดสอบที่เลือก: {sum(v=='TEST' for v in st.session_state.test_work_override_by_wo.values()):,} WO")
            except Exception as _e: st.error('Cannot load selector / โหลดรายการไม่ได้: '+str(_e))
        else: st.info('Upload Plan2026 first / กรุณาอัปโหลด Plan2026 ก่อน')

    if _nav_idx==1:
        if loads.empty:
            st.warning('No kiln schedule generated — this is an exception. Check open demand, program compatibility, kiln calendar and hard physical constraints.')
        else:
            sched=loads.copy()
            # F8 POSITIVE CAPACITY COMMITMENT: the kiln schedule is the PLAN, not only today's release list.
            # Show every physically planned load supported by ready WIP OR achievable upstream capacity.
            # HOLD is reserved for hard physical/capacity impossibility and is excluded from the committed schedule.
            _gate=sched.get('Release Gate',pd.Series('',index=sched.index)).astype(str).str.upper()
            sched=sched[~_gate.str.startswith('HOLD')].copy()
            if 'Planning Status' not in sched.columns:
                _mk=pd.to_numeric(sched.get('MAKE Before Firing pcs',0),errors='coerce').fillna(0)
                sched['Planning Status']=_mk.map(lambda q:'PLANNED — UPSTREAM CAPACITY COMMITMENT' if q>0 else 'READY / RELEASE')
            sched['_Load']=pd.to_datetime(sched.get('Load Date'),errors='coerce')
            sched['_Finish']=pd.to_datetime(sched.get('Program Finish Date'),errors='coerce')
            _sd=sched['_Load'].dropna()
            if not _sd.empty:
                _sc1,_sc2=st.columns(2); _sf=_sc1.date_input('Schedule FROM / ตารางจากวันที่',value=_sd.min().date(),key='f12y_sched_from'); _st=_sc2.date_input('Schedule TO / ตารางถึงวันที่',value=_sd.max().date(),key='f12y_sched_to')
                sched=sched[(sched['_Load'].dt.date>=_sf)&(sched['_Load'].dt.date<=_st)].copy()
            if not sched.empty:
                sched['Qty pcs']=pd.to_numeric(sched.get('Qty pcs',0),errors='coerce').fillna(0)
                sched['Weight kg']=pd.to_numeric(sched.get('Weight kg',0),errors='coerce').fillna(0)
                sched['Volume Util %']=pd.to_numeric(sched.get('Geometric Occupancy Util',0),errors='coerce').fillna(0)*100
                sched['Kiln / Program']=sched['Kiln'].astype(str)+' • '+sched['Program'].astype(str)
                fig_sched=px.timeline(sched,x_start='_Load',x_end='_Finish',y='Kiln',color='Program',hover_name='Kiln / Program',
                    hover_data={'Qty pcs':':,.0f','Weight kg':':,.1f','Volume Util %':':.1f','Load ID':True,'_Load':False,'_Finish':False},
                    title='POSITIVE KILN PLAN — all committed loads (ready + achievable upstream production)')
                fig_sched.update_yaxes(autorange='reversed')
                fig_sched.update_layout(height=620,xaxis_title='Date',yaxis_title='Kiln',legend_title='Program')
                _show_plotly_fire(fig_sched,'Kiln_schedule_timeline')
                show=[c for c in ['Load Date','Kiln','Program','Program Finish Date','Qty pcs','Ready Now pcs','MAKE Before Firing pcs','Volume Util %','Height Util %','Program Weight Util %','Suggested Safe Revised Due Date','Due Date Protection','Capacity Date Validation','Planning Status','Release Gate'] if c in sched.columns]
                st.dataframe(sched[show].sort_values(['Load Date','Kiln']),use_container_width=True,height=360)

    if _nav_idx==2:
        st.markdown('### 🧪 TEST WORK FIRING LIST / รายการงานทดสอบสำหรับแผนเผา')
        st.caption('Dedicated planner list. Default rule: Product Code starts with 1 = TEST. WO-level manual TEST/NORMAL selection is authoritative; code starting 4 is not assumed.')
        _td=fr.get('details',pd.DataFrame())
        if not isinstance(_td,pd.DataFrame) or _td.empty or 'Product Code' not in _td.columns:
            st.info('No Test Work found in the current firing plan / ไม่พบงานทดสอบในแผนเผาปัจจุบัน')
        else:
            _tx=_td.copy(); _tx['Product Code']=_tx['Product Code'].fillna('').astype(str).str.strip()
            _ov=_tx.get('Test Work Override',pd.Series('AUTO',index=_tx.index)).fillna('AUTO').astype(str).str.upper()
            _auto=_tx['Product Code'].str[:1].eq('1')
            _tx=_tx[((_auto)&(_ov!='NORMAL'))|(_ov=='TEST')].copy()
            if _tx.empty:
                st.info('No Test Work found in the current firing plan / ไม่พบงานทดสอบในแผนเผาปัจจุบัน')
            else:
                _ov2=_tx.get('Test Work Override',pd.Series('AUTO',index=_tx.index)).fillna('AUTO').astype(str).str.upper()
                _tx['Work Type / ประเภทงาน']=['TEST-M / งานทดสอบ M - AXIS GRINDING WHEEL' if str(pc)[:1]=='4' and str(ov)!='NORMAL' else 'TEST / งานทดสอบ' for pc,ov in zip(_tx['Product Code'],_ov2)]
                _cols=[c for c in ['Load Date','Kiln','Program','Load ID','Work Order','Product Code','Work Type / ประเภทงาน','Test Work Override','Category','Customer','Specification','Planned Firing Qty','Ready Now pcs','MAKE pcs','Due Date','Suggested Safe Revised Due Date','Due Date Protection','Planning Status','Risk','Release Gate','Release Reason'] if c in _tx.columns]
                _show=_tx[_cols].copy()
                _sort=[c for c in ['Due Date','Load Date','Kiln','Work Order'] if c in _show.columns]
                if _sort: _show=_show.sort_values(_sort,na_position='last')
                st.metric('Test Work lines / รายการงานทดสอบ',len(_show))
                st.dataframe(_show,use_container_width=True,height=520,hide_index=True)
                _csv=_show.to_csv(index=False).encode('utf-8-sig')
                st.download_button('⬇ DOWNLOAD TEST WORK LIST / ดาวน์โหลดรายการงานทดสอบ',_csv,file_name='TEST_WORK_FIRING_LIST.csv',mime='text/csv',use_container_width=True,key='download_test_work_list')

    if _nav_idx==3:
        if loads.empty:
            st.warning('No kiln utilization data.')
        else:
            z=loads.copy()
            z['_Date']=pd.to_datetime(z.get('Load Date'),errors='coerce')
            z=z.dropna(subset=['_Date'])
            if not z.empty:
                _zd=z['_Date'].dropna(); _uc1,_uc2=st.columns(2); _uf=_uc1.date_input('Utilization FROM / การใช้เตาจาก',value=_zd.min().date(),key='f12y_util_from'); _ut=_uc2.date_input('Utilization TO / การใช้เตาถึง',value=_zd.max().date(),key='f12y_util_to'); z=z[(z['_Date'].dt.date>=_uf)&(z['_Date'].dt.date<=_ut)].copy()
            if not z.empty:
                z['Kiln']=z['Kiln'].astype(str);z['Program']=z['Program'].astype(str);z['_Day']=z['_Date'].dt.strftime('%Y-%m-%d')
                z['Planned?']=~z.get('Release Gate',pd.Series('',index=z.index)).astype(str).str.upper().str.startswith('HOLD')
                rel=z.copy()  # show ALL allocated planned loads, including FUTURE PLANNED / MAKE; release gate remains visible on hover

                st.markdown('### 🔥 ALL PLANNED KILNS EACH DAY — kiln + program stack')
                st.caption('Each solid stack segment = one planned kiln load/start. Kiln is shown by color; program and exact details are shown on hover. T0 and resin remain separate resources in the scheduling rules.')
                if rel.empty:
                    st.warning('No planned kiln loads to plot.')
                else:
                    rel['Planned Load']=1
                    hover_cols=[c for c in ['Program','Load ID','Qty pcs','Weight kg','Release Gate','Release Reason','Planning Priority Class'] if c in rel.columns]
                    fig_all=px.bar(rel.sort_values(['_Date','Kiln']),x='_Day',y='Planned Load',color='Kiln',
                                   hover_data=hover_cols,barmode='stack',title='Daily kiln loading schedule — all planned kilns / ตารางเข้าเตารายวัน — เตาที่วางแผนทั้งหมด')
                    _daytot=rel.groupby('_Day',as_index=False)['Planned Load'].sum()
                    fig_all.add_scatter(x=_daytot['_Day'],y=_daytot['Planned Load'],mode='text',text=[f'{int(v)}' for v in _daytot['Planned Load']],textposition='top center',showlegend=False,hoverinfo='skip')
                    fig_all.update_layout(yaxis_title='Number of kiln loads / starts',xaxis_title='Load date',yaxis=dict(dtick=1),uniformtext_minsize=12,uniformtext_mode='show')
                    _show_plotly_fire(fig_all,'All_kilns_daily_stack')
                    # Daily normal-vitrified target audit. Keep the selected Planning Start visible even when 0 loads are feasible.
                    _cal=pd.DataFrame({'Date':pd.date_range(pd.Timestamp(start),periods=int(planning_days),freq='D')})
                    _cal=_cal[_cal['Date'].dt.weekday<6].copy();_cal['Day']=_cal['Date'].dt.strftime('%Y-%m-%d')
                    _normal=rel[rel['Kiln'].astype(str).str.upper().str.match(r'^T(?:[1-9]|1[0-2]|14)$')].groupby('_Day',as_index=False)['Planned Load'].sum().rename(columns={'_Day':'Day','Planned Load':'Normal Vitrified Starts'})
                    _audit=_cal.merge(_normal,on='Day',how='left');_audit['Normal Vitrified Starts']=_audit['Normal Vitrified Starts'].fillna(0).astype(int);_audit['Target Starts']=int(starts)
                    _audit['Gap to Target']=(_audit['Target Starts']-_audit['Normal Vitrified Starts']).clip(lower=0)
                    _audit['Reason if < target']=np.where(_audit['Gap to Target']>0,'No additional feasible allocated normal-vitrified load after due-date pull, kiln-cycle/availability, program/physical fit and upstream-capacity checks','TARGET ACHIEVED')
                    st.markdown('### 🎯 NORMAL VITRIFIED START TARGET AUDIT — selected start is never hidden')
                    st.caption('Target = 2 normal vitrified starts/day by default (T1–T12/T14; T0 excluded). A day below target remains visible with a reason instead of silently shifting the plan start.')
                    st.dataframe(_audit.head(min(len(_audit),45)),use_container_width=True,hide_index=True,height=320)

                st.markdown('### 📐 WHY THIS LOAD? — Volume vs Height vs Weight utilization')
                if not rel.empty:
                    rel['Volume %']=pd.to_numeric(rel.get('Geometric Occupancy Util',0),errors='coerce')*100
                    rel['Weight %']=pd.to_numeric(rel.get('Weight Util',0),errors='coerce')*100
                    rel['Height %']=pd.to_numeric(rel.get('Height Util',pd.Series(index=rel.index,dtype=float)),errors='coerce')*100
                    rel['Load Label']=rel['_Day']+' | '+rel['Kiln']+' | '+rel['Program']
                    um=rel.melt(id_vars=['Load Label','Kiln','Program','Load ID','Qty pcs','Release Reason','Limiting Constraint'],
                                value_vars=['Volume %','Height %','Weight %'],var_name='Utilization Measure',value_name='Utilization %')
                    fig_u=px.bar(um,x='Load Label',y='Utilization %',color='Utilization Measure',barmode='group',
                                 hover_data={'Kiln':True,'Program':True,'Load ID':True,'Qty pcs':':,.0f','Release Reason':True,'Limiting Constraint':True,'Utilization %':':.1f'},
                                 title='Kiln utilization explanation — volume / height / weight')
                    fig_u.add_hline(y=float(target)*100,line_dash='dash',annotation_text=f'Volume target {float(target)*100:.0f}%')
                    fig_u.update_layout(yaxis_title='Utilization %',xaxis_title='Date | Kiln | Program')
                    _show_plotly_fire(fig_u,'Kiln_multi_metric_utilization')
                    if rel['Height %'].isna().any():
                        st.info('Height % is blank where the fast scheduler has not yet run an exact detailed furniture pattern. It is intentionally NOT estimated. Open PATTERN LOADING for exact height validation.')

                st.markdown('### ⏳ BELOW-TARGET / WAITING FOR PARTS — REMAINING TO SELECTED OCCUPANCY')
                waiting=_waiting_for_parts(z,prepared,float(target))
                if waiting.empty:
                    st.success('No kiln is below the selected occupancy target and no HOLD/COMBINE load is waiting for parts.')
                else:
                    st.dataframe(waiting,use_container_width=True,height=330,hide_index=True)
                    wg=waiting.copy()
                    wg['Estimated Qty Needed to Target pcs']=pd.to_numeric(wg['Estimated Qty Needed to Target pcs'],errors='coerce')
                    wg=wg.dropna(subset=['Estimated Qty Needed to Target pcs'])
                    if not wg.empty:
                        wg['Kiln / Program']=wg['Kiln'].astype(str)+' | '+wg['Program'].astype(str)
                        fig_w=px.bar(wg,x='Kiln / Program',y='Estimated Qty Needed to Target pcs',color='Program',
                                     text='Estimated Qty Needed to Target pcs',
                                     hover_data={'Load Date':True,'Current Qty pcs':':,.0f','Current Volume %':':.1f','Target Volume %':':.1f',
                                                 'Weight %':':.1f','Height %':':.1f','Upstream WIP / Process Signal':True,'Candidate WOs':True,'Planning Action':True},
                                     title='Additional same-program parts estimated to reach occupancy target')
                        _show_plotly_fire(fig_w,'Kilns_waiting_for_parts')
                    st.warning('The qty-needed value is a SAME-MIX geometric estimate for upstream pull prioritization. It is not an operator release quantity until exact pattern/furniture/weight validation passes.')
            st.markdown('### 🔗 PLAN2026 INTEGRATED FIRING + UPSTREAM SUPPORT / แผนเผาเชื่อมทุกกระบวนการ')
            _isp=_integrated_support_plan(fr)
            if not _isp.empty:
                st.dataframe(_isp,use_container_width=True,hide_index=True,height=440)
                st.caption('Firing demand pulls Preparation → Mixing → Forming. Completed WIP pushes forward. FUTURE PULL is a target, not shop-floor release before readiness validation.')
            _bal=_daily_vitrified_balance(z if 'z' in locals() else loads,int(starts))
            if not _bal.empty:
                st.markdown('### 🔥 DAILY VITRIFIED START BALANCE / สมดุลการเริ่มเตารายวัน')
                st.dataframe(_bal,use_container_width=True,hide_index=True,height=300)
            st.markdown('### 🏭 UPSTREAM PULL BY FIRING PROGRAM / ปริมาณที่ต้องเร่งจากกระบวนการก่อนหน้า')
            _up=_all_program_upstream_pull(prepared,z if 'z' in locals() else loads,float(target))
            if not _up.empty:
                st.dataframe(_up,use_container_width=True,hide_index=True)
                st.caption('This table intentionally includes programs such as P6 even when no firing load can be released yet. It separates READY quantity from NOT-YET-READY upstream quantity.')
            st.markdown('### 📅 ALL OPEN WOs — REQUIRED PROCESS & DATE / ทุก WO ที่เปิดอยู่')
            _fd=_full_demand_process_pull(prepared,z if 'z' in locals() else loads,start)
            if not _fd.empty:
                st.dataframe(_fd,use_container_width=True,hide_index=True,height=420)
                st.caption('All open demand remains visible. A WO that is not firing-ready is not silently dropped: required Preparation/Mixing/Forming/Firing dates are shown as an upstream production signal.')

                st.markdown('### Daily kiln resource audit')
                if not rel.empty:
                    rel['Type Group']=rel['Kiln'].map(lambda k:'T0 AUX' if k.upper()=='T0' else ('RESIN' if k.upper() in {'R4','R5','R6'} else 'NORMAL VITRIFIED'))
                    daily=rel.groupby(['_Day','Type Group'],as_index=False)['Load ID'].nunique().rename(columns={'Load ID':'Starts'})
                    piv=daily.pivot(index='_Day',columns='Type Group',values='Starts').fillna(0).reset_index()
                    st.dataframe(piv,use_container_width=True,hide_index=True)
    if _nav_idx==4:
        if loads.empty: st.warning('No load generated for selected date(s).')
        else:
            showcols=[c for c in ['Load ID','Load Date','Original Proposed Load Date','Kiln','Program','Running Days','Program Finish Date','Qty pcs','Weight kg','Geometric Occupancy Util','Height Util','Weight Util','Limiting Constraint','Ready Now pcs','MAKE Before Firing pcs','Suggested Safe Revised Due Date','Due Date Protection','Capacity Date Validation','Release Gate','Release Reason'] if c in loads.columns]
            st.dataframe(loads[showcols] if showcols else loads,use_container_width=True,height=520)
    if _nav_idx==5:
        release_ids=[]
        if not loads.empty:
            mask=~loads.get('Release Gate',pd.Series(['']*len(loads))).astype(str).str.upper().str.startswith('HOLD')
            release_ids=loads.loc[mask,'Load ID'].astype(str).tolist()
        if not release_ids:
            st.warning('No released load available for pattern verification / ไม่มีโหลดที่ปล่อยสำหรับตรวจสอบรูปแบบ')
        else:
            lid=st.selectbox('Load / โหลด',release_ids,key='pattern_load')
            st.caption('TOP = selected floor. FRONT + SIDE = complete kiln load. Nested R parts are drawn centered inside the verified host hole. / TOP = ชั้นที่เลือก, FRONT + SIDE = โหลดทั้งเตา และชิ้นงาน R ที่ซ้อนในรูจะแสดงตรงกลางรูที่ตรวจสอบแล้ว')
            if st.button('SHOW DETAILED 3-VIEW PATTERN / แสดงรูปแบบ 3 มิติ',key='pattern_btn'):
                with st.spinner('Generating selected-load furniture pattern / กำลังสร้างรูปแบบอุปกรณ์สำหรับโหลดที่เลือก'):
                    try:
                        floorx,_,_,_=pat16.exact_pattern_for_load(fr,lid)
                        ok,issues=pat16.validate_pattern(floorx)
                        st.session_state['pattern_floor']=floorx
                        st.session_state['pattern_lid']=lid
                        st.session_state['pattern_ok']=ok
                        st.session_state['pattern_issues']=issues
                        st.session_state['pattern_error']=''
                        st.session_state['pattern_error_lid']=''
                    except Exception as e:
                        st.session_state['pattern_error']=str(e)
                        st.session_state['pattern_error_lid']=lid
                        st.session_state['pattern_floor']=pd.DataFrame()
                        st.session_state['pattern_lid']=lid
                        st.error(str(e))
            _perr=st.session_state.get('pattern_error','') if st.session_state.get('pattern_error_lid')==lid else ''
            if _perr:
                st.warning('Exact pattern is not released. You can still generate an A4 R/large-part furniture review sheet to show Production the kiln/part dimensions and the exact unresolved constraint. This review print is NOT a release authorization.')
                if st.button('🖨️ CREATE A4 R / LARGE-PART REVIEW',key='operator_review_btn',use_container_width=True):
                    try:
                        xp,pp=opprint.create_large_part_review_files(fr,lid,work/'OPERATOR_PRINT',_perr)
                        st.session_state['operator_review_xlsx']=xp;st.session_state['operator_review_pdf']=pp
                        st.success('Large-part review sheet created. Status remains NOT RELEASED until furniture/pattern validation passes.')
                    except Exception as e:
                        st.error('Review print error: '+str(e))
                _rx=st.session_state.get('operator_review_xlsx');_rp=st.session_state.get('operator_review_pdf')
                if _rx and Path(_rx).exists():st.download_button('⬇️ A4 REVIEW EXCEL',Path(_rx).read_bytes(),file_name=Path(_rx).name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
                if _rp and Path(_rp).exists():st.download_button('⬇️ A4 REVIEW PDF',Path(_rp).read_bytes(),file_name=Path(_rp).name,mime='application/pdf',use_container_width=True)
            floorx=st.session_state.get('pattern_floor')
            if isinstance(floorx,pd.DataFrame) and not floorx.empty and st.session_state.get('pattern_lid')==lid:
                if st.session_state.get('pattern_ok',False):
                    st.success('PHYSICAL PATTERN CHECK: PASS — no base-part collision and nested parts fit inside host holes. / ตรวจรูปแบบทางกายภาพ: ผ่าน')
                else:
                    st.error('PHYSICAL PATTERN CHECK: HOLD — collision/nesting problem detected. Do not release this pattern. / ตรวจพบการชนหรือการซ้อนผิด ห้ามปล่อยรูปแบบนี้')
                    st.dataframe(pd.DataFrame({'Pattern issue':st.session_state.get('pattern_issues',[])}),use_container_width=True)
                floors=sorted(pd.to_numeric(floorx['Floor'],errors='coerce').dropna().astype(int).unique().tolist()) if 'Floor' in floorx.columns else []
                if floors:
                    fno=st.selectbox('Top-view floor / ชั้นสำหรับมุมบน',floors,key='pattern_floor_no')
                    fx=floorx[pd.to_numeric(floorx['Floor'],errors='coerce').fillna(-1).astype(int)==int(fno)].copy()
                    _zoom=st.slider('Whole 2-view zoom / ซูม TOP+FRONT / ပုံချဲ့',100,220,120,10,key='pattern_zoom')/100.0
                    st.caption('TOP / FRONT use the same on-screen plot rectangle. SIDE view removed for operator clarity.')
                    st.markdown('**Selected-area zoom / ซูมพื้นที่ที่เลือก**')
                    _zc1,_zc2,_zc3,_zc4=st.columns(4)
                    _zview=_zc1.selectbox('View',['ALL','TOP','FRONT'],key='area_zoom_view')
                    _zx=_zc2.slider('Center X %',0,100,50,5,key='area_zoom_x')
                    _zy=_zc3.slider('Center Y %',0,100,50,5,key='area_zoom_y')
                    _zfactor=_zc4.slider('Area zoom ×',1.0,5.0,1.0,0.5,key='area_zoom_factor')
                    fig=pat16.draw_three_views(floorx,int(fno),lid,kiln_info=pat16.kiln_info_for_load(fr,lid),zoom=_zoom,
                                              zoom_view=_zview,zoom_x_pct=_zx,zoom_y_pct=_zy,area_zoom=_zfactor)
                    st.pyplot(fig,use_container_width=False)
                    _png=work/f'{lid}_2VIEW_ZOOM.png'
                    fig.savefig(_png,dpi=180,bbox_inches='tight')
                    plt.close(fig)
                    st.download_button('⬇️ HIGH-RES TOP+FRONT PNG / รูปความละเอียดสูง',_png.read_bytes(),
                                       file_name=_png.name,mime='image/png',use_container_width=True,key='pattern_png')
                st.dataframe(floorx,use_container_width=True,height=360)
                st.markdown('### 🖨️ A4 OPERATOR PRINT / ใบงาน A4 / A4 အော်ပရေတာစာရွက်')
                st.caption('One selected kiln/load only. Includes date, kiln, program, WO, pcs, clear TOP + FRONT pattern, part shape/dimensions, refractory plates and I-block/support nodes. Thai and Myanmar are rendered with dedicated fonts. Excel is A4 print-ready; PDF is generated directly.')
                if st.button('🖨️ CREATE A4 EXCEL + PDF / สร้างใบงาน A4',key='operator_print_btn',use_container_width=True):
                    try:
                        xp,pp,_=opprint.create_operator_files(fr,lid,work/'OPERATOR_PRINT')
                        st.session_state['operator_xlsx']=xp;st.session_state['operator_pdf']=pp
                        if pp is None:
                            st.warning('PDF library (ReportLab) is not installed. Excel A4 operator sheet was created. Restart using START_FIRING_PLANNER.bat to install the PDF library automatically.')
                        st.success('Operator sheet created / สร้างใบงานเรียบร้อย')
                    except Exception as e:
                        st.error('Operator print error: '+str(e))
                xp=st.session_state.get('operator_xlsx');pp=st.session_state.get('operator_pdf')
                if xp and Path(xp).exists():
                    st.download_button('⬇️ A4 EXCEL / ดาวน์โหลด Excel',Path(xp).read_bytes(),file_name=Path(xp).name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
                if pp and Path(pp).exists():
                    st.download_button('⬇️ A4 PDF / ดาวน์โหลด PDF',Path(pp).read_bytes(),file_name=Path(pp).name,mime='application/pdf',use_container_width=True)
    if _nav_idx==6: st.dataframe(details,use_container_width=True,height=520)
    if _nav_idx==7: st.dataframe(validation,use_container_width=True,height=520)
    if _nav_idx==8: st.dataframe(exc,use_container_width=True,height=520)
    if _nav_idx==9:
        st.markdown('## 🧪 TEST WORK SELECTOR / เลือกงานทดสอบ')
        st.info('Select or unselect any WO here. Product Code starting with 1 is TEST by default. Changes apply when you click CREATE FIRING PLAN again. / เลือกหรือยกเลิกงานทดสอบได้ทุก WO รหัสสินค้าที่ขึ้นต้นด้วย 1 เป็นงานทดสอบโดยอัตโนมัติ การเปลี่ยนแปลงจะมีผลเมื่อกด CREATE FIRING PLAN อีกครั้ง')
        if isinstance(prepared,pd.DataFrame) and not prepared.empty and 'Work Order' in prepared.columns:
            _cand=prepared.copy()
            _cols=[c for c in ['Work Order','Product Code','Customer','Category','Due Date','Calculated Current Process','Remaining Qty'] if c in _cand.columns]
            _cand=_cand[_cols].copy().drop_duplicates('Work Order').reset_index(drop=True)
            if 'Product Code' not in _cand.columns: _cand['Product Code']=''
            _cand['Work Order']=_cand['Work Order'].fillna('').astype(str).str.strip()
            _cand['Product Code']=_cand['Product Code'].fillna('').astype(str).str.strip()
            _sv=dict(st.session_state.get('test_work_override_by_wo',{}))
            _cand.insert(0,'TEST? / งานทดสอบ',[(_sv.get(w,('TEST' if pc[:1].upper()=='1' else 'NORMAL'))=='TEST') for w,pc in zip(_cand['Work Order'],_cand['Product Code'])])
            _ced=st.data_editor(_cand,use_container_width=True,hide_index=True,disabled=[c for c in _cand.columns if c!='TEST? / งานทดสอบ'],column_config={'TEST? / งานทดสอบ':st.column_config.CheckboxColumn('TEST? / งานทดสอบ',default=False,width='small')},key='firing_test_work_CANDIDATE_editor',height=430)
            st.session_state.test_work_override_by_wo={str(r['Work Order']).strip():('TEST' if bool(r['TEST? / งานทดสอบ']) else 'NORMAL') for _,r in _ced.iterrows()}
            st.success(f"Selected Test Work / งานทดสอบที่เลือก: {sum(v=='TEST' for v in st.session_state.test_work_override_by_wo.values()):,} WO")
        else:
            st.warning('No candidate WO available / ไม่มี WO ในรายการ Candidate')
        st.markdown('### Candidate Detail / รายละเอียด Candidate')
        st.dataframe(prepared,use_container_width=True,height=420)
    if _nav_idx==10:
        st.markdown('### A/B two-layer combination audit');st.dataframe(fr.get('two_layer_audit',pd.DataFrame()),use_container_width=True,height=300)
        st.markdown('### Plan 2026 column mapping used');st.dataframe(fr.get('plan2026_mapping',pd.DataFrame()),use_container_width=True,height=300)
        st.markdown('### Previous plan rollover audit / ตรวจสอบการต่อแผนเดิม');st.dataframe(fr.get('previous_plan_cutover_audit',pd.DataFrame()),use_container_width=True,height=220)
        st.markdown('### Latest Plan 2026 status snapshot — authoritative / สถานะล่าสุดจาก Plan 2026');st.dataframe(fr.get('plan2026_status_snapshot',pd.DataFrame()),use_container_width=True,height=300)
        _td=fr.get('details',pd.DataFrame())
        if isinstance(_td,pd.DataFrame) and not _td.empty and 'Product Code' in _td.columns:
            _tx=_td.copy(); _tx['Product Code']=_tx['Product Code'].fillna('').astype(str).str.strip()
            _auto=_tx['Product Code'].str[:1].eq('1'); _ov=_tx.get('Test Work Override',pd.Series('AUTO',index=_tx.index)).fillna('AUTO').astype(str).str.upper(); _tx=_tx[((_auto)&(_ov!='NORMAL'))|(_ov=='TEST')].copy()
            st.markdown('### 🧪 TEST WORK / งานทดสอบ — Product Code starts with 1 by default; WO manual selection can override')
            if _tx.empty: st.info('No planned Test Work found in the current firing plan / ไม่พบงานทดสอบในแผนเผาปัจจุบัน')
            else:
                _tx['Work Type / ประเภทงาน']='TEST / งานทดสอบ'
                _cols=[c for c in ['Load Date','Kiln','Program','Work Order','Product Code','Test Work Override','Work Type / ประเภทงาน','Category','Customer','Specification','Planned Firing Qty','Ready Now pcs','MAKE pcs','Due Date','Planning Status','Risk'] if c in _tx.columns]
                st.dataframe(_tx[_cols],use_container_width=True,height=320)


    st.warning('Release check / ตรวจสอบก่อนปล่อยแผน: confirm actual forming status, kiln condition and furniture availability. T0 is the existing small auxiliary vitrified kiln, normally urgent/test work, and does not consume the two normal-vitrified daily loading slots. R4/R5/R6 are separate resin resources. Every newly planned kiln load, including T0, blocks that kiln for the full program running cycle and the next load is allowed only on the next working day after program finish. / ยืนยันสถานะขึ้นรูป สภาพเตา และอุปกรณ์เตา T0 ใช้ในการวางแผนอัตโนมัติได้ตามปกติ และโหลดใหม่ทุกโหลดรวมถึง T0 จะล็อกเตาตลอดรอบโปรแกรม โดยโหลดถัดไปเริ่มได้ในวันทำงานถัดไปหลังโปรแกรมจบ')

    out=work/'FIRING_PLAN_OUTPUT_V1_9_12.xlsx'
    try:
        fc.save_firing(fr,str(out))
    except Exception as e:
        st.error('Excel output error / เกิดข้อผิดพลาดในการสร้าง Excel: '+str(e))
    if out.exists():
        data=out.read_bytes()
        try:
            _shared_out=Path(os.environ.get('SL_COMPANY_DATA',str(Path(__file__).resolve().parents[2]/'CENTRAL_DATA'/'COMPANY_DATA')))/'Firing-Plan-LATEST.xlsx'
            _shared_out.parent.mkdir(parents=True,exist_ok=True); _shared_out.write_bytes(data)
            st.success('Shared Firing Plan updated automatically. Daily Planner and Capacity use this same file.')
        except Exception as _se: st.warning(f'Shared firing output could not be updated: {_se}')
        st.download_button('⬇ DOWNLOAD FIRING PLAN EXCEL / ดาวน์โหลดแผนเผา Excel',data,file_name=out.name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)

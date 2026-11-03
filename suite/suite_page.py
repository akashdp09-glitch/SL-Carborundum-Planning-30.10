"""Planning Suite page (Streamlit). Imported lazily by hub.py inside try/except so a fault here can never break the rest of the app."""
from __future__ import annotations
import datetime as dt, os
from pathlib import Path
import pandas as pd
import streamlit as st
from suite.common import bkk_now, bkk_today
import streamlit.components.v1 as components
from .plan_reader import load_plan, ORDER
from . import planners as P, exporters as X, revision as R
from .help_f1 import search, topics_for_page

_F1_LABEL = 'F1 Help - ask about any code, process, schedule'

def install_f1(root: Path):
    """Sidebar help box + global F1 key (focuses the box)."""
    q = st.sidebar.text_input(_F1_LABEL, key='f1_query', placeholder='Press F1 anywhere, type e.g. resin, 128, P005-110826')
    page = st.query_params.get('page', 'control')
    with st.sidebar.expander('This page / หน้านี้', expanded=False):
        for e in topics_for_page(page):
            st.markdown(f"**{e['en_title']}**")
            st.caption(e['en'][:280] + ('…' if len(e['en']) > 280 else ''))
            st.caption('Source: ' + '; '.join(e['cites'][:2]))
    if q:
        hits = search(q, root)
        with st.sidebar:
            if not hits: st.caption('No match. Try another word.')
            for _, kind, title, body in hits: 
                with st.expander(f'{kind}: {title}'): st.write(body)
    components.html("""<script>
    const d=window.parent.document; if(!d.__f1){d.__f1=1; d.addEventListener('keydown',e=>{ if(e.key==='F1'){e.preventDefault();
    const el=d.querySelector('input[aria-label="%s"]'); if(el){ const sb=d.querySelector('[data-testid="stSidebar"]'); el.scrollIntoView(); el.focus(); el.select(); } }}); }
    </script>""" % _F1_LABEL, height=0)

@st.cache_data(show_spinner='Reading Plan-2026 (first time only)...', ttl=3600)
def _plan(path: str, mtime: float, cache_dir: str): return load_plan(path, cache_dir=cache_dir)

def _dl(label, sheets, fname, key, warn=None):
    st.download_button(f'⬇️ {label}', X.to_workbook(sheets, warn), file_name=fname, key=key,
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

def render(fp, DATA: Path, SHARED_ROOT: Path, register_source=None, user=''):
    st.markdown('## 🧰 Planning Suite — Bond · Material · Daily · Weekly · Monthly · Backorder · Revised Plan-2026')
    plan_path = fp('Plan-2026-LATEST.xlsx')
    if not plan_path:
        st.info('No active Plan-2026. You can create a bond/material scenario manually below; import Plan-2026 centrally to seed WO demand.')
        from .requirements_page import render as render_requirements
        render_requirements(pd.DataFrame(),None,DATA,SHARED_ROOT)
        return
    from zoneinfo import ZoneInfo
    today = st.date_input('Planning date (today)', dt.datetime.now(ZoneInfo('Asia/Bangkok')).date(), key='suite_today')
    (SHARED_ROOT / 'CACHE').mkdir(parents=True, exist_ok=True)
    try: plan = _plan(str(plan_path), Path(plan_path).stat().st_mtime, str(SHARED_ROOT / 'CACHE'))
    except Exception as e: st.error(f'Cannot read Plan-2026 master sheet (expected "แผนการเผา" or "Plan2026"): {e}'); return
    op = plan[plan['open']]
    c = st.columns(5); c[0].metric('Plan WOs', len(plan)); c[1].metric('Open WOs', len(op))
    c[2].metric('Overdue (open)', int(sum(1 for d in op['due'] if d and d < today))); c[3].metric('Waiting in Grinding', int((op.current_section == 'Grinding').sum()))
    c[4].metric('Waiting in Mixing/Prep', int(op.current_section.isin(['Preparation', 'Mixing']).sum()))
    t = st.tabs(['🧪 Bond', '🧱 Material', '📅 Daily by section', '🗓️ Weekly / Monthly', '🚨 Backorder', '✅ Open / Closed (Plan-2026)', '🆕 New orders', '📝 Revised Plan-2026 (audit)', '💎 Diamond · 📦 Packaging', '⬇️ Download all', '🧮 Generate bond / material plans', '🆕 New part / MPS-MRP', '📊 September analysis'])
    with t[10]:
        from .requirements_page import render as render_requirements
        render_requirements(plan,plan_path,DATA,SHARED_ROOT)
    from .source_manager import SourceManager
    _sm = SourceManager(SHARED_ROOT, DATA)
    with t[11]:
        from .newpart_page import render as render_newpart
        _sp = fp('Stock-on-Hand-LATEST.xlsx'); _stock = None
        if _sp:
            try: _stock = P.read_material_stock(_sp)
            except Exception as e: st.warning(f'Stock sheet not readable ({e}); material checks will say UNKNOWN.')
        render_newpart(_sm, plan, _stock, user, 'np')
    with t[12]:
        from .sept_page import render as render_sept
        render_sept(_sm, 'sept')
    sheets = {}
    with t[0]:
        st.caption('Demand = bond grams (Plan col BE) of open WOs not yet mixed. Rules: +20% uplift, safety = 1.5 × average monthly use, lots from the MRP remark. Change them below.')
        bp = DATA / 'Bond-MRP-LATEST.xlsx'
        up = st.file_uploader('Bond MRP workbook (MRP_BOND….xlsx) — stored centrally', type=['xlsx'], key='suite_bond_up')
        if up is not None and st.button('Save as active Bond MRP', key='suite_bond_save'):
            bp.write_bytes(up.getvalue())
            if register_source: register_source('Bond-MRP-LATEST.xlsx', bp, user, '', up.name, 'Planning Suite')
            st.success('Saved.')
        if bp.exists():
            a, b_, c_ = st.columns(3); h = a.number_input('Horizon (days)', 7, 120, 45, key='bh'); u = b_.number_input('Uplift %', 0, 100, 20, key='bu') / 100; sx = c_.number_input('Safety × avg', 0.0, 4.0, 1.5, key='bs')
            try:
                import openpyxl; names = openpyxl.load_workbook(bp, read_only=True).sheetnames
                sh = st.selectbox('Bond sheet', names, index=0, key='bsh')
                bt, bd = P.bond_plan(plan, P.read_bond_mrp(bp, sh), today, h, u, sx); sheets['Bond'] = bt; sheets['Bond WO detail'] = bd
                st.dataframe(bt, use_container_width=True, hide_index=True); st.caption('Drill-down: WOs behind each bond'); st.dataframe(bd, use_container_width=True, hide_index=True, height=260)
            except Exception as e: st.error(f'Bond sheet not readable: {e}')
        else: st.info('Upload the bond MRP workbook once.')
    with t[1]:
        sp = fp('Stock-on-Hand-LATEST.xlsx')
        if not sp: st.info('Upload Stock on hand first (Home / Sources).')
        else:
            try:
                mt, mu = P.material_plan(plan, P.read_material_stock(sp)); sheets['Material'] = mt
                st.caption('Need = grams in Plan R..AA for open, not-yet-mixed WOs. Compare with the stock sheet’s own “open WO” figure (last column).')
                f = st.radio('Show', ['Short only', 'All'], horizontal=True, key='mf')
                st.dataframe(mt[mt.status != 'OK'] if f == 'Short only' else mt, use_container_width=True, hide_index=True)
            except Exception as e: st.error(f'Stock sheet "Abrasive" not readable: {e}')
    with t[2]:
        st.caption('No capacity is assumed. For each section pick a registry capacity (shows source file / sheet / cell / unit / basis) or type your own. '
                   'Without a capacity the queue is listed UNSCHEDULED. Sunday is non-working (owner decision) and holidays are selected below.')
        from .capacity import load_capacity
        capfile = Path(__file__).resolve().parents[1] / 'apps' / 'daily' / 'CAPACITY_DATABASE.xlsx'
        from .calendar_ui import calendar_inputs, store_for
        from .user_settings import effective_out_of_service
        offi, hols = calendar_inputs(store_for(SHARED_ROOT), user, 'suite_cal')
        reg = load_capacity(capfile, out_of_service_cells=effective_out_of_service(store_for(SHARED_ROOT))) if capfile.exists() else None
        cols = st.columns(3); secs = {}
        kind_unit = {'Preparation': 'mills', 'Mixing': 'mills'}
        for i, s in enumerate(ORDER):
            unit = kind_unit.get(s, 'pcs'); cap = 0.0; label = 'none'
            opts = []
            if reg:
                want = 'mill_count' if unit == 'mills' else 'pieces'
                opts = [r for r in reg.records if r.section == s and r.unit_kind == want and r.time_basis == 'per day' and r.schedulable]
            choice = cols[i % 3].selectbox(f'{s}: capacity source ({unit}/day)', ['(none - unscheduled)', '(type my own)'] + [f'{r.resource} = {r.value:g} {r.unit}/day [{r.sheet}!{r.cell}]' for r in opts], key=f'capsrc_{s}')
            if choice == '(type my own)':
                cap = cols[i % 3].number_input(f'{s} capacity/day ({unit}) - user-entered, unverified', 0.0, 1e7, 0.0, key=f'cap_{s}')
            elif choice.startswith('(none'):
                cap = 0.0
            else:
                cap = opts[[f'{r.resource} = {r.value:g} {r.unit}/day [{r.sheet}!{r.cell}]' for r in opts].index(choice)].value
            sd = P.section_daily(plan, s, today, cap or None, unit, non_working_weekdays=offi, holidays=hols); secs[s] = X.daily_status_format(sd, s, plan)
        pick = st.selectbox('Section', ORDER, key='dsec'); st.dataframe(secs[pick], use_container_width=True, hide_index=True)
        sheets.update({f'Daily {k}': v for k, v in secs.items()})
        _dl('Daily plan, all sections (Daily-Status layout)', {k: v for k, v in secs.items()}, f'Daily_Plan_{today:%Y%m%d}.xlsx', 'dl_daily', {k: 'Late' for k in secs})
    with t[3]:
        for f, nm in (('W', 'Weekly'), ('M', 'Monthly')):
            tab, det = P.period_plan(plan, today, f); sheets[f'{nm} plan'] = tab.reset_index(); sheets[f'{nm} detail'] = det[['period', 'wo', 'customer', 'spec', 'due', 'current_section', 'remaining_qty']]
            st.markdown(f'**{nm} plan — open WOs by due period and the section they are waiting in**'); st.dataframe(tab, use_container_width=True)
    with t[4]:
        bo = P.backorder_plan(plan, today); sheets['Backorder'] = bo
        st.caption('Production backorder only. Whether MATERIAL is still outstanding is on the Bond/Material tabs.')
        st.dataframe(bo, use_container_width=True, hide_index=True, height=420)
    with t[5]:
        st.caption('Open / closed status of every WO by section, straight from the active Plan-2026 (closure columns CY, DH, DR, EC, EL, EU and FC). Daily-Status-based open/closed is on Daily Open / Closed Work Orders.')
        rows = []
        for s_ in ORDER:
            cl = int(plan[f'{s_}.closed'].sum()); rows.append({'Section': s_, 'Closed WOs': cl, 'Open WOs (not closed)': len(plan) - cl,
                                                              'Open WOs also open overall': int((~plan[f'{s_}.closed'] & plan['open']).sum())})
        rows.append({'Section': 'WHOLE ORDER (EU or FC)', 'Closed WOs': int((~plan['open']).sum()), 'Open WOs (not closed)': int(plan['open'].sum()), 'Open WOs also open overall': int(plan['open'].sum())})
        oc = pd.DataFrame(rows); st.dataframe(oc, use_container_width=True, hide_index=True); sheets['Open-Closed summary'] = oc
        from . import closure_rules as CR
        _cl = CR.classify(plan, today); _cs = CR.summary(_cl)
        st.markdown('**Closure rule (CLOSE-1/2): order closed = Packing EU closed OR FC closed; earlier section closures never close the order**'); st.dataframe(_cs, use_container_width=True, hide_index=True); sheets['Closure rule summary'] = _cs
        pick2 = st.selectbox('Show open WOs currently waiting in', ['All'] + ORDER, key='ocsec')
        lst = op if pick2 == 'All' else op[op.current_section == pick2]
        lst = lst[['wo', 'customer', 'spec', 'due', 'qty', 'current_section', 'status', 'remark']]; sheets['Open WOs'] = lst
        st.dataframe(lst, use_container_width=True, hide_index=True, height=360)
    with t[6]:
        st.info('New-order requests (RP → WO → Cover sheet → Plan-2026 row) use the existing planner: sidebar ▸ “RP → Work Order → Cover Sheet → Plan 2026”. Its output can feed this suite after it is appended to Plan-2026.')
    with t[7]:
        dbp = Path(os.environ.get('SL_DB_PATH', str(SHARED_ROOT / 'DATA' / 'sl_planning.db')))
        dbp = st.text_input('Mobile/scanner audit database', str(dbp), key='audb')
        since = st.date_input('Only audits since', bkk_today() - dt.timedelta(days=30), key='aus')
        if Path(dbp).exists():
            try:
                a = R.read_latest_audits(dbp); rv, ch = R.revise(plan, a, since); st.write(f'{len(ch)} audited WOs in range'); st.dataframe(ch, use_container_width=True, hide_index=True)
                keep = [c for c in rv.columns if '.' not in c]
                _dl('Revised Plan-2026 (proposed corrections + change log)', {'Plan-2026 revised': rv[keep], 'Audit changes': ch}, f'Plan2026_REVISED_{today:%Y%m%d}.xlsx', 'dl_rev', {'Plan-2026 revised': 'proposed_action'})
                st.caption('Original workbook is never modified. Proposed section corrections are marked; confirm before applying to the master file.')
            except Exception as e: st.error(f'Audit database not readable: {e}')
        else: st.warning('Audit database not found. Set the path used by the mobile server (SL_DB_PATH).')
    with t[8]:
        st.info('Existing planners are unchanged: 💎 Tooling/Diamond Plan is inside Daily Plan ▸ Tooling; 📦 Packaging Plan is sidebar ▸ Packaging Plan (uses the latest Packaging-Standard source).')
    with t[9]:
        if sheets: _dl('ALL plans in one workbook', sheets, f'SL_Plans_{today:%Y%m%d}.xlsx', 'dl_all')

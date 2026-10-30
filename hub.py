from __future__ import annotations
import io, os, re, sys, socket, sqlite3, ssl, subprocess, urllib.request, urllib.parse, zipfile, math, shutil, json, hashlib, secrets, posixpath, tempfile, base64, threading, xml.etree.ElementTree as ET
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd, numpy as np, streamlit as st, plotly.express as px
import streamlit.components.v1 as components
from openpyxl import load_workbook, Workbook
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
import qrcode
from suite.common import bkk_now, bkk_today
from suite.backorder_views import overdue_backorders, overdue_month_category, overdue_backorder_totals
from apps.daily import packaging_standard_source as packing_source
from apps.daily import production_wip_sources as wip_sources

ROOT=Path(__file__).resolve().parent
SHARED_ROOT=Path(os.environ.get('SL_SHARED_ROOT',str(ROOT/'CENTRAL_DATA'))).resolve()
DATA=Path(os.environ.get('SL_COMPANY_DATA',str(SHARED_ROOT/'COMPANY_DATA'))).resolve(); DATA.mkdir(parents=True,exist_ok=True)
REPORTS=Path(os.environ.get('SL_REPORT_ROOT',str(SHARED_ROOT/'REPORTS'))).resolve(); REPORTS.mkdir(parents=True,exist_ok=True)
SOURCE_ARCHIVE=Path(os.environ.get('SL_SOURCE_COPY_ROOT',str(SHARED_ROOT/'SOURCE_COPIES'))).resolve(); SOURCE_ARCHIVE.mkdir(parents=True,exist_ok=True)
REGISTRY=SHARED_ROOT/'source_registry.json'
from suite.source_manager import SourceManager, SLOTS as SM_SLOTS
from suite.central_paths import write_pointer as _write_runtime_pointer, resolve_plan as _resolve_shared_plan, child_environ as _child_environ
SM=SourceManager(SHARED_ROOT,DATA,SOURCE_ARCHIVE,REGISTRY)

@st.cache_data(show_spinner=False, max_entries=4)
def _cached_home_photo(path, mtime_ns, size):
    """Embed one small, bundled factory photo; key changes only when the image changes."""
    return base64.b64encode(Path(path).read_bytes()).decode('ascii')
try: _write_runtime_pointer(ROOT)
except Exception: pass
_TARGET_SLOT={_s.legacy_target:_s.slot_id for _s in SM_SLOTS.values() if _s.legacy_target and '/' not in _s.legacy_target}
# First V12 start: seed central storage from the prior package's company_data so existing uploads are not lost.
_legacy_data=ROOT/'company_data'
if _legacy_data.exists():
    for _p in _legacy_data.glob('*'):
        if _p.is_file() and not (DATA/_p.name).exists():
            try: shutil.copy2(_p,DATA/_p.name)
            except Exception: pass
OVERRIDE_DB=SHARED_ROOT/'DATABASE'/'sl_planning.db'; OVERRIDE_DB.parent.mkdir(parents=True,exist_ok=True)
DB=Path(os.environ.get('SL_DB_PATH',str(OVERRIDE_DB)))
from suite.storage_migration import migrate_legacy_database as _migrate_legacy_db, default_legacy_paths as _legacy_db_paths, restore_missing_photo_files as _restore_audit_photos, default_legacy_photo_roots as _legacy_photo_roots

@st.cache_resource(show_spinner=False)
def _startup_data_recovery(db_path, shared_root, app_root):
    """Run additive legacy recovery once per server process, not on each Streamlit rerun."""
    db_path, shared_root, app_root = Path(db_path), Path(shared_root), Path(app_root)
    photo_root = Path(os.environ.get('SL_PHOTO_ROOT', str(shared_root/'PHOTOS')))
    migration = _migrate_legacy_db(db_path, _legacy_db_paths(app_root))
    photos = _restore_audit_photos(db_path, photo_root, _legacy_photo_roots(app_root, photo_root))
    return migration, photos

DB_MIGRATION_STATUS,PHOTO_RECOVERY_STATUS=_startup_data_recovery(str(DB),str(SHARED_ROOT),str(ROOT))
# Keep Home light: load Plan-2026 here, then request other sources only from the
# page that consumes them. Published source revisions stay active across pages.
HOME_SOURCE_FILES=(
    ('Plan-2026','Plan-2026-LATEST.xlsx','home_plan'),
)
_LOGO=ROOT/'assets'/'sl_logo.png'
st.set_page_config(page_title='SL Carborundum Planning Center',page_icon=str(_LOGO) if _LOGO.exists() else '🏭',layout='wide')

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

from suite.navigation_state import preserve_navigation_values, restore_editor_draft, save_editor_draft
preserve_navigation_values(st.session_state)
st.caption((ROOT/'VERSION').read_text(encoding='utf-8').strip() if (ROOT/'VERSION').exists() else 'V16.29')
st.markdown('''<style>
.block-container{padding-top:.15rem;max-width:none;width:100%;padding-left:1.1rem;padding-right:1.1rem}.block-container>div>div:first-child{gap:.35rem}
[data-testid="stSidebar"],[data-testid="stSidebar"]>div,[data-testid="stSidebarContent"],[data-testid="stSidebarHeader"]{background:#fff8f0!important;min-width:268px;max-width:300px;color:#12395b}
[data-testid="stSidebar"][aria-expanded="false"]{min-width:0!important;max-width:0!important}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] span,[data-testid="stSidebar"] label,[data-testid="stSidebar"] li,[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,[data-testid="stSidebar"] [data-testid="stMarkdown"] p,[data-testid="stSidebar"] [data-testid="stCaptionContainer"],[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{color:#12395b!important}
[data-testid="stSidebar"] a{color:#0057b8!important}
section[data-testid="stSidebar"] *{color:#12395b}
[data-testid="stSidebar"] small,[data-testid="stSidebar"] [data-testid="stCaptionContainer"] span{color:#12395b!important}
section.main,section.main>div{width:100%!important;max-width:none!important}
h1,h2,h3{color:#12395b}.stButton button,.stDownloadButton button{border-color:#f58220;min-height:2.35rem;font-weight:800;border-radius:10px}
[data-testid="stMetric"]{background:linear-gradient(135deg,#fff,#eef4fb);border:1px solid #c5d4e6;border-radius:12px;padding:8px}
[data-testid="stMetricValue"]{font-size:1.4rem;color:#12395b}
.sl-card{background:white;border:1px solid #d5e0ec;border-radius:14px;padding:12px;box-shadow:0 4px 12px #12395b12}
.sl-orange{color:#e76613;font-weight:850}.sl-hero{border-radius:12px;min-height:88px;background-size:cover;background-repeat:no-repeat;background-color:#eef4fb;background-position:center;display:flex;align-items:end;padding:12px;margin-bottom:8px}
.sl-hero h2{background:#ffffffdd;padding:8px 12px;border-radius:10px;margin:0;font-size:1.15rem}
.stDataFrame,.stDataEditor{border-radius:12px;overflow:hidden}.sl-filebar{font-size:.8rem;background:#eef4fb;border:1px solid #c5d4e6;border-radius:10px;padding:6px 10px;margin:4px 0 8px}.sl-smalllink{font-size:.8rem}
.sl-pills{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 12px}
.sl-pills a{display:inline-block;padding:8px 14px;border-radius:999px;text-decoration:none;font-weight:800;font-size:.92rem;border:2px solid #c5d4e6;background:#fff;color:#12395b}
.sl-pills a.on{background:#0057b8;border-color:#0057b8;color:#fff}
.sl-pills a.track{border-color:#f58220}
.sl-pills a.track.on{background:#e76613;border-color:#e76613}
.sl-quick-title{font-size:.83rem;font-weight:750;color:#52677d;margin:1px 0 3px}.sl-quicklinks{display:flex;flex-wrap:wrap;gap:4px 13px;margin:0 0 8px;padding:3px 0;border-bottom:1px solid #e0e8ef}.sl-quicklinks a{display:inline-flex;align-items:center;gap:5px;padding:3px 2px;color:#0057b8;text-decoration:none;font-size:.82rem;font-weight:700;white-space:nowrap}.sl-quicklinks a span{font-size:1rem}.sl-quicklinks a:hover{color:#e76613;text-decoration:underline}.sl-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:8px 0 14px}
.sl-tiles a{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;padding:11px 10px;border-radius:14px;text-decoration:none;font-weight:750;font-size:.84rem;line-height:1.18;text-align:center;border:2px solid #d5e0ec;background:#fff;color:#12395b;min-height:86px}
.sl-tile-icon{display:block;font-size:1.9rem;line-height:1;font-weight:400}
.sl-tile-label{display:block;font-size:.84rem;line-height:1.18}
.sl-tiles a:hover{border-color:#f58220;box-shadow:0 4px 12px #f5822026}
.sl-tiles a.orange{background:#fff4e8;border-color:#f58220;color:#c44d00}
.sl-tiles a.blue{background:#e8f1fb;border-color:#0057b8;color:#0057b8}
@media(max-width:600px){.sl-tiles{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.sl-tiles a{min-height:80px;padding:9px 7px}.sl-tile-icon{font-size:1.75rem}.sl-tile-label{font-size:.78rem}}
.sl-how{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin:8px 0 14px}
.sl-how div{background:#fff;border-left:5px solid #f58220;border-radius:10px;padding:10px 12px;font-size:.88rem}
.sl-how b{display:block;color:#12395b;margin-bottom:4px}
.sl-answer{background:#fff;border:1px solid #d5e0ec;border-left:6px solid #f58220;border-radius:12px;padding:14px 16px;margin:10px 0;color:#12395b}
.sl-answer h4{margin:0 0 8px;color:#0057b8;font-size:1.05rem}
.sl-answer .sl-src{margin-top:8px;font-size:.82rem;color:#4a5d73}
.sl-chip{display:inline-block;margin:0 6px 8px 0;padding:8px 12px;border-radius:999px;background:#e8f1fb;border:1px solid #0057b8;color:#0057b8;font-weight:800;font-size:.88rem}
/* Streamlit expander icons are Material ligatures (keyboard_arrow_down). If the icon font is
   overridden they print as words on top of the heading. Hide that text and draw a chevron. */
[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stIconMaterial"]{display:none!important}
[data-testid="stExpander"] [data-testid="stIconMaterial"]{
  font-size:0!important;line-height:0!important;color:transparent!important;
  width:1.15rem!important;min-width:1.15rem!important;height:1.15rem!important;
  overflow:hidden!important;position:relative!important;flex-shrink:0!important
}
[data-testid="stExpander"] [data-testid="stIconMaterial"]::after{
  content:"▾";font-size:14px!important;font-family:"Segoe UI",Arial,sans-serif!important;
  color:#12395b!important;position:absolute;inset:0;display:flex;align-items:center;justify-content:center;line-height:1!important
}
[data-testid="stExpander"] [aria-expanded="false"] [data-testid="stIconMaterial"]::after{content:"▸"}
[data-testid="stExpander"] summary,[data-testid="stExpander"] details summary{overflow:visible!important;align-items:center}
</style>''',unsafe_allow_html=True)

def patch_formula_caches(xlsx_path, sheet_name, cell_values):
    """Write cached results for selected existing formulas without replacing their formulas."""
    main='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    pkg='http://schemas.openxmlformats.org/package/2006/relationships'
    ET.register_namespace('',main); ET.register_namespace('r',rel)
    path=Path(xlsx_path); temp=path.with_suffix('.cache.tmp')
    with zipfile.ZipFile(path,'r') as src:
        files={n:src.read(n) for n in src.namelist()}
    book=ET.fromstring(files['xl/workbook.xml']); rels=ET.fromstring(files['xl/_rels/workbook.xml.rels'])
    rid=None
    for sh in book.find(f'{{{main}}}sheets'):
        if sh.attrib.get('name')==sheet_name:rid=sh.attrib.get(f'{{{rel}}}id');break
    if not rid:raise ValueError(f'Cannot locate worksheet {sheet_name}')
    target=next((x.attrib['Target'] for x in rels.findall(f'{{{pkg}}}Relationship') if x.attrib.get('Id')==rid),None)
    if not target:raise ValueError(f'Cannot locate worksheet XML for {sheet_name}')
    xmlpath=posixpath.normpath(target.lstrip('/')) if target.startswith('/') else posixpath.normpath(posixpath.join('xl',target))
    root=ET.fromstring(files[xmlpath]); cells={c.attrib.get('r'):c for c in root.iter(f'{{{main}}}c')}
    for address,value in cell_values.items():
        cell=cells.get(address)
        if cell is None or cell.find(f'{{{main}}}f') is None:continue
        val=cell.find(f'{{{main}}}v')
        if val is None:val=ET.SubElement(cell,f'{{{main}}}v')
        if value is None:cell.set('t','str');val.text=''
        elif isinstance(value,str) and value.startswith('#'):cell.set('t','e');val.text=value
        elif isinstance(value,str):cell.set('t','str');val.text=value
        elif isinstance(value,bool):cell.set('t','b');val.text='1' if value else '0'
        elif isinstance(value,(datetime,date)):cell.attrib.pop('t',None);val.text=str(((value.date() if isinstance(value,datetime) else value)-date(1899,12,30)).days)
        else:cell.attrib.pop('t',None);val.text=str(value)
    files[xmlpath]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as out:
        for name,data in files.items():out.writestr(name,data)
    os.replace(temp,path)


@st.cache_data(show_spinner=False,ttl=20)
def health(url):
    try:
        ctx=ssl._create_unverified_context() if str(url).startswith('https') else None
        with urllib.request.urlopen(url,timeout=.7,context=ctx) as r:return r.status<500
    except:return False

def mobile_online():
    return health('http://127.0.0.1:8000/health') or health('https://127.0.0.1:8443/health')

def _hub_headers():
    try:
        return st.context.headers
    except Exception:
        return {}

def show_planner(kind, extra_query=''):
    """Embed Daily/Firing only when that program is answering. Phones get the shop-floor app, not 127.0.0.1."""
    from suite.service_launcher import ensure, probe, tail_log, SERVICES, iframe_url, host_from_headers, is_phone_ua
    thai = lang == 'ไทย'
    headers = _hub_headers()
    host = host_from_headers(headers)
    if kind == 'daily':
        _hub_root=f'http://{host}:8510/'
        _daily_q=(extra_query or '').lstrip('?')
        _t=st.query_params.get('auth_ticket','')
        _auth_tail=('&auth_ticket='+urllib.parse.quote(_t)) if _t else ''
        _central_q=urllib.parse.urlencode({'hub_wip_url':_hub_root+'?page=wip'+_auth_tail,'hub_reports_url':_hub_root+'?page=daily_closed'+_auth_tail,'hub_kpi_url':_hub_root+'?page=kpi'+_auth_tail,'hub_capacity_actual_url':_hub_root+'?page=capacity_actual'+_auth_tail,'hub_sources_url':_hub_root+'?page=control&open_source_upload=1#all-source-upload'+_auth_tail})
        extra_query=(_daily_q+'&' if _daily_q else '')+_central_q
    _hub_ticket=st.query_params.get('auth_ticket','')
    if _hub_ticket:
        extra_query=(extra_query+'&' if extra_query else '')+urllib.parse.urlencode({'hub_ticket':_hub_ticket})
    try:
        ua = headers.get('User-Agent') or headers.get('user-agent') or ''
    except Exception:
        ua = ''
    phone = is_phone_ua(ua)
    svc = SERVICES[kind]
    pub, primary, mobile_http, mobile_https, https_up, _http_up = phone_app_urls()
    name = svc['name_th'] if thai else svc['name']
    if phone:
        st.warning(
            f"{name} เป็นโปรแกรมบนเครื่องโรงงาน (พอร์ต {svc['port']}) มือถือที่เปิด 127.0.0.1 จะชนตัวมือถือเอง ไม่ใช่เครื่องโรงงาน — ใช้แอปหน้างานด้านล่าง"
            if thai else
            f"{name} is a factory-PC program (port {svc['port']}). On a phone, 127.0.0.1 means this phone, not the PC. Use the shop-floor app below."
        )
        st.markdown(
            f"<a href='{primary}' target='_self' style='display:block;padding:16px;background:#e76613;color:#fff;border-radius:12px;text-align:center;font-weight:900;text-decoration:none;margin:8px 0'>📱 {('เปิดแอปมือถือหน้างาน' if thai else 'Open phone shop-floor app')}</a>",
            unsafe_allow_html=True,
        )
        st.caption(('สำรอง HTTP (เปิดได้ทันที ไม่ต้องติดตั้งใบรับรอง): ' if thai else 'HTTP (opens now, no certificate): ') + mobile_http)
        if https_up:
            st.caption(('HTTPS สำหรับกล้อง: ' if thai else 'HTTPS for camera: ') + mobile_https)
        st.caption(('ติดตั้งใบรับรองครั้งเดียว: ' if thai else 'Install the certificate once: ') + pub['http'] + '/tls/ca.crt')
        if st.button(('เริ่มแอปมือถือบนเครื่องโรงงาน' if thai else 'Start the phone app on the factory PC'), key=f'phone_start_{kind}', use_container_width=True):
            ensure('mobile', wait_seconds=6)
            try:
                health.clear()
            except Exception:
                pass
            st.rerun()
        return
    ready = probe(kind)
    if not ready:
        with st.spinner(('กำลังเริ่ม ' if thai else 'Starting ') + name + f' :{svc["port"]} …'):
            info = ensure(kind, wait_seconds=12)
            ready = bool(info.get('ready') or probe(kind))
        try:
            health.clear()
        except Exception:
            pass
    if ready:
        url = iframe_url(kind, host, extra_query)
        components.iframe(url, height=1200, scrolling=True)
        # Do not print iframe URLs: they contain internal ports and short-lived auth tickets.
        return
    st.error(
        f"{name} ยังไม่ตอบที่พอร์ต {svc['port']} จึงไม่ฝังหน้าต่าง — นี่คือสาเหตุของข้อความ 127.0.0.1 refused to connect"
        if thai else
        f"{name} is not answering on port {svc['port']}, so this tab does not embed a dead address. That is what Chrome reports as “127.0.0.1 refused to connect.”"
    )
    st.info(
        'บนเครื่องโรงงานให้รัน START_SL_CARBORUNDUM_PLANNING_CENTER.bat หรือกดเริ่มด้านล่าง บนมือถือให้เปิดแอปหน้างานจากหน้าหลัก (ที่อยู่ LAN ไม่ใช่ 127.0.0.1)'
        if thai else
        'On the factory PC run START_SL_CARBORUNDUM_PLANNING_CENTER.bat or tap Start below. On a phone open the shop-floor app from Home (LAN address, never 127.0.0.1).'
    )
    log = tail_log(kind)
    if log:
        with st.expander('Last log / บันทึกล่าสุด', expanded=False):
            st.code(log)
    b1, b2 = st.columns(2)
    if b1.button(('เริ่ม ' if thai else 'Start ') + name, key=f'start_{kind}', use_container_width=True):
        ensure(kind, wait_seconds=15)
        try:
            health.clear()
        except Exception:
            pass
        st.rerun()
    if b2.button('Refresh / รีเฟรช', key=f'refresh_{kind}', use_container_width=True):
        try:
            health.clear()
        except Exception:
            pass
        st.rerun()


def mobile_public():
    from suite.tls_certs import public_urls
    u=public_urls(lan_ip())
    https_ok=health(u['https_local']+'/health') or health(u['http_local']+'/health')
    return u, https_ok

def phone_app_urls():
    """HTTP supports type/photo capture; live camera scanning needs HTTPS."""
    from suite.tls_certs import public_urls as _public_urls
    pub=_public_urls(os.environ.get('SL_MOBILE_HOST','').strip() or lan_ip())
    https_up=health('https://127.0.0.1:8443/health')
    http_up=health('http://127.0.0.1:8000/health')
    http_u=pub['http']+'/mobile'
    https_u=pub['https']+'/mobile'
    # Keep the known factory URL/port as the default. HTTPS is optional and
    # should never make the main audit link point at a service that is absent.
    primary=http_u
    return pub, primary, http_u, https_u, https_up, http_up

def lan_ip():
    configured=os.environ.get('SL_MOBILE_HOST','').strip()
    if configured:
        return configured
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));x=s.getsockname()[0];s.close();return x
    except:return 'SERVER-IP'

def fp(n):
    if n=='Plan-2026-LATEST.xlsx':
        p=_resolve_shared_plan()
        if p: return Path(p)
    if n=='Packaging-Standard-LATEST.xlsx':return packing_source.resolve_source(ROOT,DATA)
    p=DATA/n; return p if p.exists() else None

@st.cache_data(show_spinner=False, max_entries=4)
def _cached_existing_firing_view(path, mtime_ns, size_bytes):
    """Parse an active firing source once per revision; never recalculate a plan."""
    from suite.firing_pattern_view import load_existing_firing
    return load_existing_firing(path)

@st.cache_data(show_spinner=False,ttl=600)
def knowledge_search_rows(db_path,normalized_query,original_query):
    """Cache submitted reference searches; never rescan large books while typing."""
    con=sqlite3.connect(f'file:{Path(db_path).as_posix()}?mode=ro',uri=True)
    try:
        return con.execute('''SELECT r.record_id,r.sheet,r.row_number,r.category,r.quality,r.body,r.fields_json,
            s.filename,s.path,s.filesystem_modified,s.workbook_modified,s.sha256,s.snapshot_time
            FROM records r JOIN sources s USING(source_id) WHERE r.normalized LIKE ? ORDER BY
            CASE WHEN r.body LIKE ? THEN 0 WHEN r.normalized=? THEN 1 WHEN r.normalized LIKE ? THEN 2 ELSE 3 END,
            CASE WHEN s.filename LIKE 'MRP BOND%' THEN 0 WHEN s.filename LIKE 'Cover_S&OP%' THEN 1
                 WHEN s.filename LIKE 'PS_PBS%' OR s.filename LIKE 'PM_PBM%' THEN 2
                 WHEN s.filename LIKE 'Plan 2026%' OR s.filename LIKE 'Plan-2026%' THEN 3
                 WHEN s.filename LIKE 'P280%' THEN 4 ELSE 5 END,
            CASE WHEN r.quality LIKE '%incomplete%' THEN 1 ELSE 0 END, s.filename LIMIT 80''',
            ('%'+normalized_query+'%','%: '+original_query+' |%',normalized_query,normalized_query+'%')).fetchall()
    finally:con.close()

def archive_and_save(upload,target):
    """Single import path. Targets that belong to a Source Manager slot go through it (dedupe by sha256, numbered revisions, originals kept,
    published to the shared file every module reads); anything else keeps the legacy behaviour."""
    _scope='archive:'+str(target)
    if _upload_seen(upload,_scope):return None
    b=bytes(upload.getbuffer());_slot=_TARGET_SLOT.get(target)
    if _slot:
        _pref='home' if st.session_state.get('upload_context','').startswith('Home') else 'sources'
        _res=SM.import_bytes(_slot,upload.name,b,st.session_state.get('sl_user',''),section=st.session_state.get('sl_section',''),
            note=st.session_state.get(_pref+'_upload_source_revision','').strip(),source_folder=st.session_state.get(_pref+'_upload_source_folder','').strip())
        if _res.status in ('IMPORTED','REACTIVATED'):
            st.success(f'{_res.status}: revision {_res.revision_no}. Modules now using it: '+'; '.join(_res.affected_modules))
            _p=DATA/target;register_source(target,_p,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),upload.name,st.session_state.get('upload_context','Sources'))
            _reg=_load_registry();_e=_reg.setdefault(target,{});_e['archive_copy_path']=SM.active(_slot)['stored_path'];_e['slot_id']=_slot;_save_registry(_reg)
        elif _res.ok: st.info(_res.message)
        else: st.error(_res.message)
        _mark_upload_seen(upload,_scope)
        return DATA/target
    _existing=DATA/target;_prior=_load_registry().get(target,{})
    if _existing.exists() and _prior.get('sha256')==hashlib.sha256(b).hexdigest() and _prior.get('original_name')==upload.name:
        _mark_upload_seen(upload,_scope);return _existing
    stamp=datetime.now(ZoneInfo('Asia/Bangkok')).strftime('%Y%m%d_%H%M%S')
    _archive=SOURCE_ARCHIVE/f'{stamp}_{Path(upload.name).name}'; _archive.write_bytes(b)
    p=DATA/target; p.write_bytes(b)
    register_source(target,p,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),upload.name,st.session_state.get('upload_context','Sources'))
    _reg=_load_registry(); _entry=_reg.setdefault(target,{}); _entry['archive_copy_path']=str(_archive.resolve())
    _entry.setdefault('archive_copy_paths',[]).append(str(_archive.resolve())); _save_registry(_reg)
    _mark_upload_seen(upload,_scope)
    return p

def _import_slot(upload, slot_id):
    """Home upload into a Source Manager slot that may not have a COMPANY_DATA filename."""
    _scope='slot:'+str(slot_id)
    if _upload_seen(upload,_scope):return None
    b=bytes(upload.getbuffer()); _pref='home' if st.session_state.get('upload_context','').startswith('Home') else 'sources'
    _res=SM.import_bytes(slot_id,upload.name,b,st.session_state.get('sl_user',''),section=st.session_state.get('sl_section',''),
        note=st.session_state.get(_pref+'_upload_source_revision','').strip(),source_folder=st.session_state.get(_pref+'_upload_source_folder','').strip())
    if _res.status in ('IMPORTED','REACTIVATED'):
        st.success(f'{_res.status}: revision {_res.revision_no}. {_res.message}')
    elif _res.ok:
        st.info(_res.message)
    else:
        st.error(_res.message)
    _mark_upload_seen(upload,_scope)
    return _res


# Upload the next source only at the page that needs it.  Sources remain in the
# shared Source Manager after navigation; the closed panel is just a replacement
# control, never a request to upload the same workbook again.
_CONTEXT_SOURCE_SLOTS={
    'daily':['PLAN_2026','FIRING_PLAN','STOCK_ON_HAND','CAPACITY_DATABASE','SEPT_OPEN_CLOSED'],
    'material':['STOCK_ON_HAND'],
    'daily_wip':['PLAN_2026'],
    'daily_closed':['PLAN_2026','SEPT_OPEN_CLOSED'],
    'daily_status':['PLAN_2026'],
    'daily_recovery':['PLAN_2026','FIRING_PLAN','STOCK_ON_HAND','SALES_FORECAST','CAPACITY_DATABASE','RECOVERY_PLAN'],
    'recovery_review':['RECOVERY_PLAN','SALES_PRODUCT_REGISTER','PACKAGING_STANDARD'],
    'firing':['PLAN_2026','FIRING_PLAN','STOCK_ON_HAND','CAPACITY_DATABASE'],
    'back':['PLAN_2026','STOCK_ON_HAND','SALES_FORECAST','CAPACITY_DATABASE'],
    'mps':['PLAN_2026','SALES_FORECAST','STOCK_ON_HAND','CAPACITY_DATABASE'],
    'mrp':['PLAN_2026','STOCK_ON_HAND','SD_RECIPE_MASTER','BOND_MRP','CAPACITY_DATABASE'],
    'pack':['PLAN_2026','PACKAGING_STANDARD'],
    'newplan':['PLAN_2026','NEW_REQUEST_REFERENCE','SALES_FORECAST','STOCK_ON_HAND','CAPACITY_DATABASE'],
    'audit':['PLAN_2026'],'audits':['PLAN_2026'],'report':['PLAN_2026'],'floor':['PLAN_2026'],
    'kpi':['KPI_PLANNING_REFERENCE','KPI_PLANNING_DAILY_EXECUTION','KPI_PLANNING_JOB_CLOSURE','KPI_SECTION_PLAN_VS_ACTUAL','KPI_DELIVERY_WAREHOUSE'],
    'daily_kpi':['KPI_PLANNING_REFERENCE','KPI_SECTION_PLAN_VS_ACTUAL','KPI_DELIVERY_WAREHOUSE'],
    'wip':['PLAN_2026'],
}

def _slot_published_path(slot_id):
    slot=SM_SLOTS.get(slot_id)
    if not slot:return None
    target=slot.legacy_target
    if not target:return None
    return (SHARED_ROOT/target if target.startswith('KPI/') else DATA/target).resolve()

def _render_context_source_updates(page):
    slots=_CONTEXT_SOURCE_SLOTS.get(page,[])
    if not slots:return
    states=[];missing=[]
    for sid in slots:
        slot=SM_SLOTS[sid]; active=SM.active(sid); published=_slot_published_path(sid)
        exists=bool((published and published.is_file()) or (active and Path(active.get('stored_path','')).is_file()))
        if exists:
            source=(active or {})
            label=source.get('original_name') or (published.name if published and published.is_file() else Path(source['stored_path']).name)
            rev=f"r{source['revision_no']}" if source.get('revision_no') else 'existing source'
            imported=source.get('imported_at') or 'import time not recorded'
            digest=(source.get('sha256') or '')[:12]
            states.append(f"{slot.label}: {label} · {rev} · {imported}"+(f" · SHA {digest}" if digest else ''))
        else:
            missing.append(sid);states.append(f"{slot.label}: MISSING")
    title='📥 Update sources for this page / อัปเดตไฟล์ของหน้านี้'
    with st.expander(title,expanded=bool(missing)):
        st.caption('Only the inputs used by this page appear here. Upload a missing file, or tick Replace when you have a newer revision. Saved files remain active across pages; prior revisions stay in history.')
        for row in states:st.caption(('⚠ ' if row.endswith('MISSING') else '✓ ')+row)
        for sid in slots:
            slot=SM_SLOTS[sid]; active=SM.active(sid); published=_slot_published_path(sid)
            exists=bool((published and published.is_file()) or (active and Path(active.get('stored_path','')).is_file()))
            if sid=='FIRING_PLAN':
                st.caption('Firing source accepts the complete planner workbook or just the issued Operator Print sheet. The print must include WO, Kiln, Loading Date, planned quantity, and Firing Complete / finish date.')
            replace_key=f'ctx_replace_{page}_{sid}'
            if exists and not st.checkbox(f"Replace {slot.label}",key=replace_key):continue
            ext=['xlsx','xlsm']
            if sid=='SEPT_OPEN_CLOSED':ext=['xls','xlsx','xlsm']
            upload=st.file_uploader(f"Upload {slot.label}" if not exists else f"New revision — {slot.label}",type=ext,key=f'ctx_upload_{page}_{sid}')
            if upload is None:continue
            try:
                SM.adopt_existing(st.session_state.get('sl_user','source-import'))
                res=SM.import_bytes(sid,upload.name,upload.getvalue(),st.session_state.get('sl_user','unknown'),
                    section=slot.section or '',note=f'Context upload from {_PAGE_TITLES.get(page,page)}')
                if res.ok:
                    st.success(f"{slot.label}: {res.status} · revision {res.revision_no or 'unchanged'} · saved to shared source store.")
                    st.rerun()
                else:st.error(f"{slot.label} was not changed: {res.message}")
            except Exception as err:st.error(f"Upload failed; the previous active source is preserved. {err}")
        if page in ('daily','daily_closed','daily_status','floor','report','daily_recovery'):
            _sections=('Preparation','Mixing','Forming','Firing','Grinding','Packing')
            _ds_needed=any(not (SM.active('DAILY_STATUS_'+_sec.upper()) and Path(SM.active('DAILY_STATUS_'+_sec.upper()).get('stored_path','')).is_file()) for _sec in _sections)
            with st.expander('Daily Status — one active workbook per section / Daily Status รายแผนก',expanded=_ds_needed):
                from suite.daily_status_files import section_from_filename as _ctx_section_from_filename
                _active_rows=[]
                for _sec in _sections:
                    _sid='DAILY_STATUS_'+_sec.upper();_act=SM.active(_sid)
                    _active_rows.append(f"{_sec}: {Path(_act['stored_path']).name if _act and Path(_act['stored_path']).is_file() else 'not loaded'}")
                st.caption(' · '.join(_active_rows))
                _batch=st.file_uploader('Add or replace section workbook(s)',type=['xlsx','xlsm'],accept_multiple_files=True,key='ctx_daily_status_batch')
                _ds_changed=False
                for _up in (_batch or []):
                    _guess=_ctx_section_from_filename(_up.name)
                    _sec=_guess or st.selectbox(f'Section for {_up.name}',_sections,key='ctx_ds_sec_'+hashlib.sha1(_up.name.encode()).hexdigest()[:10])
                    _scope='slot:DAILY_STATUS_'+_sec.upper()
                    if _upload_seen(_up,_scope):continue
                    try:
                        SM.adopt_existing(st.session_state.get('sl_user','source-import'))
                        _res=SM.import_bytes('DAILY_STATUS_'+_sec.upper(),_up.name,_up.getvalue(),st.session_state.get('sl_user','unknown'),section=_sec,note='Context upload from Daily Status report')
                        if _res.ok:st.success(f'{_sec}: {_res.status}; saved as a new active section revision.');_ds_changed=True
                        else:st.error(f'{_sec}: {_res.message}')
                        _mark_upload_seen(_up,_scope)
                    except Exception as _err:st.error(f'{_sec} upload failed; previous source is preserved. {_err}')
                if _ds_changed:st.rerun()
        if page=='wip':
            with st.expander('Update Production WIP section files / อัปเดตไฟล์ WIP ฝ่ายผลิต',expanded=False):
                _uploads=st.file_uploader('Choose new section snapshots (multiple files allowed)',type=['xlsx','xlsm'],accept_multiple_files=True,key='ctx_production_wip_uploads')
                for _up in (_uploads or []):
                    _choices=['Unassigned']+wip_sources.SECTIONS;_guess=wip_sources.infer_section(_up.name)
                    _sec=_guess or st.selectbox(f'Section for {_up.name}',_choices,key='ctx_wip_sec_'+hashlib.sha1(_up.name.encode()).hexdigest()[:10])
                    _dest_dir=SHARED_ROOT/'PRODUCTION_WIP';_dest_dir.mkdir(parents=True,exist_ok=True)
                    _canonical=wip_sources.filename_for_section(_sec,Path(_up.name).suffix)
                    _dest=_dest_dir/(_canonical or Path(_up.name).name)
                    _scope='wip:'+_up.name+':'+str(_sec)
                    if _upload_seen(_up,_scope):continue
                    try:
                        _archive=None
                        _reg=_load_registry();_key='PRODUCTION_WIP/'+_dest.name;_old=_reg.get(_key,{})
                        _bytes=_up.getvalue();_sha=hashlib.sha256(_bytes).hexdigest()
                        if _dest.exists() and _old.get('sha256')!=_sha:
                            _archive=SOURCE_ARCHIVE/f"{bkk_now():%Y%m%d_%H%M%S}_WIP_{_dest.name}";_archive.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(_dest,_archive)
                        _dest.write_bytes(_bytes)
                        register_source(_key,_dest,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),_up.name,f'WIP page · {_sec}')
                        _reg=_load_registry();_entry=_reg.setdefault(_key,{})
                        _entry.update(production_section='' if _sec=='Unassigned' else _sec,wip_active=True,sha256=_sha)
                        _entry.setdefault('archive_copy_paths',[])
                        if _archive:
                            _entry['archive_copy_path']=str(_archive.resolve());_entry['archive_copy_paths'].append(str(_archive.resolve()))
                        _save_registry(_reg);_mark_upload_seen(_up,_scope)
                        st.success(f'{_up.name} saved under Production WIP / {_sec}.')
                    except Exception as _err:st.error(f'Production WIP upload failed; the previous active source is preserved. {_err}')

def _save_october_register(upload):
    """Home/Open-Closed popup: current monthly register (revised every day)."""
    if upload is None:
        return
    st.session_state['upload_context']='Home Page'
    archive_and_save(upload,'Job-Register-LATEST.xlsx')

def _check_password(password,encoded):
    from suite.demo_accounts import check_password as _ck
    return _ck(password,encoded)

def hub_login(username,password):
    from suite.demo_accounts import find_user, seed_users
    seed_users(DB)
    row=find_user(DB,username)
    if row and row.get('active',1) and _check_password(password or '',row['password_hash']):
        return row
    return None

def hub_auth_ticket():
    try:
        from suite.hub_auth import issue
        return issue(DATA,st.session_state.get('sl_user',''),st.session_state.get('sl_role','viewer'))
    except Exception:
        return ''

def hub_can_edit():
    # Owner decision OD-8 (2026-10-04): every signed-in role may edit; every save carries the user name. The anonymous default 'VIEWER' stays read-only because its edits could not be traced.
    return bool(st.session_state.get('sl_authenticated')) and bool(st.session_state.get('sl_user'))

def hub_is_production_context():
    """Use a conservative view for shop-floor roles even if they change the department selector."""
    role=str(st.session_state.get('sl_role','viewer')).strip().lower()
    section=str(st.session_state.get('sl_section','')).strip().lower()
    production_roles={'operator','production','production_operator','shop_floor','production_support'}
    production_sections={'production support','preparation','mixing','forming','firing','grinding','cutting','packing','qc'}
    return role in production_roles or section in production_sections

def hub_can_view_customers():
    """Customer names are restricted to planning/admin/management views."""
    return not hub_is_production_context()

def mask_customer_columns(df, *, drop=False):
    """Strip customer-name fields from any production-facing dataframe."""
    if df is None or not isinstance(df,pd.DataFrame) or not hub_is_production_context():
        return df
    customer_cols=[c for c in df.columns if re.search(r'customer|ลูกค้า',str(c),re.I) and not re.search(r'(id|code|customernameid)',str(c),re.I)]
    if drop:
        return df.drop(columns=customer_cols,errors='ignore')
    out=df.copy()
    for c in customer_cols: out[c]='RESTRICTED'
    return out

def format_due_date(value):
    """Full weekday, day, month and year for delivery dates; blanks stay blank."""
    try:
        d=pd.to_datetime(value,errors='coerce',dayfirst=True)
        if pd.isna(d): return '' if value is None else str(value)
        return d.strftime('%A, %d %B %Y')
    except Exception:
        return str(value or '')

@st.cache_data(show_spinner=False, max_entries=8)
def _load_registry_cached(path, mtime_ns, size):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except:return {}

def _load_registry():
    try:
        stat=REGISTRY.stat()
        return _load_registry_cached(str(REGISTRY),int(stat.st_mtime_ns),int(stat.st_size))
    except FileNotFoundError:return {}
    except:return {}

def _save_registry(d):
    REGISTRY.parent.mkdir(parents=True,exist_ok=True)
    REGISTRY.write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

def _upload_token(upload, scope):
    """Stable token for a Streamlit upload retained across reruns in this session."""
    if upload is None:return None
    fid=getattr(upload,'file_id',None)
    if not fid:return None
    return (str(scope),str(fid),str(getattr(upload,'name','')),int(getattr(upload,'size',0) or 0))

def _upload_seen(upload, scope):
    token=_upload_token(upload,scope)
    return token is not None and bool(st.session_state.get('_sl_processed_uploads',{}).get(token))

def _mark_upload_seen(upload, scope):
    token=_upload_token(upload,scope)
    if token is not None:
        seen=st.session_state.setdefault('_sl_processed_uploads',{})
        seen[token]=True
        if len(seen)>1000:
            for _old in list(seen)[:500]:seen.pop(_old,None)

def register_source(target,path,user='',section='',original_name='',upload_context='Sources'):
    d=_load_registry(); p=Path(path); stt=p.stat() if p.exists() else None
    _doc_modified=None
    try:
        with zipfile.ZipFile(p) as _z:
            _core=_z.read('docProps/core.xml').decode('utf-8','ignore')
            _m=re.search(r'<dcterms:modified[^>]*>([^<]+)',_core)
            if _m:_doc_modified=_m.group(1)
    except: pass
    _prior=d.get(target,{})
    _source_prefix='home' if upload_context.startswith('Home') else 'sources'
    _source_folder=st.session_state.get(_source_prefix+'_upload_source_folder','').strip()
    _source_revision=st.session_state.get(_source_prefix+'_upload_source_revision','').strip()
    d[target]={'active_path':str(p.resolve()),'original_name':original_name or p.name,
               'registered_at':datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds'),'updated_by':user,'section':section,
               'stored_file_modified_at':datetime.fromtimestamp(stt.st_mtime,ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds') if stt else None,
               'excel_document_modified_at':_doc_modified,
               'size_bytes':stt.st_size if stt else None,'sha256':_sha256(p) if stt else '', 'uploaded_through':upload_context,
               'archive_copy_path':_prior.get('archive_copy_path',''),'archive_copy_paths':_prior.get('archive_copy_paths',[]),
               'source_history':_prior.get('source_history',[])+([{k:_prior.get(k) for k in ['original_name','client_source_path','registered_at','source_revision_note','excel_document_modified_at','sha256','archive_copy_path']} ] if _prior else []),
               'provenance_history':_prior.get('provenance_history',[]),
               'original_location_note':'Web browsers do not provide the original PC folder path. The software records original filename, Excel document modified time when available, upload page/user/time, and central stored location.',
               'client_source_path':_source_folder or 'Not recorded — browser does not expose original folder',
               'source_path_evidence':'User provided' if _source_folder else 'Unavailable',
               'source_revision_note':_source_revision or 'Not recorded'}
    _save_registry(d)

def _sha256(p):
    try:return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except:return ''

def source_conflicts():
    rows=[]
    names=['Plan-2026-LATEST.xlsx','Sales-Forecast-LATEST.xlsx','Stock-on-Hand-LATEST.xlsx','Packaging-Standard-LATEST.xlsx','P280526-LATEST.xlsx','Firing-Plan-LATEST.xlsx']
    for name in names:
        act=DATA/name
        if not act.exists():continue
        ah=_sha256(act)
        for base in [ROOT/'company_data',ROOT/'apps'/'daily',ROOT/'apps'/'firing',ROOT/'apps'/'mobile'/'data']:
            q=base/name
            if q.exists() and q.resolve()!=act.resolve() and _sha256(q)!=ah:
                rows.append({'Source':name,'Active central file':str(act),'Different old copy':str(q),'Action':'CENTRAL FILE IS USED — old copy ignored'})
    return pd.DataFrame(rows)

def _ensure_override_table():
    con=sqlite3.connect(OVERRIDE_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS plan_overrides(
      wo_id TEXT NOT NULL, field_name TEXT NOT NULL, value_text TEXT,
      edited_by TEXT, edited_section TEXT, edited_at TEXT,
      PRIMARY KEY(wo_id,field_name))""")
    con.commit();con.close()

def save_plan_overrides(df,user,section):
    """One persistent override store. Any Hub edit with a WO becomes the next shared truth."""
    _ensure_override_table()
    # Accept translated table headings too.
    rev={v:k for k,v in COL_TH.items()}
    x=df.rename(columns={c:rev.get(c,c) for c in df.columns}).copy()
    if 'Work Order' not in x.columns:return 0
    editable=[c for c in ['Customer','Customer Thai','Customer English','Product Code','Product Category','Due Date',
                           'pcs','ton','Section','Preparation Closed','Final Closed'] if c in x.columns]
    con=sqlite3.connect(OVERRIDE_DB); n=0; now=bkk_now().isoformat(timespec='seconds')
    for _,r in x.iterrows():
        wo=str(r.get('Work Order','')).strip()
        if not wo or wo.lower() in {'nan','none'}:continue
        for c in editable:
            v=r.get(c)
            if pd.isna(v):continue
            con.execute("""INSERT INTO plan_overrides(wo_id,field_name,value_text,edited_by,edited_section,edited_at)
              VALUES(?,?,?,?,?,?) ON CONFLICT(wo_id,field_name) DO UPDATE SET
              value_text=excluded.value_text,edited_by=excluded.edited_by,edited_section=excluded.edited_section,edited_at=excluded.edited_at""",
              (wo,c,str(v),user,section,now)); n+=1
    con.commit();con.close();return n

def apply_plan_overrides(master):
    _ensure_override_table()
    con=sqlite3.connect(OVERRIDE_DB)
    try:o=pd.read_sql_query("SELECT * FROM plan_overrides",con)
    finally:con.close()
    if o.empty or master is None:return master
    x=master.copy()
    for _,r in o.iterrows():
        m=x['Work Order'].astype(str).str.strip().eq(str(r['wo_id']).strip())
        c=r['field_name']
        if c not in x.columns:x[c]=''
        val=r['value_text']
        if c in {'pcs','ton'}: val=pd.to_numeric(pd.Series([val]),errors='coerce').iloc[0]
        elif c=='Due Date': val=pd.to_datetime(val,errors='coerce')
        elif c in {'Preparation Closed','Final Closed'}: val=str(val).lower() in {'true','1','yes','ปิด','ปิดใบสั่ง'}
        x.loc[m,c]=val
    return x

def override_audit():
    _ensure_override_table(); con=sqlite3.connect(OVERRIDE_DB)
    try:return pd.read_sql_query("SELECT wo_id AS [Work Order],field_name AS Field,value_text AS Value,edited_by AS [Edited By],edited_section AS [Edited Section],edited_at AS [Edited At] FROM plan_overrides ORDER BY edited_at DESC",con)
    finally:con.close()

def export_updated_plan(plan_path):
    """Create a controlled revised Plan-2026 copy. Original source remains untouched."""
    out=REPORTS/f'Plan-2026_SOFTWARE_REVISED_{bkk_now():%Y%m%d_%H%M%S}.xlsx'
    shutil.copy2(plan_path,out)
    wb=load_workbook(out)
    ws=wb['แผนการเผา']
    hdr={str(c.value).strip():c.column for c in ws[3] if c.value is not None}
    wo_col=hdr.get('ProductionCode')
    source_map={'Customer Thai':'Customername','Customer':'Customername','Product Code':'รหัสสินค้า',
                'Product Category':'ประเภทสินค้า','Due Date':'กำหนดส่งมอบขาย'}
    aud=override_audit()
    if wo_col and not aud.empty:
        rows={}
        for r in range(4,ws.max_row+1):
            rows[str(ws.cell(r,wo_col).value or '').strip()]=r
        for _,a in aud.iterrows():
            rr=rows.get(str(a['Work Order']).strip()); src=source_map.get(a['Field'])
            if rr and src in hdr: ws.cell(rr,hdr[src]).value=a['Value']
    if 'SOFTWARE_EDIT_AUDIT' in wb.sheetnames: del wb['SOFTWARE_EDIT_AUDIT']
    aw=wb.create_sheet('SOFTWARE_EDIT_AUDIT')
    aw.append(['Work Order','Field','Value','Edited By','Edited Section','Edited At'])
    for row in aud.itertuples(index=False,name=None):aw.append(list(row))
    wb.save(out);wb.close();return out

def sync_mobile():
    """Copy the Home Plan-2026 into the same SQLite database the phone reads."""
    try:
        try: _write_runtime_pointer(ROOT)
        except Exception: pass
        if not _resolve_shared_plan():
            return False,'No shared Plan-2026. Upload it once on Home → Start here: Plan-2026.'
        env=_child_environ(ROOT)
        r=subprocess.run([sys.executable,str(ROOT/'sync_mobile_plan.py')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
        text=(r.stdout or '')+(('\n'+r.stderr) if r.stderr else '')
        return r.returncode==0,text[-900:]
    except Exception as e:return False,str(e)

def work_order_count():
    try:
        if not Path(DB).exists(): return 0
        con=sqlite3.connect(DB)
        try:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_orders'").fetchone():
                return 0
            return int(con.execute('SELECT COUNT(*) FROM work_orders').fetchone()[0])
        finally:
            con.close()
    except Exception:
        return 0

def ensure_desktop_audit_tables():
    """Create the shared physical-audit tables before either UI is first used.

    The mobile service applies its richer additive migration on startup. Keeping
    this small bootstrap here lets the desktop audit register open and save on a
    fresh installation without requiring an operator to start the phone service
    first. Existing rows and columns are left untouched.
    """
    con=sqlite3.connect(DB,timeout=15)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS mobile_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wo_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            verified_qty REAL,
            physical_status TEXT NOT NULL DEFAULT 'OK',
            physical_location TEXT,
            observed_process TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS mobile_audit_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT,
            content_type TEXT,
            created_at TEXT NOT NULL
        )""")
        con.commit()
    finally:
        con.close()

from suite.customer_names import (
    apply_customer_language as _apply_customer_language,
    display_customer as _display_customer,
    language_font_css as _language_font_css,
    localize_customer_columns as _localize_customer_columns,
    roman_customer_name as _roman_customer_name,
)

def roman_customer_name(value):
    """Readable English-script companion for Thai names. Source Thai is never changed."""
    return _roman_customer_name(value)

COL_TH={'Work Order':'ใบสั่งผลิต','Customer':'ลูกค้า','Customer Thai':'ชื่อลูกค้าไทย','Customer English':'ชื่อลูกค้าอังกฤษ',
'Product Code':'รหัสสินค้า','Product Category':'กลุ่มสินค้า','Section':'แผนก','pcs':'จำนวน (ชิ้น)','ton':'น้ำหนัก (ตัน)',
'Due Date':'กำหนดส่ง','Late days':'ล่าช้า (วัน)','WOs':'จำนวน WO','Qty pcs':'จำนวน (ชิ้น)','Weight ton':'น้ำหนัก (ตัน)',
'Due Month':'เดือนกำหนดส่ง','Status':'สถานะ','Material Code':'รหัสวัตถุดิบ','Required kg':'ต้องการ (กก.)',
'Stock kg':'สต็อก (กก.)','Incoming kg':'รอเข้า (กก.)','LAB kg':'รอ LAB (กก.)','Hard shortage kg':'ขาดจริง (กก.)',
'Shortage if LAB passes kg':'ขาดหลัง LAB ผ่าน (กก.)','Size':'ขนาด','Preparation Closed':'เตรียมปิดแล้ว',
'Final Closed':'ปิดสุดท้ายแล้ว','Authoritative Closed':'สถานะปิดควบคุม','Boxes Required':'จำนวนกล่อง',
'Pcs/Box':'ชิ้น/กล่อง','Packaging Code':'รหัสบรรจุภัณฑ์','Required Qty':'จำนวนที่ต้องการ'}
STATUS_TH={'OPEN':'เปิด','CLOSED':'ปิด','Closed':'ปิด','Preparation':'เตรียม','Mixing':'ผสม','Forming':'ขึ้นรูป',
'Firing':'เผา','Grinding':'เจียร','Cutting':'ตัด','Packing':'แพ็ค','Open / Check':'เปิด / ตรวจสอบ'}

def display_df(df):
    x=fmt_dates(df)
    x=_localize_customer_columns(x, lang)
    x=mask_customer_columns(x)
    if lang=='ไทย':
        x=x.rename(columns={c:COL_TH.get(c,c) for c in x.columns})
        for c in x.columns:
            if x[c].dtype=='object': x[c]=x[c].map(lambda v: STATUS_TH.get(str(v),v))
    return x

def editor_column_config(df,extra=None):
    cfg={}
    # Thai captions must not change a numeric editor column into text. Streamlit
    # checks the configured type against the actual pandas dtype (e.g. Qty pcs).
    for c in df.columns:
        label=COL_TH.get(c,c) if lang=='ไทย' else c
        if pd.api.types.is_bool_dtype(df[c].dtype):
            cfg[c]=st.column_config.CheckboxColumn(label)
        elif pd.api.types.is_numeric_dtype(df[c].dtype):
            cfg[c]=st.column_config.NumberColumn(label,step=1 if pd.api.types.is_integer_dtype(df[c].dtype) else 0.01)
        elif pd.api.types.is_datetime64_any_dtype(df[c].dtype):
            cfg[c]=st.column_config.DateColumn(label)
        elif lang=='ไทย' and c in COL_TH:
            cfg[c]=st.column_config.TextColumn(label)
    if extra: cfg.update(extra)
    return cfg

def editor_view(df):
    # Preserve original column keys for calculations/save; translate visible common status values only.
    x=fmt_dates(df)
    x=_localize_customer_columns(x, lang)
    if lang=='ไทย':
        for c in x.columns:
            if x[c].dtype=='object': x[c]=x[c].map(lambda v: STATUS_TH.get(str(v),v))
    return x

from suite.closure_rules import is_closed_text as is_closed_status

def _strict_status_by_wo(raw):
    """Whole-order closure = Packing Status (EU) closed OR FC 'ปิดของผลิต' closed. Preparation (CY) and FB are informational only:
    section completion is not whole-order closure (approved rule; see suite/closure_rules.py)."""
    if raw is None or raw.empty or 'ProductionCode' not in raw.columns: return pd.DataFrame(columns=['Work Order','Preparation Closed','Final Closed','Strict Closed'])
    prep = raw.iloc[:,102] if raw.shape[1]>102 else pd.Series('',index=raw.index)
    fb = raw.iloc[:,157] if raw.shape[1]>157 else pd.Series('',index=raw.index)
    final = raw.iloc[:,158] if raw.shape[1]>158 else pd.Series('',index=raw.index)
    pack = raw.iloc[:,150] if raw.shape[1]>150 else pd.Series('',index=raw.index)
    z=pd.DataFrame({'Work Order':raw['ProductionCode'].astype(str).str.strip(),
                    'Preparation Closed':[is_closed_status(x) for x in prep],
                    'FB Closed':[is_closed_status(x) for x in fb],
                    'Packing Closed':[is_closed_status(x) for x in pack],
                    'Final Closed':[is_closed_status(x) for x in final]})
    z['Strict Closed']=z[['Packing Closed','Final Closed']].any(axis=1)
    return z.groupby('Work Order',as_index=False).agg({'Preparation Closed':'max','FB Closed':'max','Packing Closed':'max','Final Closed':'max','Strict Closed':'max'})

@st.cache_data(show_spinner=False)
def model(plan_path,mtime):
    sys.path.insert(0,str(ROOT/'apps'/'daily'))
    import sl_daily_engine_v3_22_from_v17 as eng
    _blob=Path(plan_path).read_bytes()
    master,_,_=eng.read_plan2026(io.BytesIO(_blob),{})
    raw=pd.read_excel(io.BytesIO(_blob),sheet_name='แผนการเผา',header=2,usecols='A:IA')
    # User-confirmed Row-3 mapping: C=initial warehouse receipt/due; E=revised delivery; BY=mill batches.
    # Preserve D/T/H and category directly from source when the engine omits them.
    cols=[c for c in ['ProductionCode','ประเภทสินค้า','D','T','H','Customername','CustomernameID','รหัสสินค้า','Specification'] if c in raw.columns]
    aux=raw[cols].copy(); aux['Plan-2026 Source Row']=raw.index+4; aux=aux.rename(columns={'ProductionCode':'Work Order','ประเภทสินค้า':'Product Category','Customername':'Customer Source','รหัสสินค้า':'Product Source','Specification':'Specification Source'})
    aux['Work Order']=aux['Work Order'].astype(str).str.strip(); aux=aux.drop_duplicates('Work Order',keep='last')
    master=master.merge(aux,on='Work Order',how='left',suffixes=('','_src'))
    if 'Customer Source' in master.columns:
        master['Customer Thai']=master['Customer Source'].fillna('').astype(str)
        master['Customer English']=master['Customer Thai'].map(lambda v: _display_customer(v,'English'))
        # Cached Customer is the Plan-2026 original. Language toggle picks Thai vs English at display time.
        master['Customer']=master['Customer Thai']
    elif 'Customer' in master.columns:
        master['Customer Thai']=master['Customer'].fillna('').astype(str)
        master['Customer English']=master['Customer Thai'].map(lambda v: _display_customer(v,'English'))
    if 'Product Category' not in master: master['Product Category']=''
    master['Product Category']=master['Product Category'].fillna('').astype(str).str.upper().replace({'NAN':'','#N/A':''})
    master['Due Date']=pd.to_datetime(master.get('Delivery Date'),errors='coerce')
    _map=raw.drop_duplicates('ProductionCode',keep='last').set_index(raw['ProductionCode'].astype(str).str.strip())
    _keys=master['Work Order'].astype(str).str.strip()
    _issued_col=next((c for c in ['วันที่ออกใบสั่งงาน','วันที่ออกใบผลิต','วันที่ออกใบสั่งผลิต','วันที่เริ่มออกใบผลิต','Order Date','Creation Date'] if c in raw.columns),None)
    if _issued_col:
        master['Work Order Creation Date']=pd.to_datetime(_keys.map(_map[_issued_col]),errors='coerce')
    if 'กำหนดเข้าคลัง' in raw.columns: master['Initial Due Date']=pd.to_datetime(_keys.map(_map['กำหนดเข้าคลัง']),errors='coerce')
    if 'กำหนดส่งใหม่' in raw.columns:
        master['Revised Delivery']=pd.to_datetime(_keys.map(_map['กำหนดส่งใหม่']),errors='coerce')
        # Current revised customer commitment is the common date basis used by
        # Daily Planner and MPS. Fall back to the original warehouse date only
        # when no revised date exists; do not let Home and Daily disagree.
        master['Due Date']=master['Revised Delivery'].combine_first(master.get('Initial Due Date',pd.Series(pd.NaT,index=master.index)))
    elif 'Initial Due Date' in master:
        master['Due Date']=master['Initial Due Date']
    if 'กำหนดส่งมอบขาย' in raw.columns: master['Sales Delivery']=pd.to_datetime(_keys.map(_map['กำหนดส่งมอบขาย']),errors='coerce')
    if 'จำนวนโม่' in raw.columns: master['Mill Batches']=pd.to_numeric(_keys.map(_map['จำนวนโม่']),errors='coerce').fillna(0)
    _mil=[('วันที่เริ่มออกใบผลิต','Production order issued'),('Planning','Planning'),('วันที่เริ่มเตรียม','Preparation'),('รอผสม','Waiting for Mixing'),('วันที่เริ่มผสม','Mixing'),('รอขึ้นรูป','Waiting for Forming'),('วันที่เริ่มขึ้นรูป','Forming'),('รอโหลดเข้าเตา','Waiting for Kiln'),('โหลดเข้า','Kiln Loaded'),('เผา','Firing'),('โหลดออก','Kiln Unloaded'),('รอคัดกรอง','Waiting for Screening'),('วันที่เริ่มเจียร','Grinding'),('รอแพ็ค','Waiting for Packing'),('วันที่เริ่มแพ็ค','Packing'),('รอส่ง','Waiting for Dispatch'),('วันที่เริ่มส่ง','Dispatch')]
    _loc={}
    for _,_r in raw.iterrows():
        _wo=str(_r.get('ProductionCode','')).strip(); _last='Planning'
        for _c,_lab in _mil:
            _v=_r.get(_c) if _c in raw.columns else None
            if pd.notna(_v) and str(_v).strip().lower() not in {'','0','0.0','nan','none','false'}: _last=_lab
        if _wo:_loc[_wo]=_last
    master['Plan Location / Status']=_keys.map(_loc).fillna('Planning')
    oq=pd.to_numeric(master.get('Order Qty'),errors='coerce').fillna(0)
    pa=pd.to_numeric(master.get('Packing Actual Qty',master.get('Packing Actual',0)),errors='coerce')
    if not isinstance(pa,pd.Series): pa=pd.Series(float(pa or 0),index=master.index)
    pa=pa.fillna(0)
    master['pcs']=(oq-pa).clip(lower=0)
    kgpc=pd.to_numeric(master.get('Plan2026 kg/pc'),errors='coerce').fillna(0);master['ton']=master['pcs']*kgpc/1000
    for c in ['D','T','H']:
        if c not in master: master[c]=''
    master['Size']=master.apply(lambda r:f"D{r.get('D','')} × T{r.get('T','')} × H{r.get('H','')}",axis=1)
    def stage(r):
        if bool(r.get('Overall Closed',False)):return 'Closed'
        for s in ['Preparation','Mixing','Forming','Firing','Grinding / Cutting','Packing']:
            try:q=float(pd.to_numeric(pd.Series([r.get(s+' Remaining Qty',0)]),errors='coerce').fillna(0).iloc[0])
            except:q=0
            if q>0:return s
        return 'Open / Check'
    master['Section']=master['Plan Location / Status'].fillna('Planning')
    strict=_strict_status_by_wo(raw); master=master.merge(strict,on='Work Order',how='left')
    for c in ['Preparation Closed','FB Closed','Packing Closed','Final Closed','Strict Closed']: master[c]=master[c].fillna(False).astype(bool)
    engine_closed=master['Overall Closed'].fillna(False).astype(bool) if 'Overall Closed' in master else pd.Series(False,index=master.index)
    master['Authoritative Closed']=engine_closed | master['Strict Closed']
    master=apply_plan_overrides(master)
    if 'Packing Closed' in master and 'Final Closed' in master:
        master['Authoritative Closed']=master['Authoritative Closed'].fillna(False).astype(bool) | master['Packing Closed'].fillna(False).astype(bool) | master['Final Closed'].fillna(False).astype(bool)
    op=master[(~master['Authoritative Closed']) & (master['pcs']>0)].copy(); today=pd.Timestamp(bkk_today());bo=overdue_backorders(master,bkk_today())
    return raw,master,op,bo

@st.cache_data(show_spinner=False,ttl=300)
def _cached_plan_wip_fallback(plan_path,mtime_ns,size_bytes):
    from suite.planning_wip import read_plan_wip_fallback
    return read_plan_wip_fallback(plan_path)

def monthly_open_closed(master):
    if master is None or master.empty or 'Due Date' not in master:return pd.DataFrame()
    x=master.copy();x['Due Date']=pd.to_datetime(x['Due Date'],errors='coerce');x=x.dropna(subset=['Due Date']);x['Due Month']=x['Due Date'].dt.to_period('M').astype(str)
    rows=[]
    for (mo,wo),g in x.groupby(['Due Month','Work Order'],dropna=False):
        closed=bool(g.get('Authoritative Closed',g.get('Overall Closed',pd.Series(False,index=g.index))).fillna(False).astype(bool).any())
        oq=float(pd.to_numeric(g.get('Order Qty',0),errors='coerce').fillna(0).max())
        pa=float(pd.to_numeric(g.get('Packing Actual Qty',g.get('Packing Actual',0)),errors='coerce').fillna(0).max())
        r=g.iloc[0];kgpc=float(pd.to_numeric(pd.Series([r.get('Plan2026 kg/pc',0)]),errors='coerce').fillna(0).iloc[0])
        qty=max(oq,pa) if closed else max(oq-pa,0)
        rows.append({'Due Month':mo,'Work Order':wo,'Status':'CLOSED' if closed else 'OPEN','Product Category':str(r.get('Product Category','')).upper(),'Qty pcs':qty,'Weight ton':qty*kgpc/1000.0})
    return pd.DataFrame(rows)

def save_editable(df,name,user='',section=''):
    REPORTS.mkdir(exist_ok=True)
    x=df.copy(); now=bkk_now().strftime('%Y-%m-%d %H:%M:%S')
    x['Edited By']=user or 'Unknown'; x['Edited Section']=section or 'Unknown'; x['Edited At']=now
    p=REPORTS/f'{name}_LATEST.xlsx'; x.to_excel(p,index=False)
    try:
        con=sqlite3.connect(DB,timeout=20); con.execute('CREATE TABLE IF NOT EXISTS edit_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, edited_by TEXT, section TEXT, edited_at TEXT, row_count INTEGER)'); con.execute('INSERT INTO edit_audit(table_name,edited_by,section,edited_at,row_count) VALUES(?,?,?,?,?)',(name,user or 'Unknown',section or 'Unknown',now,len(x))); con.commit(); con.close()
    except Exception: pass
    return p

def editable_table(df,key,name,height=480):
    _source_view=editor_view(df)
    _resume=restore_editor_draft(st.session_state,key,_source_view)
    _editor_seed=_resume if _resume is not None else _source_view
    ed=_persistent_data_editor(_editor_seed,use_container_width=True,hide_index=True,height=height,num_rows='dynamic',key=key,disabled=not hub_can_edit(),column_config=editor_column_config(_editor_seed))
    save_editor_draft(st.session_state,key,_source_view,ed)
    c1,c2=st.columns(2)
    with c1:
        if hub_can_edit() and st.button(('Save changes' if lang=='English' else 'บันทึกการแก้ไข')+' — '+name,key='save_'+key,use_container_width=True):
            p=save_editable(ed,name,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''))
            _n=save_plan_overrides(ed,st.session_state.get('sl_user',''),st.session_state.get('sl_section','')) if ('Work Order' in ed.columns or 'ใบสั่งผลิต' in ed.columns) else 0
            st.success((('Saved: ' if lang=='English' else 'บันทึกแล้ว: ')+str(p))+ (f' • {_n} shared WO field edits registered' if _n else ''))
    with c2:
        st.download_button(('Download Excel' if lang=='English' else 'ดาวน์โหลด Excel')+' — '+name, data=to_xlsx_bytes(ed,name[:28]), file_name=name+'.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key='dl_'+key,use_container_width=True)
    return ed

def to_xlsx_bytes(df,sheet='Data'):
    bio=io.BytesIO()
    with pd.ExcelWriter(bio,engine='openpyxl') as w: df.to_excel(w,index=False,sheet_name=re.sub(r'[:\\/?*\[\]]','_',sheet)[:31])
    return bio.getvalue()

def fmt_dates(df):
    x=df.copy()
    for c in x.columns:
        if pd.api.types.is_datetime64_any_dtype(x[c]): x[c]=x[c].dt.strftime('%Y-%m-%d').replace('NaT','')
    return x

def material_pairs(df):
    # Supports BOTH real Plan-2026 duplicate-header layout (1/g,2/g.1...) and SD layout (material1/g...).
    candidates=[(1,'g'),(2,'g.1'),(3,'g.2'),(4,'g.3'),(5,'g.4'),('1','g'),('2','g.1'),('3','g.2'),('4','g.3'),('5','g.4'),('material1','g'),('material2','g.1'),('material3','g.2'),('material4','g.3'),('material5','g.4')]
    out=[]
    for a,b in candidates:
        if a in df.columns and b in df.columns and (a,b) not in out: out.append((a,b))
    return out

def safe_num(v):
    # Excel cells formatted as dates/times can otherwise become huge nanosecond integers.
    if isinstance(v,(datetime,date,time,pd.Timestamp)): return 0.0
    try:
        x=float(v)
        return x if np.isfinite(x) else 0.0
    except Exception:return 0.0

def material_mrp(raw):
    def closed(s): return s.map(is_closed_status)
    cy=raw.iloc[:,102] if raw.shape[1]>102 else pd.Series('',index=raw.index);fb=raw.iloc[:,157] if raw.shape[1]>157 else pd.Series('',index=raw.index);fc=raw.iloc[:,158] if raw.shape[1]>158 else pd.Series('',index=raw.index)
    keep=~(closed(cy)|closed(fb)|closed(fc)); rows=[]; pairs=material_pairs(raw)
    for _,r in raw.loc[keep].iterrows():
        wo=str(r.get('ProductionCode','')).strip();due=pd.to_datetime(r.get('กำหนดส่งใหม่'),errors='coerce');due=due if pd.notna(due) else pd.to_datetime(r.get('กำหนดเข้าคลัง'),errors='coerce')
        for mc,gc in pairs:
            code=str(r.get(mc,'')).strip(); grams=safe_num(r.get(gc))
            if code not in {'','0','nan','None','#N/A'} and grams>0:rows.append({'Source':'Open Plan-2026','Reference':wo,'Material Code':code,'Required kg':float(grams)/1000,'Need Date':due})
    mat=pd.DataFrame(rows)
    sales=fp('Sales-Forecast-LATEST.xlsx');pm=fp('P280526-LATEST.xlsx')
    if sales and pm:
        try:
            sd=pd.read_excel(pm,sheet_name='SD',header=1); sf=pd.read_excel(sales,sheet_name='Data Item FC26 (Revised)',header=3)
            idcol='รหัสสินค้า.1' if 'รหัสสินค้า.1' in sd.columns else next(c for c in sd.columns if str(c).strip().lower() in {'รหัสสินค้า','iditem','product code','productcode'})
            sid=next(c for c in sf.columns if 'IDItem' in str(c)); monthcols=[c for c in sf.columns if str(c).startswith('จำนวน')]
            # Prefer last non-empty recipe row per product; never invent a recipe.
            lookup={str(r[idcol]).strip():r for _,r in sd.iterrows() if pd.notna(r.get(idcol)) and str(r.get(idcol)).strip()}
            fr=[]; pairs2=material_pairs(sd)
            for _,sr in sf.iterrows():
                pid=str(sr.get(sid,'')).strip(); rr=lookup.get(pid)
                if rr is None:continue
                basis=safe_num(rr.get('QTY'))
                if basis<=0:continue
                for mc,gc in pairs2:
                    code=str(rr.get(mc,'')).strip();grams=safe_num(rr.get(gc))
                    if code in {'','0','nan','None','#N/A'} or grams<=0:continue
                    for c in monthcols:
                        q=safe_num(sr.get(c))
                        if q>0:fr.append({'Source':'Sales Forecast via SD','Reference':pid,'Material Code':code,'Required kg':float(q)*(float(grams)/float(basis))/1000,'Need Date':str(c)})
            if fr:mat=pd.concat([mat,pd.DataFrame(fr)],ignore_index=True)
        except Exception as e: st.warning(f'Forecast recipe diagnostic: {e}')
    return mat,pairs


def parse_new_request_reference(path):
    """Best-effort first-sheet extraction. Missing fields stay TO CONFIRM; planning must not fail."""
    out={'Reference File':Path(path).name}
    try:
        wb=load_workbook(path,data_only=True,read_only=True);ws=wb[wb.sheetnames[0]]
        texts=[]
        for row in ws.iter_rows():
            for c in row:
                if c.value not in (None,''): texts.append(str(c.value).strip())
        blob=' | '.join(texts)
        for label,key in [('Customer name:','Customer'),('เลขที่เอกสาร','Document No.')]:
            for i,v in enumerate(texts):
                if label.lower() in v.lower():
                    if ':' in v and v.split(':',1)[1].strip():out[key]=v.split(':',1)[1].strip()
                    elif i+1<len(texts):out[key]=texts[i+1]
                    break
        # RP forms place the document value either in the same cell or the next one;
        # a flattened row may also put an unrelated field between them.
        _doc=re.search(r'\bQ\d{2}-\d{3,}\b',blob,re.I)
        if _doc:out['Document No.']=_doc.group(0).upper()
        m=re.search(r'(?:Spec[:：]?\s*)([A-Za-z0-9.]+)',blob,re.I)
        if m:out['Specification']=m.group(1)
        m=re.search(r'(?:เปิดผลิต).*?([A-Za-z0-9.]+)\s+(\d+(?:\.\d+)?X\d+(?:\.\d+)?X\d+(?:\.\d+)?)\s*mm.*?จำนวน\s*([\d,]+)\s*P',blob,re.I)
        if m:out.update({'Specification':m.group(1),'Size':m.group(2),'Qty':float(m.group(3).replace(',',''))})
        m=re.search(r'(P\d{3}-\d{6})',blob)
        if m:out['Reference WO']=m.group(1)
        m=re.search(r'Material\s*\|?\s*([^|]+)',blob,re.I)
        if m:out['Material / Bond']=m.group(1).strip()
        m=re.search(r'(?:Machince|Machine)\s*\|?\s*([^|]+)',blob,re.I)
        if m:out['Machine']=m.group(1).strip()
        m=re.search(r'Program\s*(\d+)',blob,re.I)
        if m:out['Firing Program']=m.group(1)
        _box=re.search(r'(?:กล่องละ|บรรจุ|pack(?:ing)?[^|]{0,30}?)([\d,]+)\s*(?:ชิ้น|ก้อน|pcs?)\s*(?:ต่อกล่อง|/กล่อง|per\s*box)',blob,re.I)
        if _box:out['Packing Qty / Box']=int(_box.group(1).replace(',',''))
        _wrap=re.search(r'ห่อกระดาษ.{0,20}?([\d,]+)\s*(?:ชิ้น|ก้อน|pcs?)\s*(?:ต่อห่อ|/ห่อ)',blob,re.I)
        if _wrap:out['Paper Wrap Qty']=int(_wrap.group(1).replace(',',''))
        if re.search(r'ไม่ปั๊มตรา|no\s*brand|unbranded',blob,re.I):out['Brand / Mark']='No brand mark (RP text)'
        out['Detected Processes']='Preparing → Mixing → Pressing/Forming → Firing → Finishing/Cutting → Packing' if any('Preparing' in x for x in texts) else 'TO CONFIRM'
        wb.close()
    except Exception as e:out['Diagnostic']=str(e)
    return out

def qr_pack(all_work_orders=False, plan_df=None, section='All sections', date_from=None, date_to=None,
            status_filter='Open orders', date_field='due_date', include_undated=False):
    """Create QR labels from active Plan-2026 using requested status/date filters."""
    from suite.qr_labels import rows_from_plan_frame, filter_open_plan_rows, load_registry, save_registry, write_label_pack
    active_plan = plan_df if plan_df is not None else master
    rows = rows_from_plan_frame(active_plan)
    rows = filter_open_plan_rows(rows, section, date_from, date_to, status_filter, date_field, include_undated)
    source = 'Plan-2026-LATEST.xlsx' if rows else 'none'
    qrreg = SHARED_ROOT/'QR_REGISTRY.json'
    existing = load_registry(qrreg)
    if not rows:
        return None, 0, source
    sec_slug=re.sub(r'[^A-Za-z0-9_-]+','_',str(section or 'All_sections')).strip('_')[:35] or 'All_sections'
    df_from=date_from.strftime('%Y%m%d') if date_from else 'ALL'
    df_to=date_to.strftime('%Y%m%d') if date_to else 'ALL'
    _status_slug={'Open orders':'OPEN','Closed orders':'CLOSED','All orders':'ALL'}.get(status_filter,'OPEN')
    _date_slug='DUE' if date_field=='due_date' else 'CREATED'
    prefix = f'{_status_slug}_{_date_slug}_WO_QR' if all_work_orders else f'NEW_{_status_slug}_{_date_slug}_WO_QR'
    out = REPORTS/f'{prefix}_{sec_slug}_{df_from}_{df_to}_{bkk_now():%Y%m%d_%H%M%S}.xlsx'
    regmeta=_load_registry().get('Plan-2026-LATEST.xlsx',{})
    provenance={
        'Source workbook': str(regmeta.get('original_name') or (plan.name if plan else 'Plan-2026-LATEST.xlsx')),
        'Active stored copy': str(plan) if plan else str(SHARED_ROOT/'COMPANY_DATA'/'Plan-2026-LATEST.xlsx'),
        'Source workbook modified': str(regmeta.get('excel_document_modified_at') or 'not recorded'),
        'Imported/registered at': str(regmeta.get('registered_at') or regmeta.get('updated_at') or 'not recorded'),
        'Filter section': section or 'All sections',
        'Filter date field': 'Current due date' if date_field=='due_date' else 'Work order creation date',
        'Filter date range': f'{date_from or "all"} to {date_to or "all"}',
        'Filter order status': status_filter,
        'Include missing date': bool(include_undated),
        'Eligibility': 'Active Plan-2026 only; open means positive remaining quantity and not authoritatively closed; closed means Plan-2026 authoritative closure flag true',
        'QR format': 'SLWO:<UPPERCASE WORK ORDER> (IP-independent)',
    }
    path, n = write_label_pack(rows, out, REPORTS/'QR_TEMP', existing, all_work_orders, bkk_now(), provenance)
    if n:
        save_registry(qrreg, existing)
    return path, n, source

def english_plan_copy(plan):
    # Original is NEVER edited. Add an English-script companion column; Thai source name remains intact.
    out=REPORTS/f'Plan-2026_ENGLISH_CUSTOMERS_{bkk_now():%Y%m%d_%H%M%S}.xlsx'; shutil.copy2(plan,out)
    wb=load_workbook(out); ws=wb['แผนการเผา']; headers={str(c.value).strip():c.column for c in ws[3] if c.value is not None}; ccol=headers.get('Customername'); idcol=headers.get('CustomernameID')
    if not ccol: wb.close(); return out,0
    newcol=ws.max_column+1;ws.cell(3,newcol).value='Customername_English_Script'
    try:
        from pythainlp.transliterate import romanize
    except Exception:
        romanize=None
    n=0
    for row in range(4,ws.max_row+1):
        v=ws.cell(row,ccol).value; cid=ws.cell(row,idcol).value if idcol else ''
        txt=str(v or '').strip()
        if not txt: continue
        if re.search(r'[ก-๙]',txt):
            en=''
            if romanize:
                try: en=roman_customer_name(txt)
                except Exception: en=''
            # Never pretend an ID is a translation; it is an English-readable fallback reference.
            if not en: en=txt
            n+=1
        else: en=txt
        ws.cell(row,newcol).value=en
    ws.column_dimensions[ws.cell(3,newcol).column_letter].width=48
    wb.save(out);wb.close();return out,n

def packaging_plan(op):
    pk=packing_source.resolve_source(ROOT,DATA)
    if not pk:
        st.warning('Packaging source file is missing from the active source store.');return pd.DataFrame(),pd.DataFrame()
    try: std=packing_source.read_tables(pk)['Packaging standard']
    except Exception as ex:
        st.error(f'Packaging file is present but could not be read: {ex}');return pd.DataFrame(),pd.DataFrame()
    std=std.rename(columns={'รหัสสินค้า':'Product Code','ชื่อลูกค้า':'Pack Customer','Spec .สินค้า':'Pack Spec','จำนวนบรรจุต่อกล่อง':'Pcs/Box','กลุ่มงาน':'Pack Category'})
    std['Product Code']=std['Product Code'].astype(str).str.strip();std=std[std['Product Code'].ne('nan')].copy()
    _definition=['Pcs/Box']+[c for pair in packing_source.PAIRS for c in pair if c in std.columns]
    _unique=std[['Product Code']+_definition].astype(str).drop_duplicates();_conflicts=_unique['Product Code'].value_counts();_conflicts=set(_conflicts[_conflicts>1].index)
    if _conflicts:st.warning(f'{len(_conflicts)} product codes have conflicting packing definitions; these are excluded until reviewed.')
    std=std[~std['Product Code'].isin(_conflicts)].drop_duplicates('Product Code')
    x=op.copy(); pc='Product Code' if 'Product Code' in x.columns else 'Product Source'; x[pc]=x[pc].astype(str).str.strip(); x=x.merge(std,left_on=pc,right_on='Product Code',how='left')
    x['Pcs/Box']=pd.to_numeric(x.get('Pcs/Box'),errors='coerce'); x['Boxes Required']=np.ceil(pd.to_numeric(x['pcs'],errors='coerce').fillna(0)/x['Pcs/Box']).where(x['Pcs/Box']>0,np.nan)
    detail=x[[c for c in ['Work Order','Customer','Due Date',pc,'Product Category','D','T','H','pcs','Pcs/Box','Boxes Required','Pack Customer','Pack Spec'] if c in x.columns]].copy()
    # Material columns occur as code/quantity pairs after Pcs/Box. Multiply per-box component qty by required boxes.
    req=[]; cols=list(std.columns)
    for _,r in x[x['Boxes Required'].notna()].iterrows():
        boxes=float(r['Boxes Required'])
        for code_col,qty_col in [('กล่องนอก','จำนวน'),('กล่องใน','จำนวน.1'),('ไส้ใน','จำนวน.2'),('ตราสินค้า','จำนวน.3'),('แผนรอง 1','จำนวน.4'),('แผนรอง 2','จำนวน.5'),('แผนรอง 3','จำนวน.6'),('บู๊ซ 1','จำนวน.7'),('บู๊ซ 2','จำนวน.8'),('บู๊ซ 3','จำนวน.9'),('บู๊ซ 4','จำนวน.10'),('ใบรับประกัน','จำนวน.11'),('คู่มือการใช้งาน','จำนวน.12'),('อื่น ๆ','จำนวน.13')]:
            if code_col not in x.columns or qty_col not in x.columns:continue
            code=str(r.get(code_col,'')).strip(); q=pd.to_numeric(pd.Series([r.get(qty_col)]),errors='coerce').fillna(0).iloc[0]
            if code and code not in {'-','nan','None'} and q>0:req.append({'Packaging Code':code,'Required Qty':boxes*float(q),'Work Order':r.get('Work Order',''),'Due Date':r.get('Due Date')})
    req=pd.DataFrame(req)
    # Same-size alternative packaging: use another CURRENT open product with identical D/T/H that has a standard.
    if all(c in detail.columns for c in ['D','T','H']):
        def _sz(r):
            vals=[]
            for c in ['D','T','H']:
                try: vals.append(round(float(r.get(c)),4))
                except: vals.append(None)
            return tuple(vals)
        detail['_size_key']=detail.apply(_sz,axis=1)
        good=detail[detail['Pcs/Box'].notna()].copy()
        amap={}
        for sk,g in good.groupby('_size_key'):
            amap[sk]=' | '.join(g[pc].astype(str).drop_duplicates().head(12).tolist())
        detail['Same-size packaging options']=detail['_size_key'].map(amap).fillna('')
        detail=detail.drop(columns=['_size_key'])
    return detail,req

# Compact language control. The Home banner carries the brand, so do not repeat its title above it.
if st.query_params.get('page','control') == 'control':
    _lang_col,_lang_spacer=st.columns([1.45,5.55])
    with _lang_col:
        lang=st.radio('Language',['English','ไทย'],horizontal=True,key='global_language',label_visibility='collapsed')
else:
    _hc1,_hc2=st.columns([5,1.8])
    with _hc1:
        st.markdown('### 🏭 SL Carborundum')
    with _hc2:
        lang=st.radio('Language',['English','ไทย'],horizontal=True,key='global_language',label_visibility='collapsed')
st.session_state['lang']=lang
st.markdown(_language_font_css(lang), unsafe_allow_html=True)
# Daily / Firing / phone start when that tab is opened — not on every hub boot.
L={'English':{'control':'🏠 HOME','daily':'📅 DAILY','firing':'🔥 FIRING','audit':'⚡ QR / AUDIT','wip':'🏭 WIP','back':'🚨 BACKORDER','mps':'🗓️ MPS','mrp':'🧪 MRP','pack':'📦 PACKAGING','src':'📥 SOURCES + QR'},'ไทย':{'control':'🏠 หน้าหลัก','daily':'📅 แผนรายวัน','firing':'🔥 แผนเตา','audit':'⚡ QR / ตรวจหน้างาน','wip':'🏭 งานระหว่างทำ','back':'🚨 งานค้างส่ง','mps':'🗓️ แผนหลัก','mrp':'🧪 วัตถุดิบ','pack':'📦 บรรจุภัณฑ์','src':'📥 ข้อมูล + QR'}}[lang]
try:(DATA/'UI_LANGUAGE.txt').write_text(lang,encoding='utf-8')
except:pass
_pub,_mob_up=mobile_public()
_pub,_phone_primary,_phone_http,_phone_https,_https_up,_http_up=phone_app_urls()
st.sidebar.caption(f"Phone app: {_phone_primary}")
st.sidebar.caption(f"HTTP (opens now): {_phone_http}")
st.sidebar.caption(f"HTTPS (camera): {_phone_https}")
st.sidebar.caption(f"Cert install (once): {_pub['http']}/tls/ca.crt")
st.sidebar.markdown('### 👤 USER / ผู้ใช้')
if not st.session_state.get('sl_authenticated'):
    _ticket_user=None
    try:
        from suite.hub_auth import validate as _validate_hub_ticket
        _ticket_user=_validate_hub_ticket(DATA,st.query_params.get('auth_ticket',''))
        if _ticket_user:
            from suite.demo_accounts import find_user as _find_ticket_user
            _current=_find_ticket_user(DB,_ticket_user['username'])
            if not _current or not _current.get('active',1): _ticket_user=None
            else:
                st.session_state['sl_authenticated']=True
                st.session_state['sl_user']=_current['username']
                st.session_state['sl_role']=_current['role']
    except Exception:
        _ticket_user=None
if st.session_state.get('sl_authenticated'):
    if not st.query_params.get('auth_ticket'):
        _ticket=hub_auth_ticket()
        if _ticket: st.query_params['auth_ticket']=_ticket
    st.sidebar.success(f"Authenticated • {st.session_state.get('sl_role')}")
    if st.sidebar.button('SIGN OUT / SWITCH USER · ออกจากระบบ',use_container_width=True):
        for _k in ['sl_authenticated','sl_user','sl_role']:st.session_state.pop(_k,None)
        if 'auth_ticket' in st.query_params: del st.query_params['auth_ticket']
        st.rerun()
else:
    st.session_state['sl_user']='VIEWER';st.session_state['sl_role']='viewer'
    with st.sidebar.expander('🔐 Switch login / Edit access',expanded=True):
        with st.form('hub_login_form',clear_on_submit=False):
            _lu=st.text_input('Username',key='hub_login_user')
            _lp=st.text_input('Password',type='password',key='hub_login_pass')
            _go=st.form_submit_button('LOGIN',use_container_width=True)
        if _go:
            _u=hub_login(_lu,_lp)
            if _u:
                st.session_state['sl_authenticated']=True;st.session_state['sl_user']=_u['username'];st.session_state['sl_role']=_u['role']
                _ticket=hub_auth_ticket()
                if _ticket: st.query_params['auth_ticket']=_ticket
                st.rerun()
            else:
                st.error('Login unsuccessful. Check the account details or contact the software administrator.')
        st.caption('Use the account issued by your software administrator. Credentials and server storage paths are not displayed here.')
st.session_state['sl_section']=st.sidebar.selectbox('Department / แผนก',['Planning Department','Production Support','Preparation','Mixing','Forming','Firing','Grinding','Cutting','Packing','QC','Purchase','Management'],index=0)
st.sidebar.caption('Login stays across pages for 30 days. Use SIGN OUT / SWITCH USER to end it sooner.')

# Compact meeting mode: no large banner.
st.sidebar.markdown(f"<div style='font-size:.82rem;padding:6px 8px;border-radius:10px;background:#fff'><b>🕒 {bkk_now():%d %B %Y • %H:%M:%S}</b></div>",unsafe_allow_html=True)
with st.sidebar.expander('🔎 Meeting mode',expanded=False):
    _meet=st.toggle('Large meeting display',value=st.session_state.get('meeting_mode',False),key='meeting_mode')
_zoom=st.sidebar.select_slider('Display zoom',options=['100%','110%','125%','140%'],value='125%' if _meet else '100%',key='display_zoom')
_scale={'100%':1.0,'110%':1.10,'125%':1.25,'140%':1.40}[_zoom]
st.markdown(
    f"<style>section.main p,section.main li,section.main label,[data-testid='stMarkdownContainer'] p,[data-testid='stCaptionContainer'] p,[data-testid='stWidgetLabel'] p{{font-size:{16*_scale:.1f}px}}"
    f" [data-testid='stMetricValue']{{font-size:{1.9*_scale:.2f}rem}} .stTabs [data-baseweb='tab']{{font-size:{1.02*_scale:.2f}rem}}</style>",
    unsafe_allow_html=True,
)
st.sidebar.markdown('### 🧭 NAVIGATION / เมนู')

SECTION_STATUS_FIELDS = [
 ('Preparation','CY','Preparation status / สถานะเตรียม'),
 ('Mixing','DH','Mixing status / สถานะผสม'),
 ('Forming','DR','Forming close / ปิดขึ้นรูป'),
 ('Firing','EC','Firing close / ปิดเผา'),
 ('Grinding','EL','Grinding close / ปิดเจียร'),
 ('Packing','FB','Packing/status / สถานะบรรจุ'),
 ('Production','FC','Production close / ปิดของผลิต'),
 ('Planning','IA',"Akash/Planning close / ปิดของ Akash"),
]
PROCESS_LOCATION_FIELDS = [
 ('Production order issued','HH'),('Planning','HI'),('Preparation started','HJ'),('Waiting mixing','HK'),
 ('Mixing started','HL'),('Waiting forming','HM'),('Forming started','HN'),('Waiting kiln loading','HO'),
 ('Loaded kiln','HP'),('Firing','HQ'),('Unloaded kiln','HR'),('Waiting sorting','HS'),
 ('Grinding started','HT'),('Waiting packing','HU'),('Packing started','HV'),('Waiting dispatch','HW'),('Dispatch started','HX')
]
def _excel_col_idx(col):
    n=0
    for ch in col.upper(): n=n*26+(ord(ch)-64)
    return n
def _norm_wo(v):
    """Normalize typed, scanned and legacy URL WO values for comparisons."""
    s=urllib.parse.unquote(str(v or '')).strip()
    # QR payloads generated by this app use SLWO:<id>; old labels may be full URLs.
    s=s.rstrip('/').split('/')[-1].strip()
    s=re.sub(r'^(?:SLWO|WO)\s*[:#=-]\s*','',s,flags=re.I)
    return re.sub(r'[^A-Z0-9]','',s.upper())

def plan2026_wo_suggestions(raw_df, query, limit=12):
    """Search only needed source columns; don't copy thousands of inflated Excel columns."""
    if not query or raw_df is None or raw_df.empty:return pd.DataFrame()
    q=_norm_wo(query); qtext=str(query).strip().casefold()
    code_col='ProductionCode'
    if code_col not in raw_df.columns:return pd.DataFrame()
    code=raw_df[code_col].fillna('').astype(str).str.strip()
    code_key=code.map(_norm_wo)
    code_mask=(code_key.str.startswith(q)|code_key.str.contains(re.escape(q),regex=True)) if q else pd.Series(False,index=raw_df.index)
    text_cols=[c for c in ['Customername','CustomernameID','รหัสสินค้า','Specification','ORDER','PO.NO.'] if c in raw_df.columns]
    text_mask=pd.Series(False,index=raw_df.index)
    if qtext:
        for c in text_cols:
            text_mask |= raw_df[c].fillna('').astype(str).str.casefold().str.contains(re.escape(qtext),regex=True,na=False)
    mask=code_mask|text_mask
    if not mask.any():return pd.DataFrame()
    cols=[c for c in ['ProductionCode','Customername','CustomernameID','รหัสสินค้า','Specification','QTY','กำหนดส่งใหม่','กำหนดเข้าคลัง','ORDER','PO.NO.'] if c in raw_df.columns]
    out=raw_df.loc[mask,cols].copy()
    out.insert(0,'Plan row',out.index.astype(int)+4)
    out.insert(1,'Work Order',code.loc[out.index].values)
    def _rank(row):
        k=_norm_wo(row.get('Work Order',''))
        if q and k==q:return (0,len(k))
        if q and k.startswith(q):return (1,len(k))
        if q and q in k:return (2,len(k))
        return (3,len(k))
    out['_rank']=out.apply(_rank,axis=1)
    return out.sort_values('_rank',kind='stable').drop(columns='_rank').head(limit)

def _open_closed(v):
    x=str(v or '').strip()
    low=x.lower()
    if not x:return 'OPEN / ยังเปิด'
    if any(k in low for k in ['ปิด','closed','close','complete','cancel','ยกเลิก']):return 'CLOSED / ปิด'
    return 'OPEN / ยังเปิด'
def plan2026_wo_detail(plan_path, query, raw_df=None):
    q=_norm_wo(query)
    if not q or not plan_path:return None
    try:
        # The Home page already loaded this workbook. Use its in-memory index to avoid
        # reopening a 16 MB workbook on every Streamlit rerun while the operator types.
        if raw_df is not None and not raw_df.empty and 'ProductionCode' in raw_df.columns:
            _vals=raw_df['ProductionCode'].fillna('').astype(str).str.strip()
            _mask=_vals.map(_norm_wo).eq(q)
            if _mask.any():
                _ix=raw_df.index[_mask][0]; _r=raw_df.loc[_ix]
                def _v(*names):
                    for _n in names:
                        if _n in _r.index and pd.notna(_r[_n]):return _r[_n]
                    return None
                _process_dates=[]
                for _pc in list(raw_df.columns[94:105]):
                    _pv=_v(_pc)
                    _pd=pd.to_datetime(_pv,errors='coerce')
                    if pd.notna(_pd):_process_dates.append({'Process':str(_pc),'Planned Date':_pd.date().isoformat()})
                _sections=[]
                for _sec,_col,_label in SECTION_STATUS_FIELDS:
                    _value=_v(_label,_sec,_col)
                    _sections.append({'Section':_sec,'Plan-2026 field':_col,'Source value':_value,'Open / Closed':_open_closed(_value)})
                _loc='Not identified from HH:HX';_loc_source=''
                for _label,_col in PROCESS_LOCATION_FIELDS:
                    _value=_v(_label,_col)
                    if pd.notna(_value) and str(_value).strip() not in ('','0','0.0'):
                        _loc=_label;_loc_source=f'{_col}={_value}'
                return {'row':int(_ix)+4,'wo':_vals.loc[_ix],
                        'customer':_v('Customername','Customer','Customer Thai'),
                        'product':_v('รหัสสินค้า','Product Code','Specification'),
                        'qty':_v('QTY','Order Qty','Quantity'),
                        'initial_due':_v('กำหนดเข้าคลัง','Due Date','Initial Due'),
                        'revised_due':_v('กำหนดส่งใหม่','Revised Delivery','Revised Due'),
                        'sales_due':_v('กำหนดส่งมอบขาย','Sales Delivery'),
                        'mill_batches':_v('จำนวนโม่','Mill Batches'),
                        'sections':_sections,'process_dates':_process_dates,'location':_loc,'location_source':_loc_source,
                        'source':'Loaded Plan-2026 dataframe'}
        wb=load_workbook(plan_path,data_only=True,read_only=True)
        ws=wb['แผนการเผา'] if 'แผนการเผา' in wb.sheetnames else wb[wb.sheetnames[0]]
        found=None
        # Find the declared ProductionCode column; older code silently assumed A.
        _header={str(c.value).strip():c.column for c in ws[3] if c.value is not None}
        _wo_col=_header.get('ProductionCode',1)
        _maxrow=ws.max_row or 1048576
        for r in range(4,_maxrow+1):
            wo=ws.cell(r,_wo_col).value
            if _norm_wo(wo)==q:
                found={'row':r,'wo':wo,'customer':ws.cell(r,_excel_col_idx('F')).value,'product':ws.cell(r,_excel_col_idx('K')).value,
                       'qty':ws.cell(r,_excel_col_idx('J')).value,'initial_due':ws.cell(r,_excel_col_idx('C')).value,
                       'revised_due':ws.cell(r,_excel_col_idx('E')).value,'sales_due':ws.cell(r,_excel_col_idx('IB')).value,
                       'mill_batches':ws.cell(r,_excel_col_idx('BY')).value}
                found['process_dates']=[]
                for _c in range(95,106):
                    _name=ws.cell(3,_c).value;_value=ws.cell(r,_c).value;_date=pd.to_datetime(_value,errors='coerce')
                    if _name and pd.notna(_date):found['process_dates'].append({'Process':str(_name),'Planned Date':_date.date().isoformat()})
                found['sections']=[]
                for sec,col,label in SECTION_STATUS_FIELDS:
                    raw=ws.cell(r,_excel_col_idx(col)).value
                    found['sections'].append({'Section':sec,'Plan-2026 field':col,'Source value':raw,'Open / Closed':_open_closed(raw)})
                found['location']='Not identified from HH:HX'
                found['location_source']=''
                for label,col in PROCESS_LOCATION_FIELDS:
                    raw=ws.cell(r,_excel_col_idx(col)).value
                    if raw not in (None,'',0):
                        found['location']=label;found['location_source']=f'{col}={raw}'
                found['source']='Plan-2026 workbook';break
        wb.close();return found
    except Exception as e:
        return {'lookup_error':str(e),'source_path':str(plan_path)}

_TREE=[('▾ HOME & REFERENCE',[('🏠 Home / Main Page','control'),('📚 Code & Part Knowledge','knowledge')]),
       ('▾ PLANNING',[('📅 Daily Production Plan','daily'),('🔥 Firing / Kiln Plan','firing'),('🗓️ MPS / Future Plan','mps'),('🆕 New Part Plan','newplan'),('📦 Stock-on-Hand Material Status','material'),('🧪 Material MRP','mrp'),('⚖️ Capacity / Recovery','capacity'),('⚖️ Capacity vs Plan vs Actual','capacity_actual'),('📦 Packaging Plan','pack'),('🧰 Planning Suite','suite')]),
       ('▾ PRODUCTION & PART TRACKING',[('📋 Update WO Section Status','floor'),('⚡ Mobile Part Audit / QR','audit'),('📋 Mobile Audit Register','audits')]),
       ('▾ REPORTS',[('📋 Daily Open / Closed WO Report','daily_closed'),('🏭 WIP — Planning vs Production','wip'),('📡 Daily Status Analysis','daily_status'),('🎯 Monthly Planning KPI Scorecard','kpi'),('🎯 Department KPI Workbook Analysis','daily_kpi'),('💰 Cost & Planning KPI Analysis','cost'),('🚨 Backorder / Delivery Risk','back'),('🧯 Weekly Recovery Action Plan','daily_recovery'),('📄 Production Recovery Plan — source status, reasons & WO detail','recovery_review'),('🕘 Usage & Edit History','history')]),
       ('▾ DATA & CONTROL',[('📥 Upload / Replace Source Files','src'),('🔎 Source Traceability','src')])]
_goto_terms={
 'daily':'download plan excel export daily production schedule แผนรายวัน ดาวน์โหลดแผน',
 'material':'stock on hand material status inventory raw material shortage balance วัตถุดิบ สถานะวัตถุดิบ คงคลัง',
 'daily_closed':'open closed status section wo scan เปิด ปิด สถานะ ใบสั่งผลิต',
 'daily_status':'daily status analysis section workbook แผนกสถานะรายวัน',
 'wip':'wip work in progress production planning งานระหว่างทำ',
 'recovery_review':'production recovery plan backorder recovery commitments reason behind plan production status recovery vs plan',
 'kpi':'monthly planning kpi scorecard ตัวชี้วัดรายเดือน',
 'daily_kpi':'department kpi workbook two files warehouse delivery',
 'cost':'cost costing material cost planning KPI ต้นทุน',
 'floor':'scan wo update section status barcode qr',
 'audit':'mobile audit qr part photo location desktop status',
 'audits':'audit register search history export',
 'src':'upload source files traceability daily status source',
 'back':'backorder delivery risk late overdue',
 'daily_recovery':'backorder recovery risk recovery action plan weekly factory performance',
 'recovery_review':'recovery production committed plan snapshot sales product register packaging standard compare pack quantity',
 'newplan':'new part plan new order provisional',
 'capacity':'capacity recovery overload overtime','capacity_actual':'capacity vs plan vs actual utilization daily section กำลังการผลิต แผน ผลิตจริง',
 'knowledge':'knowledge code part help f1 thai english',
 'pack':'packaging plan box', 'mrp':'material stock shortage purchase',
 'mps':'master schedule forecast', 'firing':'firing kiln plan', 'history':'edit history usage',
 'suite':'planning suite'
}
_goto_rows=[]
for _g0,_its0 in _TREE:
    for _lb0,_pg0 in _its0:_goto_rows.append((_lb0.strip(),_pg0,_goto_terms.get(_pg0,'')))
_goto_rows += [('📤 Upload Daily Status files / อัปโหลดสถานะรายวัน','src',''),('📤 Upload Plan-2026 & other source files','src',''),('⬇️ Download Complete Daily Plan','daily_download','download plan excel export'),('📦 Material Status / Stock on Hand','daily_material','stock inventory raw material availability shortage balance วัตถุดิบ สถานะวัตถุดิบ คงคลัง')]
_search=st.sidebar.text_input('🔎 Search any function / ค้นหาฟังก์ชัน',key='function_search',placeholder='KPI, WIP, scan, download, เปิด/ปิด…')
if _search.strip():
    _needle=_search.strip().casefold()
    _matches=[(lb,pg) for lb,pg,terms in _goto_rows if _needle in lb.casefold() or _needle in terms.casefold()]
    if _matches:
        _pick=st.sidebar.selectbox('Matching pages / หน้าที่พบ',[x[0] for x in _matches],key='function_search_matches')
        _target=dict((lb,pg) for lb,pg in _matches).get(_pick)
        if st.sidebar.button('OPEN FUNCTION / เปิดฟังก์ชัน',use_container_width=True,key='function_search_open'):
            if _target=='daily_download':
                st.query_params['page']='daily';st.query_params['focus']='download'
            else:st.query_params['page']=_target
            st.rerun()
    else:st.sidebar.info('No matching function. Try: KPI, WIP, Daily Status, QR, or Download.')
for _grp,_items in _TREE:
    with st.sidebar.expander(_grp,expanded=_grp=='▾ HOME & REFERENCE'):
        for _label,_page in _items:
            _active=st.query_params.get('page','control')==_page
            _bg='#fff0e3' if _active else '#fff';_border='#e76613' if _active else '#f2c7a7'
            if st.button(('✓ ' if _active else '↳ ')+_label, key='nav28_'+str(_TREE.index((_grp,_items)))+'_'+str(_items.index((_label,_page))), use_container_width=True):
                st.query_params['page']=_page
                st.rerun()
st.sidebar.caption('Workflow: plan → shop-floor status → reports → source traceability. WIP and monthly Planning KPI each have one central page.')

# Active files are visible from every tab.
with st.sidebar.expander('📁 ACTIVE FILES / ไฟล์ที่ใช้อยู่',expanded=False):
    _reg0=_load_registry()
    for _nm in ['Plan-2026-LATEST.xlsx','Firing-Plan-LATEST.xlsx','Job-Register-LATEST.xlsx','Process-Close-LATEST.xlsx','Sales-Forecast-LATEST.xlsx','Stock-on-Hand-LATEST.xlsx','P280526-LATEST.xlsx','Packaging-Standard-LATEST.xlsx']:
        _pp=fp(_nm);_rr=_reg0.get(_nm,{})
        if _pp:
            _mt=datetime.fromtimestamp(_pp.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            st.markdown(f"**{_nm}**  \nModified: {_mt}  \nUploaded through: {_rr.get('uploaded_through','existing/seeded')}  \nOriginal name: {_rr.get('original_name',_nm)}")
        else: st.caption(f'❌ {_nm} — not loaded')
    st.caption('A blank upload box after page navigation is ready for another file; it does not mean the saved source was erased. Active files remain in CENTRAL_DATA and are listed above. Exact paths and revisions are under Files & Traceability.')

# Load shared planning truth only on pages that need the analysed tables.
plan=fp('Plan-2026-LATEST.xlsx'); raw=master=op=bo=None
_reg=_load_registry()
if plan:
    _r=_reg.get('Plan-2026-LATEST.xlsx',{})
    st.sidebar.success(f"ACTIVE PLAN: {plan.name}")
    st.sidebar.caption(f"Location: {plan}\nUpdated: {_r.get('updated_at','existing file')}\nBy: {_r.get('updated_by','—')} / {_r.get('section','—')}")
else: st.sidebar.error('ACTIVE PLAN: NOT LOADED')
# Files & Traceability also hosts the Plan-2026 QR label filters. Load the same
# analyzed active plan there so section choices and open/closed eligibility are
# based on the current shared workbook, not an empty local `master` variable.
_NEED_PLAN={'back','mps','mrp','pack','audit','wip','report','audits','newplan','floor','src','recovery_review'}
def _ensure_plan_model():
    global raw,master,op,bo
    if master is not None or not plan:
        return
    try:
        raw,master,op,bo=model(str(plan),plan.stat().st_mtime)
        st.session_state.pop('plan_analysis_error',None)
        if master is not None:
            master=_apply_customer_language(master, lang)
            if op is not None: op=_apply_customer_language(op, lang)
            if bo is not None: bo=_apply_customer_language(bo, lang)
            if hub_is_production_context():
                # Do not leave customer names available in a production session's dataframes.
                raw=mask_customer_columns(raw,drop=True)
                master=mask_customer_columns(master,drop=True)
                op=mask_customer_columns(op,drop=True) if op is not None else op
                bo=mask_customer_columns(bo,drop=True) if bo is not None else bo
    except Exception as e:
        st.session_state['plan_analysis_error']=f'{type(e).__name__}: {e}'
        st.sidebar.warning(f'Shared Plan analysis: {e}')
    # A report-transform failure must not blank the current Plan WIP. Use the
    # supported light parser to recover the open-balance list for WIP/dashboard.
    if plan and (op is None or (isinstance(op,pd.DataFrame) and op.empty)):
        try:
            _fallback_op=_cached_plan_wip_fallback(str(plan.resolve()),plan.stat().st_mtime_ns,plan.stat().st_size)
            if isinstance(_fallback_op,pd.DataFrame) and not _fallback_op.empty:
                op=_apply_customer_language(_fallback_op,lang)
                st.session_state['plan_wip_fallback_note']='Plan WIP was read using the lightweight Plan-2026 open-balance parser.'
        except Exception as _fallback_error:
            st.session_state['plan_wip_fallback_error']=f'{type(_fallback_error).__name__}: {_fallback_error}'
if st.query_params.get('page','control') in _NEED_PLAN:
    _ensure_plan_model()

try:
    if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
    from suite.suite_page import install_f1 as _install_f1
    _install_f1(ROOT)
except Exception as _f1e:
    st.sidebar.caption(f'F1 help unavailable: {_f1e}')
_page=st.query_params.get('page','control')
_PAGE_TITLES={
 'control':'Home / หน้าหลัก','daily':'Daily Production Plan / แผนผลิตรายวัน','material':'Stock-on-Hand Material Status / สถานะวัตถุดิบคงคลัง','firing':'Firing / Kiln Plan / แผนเผา',
 'floor':'WO Section Status / สถานะใบสั่งผลิตรายแผนก','audit':'Part Tracking & Audit / ติดตามและตรวจสอบชิ้นงาน',
 'report':'Audit Report / รายงานตรวจสอบ','audits':'Mobile Audit Register / ทะเบียนตรวจสอบมือถือ',
 'daily_closed':'Daily Open / Closed / เปิด-ปิดรายวัน','daily_status':'Daily Status Analysis / วิเคราะห์สถานะรายวัน','capacity_actual':'Capacity vs Plan vs Actual / กำลังผลิตเทียบแผนและผลจริง',
 'daily_kpi':'Department KPI Analysis / วิเคราะห์ KPI แผนก','daily_recovery':'Weekly Recovery Plan / แผนกู้คืนรายสัปดาห์','recovery_review':'Production Recovery Plan vs Plan-2026 / แผนกู้คืนฝ่ายผลิตเทียบ Plan-2026',
 'wip':'WIP: Planning vs Production / งานระหว่างทำ','kpi':'Planning KPI Scorecard / KPI วางแผน',
 'cost':'Cost & Planning KPI / ต้นทุนและ KPI','back':'Backorder & Delivery Risk / งานค้างและความเสี่ยงส่งมอบ',
 'mps':'MPS / แผนการผลิตหลัก','mrp':'Material MRP / วัตถุดิบ','pack':'Packaging Plan / แผนบรรจุภัณฑ์',
 'capacity':'Capacity & Recovery / กำลังผลิตและแผนฟื้นฟู','newplan':'New Part Plan / แผนชิ้นงานใหม่',
 'src':'Files & Traceability / ไฟล์และการตรวจสอบย้อนกลับ','knowledge':'Code & Part Knowledge / ความรู้รหัสและชิ้นงาน',
 'history':'Usage & Edit History / ประวัติการใช้และแก้ไข','suite':'Planning Suite / ชุดเครื่องมือวางแผน','more':'Reports & Tools / รายงานและเครื่องมือ'}
_current_title=_PAGE_TITLES.get(_page,_page.replace('_',' ').title())
if _page == 'control':
    _home_photo=ROOT/'assets'/'hero.jpg'; _home_photo_stat=_home_photo.stat() if _home_photo.exists() else None
    _home_photo_b64=_cached_home_photo(str(_home_photo),int(_home_photo_stat.st_mtime_ns),int(_home_photo_stat.st_size)) if _home_photo_stat else ''
    _home_photo_layer=(f"url('data:image/jpeg;base64,{_home_photo_b64}')" if _home_photo_b64 else 'linear-gradient(90deg,#12395b,#36749b)')
    st.markdown(f'''<section role="img" aria-label="SL Carborundum branded product banner" style="overflow:hidden;height:126px;margin:0 0 7px;padding:0;border-radius:14px;background-color:#12395b;background-image:{_home_photo_layer};background-size:cover;background-position:center 48%;box-shadow:0 4px 12px rgba(18,57,91,.12)"></section>''',unsafe_allow_html=True)
st.markdown(f"<div style='padding:6px 10px;margin:2px 0 8px;border-left:4px solid #e76613;background:#f7f9fc;border-radius:7px;color:#12395b'><small>YOU ARE HERE / ตำแหน่งปัจจุบัน</small>　<b>{_current_title}</b></div>",unsafe_allow_html=True)
if _page in ('daily_wip','daily_closed','daily_status','daily_kpi','daily_recovery','kpi','wip','capacity_actual'): _nav='more'
elif _page in ('audit','report','audits','floor'): _nav='audit'
elif _page in ('back','mps','material','mrp','pack','capacity','newplan','history','knowledge','suite','more','wip','kpi','recovery_review'): _nav='more'
elif _page in ('control','daily','firing','src'): _nav=_page
else: _nav='control'; _page='control'
_pill_en={'control':'🏠 Home','daily':'📅 Daily','firing':'🔥 Firing','audit':'⚡ Track / QR','src':'📥 Files','more':'📊 Reports & Tools'}
_pill_th={'control':'🏠 หน้าหลัก','daily':'📅 แผนรายวัน','firing':'🔥 แผนเตา','audit':'⚡ ติดตาม / QR','src':'📥 ไฟล์','more':'📊 รายงานและเครื่องมือ'}
_pills=_pill_th if lang=='ไทย' else _pill_en
def _hub_page_href(page, focus=''):
    _q={'page':page}
    if focus:_q['focus']=focus
    _t=st.query_params.get('auth_ticket','')
    if _t:_q['auth_ticket']=_t
    # Explicit same-document relative path works when the Planning Center is
    # hosted at /, behind a reverse proxy, or under a sub-path. Raw '?page=...'
    # links were unreliable in embedded/forwarded deployments.
    return './?'+urllib.parse.urlencode(_q)
st.markdown('<div class="sl-pills">'+''.join(
    f"<a class='{'on track' if k=='audit' and _nav==k else ('on' if _nav==k else ('track' if k=='audit' else ''))}' href='{_hub_page_href(k)}' target='_self'>{_pills[k]}</a>"
    for k in ('control','daily','firing','audit','src','more')
)+'</div>',unsafe_allow_html=True)
st.markdown(f"<div class='sl-quick-title'>{'เปิดใช้ด่วน' if lang=='ไทย' else 'Quick access'}</div>",unsafe_allow_html=True)
_fastlinks=[('📅','แผนรายวัน' if lang=='ไทย' else 'Daily plan','daily',''),('📦','สถานะวัตถุดิบ' if lang=='ไทย' else 'Material status','material',''),('⬇','ดาวน์โหลดแผน' if lang=='ไทย' else 'Download plan','daily','download'),('⚖️','กำลังผลิต vs แผน vs ผลจริง' if lang=='ไทย' else 'Capacity vs Plan vs Actual','capacity_actual',''),('📋','เปิด/ปิดรายวัน' if lang=='ไทย' else 'Daily status','daily_closed',''),('🏭','WIP','wip',''),('🚨','งานค้างส่ง' if lang=='ไทย' else 'Backorders','back',''),('🧯','แผนปฏิบัติการรายสัปดาห์' if lang=='ไทย' else 'Weekly recovery actions','daily_recovery',''),('📄','แผนกู้คืนฝ่ายผลิต' if lang=='ไทย' else 'Production Recovery Plan','recovery_review',''),('🎯','KPI','kpi',''),('⚡','ตรวจสอบชิ้นงาน' if lang=='ไทย' else 'Part audit','audit',''),('📊','รายงานตรวจสอบ' if lang=='ไทย' else 'Audit report','report','')]
st.markdown('<nav class="sl-quicklinks" aria-label="Quick access">'+''.join(f"<a href='{_hub_page_href(_pg,_focus)}' target='_self'><span aria-hidden='true'>{_icon}</span>{_label}</a>" for _icon,_label,_pg,_focus in _fastlinks)+'</nav>',unsafe_allow_html=True)
_render_context_source_updates(_page)
if _page not in ('control','src'):
    st.markdown(f"<a href='{_hub_page_href('src')}' target='_self' style='display:inline-block;font-size:.78rem;color:#0057b8;text-decoration:underline;margin:0 0 8px'>↗ Upload / replace source file used by this analysis</a>",unsafe_allow_html=True)
from suite.service_launcher import is_phone_ua as _is_phone_ua
try:
    _ua=_hub_headers().get('User-Agent') or _hub_headers().get('user-agent') or ''
except Exception:
    _ua=''
if _is_phone_ua(_ua):
    st.markdown(
        f"<a href='{_hub_page_href('floor')}' target='_self' style='display:block;padding:14px;background:#e76613;color:#fff;border-radius:12px;text-align:center;font-weight:900;text-decoration:none;margin:0 0 8px'>📱 {('สแกนใบสั่ง — เปิด/ปิดแต่ละแผนก' if lang=='ไทย' else 'Scan WO — section OPEN / CLOSED')}</a>"
        f"<a href='{_phone_primary}' target='_self' style='display:block;padding:12px;background:#0057b8;color:#fff;border-radius:12px;text-align:center;font-weight:900;text-decoration:none;margin:0 0 12px'>📱 {('แอปมือถือสำรอง (พอร์ต 8000) — ห้ามใช้ 127.0.0.1' if lang=='ไทย' else 'Backup phone app (port 8000) — do not use 127.0.0.1')}</a>",
        unsafe_allow_html=True,
    )

if _page in ('control',):
    if DB_MIGRATION_STATUS.get('state')=='MIGRATED':
        st.success('Previous audit database restored from the former shared location. Existing audit rows and users are available again; source database was left unchanged.')
    elif DB_MIGRATION_STATUS.get('state')=='AUDIT_HISTORY_MERGED':
        st.success(f"Recovered {DB_MIGRATION_STATUS.get('audits_added',0)} previous audit record(s) and {DB_MIGRATION_STATUS.get('photos_added',0)} photo reference(s). Both database copies were preserved.")
    elif DB_MIGRATION_STATUS.get('state')=='CONFLICT':
        st.error('Two databases contain records. Nothing was overwritten. Previous audit data may still be in the former database; ask the administrator to reconcile the database copies before using the new one.')
    if PHOTO_RECOVERY_STATUS.get('copied'):
        st.success(f"Recovered {PHOTO_RECOVERY_STATUS['copied']} missing audit photo file(s) into the active photo folder. Original photo files were kept.")
    if PHOTO_RECOVERY_STATUS.get('missing'):
        st.warning(f"{PHOTO_RECOVERY_STATUS['missing']} audit photo file(s) are still not in the active folder. Their database references were preserved; check the former photo folder and exact paths in Files & Traceability.")
    # One shortcut set only: compact Quick access links above.
    c1,c2,c3,c4=st.columns(4)
    from suite.service_launcher import probe as _svc_probe, mobile_https_up as _https_up
    if not mobile_online() and not st.session_state.get('_home_mobile_autostart_requested'):
        st.session_state['_home_mobile_autostart_requested']=True
        def _start_mobile_in_background():
            try:
                from suite.service_launcher import ensure as _ensure_mobile_sidecar
                _ensure_mobile_sidecar('mobile', wait_seconds=12)
            except Exception:
                pass
        threading.Thread(target=_start_mobile_in_background, name='sl-mobile-autostart', daemon=True).start()
    c1.metric('Daily Planner','ONLINE' if _svc_probe('daily') else 'NOT READY');c2.metric('Firing Planner','ONLINE' if _svc_probe('firing') else 'NOT READY');c3.metric('QR / Audit','HTTPS' if _https_up() else ('HTTP' if mobile_online() else 'NOT READY'));c4.metric('Shared Plan','LOADED' if fp('Plan-2026-LATEST.xlsx') else 'MISSING')
    _home_missing=[_lab for _lab,_tgt,_k in HOME_SOURCE_FILES if not fp(_tgt)]
    if lang=='ไทย':
        st.markdown('อัปโหลดหรือเปลี่ยนไฟล์ด้านล่าง ไฟล์ที่บันทึกแล้วใช้ร่วมกันตามหน้าที่เกี่ยวข้อง')
        if _home_missing:
            st.warning('ยังขาด: '+', '.join(_home_missing)+' · เปิดอัปโหลดไฟล์โรงงานด้านล่าง')
        else:
            st.success('โหลดไฟล์โรงงานแล้ว')
    else:
        st.markdown('Start with Plan-2026. Other sources remain saved and can be added from the relevant analysis page only when needed.')
        if _home_missing:
            st.warning('Missing: '+', '.join(_home_missing)+' · open the Plan-2026 box below.')
        else:
            st.success('Plan-2026 is loaded. Other files are requested only by the related analysis.')
    _wo_n=work_order_count()
    if fp('Plan-2026-LATEST.xlsx') and _wo_n==0:
        st.error('Plan-2026 is on Home, but the phone database has 0 work orders. QR labels printed from the plan will scan as “work order does not exist” until you tap **Load Plan-2026 into the phone database** below.')
    elif _wo_n:
        st.caption(f'Phone / QR database: {_wo_n:,} work orders in `{DB}` (same file the shop-floor app reads).')
    with st.expander('📚 REFERENCE FILE LOCATIONS / IMPORT TIMES',expanded=False):
        _manifest=ROOT/'knowledge'/'SOURCE_MANIFEST_V16_15.csv'
        if _manifest.exists():
            _mdata=pd.read_csv(_manifest,keep_default_na=False)
            st.dataframe(_mdata,use_container_width=True,hide_index=True,height=360)
            st.caption('Product register and training files stay in Knowledge / F1. Do not upload them on Home or Sources.')
        else:st.info('Reference manifest is not present yet. See Code & Part Knowledge → Snapshot file list and provenance.')
    st.caption(f"Scanned-photo folder: {SHARED_ROOT/'PHOTOS'/'QR_SCANS'} · Audit-photo folder: {SHARED_ROOT/'PHOTOS'/'MOBILE_AUDITS'} · Work-order QR exports: {REPORTS/'QR_TEMP'}")
    with st.expander('📱 Mobile connection / เชื่อมต่อมือถือ', expanded=False):
        _pub,_phone_primary,_phone_http,_phone_https,_https_up,_http_up=phone_app_urls()
        _mobile_url=_phone_primary+'/scan' if not _phone_primary.endswith('/scan') else _phone_primary
        _hq1,_hq2=st.columns([1,2])
        with _hq1:
            try:
                import qrcode,io
                _bio=io.BytesIO();qrcode.make(_mobile_url).save(_bio,format='PNG')
                st.image(_bio.getvalue(),caption='Scan with phone camera to open the shop-floor app',width=230)
            except Exception as _e:st.warning(f'Connection QR unavailable: {_e}')
        with _hq2:
            st.code(_mobile_url)
            st.write('HTTP :8000', 'ONLINE' if _http_up else 'NOT READY', ' · HTTPS :8443', 'ONLINE' if _https_up else 'OPTIONAL / NOT READY')
            if not _http_up:
                st.info('The phone service starts automatically in the background. If HTTP :8000 is still NOT READY after 15 seconds, click Start phone app and check the mobile log under the program folder.')
            st.caption('Open HTTP first — that is the shop-floor app and does not need a certificate. Phones must use the factory LAN address (never 127.0.0.1 — that is the phone itself). HTTPS is only for the live camera: install '+_pub['http']+'/tls/ca.crt once, or ask IT to replace CENTRAL_DATA/TLS with the company certificate. Work-order labels stay SLWO:<WO> and do not contain an IP.')
            if not mobile_online():
                if st.button('Start phone app on this PC / เริ่มแอปมือถือบนเครื่องนี้', key='home_start_mobile', use_container_width=True):
                    from suite.service_launcher import ensure as _ens
                    _ens('mobile', wait_seconds=8)
                    try: health.clear()
                    except Exception: pass
                    st.rerun()
            st.markdown(f"<a href='{_hub_page_href('floor')}' target='_self' style='display:inline-block;padding:12px 18px;background:#e76613;color:white;border-radius:10px;text-decoration:none;font-weight:900;margin-right:8px'>Scan WO · OPEN / CLOSED</a> <a href='{_phone_http}' target='_blank' style='display:inline-block;padding:12px 18px;background:#e76613;color:white;border-radius:10px;text-decoration:none;font-weight:900;margin-right:8px'>Open phone app (HTTP)</a> <a href='{_phone_https}' target='_blank' style='display:inline-block;padding:12px 18px;background:#0057b8;color:white;border-radius:10px;text-decoration:none;font-weight:900;margin-right:8px'>HTTPS (camera)</a> <a href='{_hub_page_href('audits')}' target='_self' style='display:inline-block;padding:12px 18px;background:#0057b8;color:white;border-radius:10px;text-decoration:none;font-weight:900;margin-right:8px'>Open audit database</a> <a href='{_hub_page_href('audit')}' target='_self' style='display:inline-block;padding:12px 18px;background:#0057b8;color:white;border-radius:10px;text-decoration:none;font-weight:900'>Scan / update status</a>",unsafe_allow_html=True)
            _floor_url=f"http://{lan_ip()}:8510/?page=floor"
            st.caption('Same Planning Center on the phone: '+_floor_url+' (factory LAN, never 127.0.0.1).')
            _floor_q1,_floor_q2=st.columns([1,3])
            with _floor_q1:
                try:
                    _floor_buf=io.BytesIO();qrcode.make(_floor_url).save(_floor_buf,format='PNG')
                    st.image(_floor_buf.getvalue(),caption='Section status — phone or computer',width=145)
                except Exception as _floor_qe:st.caption(f'Shop-floor QR unavailable: {_floor_qe}')
            with _floor_q2:
                st.code(_floor_url)
                st.caption('Section entries from phone/computer save on this host PC in its configured CENTRAL_DATA on D:. Client devices do not need direct D: or company-server access; keep this PC running on factory Wi-Fi.')

    if plan:
        with st.expander('🧭 Section plan check / ตรวจแผนแต่ละฝ่าย', expanded=False):
            st.caption('Compares Preparation → Mixing → Forming → Firing → Grinding → Packing on the same WO. If a later section is done while an earlier one is still open, or section qty ≠ master qty, both figures are listed. Nothing is chosen as the winner.')
            try:
                from suite.plan_consistency import check_plan as _chk_plan
                _ck=_chk_plan(str(plan), cache_dir=str(SHARED_ROOT/'CACHE'))
                st.metric('WO rows checked', _ck['wos'])
                if _ck['issue_count']:
                    st.error(f"{_ck['issue_count']} contradiction(s) — { _ck['by_kind'] }")
                    st.dataframe(pd.DataFrame(_ck['issues'][:200]), use_container_width=True, hide_index=True, height=240)
                else:
                    st.success('No section-order or qty contradictions in the Plan-2026 section columns.')
            except Exception as _ce:
                st.warning(f'Section check unavailable: {_ce}')

    with st.expander('📥 Start here: Plan-2026 / เริ่มที่ไฟล์ Plan-2026', expanded=bool(_home_missing)):
        st.caption('Upload or replace Plan-2026 here. Other sources are under All software inputs below or on the relevant page. Imported filename, checksum, user and time are recorded automatically. Existing printed QR labels keep the same work-order identity.')
        _plan_upload=st.file_uploader('Upload / replace Plan-2026',type=['xlsx','xlsm'],key='primary_home_plan')
        if _plan_upload is not None:
            st.session_state['upload_context']='Home Page — Plan-2026'
            _saved_path=archive_and_save(_plan_upload,'Plan-2026-LATEST.xlsx')
            if _saved_path is not None:
                _ok,_msg=sync_mobile()
                if _ok:st.success('Plan-2026 saved. The shared planning and shop-floor sources were refreshed. '+_msg)
                else:st.warning('Plan-2026 was saved for desktop planning; phone WO synchronization needs attention. '+_msg)
        if st.button('Load active Plan-2026 to the phone database',key='home_sync_mobile',use_container_width=False):
            _ok,_msg=sync_mobile()
            (st.success if _ok else st.error)(_msg or ('Phone database refreshed.' if _ok else 'Phone database was not updated.'))

    with st.expander('📤 All software inputs / ไฟล์ข้อมูลทั้งหมด',expanded=st.query_params.get('open_source_upload')=='1'):
        st.markdown("<span id='all-source-upload'></span>",unsafe_allow_html=True)
        st.caption('Choose a source type, then upload its new revision. This list includes Plan, Firing, Stock, Capacity, Forecast, both Production KPI files, Planning KPI, monthly Open/Close, Daily Status, Recovery snapshot, Sales registered-product master, Production packaging standard and other sources. Saved sources and prior revisions remain available when you switch pages.')
        _home_slot_ids=[sid for sid,_slot in SM_SLOTS.items() if not _slot.knowledge_only and sid!='PLAN_2026']
        _home_slot_label={sid:SM_SLOTS[sid].label for sid in _home_slot_ids}
        _home_slot=st.selectbox('Source type / ประเภทไฟล์',_home_slot_ids,format_func=lambda sid:_home_slot_label[sid],key='home_all_source_slot')
        _home_allowed=['xlsx','xlsm']
        if _home_slot=='SEPT_OPEN_CLOSED':_home_allowed=['xls','xlsx','xlsm']
        _home_file=st.file_uploader('Upload or replace selected source / อัปโหลดหรือแทนที่ไฟล์',type=_home_allowed,key='home_any_source_upload_'+_home_slot)
        if _home_file is not None:
            st.session_state['upload_context']='Home Page — All source types'
            _home_result=_import_slot(_home_file,_home_slot)
            if _home_result is not None and getattr(_home_result,'ok',False):st.rerun()
        with st.expander('Daily Status — upload multiple section workbooks / อัปโหลดหลายแผนกพร้อมกัน',expanded=False):
            from suite.daily_status_files import section_from_filename as _home_section_from_filename
            _home_sections=('Preparation','Mixing','Forming','Firing','Grinding','Packing')
            _home_batch=st.file_uploader('Select all revised Daily Status workbooks',type=['xlsx','xlsm'],accept_multiple_files=True,key='home_daily_status_batch')
            _home_changed=False
            for _hu in (_home_batch or []):
                _hs=_home_section_from_filename(_hu.name)
                if not _hs:_hs=st.selectbox(f'Section for {_hu.name}',_home_sections,key='home_daily_section_'+hashlib.sha1(_hu.name.encode()).hexdigest()[:10])
                _hslot='DAILY_STATUS_'+_hs.upper()
                if _upload_seen(_hu,'slot:'+_hslot):continue
                try:
                    _home_ds_result=SM.import_bytes(_hslot,_hu.name,_hu.getvalue(),st.session_state.get('sl_user','unknown'),section=_hs,note='Home batch upload — Daily Status')
                    if _home_ds_result.ok:
                        st.success(f'{_hs}: saved revision {_home_ds_result.revision_no or "unchanged"}.')
                        _home_changed=True
                    else:st.error(f'{_hs}: {_home_ds_result.message}')
                    _mark_upload_seen(_hu,'slot:'+_hslot)
                except Exception as _hds_err:st.error(f'{_hs} upload failed; previous source remains active. {_hds_err}')
            if _home_changed:st.rerun()
        with st.expander('Production WIP — upload multiple section snapshots / อัปโหลดไฟล์ WIP ฝ่ายผลิต',expanded=False):
            _home_wip_uploads=st.file_uploader('Choose Production WIP section files',type=['xlsx','xlsm'],accept_multiple_files=True,key='home_production_wip_uploads')
            for _wu in (_home_wip_uploads or []):
                _wchoices=['Unassigned']+wip_sources.SECTIONS;_wguess=wip_sources.infer_section(_wu.name)
                _wsec=_wguess or st.selectbox(f'Section for {_wu.name}',_wchoices,key='home_wip_sec_'+hashlib.sha1(_wu.name.encode()).hexdigest()[:10])
                _wdest_dir=SHARED_ROOT/'PRODUCTION_WIP';_wdest_dir.mkdir(parents=True,exist_ok=True)
                _wcanonical=wip_sources.filename_for_section(_wsec,Path(_wu.name).suffix)
                _wdest=_wdest_dir/(_wcanonical or Path(_wu.name).name)
                _wscope='wip:'+_wu.name+':'+str(_wsec)
                if _upload_seen(_wu,_wscope):continue
                try:
                    _wbytes=_wu.getvalue();_wsha=hashlib.sha256(_wbytes).hexdigest();_wreg=_load_registry();_wkey='PRODUCTION_WIP/'+_wdest.name;_wold=_wreg.get(_wkey,{})
                    _warchive=None
                    if _wdest.exists() and _wold.get('sha256')!=_wsha:
                        _warchive=SOURCE_ARCHIVE/f"{bkk_now():%Y%m%d_%H%M%S}_WIP_{_wdest.name}";_warchive.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(_wdest,_warchive)
                    _wdest.write_bytes(_wbytes)
                    register_source(_wkey,_wdest,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),_wu.name,f'Home upload · Production WIP · {_wsec}')
                    _wreg=_load_registry();_we=_wreg.setdefault(_wkey,{})
                    _we.update(production_section='' if _wsec=='Unassigned' else _wsec,wip_active=True,sha256=_wsha);_we.setdefault('archive_copy_paths',[])
                    if _warchive:_we['archive_copy_path']=str(_warchive.resolve());_we['archive_copy_paths'].append(str(_warchive.resolve()))
                    _save_registry(_wreg);_mark_upload_seen(_wu,_wscope);st.success(f'{_wu.name} saved to Production WIP / {_wsec}.')
                except Exception as _werr:st.error(f'Production WIP upload failed; previous source remains active. {_werr}')

    st.markdown('### 🧾 Uploaded Files & Traceability / ตำแหน่งและประวัติไฟล์')
    st.caption('Each row separates the original upload name from the new stored name and exact server folder. The browser does not provide the source PC/mobile folder path; that is explicitly marked instead of guessed.')
    _trace_rows=[]
    def _trace_row(path,source,original,imported_at='',uploaded_by='',sha='',archive='',excel_modified='',status='Active',period='',source_path='',revision_note=''):
        _p=Path(path)
        if not _p.is_file():return
        _st=_p.stat(); _doc=excel_modified
        if not _doc:
            try:
                with zipfile.ZipFile(_p) as _z:
                    _core=_z.read('docProps/core.xml').decode('utf-8','ignore');_mm=re.search(r'<dcterms:modified[^>]*>([^<]+)',_core)
                    if _mm:_doc=_mm.group(1)
            except Exception:pass
        _trace_rows.append({'Type':source,'Report period':period or '', 'Original import filename':original or 'Not recorded','Original source folder':source_path or 'Not recorded — browser does not expose it','User-provided revision':revision_note or 'Not recorded', 'Stored filename':_p.name,
          'Stored location':str(_p.resolve()),'Imported at':imported_at or 'Not recorded',
          'Workbook modified at':_doc or 'Not recorded in workbook','Uploaded by':uploaded_by or 'Not recorded',
          'Size (MB)':round(_st.st_size/1048576,2),'SHA-256':sha or 'Not recorded','Archive copy':archive or '', 'Status':status})
    _mainreg=_load_registry()
    with st.expander('Record original source properties for an existing upload'):
        _targets=[k for k,v in _mainreg.items() if isinstance(v,dict) and v.get('active_path')]
        if _targets:
            _target=st.selectbox('Uploaded source',_targets,format_func=lambda k:_mainreg[k].get('original_name',k))
            _entry=_mainreg[_target]
            _original=st.text_input('Original filename',value=_entry.get('original_name',''),key='trace_original_filename_'+_target)
            _folder=st.text_input('Original source folder',value=_entry.get('client_source_path','') if _entry.get('source_path_evidence')=='User provided' else '',key='trace_original_folder_'+_target)
            _revision=st.text_input('Original revision / modified date and time (user provided)',value=_entry.get('source_revision_note',''),key='trace_original_revision_'+_target)
            if hub_can_edit() and st.button('Save original source properties'):
                _entry.setdefault('provenance_history',[]).append({'changed_at':datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds'),'changed_by':st.session_state.get('sl_user',''),'previous_original_name':_entry.get('original_name'),'previous_source_folder':_entry.get('client_source_path'),'previous_revision_note':_entry.get('source_revision_note')})
                _entry.update(original_name=_original.strip() or _entry.get('original_name'),client_source_path=_folder.strip() or 'Not recorded',source_path_evidence='User provided' if _folder.strip() else 'Unavailable',source_revision_note=_revision.strip() or 'Not recorded')
                _save_registry(_mainreg);st.success('Original source properties saved with change history.')

    for _key,_m in _mainreg.items():
        _trace_row(_m.get('active_path',''),_m.get('uploaded_through','Central source'),_m.get('original_name',_key),_m.get('registered_at',''),_m.get('updated_by',''),_m.get('sha256',''),_m.get('archive_copy_path',''),_m.get('excel_document_modified_at',''),source_path=_m.get('client_source_path',''),revision_note=_m.get('source_revision_note',''))
    for _kind,_folder in [('Daily Status section',SHARED_ROOT/'DAILY_STATUS'),('KPI workbook',SHARED_ROOT/'KPI'),('Production WIP section',SHARED_ROOT/'PRODUCTION_WIP')]:
        _mf=_folder/'source_registry.json'
        try:_items=json.loads(_mf.read_text(encoding='utf-8')).get('records',[]) if _mf.exists() else []
        except Exception:_items=[]
        _activepaths=set()
        for _m in _items:
            _activepaths.add(_m.get('stored_path',''))
            _trace_path=_m.get('stored_path','') if _m.get('active') else (_m.get('archived_path') or _m.get('stored_path',''))
            _trace_row(_trace_path,_m.get('kind',_kind),_m.get('original_filename',''),_m.get('uploaded_at',''),_m.get('uploaded_by',''),_m.get('sha256',''),_m.get('archived_path',''),_m.get('excel_document_modified_at',''),'Active' if _m.get('active') else 'Archived',_m.get('report_period',''))
        if _folder.exists():
            for _p in list(_folder.glob('*.xlsx'))+list(_folder.glob('*.xlsm')):
                if str(_p.resolve()) not in _activepaths:_trace_row(_p,_kind,_p.name,status='Legacy / metadata unavailable')
    for _base,_kind in [(DATA,'Central planning source')]:
        if _base.exists():
            for _p in list(_base.glob('*.xlsx'))+list(_base.glob('*.xlsm')):
                if str(_p.resolve()) not in {x.get('active_path') for x in _mainreg.values()}:
                    _trace_row(_p,_kind,'',status='Existing / import metadata unavailable')
    _photos=Path(os.environ.get('SL_PHOTO_ROOT',str(SHARED_ROOT/'PHOTOS')))/'MOBILE_AUDITS'
    if _photos.exists():
        try:
            _trace_rows.append({'Type':'Mobile audit photos','Original import filename':'Captured from mobile camera','Stored filename':'<Work Order>_<location>_<datetime>.jpg',
              'Stored location':str(_photos.resolve()),'Imported at':'Per-photo timestamp in database and filename','Workbook modified at':'—','Uploaded by':'Operator audit record',
              'Size (MB)':'—','SHA-256':'—','Archive copy':'—','Status':'Per-audit photo evidence folder'})
        except Exception:pass
    _manual_status_db=DATA/'daily_status_entries.sqlite3'
    _trace_rows.append({'Type':'Manual section status ledger','Original import filename':'Operator scan / typed entry','Stored filename':_manual_status_db.name,
      'Stored location':str(_manual_status_db.resolve()),'Imported at':'Per-event Thailand local timestamp — Phan Thong, Chonburi','Workbook modified at':'—','Uploaded by':'Per-event authenticated user',
      'Size (MB)':round(_manual_status_db.stat().st_size/1048576,2) if _manual_status_db.exists() else 0,'SHA-256':'—','Archive copy':'Append-only SQLite events','Status':'Active' if _manual_status_db.exists() else 'Created on first manual entry'})
    if _trace_rows:
        _trdf=pd.DataFrame(_trace_rows).drop_duplicates(subset=['Type','Stored location','SHA-256'],keep='last')
        with st.expander('📍 Source files & import traceability',expanded=False):
            st.dataframe(_trdf,use_container_width=True,hide_index=True,height=min(650,120+len(_trdf)*38))
            if not _trdf.empty:
                _trace_pick=st.selectbox('Show complete file path and provenance',range(len(_trdf)),format_func=lambda i:f"{_trdf.iloc[i]['Original import filename']} → {_trdf.iloc[i]['Stored filename']} [{_trdf.iloc[i]['Status']}]",key='trace_exact_file')
                _tr=_trdf.iloc[_trace_pick]
                st.code(f"Original uploaded filename: {_tr['Original import filename']}\nOriginal device folder: Not exposed by browser upload\nStored filename: {_tr['Stored filename']}\nStored server location: {_tr['Stored location']}\nImport date/time: {_tr['Imported at']}\nUploaded through: {_tr['Type']}\nWorkbook modified: {_tr['Workbook modified at']}\nSHA-256: {_tr['SHA-256']}\nArchive copy: {_tr['Archive copy']}\nStatus: {_tr['Status']}",language=None)
        st.download_button('⬇️ Download source traceability register (CSV)',_trdf.to_csv(index=False).encode('utf-8-sig'),file_name='SL_Source_Traceability_Register.csv',mime='text/csv',key='home_source_trace_csv')
    else:st.info('No imported source files are recorded yet. Start with Plan-2026 on Home; other source uploads appear in the related analysis page.')

    st.markdown('### 📊 Today summary')
    if not st.session_state.get('show_today_summary') and st.button('Open dashboard analysis (loads Plan-2026 once)', key='open_today'):
        st.session_state['show_today_summary']=True
        st.rerun()
    if st.session_state.get('show_today_summary'):
        _ensure_plan_model()
    if not st.session_state.get('show_today_summary'):
        st.caption('Numbers stay closed until you need them, so Home stays fast.')
    else:
        try:
            _plan_n=int(master['Work Order'].nunique()) if master is not None and 'Work Order' in master.columns else 0
            _open_n=int((~master['Authoritative Closed'].fillna(False)).sum()) if master is not None and 'Authoritative Closed' in master.columns else 0
            _closed_n=int(master['Authoritative Closed'].fillna(False).sum()) if master is not None and 'Authoritative Closed' in master.columns else 0
            _con=sqlite3.connect(DB);_aud_n=int(pd.read_sql_query("SELECT COUNT(DISTINCT wo_id) n FROM mobile_audits",_con).iloc[0,0]);_con.close()
            _s1,_s2,_s3,_s4=st.columns(4);_s1.metric('Plan WOs',_plan_n);_s2.metric('Open',_open_n);_s3.metric('Closed',_closed_n);_s4.metric('Audited',_aud_n)
            if op is not None and not op.empty:
                _sg=op.groupby('Section',dropna=False).agg(WOs=('Work Order','nunique'),pcs=('pcs','sum')).reset_index()
                st.bar_chart(_sg.set_index('Section')['pcs'],height=230)
            # The management WIP headline must include the Production section
            # snapshots, which are the physical WIP source, not only Plan-2026.
            try:
                _pwc=ROOT/'apps'/'daily'
                if str(_pwc) not in sys.path:sys.path.insert(0,str(_pwc))
                from production_wip_control import production_snapshot as _home_prod_wip
                _hwip,_hwip_issues=_home_prod_wip(_pwc)
                st.markdown('#### Production WIP by section and category / WIP ฝ่ายผลิต')
                if not _hwip.empty:
                    _hwip_sum=_hwip.groupby(['Section','Category'],as_index=False)['Open t'].sum(min_count=1)
                    _hwip_fig=px.bar(_hwip_sum,x='Section',y='Open t',color='Category',barmode='stack',category_orders={'Category':['P','R','S','T','M','PB']},title='Production-reported WIP (gross tonnes)')
                    _hwip_tot=_hwip_sum.groupby('Section',as_index=False)['Open t'].sum(min_count=1)
                    for _,_tw in _hwip_tot.iterrows():_hwip_fig.add_annotation(x=_tw['Section'],y=float(_tw['Open t']),text=f"{float(_tw['Open t']):,.2f} t",showarrow=False,yshift=10,font=dict(size=12,color='#17324D'))
                    _hwip_fig.update_layout(height=390,xaxis_tickangle=-20,yaxis_title='Gross tonnes')
                    st.plotly_chart(_hwip_fig,use_container_width=True,config={'displayModeBar':False})
                    _hwip_sources=', '.join(sorted(_hwip['Original filename'].dropna().astype(str).unique())) if 'Original filename' in _hwip else 'Source filename unavailable'
                    _hwip_times=', '.join(sorted(_hwip['Uploaded at'].dropna().astype(str).unique())) if 'Uploaded at' in _hwip else 'Import time unavailable'
                    st.caption(f'Physical WIP source: {_hwip_sources} · imported: {_hwip_times}. Open-WO counts are section records; process totals may repeat the same WO.')
                else:
                    st.info('Production WIP is not available from the active section workbooks. Check Files → Production WIP source assignment.')
                if _hwip_issues:
                    with st.expander('Production WIP source issues'):
                        st.write('\n'.join(map(str,_hwip_issues)))
            except Exception as _hwip_err:
                st.warning(f'Production WIP could not be loaded: {_hwip_err}')
            if isinstance(master,pd.DataFrame) and not master.empty:
                _due_graph=overdue_month_category(master,bkk_today())
                st.markdown('#### Past-due backorders / งานค้างส่งเกินกำหนด')
                st.caption(f"Only open positive balances due before {bkk_today():%d %b %Y} are shown. Date basis: revised delivery date (Plan-2026 E), falling back to initial date (C); open pcs = QTY − Packing Actual; whole-WO close = EU or FC. Future open orders stay outside backorders.")
                if not _due_graph.empty:
                    _due_months=sorted(_due_graph['Due Month'].dropna().astype(str).unique(),key=lambda x:pd.Period(x,freq='M'))
                    _due_fig=px.bar(_due_graph,x='Due Month',y='Qty pcs',color='Product Category',barmode='stack',category_orders={'Due Month':_due_months},hover_data=['WOs'],title='Overdue open quantity by current due month · future orders excluded')
                    _due_fig.update_xaxes(type='category',categoryorder='array',categoryarray=_due_months,tickangle=-45)
                    st.plotly_chart(_due_fig,use_container_width=True,config={'displayModeBar':False})
                else:
                    st.success('No past-due open work orders today.')
                # RC29.33: one shared authoritative WO-level calculation.
                _dashboard_summary=overdue_backorder_totals(master,bkk_today())
                _past_due_n=_dashboard_summary['WOs'];_past_due_qty=_dashboard_summary['Qty pcs'];_past_due_ton=_dashboard_summary['Weight ton']
                st.metric('Overdue OPEN work orders / WO เปิดที่เกินกำหนด',f'{_past_due_n:,} WOs · {_past_due_qty:,.0f} pcs · {_past_due_ton:,.2f} ton')
                st.caption(f'As of {bkk_today():%d-%m-%Y} · All overdue due months')
                _chart_qty=float(pd.to_numeric(_due_graph['Qty pcs'],errors='coerce').fillna(0).sum()) if not _due_graph.empty else 0
                if abs(_chart_qty-_past_due_qty)>0.001:
                    st.error(f'Backorder reconciliation warning: chart {_chart_qty:,.0f} pcs vs detailed {_past_due_qty:,.0f} pcs.')

            if isinstance(master,pd.DataFrame) and not master.empty and 'Due Date' in master.columns:
                _due_now=master.copy()
                _due_now['_due_day']=pd.to_datetime(_due_now['Due Date'],errors='coerce',dayfirst=True).dt.date
                _today_bkk=bkk_today();_tomorrow_bkk=_today_bkk+pd.Timedelta(days=1)
                _due_now=_due_now[_due_now['_due_day'].isin([_today_bkk,_tomorrow_bkk])].copy()
                if 'Authoritative Closed' in _due_now:_due_now=_due_now[~_due_now['Authoritative Closed'].fillna(False)]
                if not _due_now.empty:
                    _due_now['Delivery Timing']=_due_now['_due_day'].map({_today_bkk:'DUE TODAY',_tomorrow_bkk:'DUE TOMORROW'})
                    _due_now['Due Date']=_due_now['Due Date'].map(format_due_date)
                    _due_cols=[c for c in ['Delivery Timing','Work Order','Customer Thai','Product Code','Due Date','pcs'] if c in _due_now]
                    st.markdown('### 📅 Due today / tomorrow — delivery date and day')
                    st.dataframe(_due_now[_due_cols].rename(columns={'Customer Thai':'Customer as in Plan-2026','pcs':'Quantity (pcs)'}),use_container_width=True,hide_index=True)
                else:
                    st.caption(f'No open work orders due today ({format_due_date(_today_bkk)}) or tomorrow ({format_due_date(_tomorrow_bkk)}).')
            st.markdown('### 🎯 Customer delivery on-time / ส่งมอบตรงกำหนดลูกค้า')
            _due_fields={'Work Order':'ProductionCode','Initial Due':'กำหนดเข้าคลัง','Revised Due':'กำหนดส่งใหม่','Actual Warehouse Date':'วันที่เข้าคลัง','Customer':'Customername','Order Qty':'QTY'}
            if isinstance(raw,pd.DataFrame) and all(v in raw.columns for v in _due_fields.values()):
                _ontime=raw[list(_due_fields.values())].copy().rename(columns={v:k for k,v in _due_fields.items()})
                _ontime['Plan-2026 Source Row']=_ontime.index+4
                _ontime['Work Order']=_ontime['Work Order'].astype(str).str.strip()
                _ontime['_WO_KEY']=_ontime['Work Order'].str.upper().str.replace(r'[^A-Z0-9]','',regex=True)
                _ontime=_ontime.drop_duplicates('_WO_KEY',keep='last')
                for _c in ['Initial Due','Revised Due','Actual Warehouse Date']:_ontime[_c]=pd.to_datetime(_ontime[_c],errors='coerce',dayfirst=True)
                _ontime['Order Qty']=pd.to_numeric(_ontime['Order Qty'],errors='coerce')
                _delivered=_ontime[_ontime['Actual Warehouse Date'].notna()].copy()
                _init=_delivered[_delivered['Initial Due'].notna()];_rev=_delivered[_delivered['Revised Due'].notna()]
                _delivered['Initial Scored']=_delivered['Initial Due'].notna()
                _delivered['Revised Scored']=_delivered['Revised Due'].notna()
                _delivered['Initial On Time']=_delivered['Initial Scored']&_delivered['Actual Warehouse Date'].dt.normalize().le(_delivered['Initial Due'].dt.normalize())
                _delivered['Revised On Time']=_delivered['Revised Scored']&_delivered['Actual Warehouse Date'].dt.normalize().le(_delivered['Revised Due'].dt.normalize())
                _delivered['Initial On-time Pcs']=np.where(_delivered['Initial On Time'],_delivered['Order Qty'],0)
                _delivered['Revised On-time Pcs']=np.where(_delivered['Revised On Time'],_delivered['Order Qty'],0)
                _op1,_op2,_op3,_op4=st.columns(4)
                _op1.metric('Delivered WOs scored',f'{len(_delivered):,}')
                _op2.metric('On time vs initial date',f"{(100*_init['Actual Warehouse Date'].le(_init['Initial Due']).mean() if len(_init) else 0):.1f}%",f"{_init['Actual Warehouse Date'].le(_init['Initial Due']).sum():,}/{len(_init):,} scored")
                _op3.metric('On time vs revised date',f"{(100*_rev['Actual Warehouse Date'].le(_rev['Revised Due']).mean() if len(_rev) else 0):.1f}%",f"{_rev['Actual Warehouse Date'].le(_rev['Revised Due']).sum():,}/{len(_rev):,} scored")
                _op4.metric('On-time parts vs revised',f"{_delivered['Revised On-time Pcs'].sum():,.0f} pcs",f"of {_rev['Order Qty'].sum():,.0f} revised-date-scored pcs")
                st.caption('Calculated from Plan-2026 C (initial due), E (revised due), and EV / “วันที่เข้าคลัง” (actual warehouse date). Rows with missing or text dates are excluded from the relevant denominator.')
                if not _delivered.empty:
                    _customer_chart=_delivered.groupby('Customer',dropna=False).agg(Delivered=('Work Order','nunique'),Initial_Scored=('Initial Scored','sum'),Revised_Scored=('Revised Scored','sum'),Initial_On_Time=('Initial On Time','sum'),Revised_On_Time=('Revised On Time','sum')).reset_index()
                    _customer_chart['On time initial %']=100*_customer_chart['Initial_On_Time']/ _customer_chart['Initial_Scored'].replace(0,np.nan)
                    _customer_chart['On time revised %']=100*_customer_chart['Revised_On_Time']/ _customer_chart['Revised_Scored'].replace(0,np.nan)
                    _customer_chart=_customer_chart.sort_values('Delivered',ascending=False).head(12)
                    _cust_fig=px.bar(_customer_chart,x='Customer',y=['On time initial %','On time revised %'],barmode='group',title='Customer on-time delivery — actual warehouse date vs both promise dates')
                    _cust_fig.update_layout(font=dict(family='TH Sarabun New, Sarabun, Tahoma, sans-serif' if lang=='ไทย' else 'Segoe UI, Calibri, sans-serif'))
                    st.plotly_chart(_cust_fig,use_container_width=True)
                with st.expander('Traceable WO delivery detail',expanded=False):
                    _ontime['Initial Result']=np.where(_ontime['Actual Warehouse Date'].notna()&_ontime['Initial Due'].notna(),np.where(_ontime['Actual Warehouse Date'].dt.normalize()<=_ontime['Initial Due'].dt.normalize(),'ON TIME','LATE'),'NOT SCORED')
                    _ontime['Revised Result']=np.where(_ontime['Actual Warehouse Date'].notna()&_ontime['Revised Due'].notna(),np.where(_ontime['Actual Warehouse Date'].dt.normalize()<=_ontime['Revised Due'].dt.normalize(),'ON TIME','LATE'),'NOT SCORED')
                    _delivery_display=_ontime.copy()
                    for _date_col in ['Initial Due','Revised Due','Actual Warehouse Date']:
                        _delivery_display[_date_col]=_delivery_display[_date_col].map(format_due_date)
                    _delivery_display=mask_customer_columns(_delivery_display)
                    st.dataframe(_delivery_display,use_container_width=True,hide_index=True,height=390)
                    st.download_button('⬇ Download delivery trace CSV',_delivery_display.to_csv(index=False).encode('utf-8-sig'),'Plan2026_Customer_OnTime_Trace.csv','text/csv',key='home_delivery_trace')
        except Exception as _e:st.caption(f'Today summary diagnostic: {_e}')

if _page in ('daily','daily_wip','daily_closed','daily_status','daily_kpi','daily_recovery','capacity_actual'):
    st.markdown("<div style='padding:12px 18px;border-left:6px solid #e76613;background:#fff6ed;border-radius:10px'><h2 style='margin:0;color:#12395b'>📅 Daily Planning</h2><span>Plan · Delivery · Capacity · Recovery</span></div>",unsafe_allow_html=True)
    st.subheader('📅 Daily / Section Planner')
    _daily_focus={'daily_wip':'wip','daily_closed':'closed','daily_status':'status','daily_kpi':'kpi','daily_recovery':'recovery','capacity_actual':'capacity_actual'}.get(_page,'')
    if _page=='daily' and st.query_params.get('focus') in ('download','material','capacity','capacity_actual','mixing'):_daily_focus=st.query_params.get('focus')
    if _page=='daily_closed':
        st.markdown('### 📋 Daily Open / Closed — from files already on Home')
        _jr=fp('Job-Register-LATEST.xlsx')
        _jrmeta=_load_registry().get('Job-Register-LATEST.xlsx',{})
        st.caption("The current month Open/Close register is revised every day. Upload today's copy in the Home upload box; Daily does not ask for it again. JOB and Item stay un-netted.")
        if _jr:
            st.success(f"Current register: `{_jrmeta.get('original_name','Job-Register-LATEST.xlsx')}` stored as `{_jr}`")
        _daily_dir=str(ROOT/'apps'/'daily')
        if _daily_dir not in sys.path:
            sys.path.insert(0, _daily_dir)
        import daily_job_control as _jobs50
        _jobs50.render(st, _daily_dir)
        from suite.open_closed_view import render as _render_oc
        _render_oc(st, plan_path=str(plan) if plan else None, job_path=str(_jr or ''),
                   cache_dir=str(SHARED_ROOT/'CACHE'), key='hub_oc')
        st.markdown('### 📝 Saved manual WO-section status events')
        st.caption('This event log shows the OPEN/CLOSED action saved on the shop-floor page. A section event is traceable but does not change the workbook actual quantity or whole-order closure rule.')
        try:
            from suite.floor_open_close import load_entries as _load_section_events
            _manual_events=_load_section_events(DATA)
            if _manual_events.empty:
                st.info('No manual WO-section status events have been saved yet.')
            else:
                _manual_events['Time']=pd.to_datetime(_manual_events['Time'],errors='coerce')
                _latest_events=_manual_events.sort_values('Time').drop_duplicates(['Work Order','Section'],keep='last').sort_values('Time',ascending=False)
                st.dataframe(_latest_events,use_container_width=True,hide_index=True,height=340)
                with st.expander('All saved section-status event history / ประวัติเหตุการณ์ทั้งหมด'):
                    st.dataframe(_manual_events.sort_values('Time',ascending=False),use_container_width=True,hide_index=True,height=360)
        except Exception as _event_error:
            st.error(f'Manual WO-section event log could not be read: {_event_error}')
        st.info('This page reports loaded workbooks and saved section events. It does not record a new section status. To enter OPEN/CLOSED for one WO section, use Production → Update WO Section Status.')
        if st.button('Open WO Section Status Entry / เปิดบันทึกสถานะรายแผนก', key='open_floor_from_daily_report', type='primary', use_container_width=True):
            st.query_params['page']='floor'; st.rerun()
        with st.expander('Calculated Daily plan (starts the Daily program only if you open this)', expanded=False):
            st.caption('Date-by-date Daily Status open/closed is in the planner when those section workbooks are already stored. Boxes there only replace a newer file.')
            show_planner('daily', 'focus=closed')
    elif plan:
        st.success(f'Plan-2026 already loaded on Home: `{plan}`. Daily / Firing / reports use this file. Do not upload it again.')
        show_planner('daily', ('focus='+_daily_focus) if _daily_focus else '')
    else:
        st.warning('Plan-2026 is not on Home yet. Upload it once under Home → Upload / replace source files.')
        show_planner('daily', ('focus='+_daily_focus) if _daily_focus else '')
if _page == 'floor':
    st.markdown('## Shop floor / หน้างาน')
    st.caption('Type a work order, use a USB QR scanner, or take/upload a QR photo. Save OPEN/CLOSED for the selected section. Records are stored locally in CENTRAL_DATA and do not require section workbook uploads.')
    from suite.floor_open_close import render as _floor_page
    _qr_scan_dir=Path(os.environ.get('SL_PHOTO_ROOT',str(SHARED_ROOT/'PHOTOS')))/'QR_SCANS'
    _floor_page(st, plan_path=str(plan) if plan else None, db_file=DB, data_dir=DATA, raw_df=raw,
                can_edit=hub_can_edit(), user=st.session_state.get('sl_user','desktop'),
                show_customer=hub_can_view_customers(), key='hub_floor', qr_scan_dir=_qr_scan_dir)
if _page == 'firing':
    st.markdown("<div style='padding:12px 18px;border-left:6px solid #e76613;background:#fff6ed;border-radius:10px'><h2 style='margin:0;color:#12395b'>🔥 Firing / Kiln Planning</h2></div>",unsafe_allow_html=True)
    st.subheader('🔥 Firing Plan')
    st.session_state['upload_context']='Firing tab'
    st.caption('Previous firing input may be the full workbook or only the issued Operator Print sheet. Upload it in “Update sources for this page”; the saved active copy is reused by Firing and Daily.')
    _fp=fp('Firing-Plan-LATEST.xlsx')
    if _fp: st.caption(f"Active firing file: {_fp.name} • {datetime.fromtimestamp(_fp.stat().st_mtime):%Y-%m-%d %H:%M:%S} • {_fp}")
    with st.expander('🔎 View existing firing loads / kiln pattern (read only)', expanded=True):
        if not _fp:
            st.info('Upload the issued firing workbook or Operator Print in the source panel above. This viewer will not create a firing plan.')
        else:
            try:
                _existing_fire = _cached_existing_firing_view(str(_fp), _fp.stat().st_mtime_ns, _fp.stat().st_size)
                _sched = _existing_fire['schedule'].copy()
                _sched['Load Date'] = pd.to_datetime(_sched['Load Date'], errors='coerce')
                _nloads = len(_sched)
                _c1, _c2, _c3 = st.columns(3)
                _c1.metric('Existing kiln loads', f'{_nloads:,}')
                _c2.metric('Scheduled quantity', f"{pd.to_numeric(_sched['Qty'], errors='coerce').fillna(0).sum():,.0f} pcs")
                _c3.metric('Work orders', f"{int(pd.to_numeric(_sched['WO Count'], errors='coerce').fillna(0).sum()):,}")
                st.caption(f"Source: {_fp.name} · file modified {datetime.fromtimestamp(_fp.stat().st_mtime):%d %b %Y %H:%M} · sheet: {_existing_fire['schedule_sheet']} · read only; no planner run.")
                if not _sched.empty:
                    import plotly.express as _px_existing
                    _by_day = _sched.groupby(['Load Date', 'Kiln'], as_index=False).agg(Loads=('Load ID', 'nunique'), **{'Planned pcs': ('Qty', 'sum')})
                    _metric = st.radio('Graph measure', ['Kiln loads', 'Planned pcs'], horizontal=True, key='existing_fire_pattern_measure')
                    _fig_existing = _px_existing.bar(_by_day, x='Load Date', y='Loads' if _metric == 'Kiln loads' else 'Planned pcs', color='Kiln', barmode='stack',
                        title=f"Existing uploaded firing plan — {_metric}", hover_data=['Kiln', 'Loads', 'Planned pcs'])
                    _fig_existing.update_layout(height=350, xaxis_title='Load date', yaxis_title=_metric, legend_title='Kiln')
                    st.plotly_chart(_fig_existing, use_container_width=True, key='existing_firing_load_graph')
                    _display = _sched.rename(columns={'Load ID':'Load', 'Load Date':'Loading date', 'WO Count':'WO count', 'Qty':'Planned pcs', 'Finish':'Program finish'})
                    st.dataframe(_display, use_container_width=True, hide_index=True, height=280)
                    _load_choices = _sched['Load ID'].astype(str).drop_duplicates().tolist()
                    _selected_existing = st.selectbox('Inspect existing load', _load_choices, key='existing_fire_load_pick')
                    _floor_data = _existing_fire.get('floor', pd.DataFrame())
                    if not _floor_data.empty and {'Load ID', 'Floor'}.issubset(_floor_data.columns):
                        _load_floor = _floor_data[_floor_data['Load ID'].astype(str).eq(str(_selected_existing))].copy()
                        if not _load_floor.empty:
                            _floors = sorted(pd.to_numeric(_load_floor['Floor'], errors='coerce').dropna().astype(int).unique().tolist())
                            _floor_no = st.selectbox('Floor', _floors, key='existing_fire_floor_pick')
                            try:
                                from apps.firing import pattern_on_demand_v16 as _pattern_view
                                _kr = _existing_fire.get('kiln_master', pd.DataFrame())
                                _kiln_name = str(_sched.loc[_sched['Load ID'].astype(str).eq(str(_selected_existing)), 'Kiln'].iloc[0])
                                _km = _kr[_kr.get('Kiln', pd.Series(dtype=str)).astype(str).str.upper().eq(_kiln_name.upper())] if not _kr.empty and 'Kiln' in _kr else pd.DataFrame()
                                _ki = _km.iloc[0].to_dict() if not _km.empty else None
                                _fig_pattern = _pattern_view.draw_three_views(_load_floor, int(_floor_no), str(_selected_existing), kiln_info=_ki)
                                st.pyplot(_fig_pattern, use_container_width=True)
                                import matplotlib.pyplot as _plt_existing
                                _plt_existing.close(_fig_pattern)
                                st.caption('This is the stored physical floor pattern from the uploaded workbook. It is displayed as-is; no new packing, allocation, or release validation was run.')
                            except Exception as _pattern_error:
                                st.warning(f"Stored pattern rows were found, but the drawing could not be rendered: {_pattern_error}")
                                st.dataframe(_load_floor, use_container_width=True, hide_index=True, height=260)
                        else:
                            st.info('This workbook has a Floor Pattern Data sheet, but this selected load has no stored placement rows.')
                    else:
                        st.info('This uploaded file contains the issued schedule only (for example, Operator Print). It has no physical floor coordinates, so this view shows its existing kiln/date/program/load/WO pattern without inventing a physical layout. Upload a full firing output workbook to view saved TOP/FRONT pattern drawings.')
                else:
                    st.warning('The active firing workbook was read, but it contains no dated positive-quantity loads.')
            except Exception as _existing_fire_error:
                st.error(f'Could not read existing firing plan: {_existing_fire_error}')
    st.caption('Full Firing Planner below')
    show_planner('firing')
if _page == 'report':
    if not mobile_online() and not st.session_state.get('_audit_mobile_autostart_attempted'):
        st.session_state['_audit_mobile_autostart_attempted']=True
        with st.spinner('Starting shared part-tracking service on this PC…'):
            try:
                from suite.service_launcher import ensure as _ensure_report_mobile
                _report_start=_ensure_report_mobile('mobile',wait_seconds=8)
                try:health.clear()
                except Exception:pass
                if _report_start.get('ready'):st.rerun()
            except Exception as _report_service_error:
                st.session_state['_audit_mobile_start_error']=str(_report_service_error)
    st.header('📊 Audit Report / รายงานตรวจสอบ')
    st.caption('Live desktop report from the shared audit database used by the shop-floor phone app. Refresh the page to include newly submitted audits.')
    _rep_cols=st.columns([1,1,2])
    _rep_cols[0].link_button('↩ Open Part Audit',_hub_page_href('audit'),use_container_width=True)
    _rep_cols[1].link_button('📥 Source Files',_hub_page_href('src'),use_container_width=True)
    _audit_photo_root=Path(os.environ.get('SL_PHOTO_ROOT',str(SHARED_ROOT/'PHOTOS')))/'MOBILE_AUDITS'
    try:
        ensure_desktop_audit_tables()
        from suite.audit_report import load_all_audits as _report_all, analyze as _report_analyze, enrich_from_plan as _report_enrich
        _report_df=_report_all(DB)
        if not _report_df.empty and master is not None and not master.empty:
            _report_df=_report_enrich(_report_df,master)
        _report_stats=_report_analyze(_report_df)
        _report_summary=_report_stats['summary'].iloc[0]
        _r1,_r2,_r3,_r4=st.columns(4)
        _r1.metric('Audit records',int(len(_report_df)))
        _r2.metric('Work orders',int(_report_df['wo_id'].nunique()) if 'wo_id' in _report_df else 0)
        _r3.metric('Locations',int(_report_summary.get('Locations',0)))
        _r4.metric('Photos linked',int(_report_df.get('photo_filename',pd.Series(dtype=str)).fillna('').astype(str).str.strip().ne('').sum()))
        if _report_df.empty:
            st.info('No audit records are saved yet. Submit an audit from Part Audit; it will appear here after refresh.')
        else:
            _rg1,_rg2=st.columns(2)
            with _rg1:
                if not _report_stats['by_status'].empty:
                    st.plotly_chart(px.bar(_report_stats['by_status'],x='Status',y='WOs',color='Status',title='Latest audit status · work orders'),use_container_width=True)
                if not _report_stats['by_process'].empty:
                    st.plotly_chart(px.bar(_report_stats['by_process'],x='Observed process',y='WOs',color='Observed process',title='Audited work orders by section'),use_container_width=True)
            with _rg2:
                if not _report_stats['by_date'].empty:
                    st.plotly_chart(px.bar(_report_stats['by_date'],x='Date',y='WOs',title='Audits by date'),use_container_width=True)
                if not _report_stats['by_location'].empty:
                    st.dataframe(_report_stats['by_location'],use_container_width=True,hide_index=True,height=260)
            _view_cols=[c for c in ['id','created_at','wo_id','user_name','verified_qty','physical_status','physical_location','observed_process','notes','photo_filename','product_category','product_code'] if c in _report_df]
            st.subheader('Audit records / รายการตรวจสอบ')
            st.dataframe(_report_df[_view_cols],use_container_width=True,hide_index=True,height=380)
            _photo_col=next((c for c in ['photo_filename','Photo filename'] if c in _report_df),None)
            if _photo_col:
                _photo_rows=_report_df[_report_df[_photo_col].fillna('').astype(str).str.strip().ne('')].head(12)
                if not _photo_rows.empty:
                    st.subheader('Photo evidence / รูปหลักฐาน')
                    for _pi in range(0,len(_photo_rows),3):
                        _pcols=st.columns(3)
                        for _pcol,(_, _pr) in zip(_pcols,_photo_rows.iloc[_pi:_pi+3].iterrows()):
                            _pfile=_audit_photo_root/Path(str(_pr[_photo_col])).name
                            if _pfile.is_file():_pcol.image(str(_pfile),caption=f"{_pr.get('wo_id','')} · {_pr.get('observed_process','')} · {_pr.get('physical_location','')} · {_pr.get('created_at','')}",use_container_width=True)
            st.markdown('### Downloadable audit report / ดาวน์โหลดรายงานตรวจสอบ')
            st.caption('The Excel report contains every physical-audit event, section summary, and photo evidence with the original saved filename and path. It reads the same database as mobile audit.')
            _excel_buffer=io.BytesIO()
            with pd.ExcelWriter(_excel_buffer,engine='openpyxl') as _writer:
                _report_df.to_excel(_writer,index=False,sheet_name='All Audit Records')
                for _tab,_tab_df in _report_stats.items():_tab_df.to_excel(_writer,index=False,sheet_name=('Summary '+_tab)[:31])
            _excel_buffer.seek(0)
            # Include evidence thumbnails alongside the audit rows when the saved image is readable.
            try:
                from openpyxl import load_workbook as _report_load_workbook
                _wb_report=_report_load_workbook(_excel_buffer)
                _ws_report=_wb_report['All Audit Records']
                _filename_col=next((i+1 for i,c in enumerate(_report_df.columns) if c==_photo_col),None) if _photo_col else None
                if _filename_col:
                    from openpyxl.utils import get_column_letter as _report_col_letter
                    _ws_report.column_dimensions[_report_col_letter(_filename_col+1)].width=25
                    for _ri,(_, _rrow) in enumerate(_report_df.iterrows(),start=2):
                        _filename=str(_rrow.get(_photo_col,'') or '').strip()
                        _photo_file=_audit_photo_root/Path(_filename).name if _filename else None
                        if not _photo_file or not _photo_file.is_file():continue
                        try:
                            from PIL import Image as _ReportImage
                            _im=_ReportImage.open(_photo_file);_im.thumbnail((180,110));_buf=io.BytesIO();_im.convert('RGB').save(_buf,format='JPEG',quality=68,optimize=True);_buf.seek(0)
                            _xl_img=XLImage(_buf);_xl_img.width=120;_xl_img.height=max(1,int(120*_im.height/max(_im.width,1)))
                            _ws_report.add_image(_xl_img,f'{_report_col_letter(_filename_col+1)}{_ri}');_ws_report.row_dimensions[_ri].height=64
                        except Exception:continue
                _out=io.BytesIO();_wb_report.save(_out);_wb_report.close();_excel_buffer=_out;_excel_buffer.seek(0)
            except Exception as _thumb_error:
                st.caption(f'Excel remains available with photo filenames and locations; thumbnail embedding was skipped: {_thumb_error}')
            st.download_button('⬇ Download Audit Report (Excel + photo evidence)',_excel_buffer.getvalue(),f'SL_AUDIT_REPORT_{bkk_now():%Y%m%d_%H%M%S}.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='desktop_audit_report_download',type='primary',use_container_width=True)
    except Exception as _report_error:
        st.error(f'Audit report unavailable: {_report_error}')

if _page in ('audit','audits'):
    if not mobile_online() and not st.session_state.get('_audit_mobile_autostart_attempted'):
        st.session_state['_audit_mobile_autostart_attempted']=True
        with st.spinner('Starting part tracking service on this PC…'):
            try:
                from suite.service_launcher import ensure as _ensure_mobile
                _mobile_start=_ensure_mobile('mobile',wait_seconds=8)
                try: health.clear()
                except Exception: pass
                if _mobile_start.get('ready'): st.rerun()
            except Exception as _mobile_start_error:
                st.session_state['_audit_mobile_start_error']=str(_mobile_start_error)
    st.markdown('## Part Audit, QR & Audit Register')
    st.markdown("""<div class="sl-how">
<div><b>1. Find a work order</b>Type any format (P005-110826 or p005110826). USB scanner works in the same box. Camera photo is optional.</div>
<div><b>2. Update status</b>After the WO is selected: change status, location and quantity, then take a photo. File name is WO + location + time.</div>
<div><b>3. Pictures</b>Saved in PHOTOS/MOBILE_AUDITS. Scan photos: PHOTOS/QR_SCANS. Open Files for the exact folder.</div>
<div><b>4. QR labels</b>Generate below. Payload is SLWO:&lt;WO&gt; — no server IP. Phone scans inside the mobile app.</div>
<div><b>5. Report</b>Category / date / location analysis is at the bottom of this page.</div>
</div>""",unsafe_allow_html=True)
    st.caption('USB handheld scanner works as keyboard input: click the WO box and scan.')

    st.markdown('### 📋 Mobile audit database')
    st.caption(f"Live file: `{DB}` · Photos: `{Path(os.environ.get('SL_PHOTO_ROOT',str(SHARED_ROOT/'PHOTOS')))/'MOBILE_AUDITS'}`")
    try:
        ensure_desktop_audit_tables()
        from suite.audit_report import load_all_audits as _all_aud
        _adb=_all_aud(DB)
        _n1,_n2,_n3=st.columns(3)
        _n1.metric('Audit rows',int(len(_adb)))
        _n2.metric('Work orders',int(_adb['wo_id'].nunique()) if not _adb.empty and 'wo_id' in _adb.columns else 0)
        _n3.metric('Database', 'FOUND' if DB.exists() else 'MISSING')
        if not _adb.empty:
            st.dataframe(_adb.head(500),use_container_width=True,hide_index=True,height=320)
            if st.button('Prepare Excel export',key='prep_audit_xlsx'):
                _ax=REPORTS/f'MOBILE_AUDIT_DATABASE_{bkk_now():%Y%m%d_%H%M%S}.xlsx'
                _adb.to_excel(_ax,index=False);st.session_state['audit_db_xlsx']=str(_ax)
            _axp=Path(st.session_state.get('audit_db_xlsx','')) if st.session_state.get('audit_db_xlsx') else None
            if _axp and _axp.exists():
                st.download_button('⬇ Download all audits (Excel)',_axp.read_bytes(),_axp.name,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='audit_db_xlsx_dl',use_container_width=True)
        if DB.exists() and st.button('Prepare SQLite copy',key='prep_audit_sqlite'):
            _snap=REPORTS/f'sl_planning_audit_copy_{bkk_now():%Y%m%d_%H%M%S}.db'
            shutil.copy2(DB,_snap);st.session_state['audit_db_snap']=str(_snap)
        _snapp=Path(st.session_state.get('audit_db_snap','')) if st.session_state.get('audit_db_snap') else None
        if _snapp and _snapp.exists():
            st.download_button('⬇ Download planning/audit SQLite copy',_snapp.read_bytes(),_snapp.name,'application/vnd.sqlite3',key='audit_db_sqlite_dl',use_container_width=True)
        _pub2,_phone_primary,_phone_http,_phone_https,_https_ready,_http_ready=phone_app_urls()
        st.markdown(f"<a href='{_phone_http}/register' target='_blank' style='display:inline-block;padding:10px 14px;background:#0057b8;color:#fff;border-radius:10px;text-decoration:none;font-weight:800'>Open live register (HTTP :8000)</a>",unsafe_allow_html=True)
        st.caption(f"Mobile audit: `{_phone_http}` · live camera link (optional): `{_phone_https}`" + ('' if _https_ready else ' · HTTPS camera service is not running; use QR photo or type/USB scan.'))
    except Exception as _ade: st.warning(f'Audit database could not be opened: {_ade}')


    # Clear navigation: no embedded planners/charts on this screen.
    _report_link=st.columns([1,1,1,1,1])[4]
    _report_link.link_button('📊 Open Audit Report + Download',_hub_page_href('report'),use_container_width=True)
    _n1,_n2,_n3,_n4=st.columns(4)
    _n1.markdown(f"<a href='{_hub_page_href('floor')}' target='_self' style='display:block;padding:15px;background:#fff7ef;border:1px solid #f58220;border-radius:12px;text-align:center;text-decoration:none;font-weight:900'>📋 Update WO Section Status</a>",unsafe_allow_html=True)
    _n2.markdown(f"<a href='{_hub_page_href('daily')}' target='_self' style='display:block;padding:15px;background:#fff7ef;border:1px solid #f58220;border-radius:12px;text-align:center;text-decoration:none;font-weight:900'>📅 Daily Plan</a>",unsafe_allow_html=True)
    _n3.markdown("<a href='#daily-status' style='display:block;padding:15px;background:#fff7ef;border:1px solid #f58220;border-radius:12px;text-align:center;text-decoration:none;font-weight:900'>📝 Daily Status</a>",unsafe_allow_html=True)
    _n4.markdown(f"<a href='{_hub_page_href('src')}' target='_self' style='display:block;padding:15px;background:#fff7ef;border:1px solid #f58220;border-radius:12px;text-align:center;text-decoration:none;font-weight:900'>📥 Source Files</a>",unsafe_allow_html=True)

    st.markdown('### 📊 Plan vs Physical — Graph Comparison Summary')
    try:
        if master is not None and not master.empty:
            _sum=master.copy(); _sum['Plan Section']=_sum['Section'].fillna('Not identified') if 'Section' in _sum else 'Not identified'
            _con=sqlite3.connect(DB)
            _la=pd.read_sql_query("SELECT physical_location,COUNT(*) AS [Physical Audits] FROM mobile_audits WHERE id IN (SELECT MAX(id) FROM mobile_audits GROUP BY wo_id) GROUP BY physical_location ORDER BY COUNT(*) DESC",_con)
            _tot_aud=pd.read_sql_query("SELECT COUNT(DISTINCT wo_id) n FROM mobile_audits",_con).iloc[0,0]
            _con.close()
            _m1,_m2=st.columns(2);_m1.metric('Physically audited WOs',int(_tot_aud));_m2.metric('Locations in latest audits',int(len(_la)))
            _pc=_sum.groupby('Plan Section',dropna=False).size().reset_index(name='Plan WOs').sort_values('Plan WOs',ascending=False).head(12)
            st.bar_chart(_pc.set_index('Plan Section')['Plan WOs'],height=260)
            if not _la.empty:
                with st.expander('Physical audit location summary',expanded=False):st.dataframe(_la,use_container_width=True,hide_index=True)
    except Exception as _e: st.warning(f'Comparison summary unavailable: {_e}')

    st.markdown('### 📝 Manual section status')
    st.caption('Use the dedicated Scan WO · section OPEN / CLOSED page. It confirms the scanned work order against the active plan before saving and records an event in the shared status database.')
    if st.button('Open scan / manual section status',key='goto_floor_from_home',use_container_width=True):
        st.query_params['page']='floor';st.rerun()

    st.markdown('### 1. Find Work Order')
    _typed=st.text_input('🔫 USB scanner or type Work Order',key='audit_wo_lookup',placeholder='P005-110826 / p005110826',help='Click here first. A USB QR/barcode scanner sends the code like a keyboard and Enter.')
    with st.expander('📷 Laptop / built-in camera QR — take one clear picture',expanded=False):
        st.caption('This is optional. USB scanner or typing is the fastest desktop method. For camera, allow browser camera permission once, hold QR flat and fill most of the frame.')
        _cam=st.camera_input('Take QR picture',key='desktop_qr_camera')
        _upcam=st.file_uploader('Or choose a QR photo',type=['png','jpg','jpeg'],key='desktop_qr_photo')
    _camera_wo=''
    _imgsrc=_cam if _cam is not None else _upcam
    if _imgsrc is not None:
        try:
            import cv2, numpy as np
            _arr=np.frombuffer(_imgsrc.getvalue(),dtype=np.uint8);_img=cv2.imdecode(_arr,cv2.IMREAD_COLOR)
            _val,_,_=cv2.QRCodeDetector().detectAndDecode(_img)
            if _val:
                _camera_wo=urllib.parse.unquote(_val.rstrip('/').split('/')[-1]);st.success(f'QR read: {_camera_wo}')
            else: st.error('QR was not detected in this picture. Move closer and retake, or use USB scanner/type the WO.')
        except Exception as _e: st.error(f'QR picture could not be read: {_e}')
    _aq=_camera_wo or _typed
    _ad=None
    if _aq:
        _ensure_plan_model()
        _planpath=fp('Plan-2026-LATEST.xlsx') or _resolve_shared_plan()
        try:
            from suite.wo_lookup import lookup as _wo_lookup
            _suggestions,_src=_wo_lookup(_aq, plan_path=_planpath, raw_df=raw, db_file=DB)
            if _src and Path(_src).suffix.lower() in {'.xlsx','.xlsm'}:
                _planpath=Path(_src)
        except Exception:
            _suggestions=plan2026_wo_suggestions(raw,_aq)
        if _suggestions is None:
            _suggestions=pd.DataFrame()
        if not _planpath and _suggestions.empty:
            st.error(f"No active Plan-2026 is loaded. Upload it on Home → Start here: Plan-2026. Expected central location: `{DATA/'Plan-2026-LATEST.xlsx'}`")
        elif _suggestions.empty:
            st.error(f"No match for `{_aq}` in active Plan-2026{(' ('+_planpath.name+')') if _planpath else ''} or the phone database. Check the typed/scanned WO, or replace the Plan file on Home.")
            if _planpath:
                st.caption(f"Search source: `{_planpath}` • Worksheet expected: `แผนการเผา` • key: ProductionCode")
            if _planpath and work_order_count()==0:
                st.error('Plan-2026 is loaded but the phone database has 0 work orders. Tap the button below, then search again.')
                if st.button('Load Plan-2026 into the phone database now / โหลด Plan-2026 เข้าฐานข้อมูลมือถือ', key='audit_sync_now', use_container_width=True):
                    _sok,_smsg=sync_mobile()
                    (st.success if _sok else st.error)(_smsg or ('Loaded.' if _sok else 'Sync failed.'))
                    st.rerun()
        else:
            _scols=[c for c in ['Plan row','Work Order','Customername','CustomernameID','รหัสสินค้า','Specification','QTY','กำหนดส่งใหม่'] if c in _suggestions.columns]
            if not hub_can_view_customers():_scols=[c for c in _scols if 'customer' not in str(c).lower() and 'ลูกค้า' not in str(c)]
            _exact=_suggestions[_suggestions['Work Order'].map(_norm_wo).eq(_norm_wo(_aq))]
            if not _exact.empty:
                _selected_wo=_exact.iloc[0]['Work Order']
            else:
                st.info(f"{len(_suggestions)} suggestion(s) from `{_planpath.name if _planpath else 'phone database'}`. Select the correct WO below.")
                _selected_wo=st.selectbox('Matching work orders',_suggestions['Work Order'].astype(str).tolist(),key='desktop_wo_suggestion')
                st.dataframe(display_df(_suggestions[_scols].rename(columns={'Customername':'Customer','รหัสสินค้า':'Product','QTY':'Quantity','กำหนดส่งใหม่':'Revised due'})),use_container_width=True,hide_index=True)
            _ad=plan2026_wo_detail(_planpath,_selected_wo,raw) if _planpath else None
            if _ad is None and not _suggestions.empty:
                _hit=_suggestions[_suggestions['Work Order'].map(_norm_wo).eq(_norm_wo(_selected_wo))]
                _r=(_hit if not _hit.empty else _suggestions).iloc[0]
                _ad={'row':_r.get('Plan row',''),'wo':_selected_wo,'customer':_r.get('Customername',''),'product':_r.get('รหัสสินค้า',''),
                     'qty':_r.get('QTY'),'initial_due':_r.get('กำหนดเข้าคลัง'),'revised_due':_r.get('กำหนดส่งใหม่'),
                     'sales_due':'','mill_batches':None,'sections':[],'location':'Not identified from HH:HX','location_source':'','source':'phone database'}
        if _ad:
            if _ad.get('lookup_error'):
                st.error(f"Plan lookup failed: {_ad['lookup_error']}")
                st.caption(f"File: `{_ad.get('source_path',_planpath)}`")
                _ad=None
        if _ad:
            _customer_label=(_ad.get('customer') or '—') if hub_can_view_customers() else 'RESTRICTED'
            st.success(f"WO {_ad['wo']}  |  {_customer_label}  |  {_ad['product']}  |  PLAN LOCATION: {_ad['location']}  |  Plan row {_ad['row']}")
            _x1,_x2,_x3,_x4=st.columns(4);_x1.metric('Quantity',_ad['qty'] or '—');_x2.metric('Initial due',format_due_date(_ad['initial_due']) or '—');_x3.metric('Revised due',format_due_date(_ad['revised_due']) or '—');_x4.metric('BY mill batches',_ad['mill_batches'] or '—')
            st.markdown('#### Plan-2026 — Open / Closed by section')
            st.dataframe(pd.DataFrame(_ad['sections']),use_container_width=True,hide_index=True)
            _plan_date_rows=_ad.get('process_dates',[]);_actual_by_proc={}
            try:
                _con=sqlite3.connect(DB,timeout=2);_con.row_factory=sqlite3.Row
                _rr=_con.execute('SELECT process_name,planned_date FROM routes WHERE wo_id=? ORDER BY seq',(_ad['wo'],)).fetchall()
                _ee=_con.execute('SELECT process_name,location,event_type,event_time FROM events WHERE wo_id=? ORDER BY id',(_ad['wo'],)).fetchall();_con.close()
                _norm_proc=lambda x:''.join(ch for ch in str(x or '').upper() if ch.isalnum())
                for _e in _ee:
                    _k=_norm_proc(_e['process_name']);_slot=_actual_by_proc.setdefault(_k,{'Actual Start':'','Actual Complete':''})
                    if _e['event_type'] in ('RECEIVE','START','RESUME','MOVE') and not _slot['Actual Start']:_slot['Actual Start']=_e['event_time']
                    if _e['event_type'] in ('COMPLETE','PARTIAL_COMPLETE'):_slot['Actual Complete']=_e['event_time']
                _qty_con=sqlite3.connect(DB,timeout=2)
                _qty_events=_qty_con.execute("SELECT qty FROM events WHERE wo_id=? AND event_type IN ('PARTIAL_COMPLETE','COMPLETE') AND qty IS NOT NULL ORDER BY id",(_ad['wo'],)).fetchall();_qty_con.close()
                _reported_qty=max((float(x[0]) for x in _qty_events if x[0] is not None),default=None)
                _order_qty=pd.to_numeric(pd.Series([_ad.get('qty')]),errors='coerce').iloc[0]
                if _reported_qty is not None and pd.notna(_order_qty) and float(_order_qty)>0:
                    _pct=float(_reported_qty)/float(_order_qty)*100
                    st.metric('Production-reported completion / ผลิตแล้วตามบันทึก',f'{_reported_qty:,.0f} pcs · {_pct:.1f}% of WO quantity')
                else:
                    st.caption('Production completion quantity: NOT RECORDED in shop-floor completion events; no percentage inferred.')
                _last_loc=next((_e for _e in reversed(_ee) if _e['process_name']),None)
                if _last_loc:st.caption(f"Latest shop-floor process/location: {_last_loc['process_name']} · {_last_loc['location'] or 'location not entered'} · {_last_loc['event_time']} (Plan-2026 location: {_ad.get('location') or '—'}). Physical audit location is shown separately in Audit Report.")
                if _rr:_plan_date_rows=[{'Process':x['process_name'],'Planned Date':x['planned_date']} for x in _rr]
            except Exception as _audit_trace_error:st.caption(f'Actual event trace unavailable: {_audit_trace_error}')
            if _plan_date_rows:
                _compare=[]
                for _pr in _plan_date_rows:
                    _actual=_actual_by_proc.get(_norm_proc(_pr.get('Process')),{})
                    _compare.append({'Process':_pr.get('Process'),'Plan date (Plan-2026)':_pr.get('Planned Date'),'Actual start (shop-floor event)':_actual.get('Actual Start',''),'Actual complete (shop-floor event)':_actual.get('Actual Complete','')})
                st.markdown('#### Planned vs actual process dates / วันที่ตามแผนเทียบวันที่จริง')
                st.dataframe(pd.DataFrame(_compare),use_container_width=True,hide_index=True)
            else:st.info('Plan-2026 has no readable process-date values for this WO; section OPEN/CLOSED status is shown above. Re-sync/replace Plan-2026 to refresh planned route dates.')

    if _ad:
        st.markdown('### 2. Physical Audit — Edit & Submit')
        _ac1,_ac2,_ac3=st.columns(3)
        _ast=_ac1.selectbox('Physical status',['OK','OPEN','CLOSED','HOLD','REWORK','NCR','UNIDENTIFIED'],key='desk_audit_status_'+_norm_wo(_ad['wo']))
        _aloc=_ac2.text_input('Physical location / section — enter observed location',value='',key='desk_audit_loc_'+_norm_wo(_ad['wo']))
        _qty_unknown=st.checkbox('Quantity unknown / not counted yet',value=True,key='desk_audit_qty_unknown_'+_norm_wo(_ad['wo']))
        _aqty=None if _qty_unknown else _ac3.number_input('Verified physical quantity (pcs)',min_value=0.0,value=0.0,step=1.0,key='desk_audit_qty_'+_norm_wo(_ad['wo']))
        _aproc=st.text_input('Observed process — enter actual section',value='',key='desk_audit_process_'+_norm_wo(_ad['wo']))
        _anote=st.text_area('Audit notes',key='desk_audit_notes_'+_norm_wo(_ad['wo']))
        _aphoto=st.camera_input('📸 Part photo — optional evidence',key='desk_part_photo_'+_norm_wo(_ad['wo']))
        _sub_key='desktop_audit_submission_'+_norm_wo(_ad['wo'])
        _photo_hash=hashlib.sha256(_aphoto.getvalue()).hexdigest() if _aphoto is not None else ''
        _form_fingerprint=hashlib.sha256(repr((_norm_wo(_ad['wo']),_ast,_aloc,_aqty,_qty_unknown,_aproc,_anote,_photo_hash)).encode()).hexdigest()
        if st.session_state.get(_sub_key+'_fingerprint')!=_form_fingerprint:
            st.session_state[_sub_key]=uuid.uuid4().hex
            st.session_state[_sub_key+'_fingerprint']=_form_fingerprint
        if st.button('＋ Start a new observation / บันทึกการตรวจครั้งใหม่',key='desktop_audit_new_observation'):
            st.session_state[_sub_key]=uuid.uuid4().hex
            st.rerun()
        if hub_can_edit() and st.button('💾 SAVE PHYSICAL AUDIT',type='primary',use_container_width=True):
            _submission_id=st.session_state.setdefault(_sub_key,uuid.uuid4().hex)
            _con=None
            try:
                ensure_desktop_audit_tables()
                _con=sqlite3.connect(DB,timeout=15);_con.execute('PRAGMA busy_timeout=15000');_cur=_con.cursor()
                _cols={r[1] for r in _cur.execute('PRAGMA table_info(mobile_audits)').fetchall()}
                if not _cols:raise RuntimeError('Audit table is missing. Start the mobile audit service once, then reload this page.')
                for _col,_ddl in [('client_submission_id','TEXT'),('client_time','TEXT'),('server_received_at','TEXT'),('qty_unknown','INTEGER NOT NULL DEFAULT 0'),('qty_unit','TEXT')]:
                    if _col not in _cols:_cur.execute(f'ALTER TABLE mobile_audits ADD COLUMN {_col} {_ddl}')
                _cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_desktop_audit_submission ON mobile_audits(client_submission_id) WHERE client_submission_id IS NOT NULL')
                _existing=_cur.execute('SELECT id FROM mobile_audits WHERE client_submission_id=?',(_submission_id,)).fetchone()
                _now=bkk_now().isoformat(timespec='seconds');_user=st.session_state.get('sl_user','desktop')
                if _existing:
                    _aid=int(_existing[0]);_duplicate=True
                else:
                    _cur.execute('INSERT INTO mobile_audits(wo_id,user_name,verified_qty,physical_status,physical_location,observed_process,notes,created_at,client_submission_id,client_time,server_received_at,qty_unknown,qty_unit) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(_ad['wo'],_user,_aqty,_ast,_aloc,_aproc,_anote,_now,_submission_id,_now,_now,int(_qty_unknown),'pcs'));_aid=_cur.lastrowid;_duplicate=False
                if _aphoto is not None and not _duplicate:
                    from suite.qr_labels import photo_stem as _pstem
                    _pd=Path(os.environ.get('SL_PHOTO_ROOT',str(SHARED_ROOT/'PHOTOS')))/'MOBILE_AUDITS';_pd.mkdir(parents=True,exist_ok=True);_fn=_pstem(_ad['wo'],_aloc,bkk_now())+'_'+_submission_id[:8]+'.jpg';(_pd/_fn).write_bytes(_aphoto.getvalue())
                    _cur.execute('INSERT INTO mobile_audit_photos(audit_id,filename,original_name,content_type,created_at) VALUES(?,?,?,?,?)',(_aid,_fn,_fn,'image/jpeg',_now))
                _con.commit()
                st.success(f"{'Already saved — duplicate retry ignored' if _duplicate else 'Physical audit saved'} · Audit ID {_aid} · {_now} Thailand local time — Phan Thong, Chonburi · photo folder: {_pd if _aphoto is not None and not _duplicate else Path(os.environ.get('SL_PHOTO_ROOT',str(SHARED_ROOT/'PHOTOS')))/'MOBILE_AUDITS'}")
            except Exception as _e:
                if _con is not None:
                    try:_con.rollback()
                    except Exception:pass
                st.error(f'Audit save failed; nothing was acknowledged as saved: {_e}')
            finally:
                if _con is not None:
                    try:_con.close()
                    except Exception:pass

    st.markdown('### 📱 Mobile Phone Connection')
    import qrcode, io
    _pub3,_phone_primary3,_phone_http3,_phone_https3,_https_up3,_http_up3=phone_app_urls()
    _mobile_url=_phone_primary3
    _qr=qrcode.make(_mobile_url);_buf=io.BytesIO();_qr.save(_buf,format='PNG')
    _mc1,_mc2=st.columns([1,2]);_mc1.image(_buf.getvalue(),width=190);_mc2.code(_mobile_url);_mc2.caption('Use the factory LAN address, never 127.0.0.1 (that is the phone itself). HTTP supports type/photo; live camera QR scanning requires HTTPS. Open '+_phone_https3+' and install '+_pub3['http']+'/tls/ca.crt once, or ask IT to place the company certificate in CENTRAL_DATA/TLS. HTTP: '+_phone_http3+' · HTTPS camera: '+_phone_https3)
    if not mobile_online():
        if st.session_state.get('_audit_mobile_start_error'):
            st.caption('Service start detail: '+str(st.session_state['_audit_mobile_start_error'])[:240])
        if st.button('Start phone app on this PC / เริ่มแอปมือถือ', key='audit_start_mobile', use_container_width=True):
            from suite.service_launcher import ensure as _ens_m
            _ens_m('mobile', wait_seconds=8)
            st.session_state['_audit_mobile_autostart_attempted']=False
            try: health.clear()
            except Exception: pass
            st.rerun()
    with st.expander('▦ Work Order QR Labels — IP-independent',expanded=True):
        st.caption('QR contains SLWO:<WO>, not an IP address. Generate labels by section and current due-date range under Files & Traceability. The uppercase WO prints directly beneath its QR on the same sticker.')
        st.markdown(f'<a href="{_hub_page_href("src")}#qr-label-generator">Open QR label generator →</a>',unsafe_allow_html=True)

    st.markdown("<div id='daily-status'></div>",unsafe_allow_html=True)
    st.markdown('### 📝 Daily Status — Edit & Save')
    if DB.exists() and master is not None and not master.empty:
        try:
            _con=sqlite3.connect(DB)
            _ev=pd.read_sql_query("""SELECT wo_id AS [Work Order],physical_status AS [Physical Status],physical_location AS [Physical Location],verified_qty AS [Audit Qty],user_name AS [Audited By],created_at AS [Audit Time],notes AS [Audit Notes] FROM mobile_audits WHERE id IN (SELECT MAX(id) FROM mobile_audits GROUP BY wo_id) ORDER BY created_at DESC""",_con)
            _con.close()
            _pc=master[[c for c in ['Work Order','Customer','Product Code','Section','pcs','Due Date','Authoritative Closed'] if c in master]].copy()
            _ds=_pc.merge(_ev,on='Work Order',how='left');_ds['Planning Department Review']=''
            _dsed=_persistent_data_editor(_ds.head(1000),use_container_width=True,hide_index=True,height=330,key='audit_daily_status_editor',disabled=not hub_can_edit())
            if hub_can_edit() and st.button('💾 SAVE DAILY STATUS',use_container_width=True):
                _dp=DATA/'Daily-Status-LATEST.xlsx';_dp.write_bytes(to_xlsx_bytes(_dsed,'Daily Status'));register_source('Daily-Status-LATEST.xlsx',_dp,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),'Daily-Status-LATEST.xlsx','Desktop Operator Control');st.success('Daily Status saved centrally.')
        except Exception as _e: st.warning(f'Daily Status unavailable: {_e}')
    else: st.info('Load Plan-2026 to create Daily Status.')

    st.markdown('### 📊 Physical status report — category, date, location')
    try:
        from suite.audit_report import analyze as _ar_analyze, enrich_from_plan as _ar_enrich, load_latest_audits as _ar_load
        _aud=_ar_enrich(_ar_load(DB), master)
        _rep=_ar_analyze(_aud)
        _rs=_rep['summary'].iloc[0]
        _r1,_r2,_r3,_r4=st.columns(4)
        _r1.metric('Audited WOs',int(_rs['Audited WOs']));_r2.metric('Categories',int(_rs['Categories']));_r3.metric('Dates',int(len(_rep['by_date'])));_r4.metric('Locations',int(_rs['Locations']))
        if not _rep['by_category'].empty:
            _c1,_c2=st.columns(2)
            with _c1: st.plotly_chart(px.bar(_rep['by_category'],x='Product category',y='WOs',color='Product category',title='Audited work orders by product category',text_auto='.0f'),use_container_width=True)
            with _c2: st.plotly_chart(px.bar(_rep['by_date'],x='Date',y='WOs',title='Audits by date',text_auto='.0f'),use_container_width=True)
            _c3,_c4=st.columns(2)
            with _c3: st.plotly_chart(px.pie(_rep['by_status'],names='Status',values='WOs',title='Latest physical status'),use_container_width=True)
            with _c4: st.dataframe(_rep['by_location'],use_container_width=True,hide_index=True,height=280)
            with st.expander('📍 Audit summary by section / สรุปตรวจนับแยกแผนก',expanded=False):
                if not _rep['by_process'].empty:
                    st.plotly_chart(px.bar(_rep['by_process'],x='Observed process',y='WOs',color='Observed process',title='Audited work orders by observed section',text_auto='.0f'),use_container_width=True)
                    st.dataframe(_rep['by_process'],use_container_width=True,hide_index=True)
            _photo_col=next((c for c in ['photo_filename','Photo filename'] if c in _aud.columns),None)
            _photo_root=Path(os.environ.get('SL_PHOTO_ROOT',str(SHARED_ROOT/'PHOTOS')))/'MOBILE_AUDITS'
            if _photo_col:
                with st.expander('📷 Latest audit photos / รูปถ่ายตรวจนับล่าสุด',expanded=False):
                    _photo_rows=_aud[_aud[_photo_col].fillna('').astype(str).str.strip().ne('')].head(12)
                    if _photo_rows.empty: st.info('No audit photos are linked to the latest records yet.')
                    else:
                        for _st_i in range(0,len(_photo_rows),3):
                            _cols=st.columns(3)
                            for _col, (_, _pr) in zip(_cols,_photo_rows.iloc[_st_i:_st_i+3].iterrows()):
                                _ph=_photo_root/Path(str(_pr[_photo_col])).name
                                if _ph.is_file(): _col.image(str(_ph),caption=f"{_pr.get('wo_id','')} · {_pr.get('observed_process','')} · {_pr.get('physical_location','')} · {_pr.get('created_at','')}",use_container_width=True)
            st.caption('Desktop summary charts use the latest audit per WO. The complete download below includes every audit event, picture files, section events and separately labelled WIP sources.')
            if st.button('📦 BUILD COMPLETE AUDIT + PART STATUS + WIP REPORT',key='build_complete_audit_wip_report',use_container_width=True,type='primary'):
                with st.spinner('Building the complete report from saved audit records and current WIP sources...'):
                    try:
                        from suite.audit_report import load_all_audits as _ar_all, load_open_wip_by_process as _ar_event_wip, load_production_wip_snapshot as _ar_prod_wip
                        _all_aud=_ar_enrich(_ar_all(DB),master)
                        _all_summary=_ar_analyze(_all_aud)
                        _rcon=sqlite3.connect(DB)
                        try:
                            _evt=pd.read_sql_query('SELECT event_time,wo_id,event_type,qty,process_name,location,terminal_code,user_name,source,reason,notes FROM events ORDER BY id',_rcon)
                            _qrlog=pd.read_sql_query('SELECT id,created_at,wo_id,payload,scanned_by,scan_method,result,photo_path,photo_sha256 FROM qr_scan_log ORDER BY id',_rcon)
                            _unknown=pd.read_sql_query('SELECT temp_id,qty,process_name,location,issue_type,notes,reporter,created_at FROM unidentified_parts ORDER BY id',_rcon)
                            _photos=pd.read_sql_query('SELECT p.id,p.audit_id,a.wo_id,a.created_at,a.physical_status,a.physical_location,a.observed_process,p.filename,p.original_name,p.content_type,p.created_at AS photo_saved_at FROM mobile_audit_photos p LEFT JOIN mobile_audits a ON a.id=p.audit_id ORDER BY p.id',_rcon)
                        finally:_rcon.close()
                        _photo_base=Path(os.environ.get('SL_PHOTO_ROOT',str(SHARED_ROOT/'PHOTOS')))/'MOBILE_AUDITS'
                        if not _photos.empty:
                            _photos['Stored path']=_photos['filename'].fillna('').astype(str).map(lambda _n:str(_photo_base/Path(_n).name) if _n else '')
                            _photos['SHA-256']=_photos['filename'].fillna('').astype(str).map(lambda _n:hashlib.sha256((_photo_base/Path(_n).name).read_bytes()).hexdigest() if _n and (_photo_base/Path(_n).name).is_file() else '')
                        _status_cols=[c for c in ['Work Order','Customer','Product Category','Product Code','Specification','Section','pcs','ton','Due Date','Authoritative Closed'] if c in master.columns]
                        _status=master[_status_cols].copy() if _status_cols else pd.DataFrame()
                        _plan_open=op.copy() if isinstance(op,pd.DataFrame) else pd.DataFrame()
                        _event_wip=_ar_event_wip(DB)
                        _prod_wip,_prod_wip_errors=_ar_prod_wip(ROOT)
                        _xl=REPORTS/f'COMPLETE_AUDIT_PART_STATUS_WIP_{bkk_now():%Y%m%d_%H%M%S}.xlsx'
                        _summary_rows=[('Generated at (Thailand)',bkk_now().strftime('%Y-%m-%d %H:%M:%S')),('Planning source',plan.name if plan else 'Not loaded'),('Audit records',len(_all_aud)),('Distinct audited WOs',int(_all_aud['wo_id'].nunique()) if not _all_aud.empty and 'wo_id' in _all_aud else 0),('Saved audit pictures',len(_photos)),('WO section / movement events',len(_evt)),('QR scan records',len(_qrlog)),('Unidentified part records',len(_unknown)),('Plan-2026 planning WIP',f'{_plan_open["Work Order"].nunique() if "Work Order" in _plan_open else len(_plan_open)} WOs; remaining quantity'),('Scan-event WIP rows',len(_event_wip)),('Production WIP source rows',len(_prod_wip)),('Production WIP source notes','; '.join(_prod_wip_errors) if _prod_wip_errors else 'No source errors reported'),('WIP definitions','Plan WIP = Plan-2026 open balance; Scan-event WIP = latest production scan process and remaining WO quantity; Production WIP = section workbook snapshot. These measures are separate and must not be added.')]
                        with pd.ExcelWriter(_xl,engine='openpyxl') as _xw:
                            pd.DataFrame(_summary_rows,columns=['Report item','Value']).to_excel(_xw,sheet_name='READ ME + SUMMARY',index=False)
                            for _nm,_df in _all_summary.items():_df.to_excel(_xw,sheet_name=('Audit '+str(_nm))[:31],index=False)
                            _status.to_excel(_xw,sheet_name='Plan WO STATUS',index=False)
                            _all_aud.to_excel(_xw,sheet_name='ALL PHYSICAL AUDITS',index=False)
                            _evt.to_excel(_xw,sheet_name='SECTION EVENT HISTORY',index=False)
                            _qrlog.to_excel(_xw,sheet_name='QR SCAN LOG',index=False)
                            _unknown.to_excel(_xw,sheet_name='UNIDENTIFIED PARTS',index=False)
                            _plan_open.to_excel(_xw,sheet_name='PLAN-2026 OPEN WIP',index=False)
                            _event_wip.to_excel(_xw,sheet_name='SCAN EVENT WIP',index=False)
                            (_prod_wip if not _prod_wip.empty else pd.DataFrame([{'Source note':'No active Production WIP source was readable.'}])).to_excel(_xw,sheet_name='PRODUCTION WIP SNAPSHOT',index=False)
                            (_photos if not _photos.empty else pd.DataFrame(columns=['audit_id','wo_id','filename','photo_saved_at'])).to_excel(_xw,sheet_name='PHOTO EVIDENCE',index=False)
                        # Embed optimized thumbnails on the Photo Evidence tab, preserving every image file record and its audit link.
                        if not _photos.empty:
                            from openpyxl import load_workbook as _load_xl
                            _wb=_load_xl(_xl);_pws=_wb['PHOTO EVIDENCE'];_pws.freeze_panes='A2';_pws.auto_filter.ref=_pws.dimensions
                            _pws.column_dimensions['L'].width=24
                            for _pi,_pr in _photos.iterrows():
                                _photo_path=_photo_base/Path(str(_pr.get('filename') or '')).name
                                _excelrow=int(_pi)+2
                                if _photo_path.is_file():
                                    try:
                                        from PIL import Image as _PILImage
                                        _im=_PILImage.open(_photo_path);_im.thumbnail((180,110));_buf=io.BytesIO();_im.convert('RGB').save(_buf,format='JPEG',quality=68,optimize=True);_buf.seek(0)
                                        _ximg=XLImage(_buf);_ximg.width=120;_ximg.height=max(1,int(120*_im.height/max(_im.width,1)));_pws.add_image(_ximg,f'L{_excelrow}');_pws.row_dimensions[_excelrow].height=64
                                    except Exception:pass
                            _wb.save(_xl);_wb.close()
                        st.session_state['complete_audit_wip_report_path']=str(_xl)
                        st.success(f'Complete report ready · {_xl.name} · {_xl.stat().st_size/1_000_000:.1f} MB')
                    except Exception as _report_error:st.error(f'Complete report could not be built: {_report_error}')
            _report_path=Path(st.session_state.get('complete_audit_wip_report_path','')) if st.session_state.get('complete_audit_wip_report_path') else None
            if _report_path and _report_path.is_file():st.download_button('⬇ DOWNLOAD COMPLETE AUDIT + PART STATUS + WIP REPORT',_report_path.read_bytes(),_report_path.name,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='audit_report_xlsx',use_container_width=True)
        else:
            st.info('No physical audits yet. Scan or type a WO above, then save status with a photo.')
        st.caption(f"Pictures: {Path(os.environ.get('SL_PHOTO_ROOT',str(SHARED_ROOT/'PHOTOS')))/'MOBILE_AUDITS'} · QR scans: {SHARED_ROOT/'PHOTOS'/'QR_SCANS'}")
    except Exception as _re: st.warning(f'Report unavailable: {_re}')

if _page == 'wip':
    st.header('🏭 WIP — Planning vs Production / WIP แผนเทียบฝ่ายผลิต')
    st.caption('One WIP destination. The two source measures are shown separately with their own definitions, units, cut-off and source evidence; they are never added together.')
    _wiplink,_recoverlink=st.columns(2)
    with _wiplink:st.markdown(f"<a href='{_hub_page_href('daily','capacity')}' target='_self' style='font-size:.84rem;color:#0057b8;text-decoration:underline'>↗ Section Plan vs Capacity graphs</a>",unsafe_allow_html=True)
    with _recoverlink:st.markdown(f"<a href='{_hub_page_href('recovery_review')}' target='_self' style='font-size:.84rem;color:#0057b8;text-decoration:underline'>↗ Production Backorder Recovery Plan — status, reasons and WO detail</a>",unsafe_allow_html=True)
    _asof=bkk_now().strftime('%d %b %Y %H:%M Bangkok')
    _plan_wip_cat=pd.DataFrame()
    _prod_wip_cat=pd.DataFrame()
    _plan_wip_error=''
    if plan and (op is None or (isinstance(op,pd.DataFrame) and op.empty)):
        try:
            from suite.planning_wip import open_order_wip
            op=open_order_wip(master) if isinstance(master,pd.DataFrame) and not master.empty else _cached_plan_wip_fallback(str(plan.resolve()),plan.stat().st_mtime_ns,plan.stat().st_size)
            master=master if isinstance(master,pd.DataFrame) else pd.DataFrame()
        except Exception as _plan_wip_exc:
            _plan_wip_error=f'{type(_plan_wip_exc).__name__}: {_plan_wip_exc}'
    if plan:
        st.success(f'PLAN-2026 PLANNING WIP · Source: {plan.name} · modified {datetime.fromtimestamp(plan.stat().st_mtime):%Y-%m-%d %H:%M} · displayed { _asof }')
        if op is None:
            st.warning('Planning WIP could not be calculated from the active Plan-2026. No zero value is substituted.')
            st.error(_plan_wip_error or st.session_state.get('plan_wip_fallback_error') or st.session_state.get('plan_analysis_error','Plan-2026 analysis did not return an open-order table.'))
        else:
            if st.session_state.get('plan_wip_fallback_note'):
                st.caption(st.session_state['plan_wip_fallback_note'])
            _p1,_p2,_p3=st.columns(3)
            _p1.metric('Planning WIP work orders',int(op['Work Order'].astype(str).nunique()) if 'Work Order' in op else len(op))
            _p2.metric('Planning WIP quantity (pcs)',f"{pd.to_numeric(op.get('pcs',pd.Series(dtype=float)),errors='coerce').sum(min_count=1):,.0f}" if 'pcs' in op else '—')
            _p3.metric('Planning WIP estimated net weight (t)',f"{pd.to_numeric(op.get('ton',pd.Series(dtype=float)),errors='coerce').sum(min_count=1):,.3f}" if 'ton' in op else '—')
            st.caption('Meaning: open/remaining quantities and process queues derived from Plan-2026 planning fields. Weight is estimated from Plan-2026 product weight. This is not a physical shop-floor count.')
            _catcol=next((c for c in ['Product Category','Category'] if c in op.columns),None)
            if _catcol and 'Work Order' in op.columns:
                _wx=op.copy();_wx[_catcol]=_wx[_catcol].fillna('UNCLASSIFIED').astype(str).str.upper().replace({'F':'P','':'UNCLASSIFIED'})
                _plan_wip_cat=_wx.groupby(_catcol,as_index=False).agg(**{'Planning WIP WOs':('Work Order','nunique'),'Planning WIP pcs':('pcs',lambda s:pd.to_numeric(s,errors='coerce').sum(min_count=1)),'Planning WIP t':('ton',lambda s:pd.to_numeric(s,errors='coerce').sum(min_count=1))}).rename(columns={_catcol:'Product Category'})
                st.markdown('#### Plan-2026 WIP by process and product category / WIP แผนตามกระบวนการและกลุ่มสินค้า')
                if 'Section' in _wx.columns:
                    _plan_stack=_wx.groupby(['Section',_catcol],as_index=False).agg(**{'Remaining WIP t':('ton',lambda s:pd.to_numeric(s,errors='coerce').sum(min_count=1))})
                    _plan_stack=_plan_stack.dropna(subset=['Remaining WIP t'])
                    if not _plan_stack.empty:
                        _plan_stack_fig=px.bar(_plan_stack,x='Section',y='Remaining WIP t',color=_catcol,barmode='stack',text_auto='.2f',
                            category_orders={_catcol:['P','R','S','T','M','PB']},title='Plan-2026 remaining WIP by process · tonnes · stacked by category')
                        _plan_stack_totals=_plan_stack.groupby('Section',as_index=False)['Remaining WIP t'].sum(min_count=1)
                        for _,_pw in _plan_stack_totals.iterrows():
                            _plan_stack_fig.add_annotation(x=_pw['Section'],y=float(_pw['Remaining WIP t']),text=f"{float(_pw['Remaining WIP t']):,.2f} t",showarrow=False,yshift=11,font=dict(size=12,color='#17324D'))
                        _pmax=pd.to_numeric(_plan_stack_totals['Remaining WIP t'],errors='coerce').max()
                        if pd.notna(_pmax) and _pmax>0:_plan_stack_fig.update_yaxes(range=[0,_pmax*1.18])
                        _plan_stack_fig.update_layout(height=400,xaxis_title='Current process / กระบวนการปัจจุบัน',yaxis_title='Remaining estimated tonnes / ตันคงเหลือโดยประมาณ',legend_title='Product category / กลุ่มสินค้า')
                        st.plotly_chart(_plan_stack_fig,use_container_width=True,config={'displaylogo':False})
                _wc1,_wc2,_wc3=st.columns(3)
                with _wc1:st.plotly_chart(px.bar(_plan_wip_cat,x='Product Category',y='Planning WIP WOs',color='Product Category',title='Planning open WO count by category',text_auto='.0f'),use_container_width=True)
                with _wc2:st.plotly_chart(px.bar(_plan_wip_cat,x='Product Category',y='Planning WIP pcs',color='Product Category',title='Planning WIP pieces by category',text_auto=',.0f'),use_container_width=True)
                with _wc3:st.plotly_chart(px.bar(_plan_wip_cat,x='Product Category',y='Planning WIP t',color='Product Category',title='Estimated planning WIP tonnes by category',text_auto='.2f'),use_container_width=True)
                st.dataframe(_plan_wip_cat,use_container_width=True,hide_index=True)
            _pshow=[c for c in ['Section','Product Category','Work Order','Customer','Product Code','pcs','ton','Due Date'] if c in op.columns]
            if _pshow: st.dataframe(display_df(op[_pshow]),use_container_width=True,hide_index=True,height=360)
    else:
        st.warning('PLAN-2026 PLANNING WIP is unavailable because the active Plan-2026 source is not loaded.')
    st.divider()
    st.success(f'PRODUCTION WIP · section snapshot reports · displayed {_asof}')
    try:
        _pwc=ROOT/'apps'/'daily'
        if str(_pwc) not in sys.path: sys.path.insert(0,str(_pwc))
        from production_wip_control import production_snapshot as _prod_snapshot
        _prod,_prod_errors=_prod_snapshot(_pwc)
        if _prod.empty:
            st.info('No readable active Production WIP section reports are available. Missing sections remain blank and are not converted to zero.')
        else:
            _pr1,_pr2,_pr3=st.columns(3)
            _pr1.metric('Production open WO records (section counts)',f"{pd.to_numeric(_prod['Open WO'],errors='coerce').sum(min_count=1):,.0f}")
            _pr2.metric('Production open gross weight (t)',f"{pd.to_numeric(_prod['Open t'],errors='coerce').sum(min_count=1):,.3f}")
            _pr3.metric('Sections loaded',int(_prod['Section'].nunique()))
            st.caption('Meaning: actual open quantities/weight reported by department workbooks. WO counts are section records, not unique factory WOs. Weight is gross reported weight; curing is included under Firing + curing.')
            _prod_wip_cat=_prod.groupby('Category',as_index=False).agg(**{'Production open WO records':('Open WO',lambda s:pd.to_numeric(s,errors='coerce').sum(min_count=1)),'Production WIP gross t':('Open t',lambda s:pd.to_numeric(s,errors='coerce').sum(min_count=1))})
            st.markdown('#### Production WIP graphs / กราฟ WIP ฝ่ายผลิต')
            _wp1,_wp2=st.columns([3,2])
            with _wp1:
                _wip_section_cat=_prod.groupby(['Section','Category'],as_index=False)['Open t'].sum(min_count=1)
                _wip_stacked=px.bar(_wip_section_cat,x='Section',y='Open t',color='Category',barmode='stack',
                    category_orders={'Category':['P','R','S','T','M','PB']},title='Production WIP by section and category (gross tonnes)')
                _stack_totals=_wip_section_cat.groupby('Section',as_index=False)['Open t'].sum(min_count=1)
                for _,_tw in _stack_totals.iterrows():_wip_stacked.add_annotation(x=_tw['Section'],y=float(_tw['Open t']),text=f"{float(_tw['Open t']):,.2f} t",showarrow=False,yshift=10,font=dict(size=12,color='#17324D'))
                _stack_max=pd.to_numeric(_stack_totals['Open t'],errors='coerce').max()
                if pd.notna(_stack_max) and _stack_max>0:_wip_stacked.update_yaxes(range=[0,_stack_max*1.14])
                _wip_stacked.update_layout(height=460,xaxis_tickangle=-18,yaxis_title='Gross tonnes',legend_title='Category')
                st.plotly_chart(_wip_stacked,use_container_width=True,config={'displaylogo':False})
            with _wp2:
                _wip_mix=_prod.groupby('Category',as_index=False)['Open t'].sum(min_count=1)
                _wip_donut=px.pie(_wip_mix,names='Category',values='Open t',hole=.52,
                    category_orders={'Category':['P','R','S','T','M','PB']},title='Production WIP composition (gross tonnes)')
                _wip_donut.update_layout(height=460,legend_title='Category')
                st.plotly_chart(_wip_donut,use_container_width=True,config={'displaylogo':False})
            st.caption('Both graphs use the same active Production WIP section workbooks. The stack shows section × product category; the ring shows category share.')
            st.caption('The department summary workbooks do not provide production WIP pcs in this summary. PCS comparison is therefore shown for Plan-2026 only; no production PCS is inferred from tonnes.')
            _pshow=[c for c in ['Section','Category','Open WO','Open kg','Open t','Original filename','Uploaded at','Source'] if c in _prod.columns]
            st.dataframe(_prod[_pshow],use_container_width=True,hide_index=True,height=360)
        if _prod_errors:
            with st.expander('Production WIP source problems / sections needing review'):
                st.dataframe(pd.DataFrame({'Source issue':_prod_errors}),use_container_width=True,hide_index=True)
    except Exception as _werr:
        st.error(f'Production WIP could not be read: {_werr}')
    if not _plan_wip_cat.empty and not _prod_wip_cat.empty:
        _wc=_plan_wip_cat.merge(_prod_wip_cat,left_on='Product Category',right_on='Category',how='outer')
        st.markdown('#### Category comparison — separate source measures / เทียบรายกลุ่มโดยแยกฐานข้อมูล')
        st.caption('Planning WO counts are unique open WOs by Plan-2026 current stage; Production WO counts are section records and may repeat the same WO. Planning weight is estimated net weight; Production is reported gross weight. Compare directionally only until the WO lists and cut-off dates match.')
        _cmpw=_wc.melt(id_vars=['Product Category'],value_vars=['Planning WIP t','Production WIP gross t'],var_name='Source measure',value_name='Weight t').dropna(subset=['Weight t'])
        if not _cmpw.empty:st.plotly_chart(px.bar(_cmpw,x='Product Category',y='Weight t',color='Source measure',barmode='group',title='Planning estimated net WIP vs Production gross WIP by category (t)'),use_container_width=True)
        st.dataframe(_wc,use_container_width=True,hide_index=True)
    st.info('How to read differences: compare only the same confirmed cut-off and matching process/category. Planning WIP is a planned remaining-quantity measure; Production WIP is a department-reported physical snapshot. A mismatch is a reconciliation item, not an automatic correction.')

if _page == 'kpi':
    from suite.planning_kpi import render as _render_planning_kpi
    _render_planning_kpi(st, DB, can_edit=hub_can_edit(), user=st.session_state.get('sl_user','Unknown'), language=lang, source_manager=SM)

if _page == 'cost':
    from suite.cost_kpi import render as _render_cost_kpi
    _render_cost_kpi(st, SM, user=st.session_state.get('sl_user','Unknown'), can_edit=hub_can_edit())

if _page == 'more':
    st.markdown('## More planning tools')
    _tool_links=[('back','🚨 Backorder'),('mps','🗓️ MPS'),('mrp','🧪 MRP'),('pack','📦 Packaging'),('capacity','⚖️ Capacity'),('newplan','🆕 New order'),('history','🕘 History'),('knowledge','📚 Knowledge'),('suite','🧰 Planning suite')]
    st.markdown('<div class="sl-tiles">'+''.join(f'<a href="{_hub_page_href(_p)}" target="_self">{_label}</a>' for _p,_label in _tool_links)+'</div>',unsafe_allow_html=True)
    st.caption('These tools stay one click away. Daily, Firing, Track and Files are on the top bar so the software stays small and fast.')

if _page == 'recovery_review':
    st.header('📄 Production Backorder Recovery Plan / แผนกู้คืนงานค้างส่งฝ่ายผลิต')
    st.caption('Production source status, reason/hold, proposed recovery date and WO-level comparison with the active Plan-2026. Original due dates remain separate.')
    st.info(f"Plan-2026 is the current, ongoing master. The Production recovery workbook is a dated activity snapshot, so its older backorders can outnumber today's overdue Plan-2026 list after dates, quantities, or closure status change. This page reconciles each WO as of {bkk_today():%d %b %Y}; a later Plan date is shown as a difference to verify, not assumed to be an authorized customer-date change.")
    def _active_src(sid):
        a=SM.active(sid)
        if a and Path(a.get('stored_path','')).is_file(): return Path(a['stored_path']),a
        p=_slot_published_path(sid)
        return (p,{}) if p and p.is_file() else (None,{})
    _rp,_rmeta=_active_src('RECOVERY_PLAN'); _salesp,_smeta=_active_src('SALES_PRODUCT_REGISTER'); _packp,_pmeta=_active_src('PACKAGING_STANDARD')
    for _lab,_path,_meta in [('Production recovery snapshot',_rp,_rmeta),('Sales product register',_salesp,_smeta),('Production packaging standard',_packp,_pmeta)]:
        if _path:
            st.caption(f"{_lab}: {_meta.get('original_name',_path.name)} · {('r'+str(_meta.get('revision_no'))) if _meta.get('revision_no') else 'saved source'} · imported {_meta.get('imported_at','time not recorded')}")
        else: st.warning(f'{_lab} is not loaded. Use “Update sources for this page” above; earlier revisions remain retained.')
    if _rp:
        try:
            from suite.recovery_product_review import read_recovery_snapshot
            _rec,_rec_sheets=read_recovery_snapshot(str(_rp))
            from suite.recovery_progress_page import render as _render_recovery_progress
            _render_recovery_progress(st, str(_rp))
            from suite.recovery_product_review import reconcile_recovery_to_plan
            _bridge,_plan_only=reconcile_recovery_to_plan(_rec,master,bo,bkk_today())
            from suite.recovery_product_review import recovery_unique_orders
            _rec_unique=recovery_unique_orders(_rec)
            _status_col='Recovery status (source)'
            _onplan=int(_rec_unique[_status_col].eq('ตามแผน').sum()) if not _rec_unique.empty else 0
            _behind=int(_rec_unique[_status_col].eq('ตกแผน').sum()) if not _rec_unique.empty else 0
            _conflict=int(_rec_unique[_status_col].str.contains('CONFLICT',na=False).sum()) if not _rec_unique.empty else 0
            _plan_open=int(_bridge.get('Plan status',pd.Series(dtype=str)).eq('OPEN').sum()) if not _bridge.empty else 0
            _plan_closed_positive=int((_bridge.get('Plan status',pd.Series(dtype=str)).eq('CLOSED') & pd.to_numeric(_bridge.get('Plan open balance (pcs)',pd.Series(dtype=float)),errors='coerce').fillna(0).gt(0)).sum()) if not _bridge.empty else 0
            _strict_overdue=int(bo['Work Order'].astype(str).nunique()) if isinstance(bo,pd.DataFrame) and not bo.empty and 'Work Order' in bo else 0
            _snapdates=pd.to_datetime(_rec.get('Recovery snapshot as-of date',pd.Series(dtype=object)),errors='coerce').dropna()
            if not _snapdates.empty:st.caption(f"Production recovery sheet snapshot date: {_snapdates.iloc[0]:%d %b %Y} · status is the source's Achieve by Item field (FQ). It is separate from today's strict Plan-2026 overdue rule.")
            st.subheader('Production recovery status vs current Plan-2026 / แผนกู้คืนฝ่ายผลิตเทียบ Plan ปัจจุบัน')
            _s1,_s2,_s3,_s4,_s5=st.columns(5)
            _s1.metric('Current Plan overdue WOs',f'{_strict_overdue:,}')
            _s2.metric('Production recovery WOs',f'{len(_rec_unique):,}')
            _s3.metric('Source says on plan / ตามแผน',f'{_onplan:,}')
            _s4.metric('Source says behind / ตกแผน',f'{_behind:,}')
            _s5.metric('Recovery WOs still open in Plan',f'{_plan_open:,}')
            _bridge_overdue=int(_bridge.get('Current overdue in Plan-2026',pd.Series(dtype=bool)).fillna(False).sum()) if not _bridge.empty else 0
            st.caption(f"Bridge: {_bridge_overdue:,} recovery-list WOs are overdue in current Plan-2026; {len(_plan_only):,} additional current Plan overdue WOs are absent from the Production recovery file. {_plan_closed_positive:,} WOs are marked CLOSED in Plan but still carry positive residual pcs for review.")
            if _conflict:st.warning(f'{_conflict:,} recovery WOs have conflicting on-plan/behind source rows; they are not counted as either status.')
            _wip_src=pd.to_numeric(_rec_unique.get('Recovery source WIP (unit not specified)',pd.Series(dtype=float)),errors='coerce')
            if _wip_src.notna().any():
                _behind_wip=pd.to_numeric(_rec_unique.loc[_rec_unique[_status_col].eq('ตกแผน'),'Recovery source WIP (unit not specified)'],errors='coerce')
                _onplan_wip=pd.to_numeric(_rec_unique.loc[_rec_unique[_status_col].eq('ตามแผน'),'Recovery source WIP (unit not specified)'],errors='coerce')
                st.caption(f"Recovery WIP field (unit not specified): behind-plan {_behind_wip.sum(min_count=1):,.0f}; on-plan {_onplan_wip.sum(min_count=1):,.0f}; all distinct WOs {_wip_src.sum(min_count=1):,.0f}. Do not compare this source field with Production WIP tonnes or Plan-2026 pcs.")
            _status_plot=_rec_unique.groupby(_status_col,dropna=False,as_index=False).agg(WOs=('_key','nunique')) if not _rec_unique.empty else pd.DataFrame()
            _cause_base=_rec_unique[_rec_unique[_status_col].isin(['ตกแผน','CONFLICT — inspect source rows'])].copy() if not _rec_unique.empty else pd.DataFrame()
            _cause_plot=_cause_base.groupby('Recovery reason / note',dropna=False,as_index=False).agg(WOs=('_key','nunique')).sort_values('WOs',ascending=False) if not _cause_base.empty else pd.DataFrame()
            _behind_rows=_rec_unique[_rec_unique[_status_col].eq('ตกแผน')] if not _rec_unique.empty else pd.DataFrame()
            _behind_no_reason=int(_behind_rows['Recovery reason / note'].eq('No reason recorded in source').sum()) if not _behind_rows.empty else 0
            _behind_with_reason=len(_behind_rows)-_behind_no_reason
            if not _status_plot.empty:
                _g1,_g2=st.columns(2)
                with _g1:st.plotly_chart(px.bar(_status_plot,x=_status_col,y='WOs',color=_status_col,title='Production source: recovery items on plan vs behind'),use_container_width=True)
                with _g2:
                    if not _cause_plot.empty:st.plotly_chart(px.bar(_cause_plot.head(12),x='WOs',y='Recovery reason / note',orientation='h',title='Recorded reasons / notes on behind-plan recovery WOs'),use_container_width=True)
                    else:st.info('No source reason/note is available for behind-plan items.')
            st.caption(f'Among {_behind:,} behind-plan WOs, {_behind_with_reason:,} have a recorded reason/note and {_behind_no_reason:,} have none in the source. Counts use distinct WOs; reason groups combine note and cause when both exist. “On plan” does not by itself prove warehouse receipt or customer delivery.')
            _rec_cols=[c for c in ['Work Order','Recovery status (source)','Recovery source WIP (unit not specified)','Recovery source order qty','Original due date','Production proposed date / hold','Recovery reason / note','Recovery rows','Recovery source row(s)','Recovery source cell references'] if c in _rec_unique]
            st.dataframe(_rec_unique[_rec_cols],use_container_width=True,hide_index=True,height=350)
            st.download_button('⬇ Download distinct Production recovery status and reasons',_rec_unique[_rec_cols].to_csv(index=False).encode('utf-8-sig'),'production_recovery_status_by_wo.csv','text/csv',key='recovery_status_reason_download')
            if not _bridge.empty:
                _both=int(_bridge['Current overdue in Plan-2026'].sum())
                _r1,_r2,_r3,_r4,_r5=st.columns(5)
                _r1.metric('Recovery snapshot WOs',f'{_bridge["_key"].nunique():,}')
                _r2.metric('Still overdue in current Plan',f'{_both:,}')
                _r3.metric('Recovery WOs not overdue now',f'{len(_bridge)-_both:,}')
                _r4.metric('Current Plan overdue total',f'{bo["Work Order"].nunique() if isinstance(bo,pd.DataFrame) and not bo.empty else 0:,}')
                _r5.metric('Plan overdue absent from snapshot',f'{len(_plan_only):,}')
                _bridge['_due_month']=pd.to_datetime(_bridge['Historical due date (Recovery)'],errors='coerce').dt.strftime('%Y-%m')
                _bridge_chart=_bridge.dropna(subset=['_due_month']).groupby(['_due_month','Reconciliation result'],as_index=False).agg(WOs=('_key','nunique'))
                if not _bridge_chart.empty:
                    _month_order=sorted(_bridge_chart['_due_month'].unique())
                    st.plotly_chart(px.bar(_bridge_chart,x='_due_month',y='WOs',color='Reconciliation result',barmode='stack',category_orders={'_due_month':_month_order},title='Production recovery snapshot WOs by historical due month and current Plan-2026 status'),use_container_width=True)
                st.caption('Interpretation: “Recovery only” does not mean the old delay never happened. It means this recovery snapshot WO is not in today’s strict overdue list; check whether the current Plan shows it closed, has no balance, has a later date, or is missing the WO. Production recovery rows are counted once per normalized WO; repeats remain visible in the source-row column.')
                _bridge_cols=['Recovery Work Order','Historical due date (Recovery)','Production proposed date / hold','Recovery result (source)','Recovery QTY (source)','Recovery WIP (source)','Current Plan due date','Plan status','Plan open balance (pcs)','Plan section / location','Current overdue in Plan-2026','Reconciliation result','Recovery source row(s)','Plan source row(s)','Recovery customer (source)','Recovery specification (source)','Recovery reason (source)','Recovery note (source)','Recovery source cell references','Recovery result source cell(s)']
                _bridge_cols=[c for c in _bridge_cols if c in _bridge]
                _bridge_view=_bridge[_bridge_cols].copy()
                _bridge_view=_bridge_view.rename(columns={'Recovery Work Order':'Work Order'})
                st.markdown('#### Work-order reconciliation / เทียบสถานะรายใบสั่งผลิต')
                st.dataframe(_bridge_view,use_container_width=True,hide_index=True,height=430)
                st.download_button('⬇ Download Plan vs Recovery reconciliation CSV',_bridge_view.to_csv(index=False).encode('utf-8-sig'),'plan_vs_production_recovery_reconciliation.csv','text/csv',key='recovery_plan_bridge_download')
                if not _plan_only.empty:
                    with st.expander(f'Current Plan overdue WOs not found in this Production snapshot ({len(_plan_only):,})'):
                        st.dataframe(_plan_only,use_container_width=True,hide_index=True,height=300)
                        st.download_button('⬇ Download Plan-only overdue WOs',_plan_only.to_csv(index=False).encode('utf-8-sig'),'plan_overdue_not_in_recovery_snapshot.csv','text/csv',key='plan_only_recovery_download')
            else:
                st.warning('No recovery work orders could be reconciled. Check that Plan-2026 and the dated Production recovery workbook are both loaded, and compare source WO formats.')
            _u=_rec.sort_values('Recovery Source Row').groupby('_key',as_index=False).agg(
                **{'Work Order':('Fac No','first'),'Recovery rows':('Fac No','size'),'Original Due Date':('Original Due Date',lambda x:x.dropna().iloc[0] if x.notna().any() and x.dropna().nunique()==1 else pd.NaT),
                   'Internal Recovery Date':('Internal Recovery Date',lambda x:x.dropna().iloc[0] if x.notna().any() and x.dropna().nunique()==1 else pd.NaT),
                   'Recovery status':('Recovery Result',lambda x:x.iloc[0] if x.nunique()==1 else 'CONFLICT — inspect source rows'),
                   'QTY source':('QTY',lambda x:x.dropna().iloc[0] if x.notna().any() and x.dropna().nunique()==1 else None),
                   'Reported warehouse QTY':('Reported Warehouse QTY (source unit)','max'),
                   'Customer':('Custumer','first'),'Spec':('Spec','first'),'Delay / reason':('สาเหตุที่ตกแผน','first')})
            _r1,_r2,_r3,_r4=st.columns(4)
            _r1.metric('Recovery source rows',f'{len(_rec):,}')
            _r2.metric('Distinct work orders',f'{_u["_key"].nunique():,}')
            _r3.metric('Repeated WO keys',f'{int((_u["Recovery rows"]>1).sum()):,}')
            _r4.metric('Status conflicts',f'{int(_u["Recovery status"].str.startswith("CONFLICT").sum()):,}')
            _u['Due month']=pd.to_datetime(_u['Original Due Date'],errors='coerce').dt.strftime('%Y-%m')
            _month=_u.dropna(subset=['Due month']).groupby(['Due month','Recovery status'],as_index=False).agg(WOs=('Work Order','nunique'))
            if not _month.empty:
                _months=sorted(_month['Due month'].unique())
                st.plotly_chart(px.bar(_month,x='Due month',y='WOs',color='Recovery status',barmode='stack',category_orders={'Due month':_months},title='Distinct recovery WOs by original due month and source result'),use_container_width=True)
            st.caption('Duplicate WO rows are retained below. Headline WOs are distinct keys; dates and quantities are only rolled up when duplicate rows agree. Warehouse quantity is shown in the source unit because the workbook does not label a consistent unit.')
            _cols=[c for c in ['Recovery Source Row','Fac No','Custumer','Spec','QTY','Wip','Original Due Date','Internal Date / Hold Status','Recovery Result','Reported Warehouse QTY (source unit)','Recovery reason (source)','Recovery note (source)','Recovery source cell references','Duplicate WO Rows','Duplicate WO Review'] if c in _rec]
            st.dataframe(_rec[_cols],use_container_width=True,hide_index=True,height=440)
            st.download_button('⬇ Download recovery detail CSV',_rec[_cols].to_csv(index=False).encode('utf-8-sig'),'recovery_snapshot_detail.csv','text/csv',key='recovery_snapshot_download')
            with st.expander('Snapshot validation and coverage'):
                st.write({'Sheets in source':_rec_sheets,'Repeated source rows':int((_rec['Duplicate WO Rows']>1).sum()),'Distinct WOs':int(_rec['_key'].nunique()),'Rows with original due date':int(_rec['Original Due Date'].notna().sum()),'Rows with internal recovery date':int(_rec['Internal Recovery Date'].notna().sum()),'Internal hold/status text rows':int(_rec['Internal Date / Hold Status'].str.strip().ne('').sum())})
                st.caption('Text values such as “รอแผนขาย”, “NCR”, or “รอปรับแผน” remain hold/status values, never dates. The page does not call a WO “Production accepted” unless an explicit approval field exists.')
        except Exception as _e: st.error(f'Recovery snapshot could not be analyzed: {_e}')
    if _salesp and _packp:
        try:
            from suite.recovery_product_review import compare_product_masters
            _cmp,_prod=compare_product_masters(str(_salesp),str(_packp))
            _distinct=_cmp.sort_values('Sales Source Row').drop_duplicates('Product Code')
            _s1,_s2,_s3,_s4=st.columns(4)
            _s1.metric('Sales register rows',f'{len(_cmp):,}')
            _s2.metric('Distinct Sales codes',f'{_cmp["Product Code"].nunique():,}')
            _s3.metric('Production standard rows / codes',f'{len(_prod):,} / {_prod["Product Code"].nunique():,}')
            _s4.metric('Exact codes shared',f'{int(_distinct["Production Source Row"].notna().sum()):,}')
            _status=_distinct['Comparison'].value_counts().rename_axis('Comparison').reset_index(name='Products')
            st.plotly_chart(px.bar(_status,x='Comparison',y='Products',color='Comparison',title='Sales registration vs Production packaging standard — code/pack check'),use_container_width=True)
            st.caption('Sales register = registered product/code, customer-facing description, brand and registered pack quantity. Production standard = packing quantity and shop-floor packing material instructions. Each stays an independent revision; mismatches require review and are not auto-corrected.')
            _filter=st.multiselect('Show comparison status',sorted(_distinct['Comparison'].dropna().unique()),default=sorted(_distinct['Comparison'].dropna().unique()),key='recovery_product_compare_filter')
            _show=_cmp[_cmp['Comparison'].isin(_filter)]
            st.dataframe(_show,use_container_width=True,hide_index=True,height=420)
            st.download_button('⬇ Download product master comparison CSV',_show.to_csv(index=False).encode('utf-8-sig'),'sales_vs_production_product_master.csv','text/csv',key='product_master_compare_download')
        except Exception as _e: st.error(f'Product master comparison could not be completed: {_e}')
if _page == 'back':
    st.header('🚨 Past-due Backorders / งานค้างส่งเกินกำหนด')
    st.markdown(f"<a href='{_hub_page_href('recovery_review')}' target='_self' style='font-size:.9rem;color:#0057b8;text-decoration:underline'>↗ Open Production Recovery Plan — accepted status, hold reasons, proposed recovery dates & WO detail</a>",unsafe_allow_html=True)
    st.caption(f"As of {bkk_today():%d %b %Y} (Phan Thong, Chonburi): revised delivery date (Plan-2026 E), falling back to initial date (C); open pcs = QTY − Packing Actual; whole-WO closed = EU or FC. Due today/future orders are not backorders.")
    st.caption('Plan-2026 overdue WOs and the dated Production recovery status are separate views. Use Recovery Analysis to compare the two; use Weekly Recovery Plan to prepare actions.')
    _b1,_b2=st.columns(2)
    if _b1.button('📄 Production Recovery Plan — status, reasons and WO detail',key='open_production_recovery_analysis',type='primary'):
        st.query_params['page']='recovery_review';st.rerun()
    if _b2.button('🧯 Weekly Recovery Action Plan', key='open_weekly_recovery_from_backorder'):
        st.query_params['page']='daily_recovery'
        st.rerun()
    if master is None:st.warning('Load Plan-2026 in SOURCES first.')
    else:
        if bo is None or bo.empty:
            st.success(f"No past-due open work orders as of {bkk_today():%d %b %Y}.")
        else:
            st.metric('Overdue open work orders / จำนวน WO ค้างส่ง',f"{bo['Work Order'].astype(str).nunique():,} · {pd.to_numeric(bo['pcs'],errors='coerce').fillna(0).sum():,.0f} pcs")
            _overdue=bo.copy();_overdue['Product Category']=_overdue.get('Product Category','').astype(str).str.upper().str.strip().replace({'F':'P','':'UNKNOWN'})
            _overdue['Due Month']=pd.to_datetime(_overdue['Due Date'],errors='coerce').dt.to_period('M').astype(str)
            _overdue=_overdue.dropna(subset=['Due Date'])
            _og=_overdue.groupby(['Due Month','Product Category'],as_index=False).agg(**{'Qty pcs':('pcs','sum'),'Weight ton':('ton','sum'),'WOs':('Work Order','nunique')})
            if not _og.empty:
                _past_months=sorted(_og['Due Month'].dropna().astype(str).unique(),key=lambda x:pd.Period(x,freq='M'))
                _of=px.bar(_og,x='Due Month',y='Qty pcs',color='Product Category',barmode='stack',title='Past-due open quantity by original due month · future orders excluded',text_auto='.0f',category_orders={'Due Month':_past_months})
                _of.update_xaxes(type='category',categoryorder='array',categoryarray=_past_months,tickangle=-45)
                st.plotly_chart(_of,use_container_width=True)
                editable_table(_og,'backorder_monthly','Backorder_Open_Overdue_Monthly',350)
            st.subheader('Overdue OPEN work orders / WO เปิดที่เกินกำหนด')
            editable_table(bo[[c for c in ['Work Order','Customer','Product Code','Product Category','Size','Section','pcs','ton','Due Date','Late days'] if c in bo]],'backorder_open_detail','Backorder_Open_Detail',500)
        # Future due work is useful demand information, but is deliberately kept out
        # of the past-due backorder chart and recovery count.
        _asof=pd.Timestamp(bkk_today()).normalize()
        _future=op[pd.to_datetime(op.get('Due Date'),errors='coerce').ge(_asof)].copy() if op is not None and not op.empty else pd.DataFrame()
        if not _future.empty:
            with st.expander('Due today / future open demand — not backorders / งานเปิดกำหนดวันนี้และอนาคต — ไม่นับเป็นงานค้าง',expanded=False):
                _future['Due Month']=pd.to_datetime(_future['Due Date'],errors='coerce').dt.to_period('M').astype(str)
                _future_g=_future.groupby(['Due Month','Product Category'],as_index=False).agg(WOs=('Work Order','nunique'),pcs=('pcs','sum'),ton=('ton','sum'))
                _future_g=_future_g.sort_values('Due Month')
                _ff=px.bar(_future_g,x='Due Month',y='pcs',color='Product Category',barmode='stack',title='Future open orders by due month · demand outlook only')
                _ff.update_xaxes(type='category',categoryorder='array',categoryarray=sorted(_future_g['Due Month'].astype(str).unique(),key=lambda x:pd.Period(x,freq='M')))
                st.plotly_chart(_ff,use_container_width=True)
                st.dataframe(_future_g,use_container_width=True,hide_index=True)
if _page == 'mps':
    st.header('🗓️ MPS — open demand by due period + category')
    if op is None:st.warning('Load Plan-2026 in SOURCES first.')
    else:
        _m1,_m2,_m3,_m4=st.columns(4)
        _m1.metric('Open WOs',int(op['Work Order'].nunique()) if 'Work Order' in op.columns else len(op))
        _m2.metric('Open pcs',f"{float(op['pcs'].sum()):,.0f}" if 'pcs' in op.columns else '—')
        _m3.metric('Open ton',f"{float(op['ton'].sum()):,.2f}" if 'ton' in op.columns else '—')
        _m4.metric('Due months',int(op['Due Date'].dt.to_period('M').nunique()) if 'Due Date' in op.columns else 0)
        x=op.copy();x['Due Month']=x['Due Date'].dt.strftime('%Y-%m');g=x.groupby(['Due Month','Product Category'],dropna=False).agg(WOs=('Work Order','nunique'),pcs=('pcs','sum'),ton=('ton','sum')).reset_index();st.plotly_chart(px.bar(g,x='Due Month',y='pcs',color='Product Category',barmode='stack',title='MPS open requirement — pcs',text_auto='.0f'),use_container_width=True);st.plotly_chart(px.bar(g,x='Due Month',y='ton',color='Product Category',barmode='stack',title='MPS open requirement — tonnes',text_auto='.2f'),use_container_width=True);st.dataframe(display_df(g),use_container_width=True,hide_index=True)
if _page == 'material':
    st.header('📦 Stock-on-Hand Material Status / สถานะวัตถุดิบคงคลัง')
    st.caption('This page reads the active shared Stock on Hand workbook directly. It does not run or rebuild the Daily Plan. Stock status and work-order material feasibility are separate checks.')
    _stock_file=fp('Stock-on-Hand-LATEST.xlsx')
    if not _stock_file:
        st.warning('No active Stock on Hand workbook is loaded. Use “Update sources for this page” above to upload it once; other pages will reuse the same revision.')
    else:
        try:
            _daily_engine_dir=ROOT/'apps'/'daily'
            if str(_daily_engine_dir) not in sys.path:sys.path.insert(0,str(_daily_engine_dir))
            import sl_mps_mrp_engine_v2_4 as _stock_engine
            with st.spinner('Reading the active Stock on Hand source…'):
                _material_stock=_stock_engine.parse_stock(Path(_stock_file).read_bytes()).copy()
            _stock_meta=SM.active('STOCK_ON_HAND') or {}
            _source_name=_stock_meta.get('original_name') or Path(_stock_file).name
            _source_revision=_stock_meta.get('revision_no')
            _source_imported=_stock_meta.get('imported_at') or 'Import time not recorded'
            _source_sha=_stock_meta.get('sha256') or ''
            st.caption(f"Source workbook: {_source_name} · Revision {('r'+str(_source_revision)) if _source_revision else 'existing file'} · Imported {_source_imported}"+(f" · SHA-256 {_source_sha[:16]}…" if _source_sha else ''))
            st.info('The import timestamp identifies when this software received the workbook; it is not assumed to be the stock-count date. Check the workbook’s own report date before acting.')
            # Render the two familiar graphs before the evidence table; reuse the page's already parsed DataFrame.
            _graph_all=st.toggle('Show every material on the graph / แสดงวัตถุดิบทั้งหมด',value=False,key='material_graph_all_rc31')
            _graph_stock=_material_stock.copy()
            for _gc in ['Order on Hand g','Physical Stock g','Waiting to Receive g','Under Test g','Balance Stock g']:
                _graph_stock[_gc]=pd.to_numeric(_graph_stock.get(_gc,0),errors='coerce').fillna(0)
            _graph_stock['Display']=_graph_stock['Material'].fillna('').astype(str)+' | '+_graph_stock['Material Name'].fillna('').astype(str)
            _graph_stock['Shortage t']=(-_graph_stock['Balance Stock g']).clip(lower=0)/1e6
            if not _graph_all and len(_graph_stock)>40:
                _graph_stock=_graph_stock.sort_values(['Shortage t','Order on Hand g'],ascending=[False,False]).head(40)
                st.caption('Graph shows the 40 highest shortage/order materials for readability and speed. Turn on the option above for every material; the table and download retain all rows.')
            import plotly.graph_objects as _go
            _material_fig=_go.Figure()
            _material_fig.add_bar(x=_graph_stock['Display'],y=_graph_stock['Order on Hand g']/1e6,name='Order on Hand',offsetgroup='orders',marker_color='#315fce',hovertemplate='%{x}<br>Order on Hand: %{y:.3f} t<extra></extra>')
            for _col,_label,_color in [('Physical Stock g','Stock in Hand','#ef5141'),('Waiting to Receive g','Under Receiving','#04b894'),('Under Test g','Under Test','#a34df4')]:
                _material_fig.add_bar(x=_graph_stock['Display'],y=_graph_stock[_col]/1e6,name=_label,offsetgroup='supply',marker_color=_color,hovertemplate='%{x}<br>'+_label+': %{y:.3f} t<extra></extra>')
            _supply_total=(_graph_stock['Physical Stock g']+_graph_stock['Waiting to Receive g']+_graph_stock['Under Test g'])/1e6
            _material_fig.add_scatter(x=_graph_stock['Display'],y=_supply_total,mode='markers+text',text=[f'{v:.2f}' for v in _supply_total],textposition='top center',name='Total Supply',marker={'color':'#ff9d3d','size':7},hovertemplate='%{x}<br>Total supply: %{y:.3f} t<extra></extra>')
            _material_fig.update_layout(barmode='stack',title='Material-level stock position — hover for exact values',yaxis_title='Tonnes',xaxis_tickangle=-55,hovermode='x unified',height=max(520,min(850,420+len(_graph_stock)*3)),legend_title='Stock component',margin={'l':35,'r':20,'t':75,'b':150})
            st.plotly_chart(_material_fig,use_container_width=True,config={'displaylogo':False})
            _stock_by_sheet=_material_stock.groupby('Stock Source Sheet',as_index=False)[['Physical Stock g','Order on Hand g','Waiting to Receive g','Under Test g','Balance Stock g']].sum(min_count=1)
            _sheet_fig=_go.Figure()
            _sheet_fig.add_bar(x=_stock_by_sheet['Stock Source Sheet'],y=_stock_by_sheet['Order on Hand g']/1e6,name='Order on Hand',offsetgroup='orders',marker_color='#315fce')
            for _col,_label,_color in [('Physical Stock g','Stock in Hand','#ef5141'),('Waiting to Receive g','Under Receiving','#04b894'),('Under Test g','Under Test','#a34df4')]:
                _sheet_fig.add_bar(x=_stock_by_sheet['Stock Source Sheet'],y=_stock_by_sheet[_col]/1e6,name=_label,offsetgroup='supply',marker_color=_color)
            _sheet_supply=(_stock_by_sheet['Physical Stock g']+_stock_by_sheet['Waiting to Receive g']+_stock_by_sheet['Under Test g'])/1e6
            _sheet_fig.add_scatter(x=_stock_by_sheet['Stock Source Sheet'],y=_sheet_supply,mode='markers+text',text=[f'{v:.2f} t' for v in _sheet_supply],textposition='top center',name='Total Supply',marker={'color':'#ff9d3d','size':8})
            _sheet_fig.update_layout(barmode='stack',title='Stock position by controlled source sheet',yaxis_title='Tonnes',hovermode='x unified',height=420,legend_title='Stock component')
            st.plotly_chart(_sheet_fig,use_container_width=True,config={'displaylogo':False})
            _bal=pd.to_numeric(_material_stock.get('Balance Stock g',pd.Series(0,index=_material_stock.index)),errors='coerce').fillna(0)
            _order=pd.to_numeric(_material_stock.get('Order on Hand g',pd.Series(0,index=_material_stock.index)),errors='coerce').fillna(0)
            _status=_material_stock.get('Stock Status',pd.Series('',index=_material_stock.index)).astype(str).str.upper()
            _m1,_m2,_m3,_m4,_m5=st.columns(5)
            _m1.metric('Material records',f'{len(_material_stock):,}')
            _m2.metric('Shortage',f'{int((_bal<0).sum()):,}')
            _m3.metric('Zero / urgent',f'{int(((_bal==0)&(_order>0)).sum()):,}')
            _m4.metric('Watch',f'{int(_status.eq("WATCH").sum()):,}')
            _m5.metric('OK',f'{int(_status.eq("OK").sum()):,}')
            _filter1,_filter2=st.columns([1,2])
            _status_filter=_filter1.selectbox('Status filter', ['All','SHORTAGE','ZERO / URGENT','WATCH','OK'], key='material_status_filter')
            _find_material=_filter2.text_input('Find material code or name',key='material_status_search',placeholder='Type material code or description')
            _view=_material_stock.copy()
            if _status_filter!='All':_view=_view[_view['Stock Status'].astype(str).str.upper()==_status_filter]
            if _find_material.strip():
                _q=re.escape(_find_material.strip())
                _mask=_view['Material'].fillna('').astype(str).str.contains(_q,case=False,regex=True,na=False)|_view['Material Name'].fillna('').astype(str).str.contains(_q,case=False,regex=True,na=False)
                _view=_view[_mask]
            _status_rank={'SHORTAGE':0,'ZERO / URGENT':1,'WATCH':2,'OK':3}
            _view['_status_order']=_view['Stock Status'].astype(str).str.upper().map(_status_rank).fillna(9)
            _view=_view.sort_values(['_status_order','Balance Stock g','Material'],ascending=[True,True,True]).drop(columns=['_status_order'])
            _display_cols=[c for c in ['Stock Status','Material','Material Name','Type','Order on Hand g','Physical Stock g','Waiting to Receive g','Under Test g','Balance Stock g','Stock Source Sheet','Stock Source Row','Stock Source Column','Stock Source Unit'] if c in _view.columns]
            st.caption(f"Showing {_view.shape[0]:,} of {_material_stock.shape[0]:,} material records · balances are displayed in the source unit (grams). Each row names its source sheet and balance column.")
            st.dataframe(_view[_display_cols],use_container_width=True,hide_index=True,height=520)
            _export=_view[_display_cols].copy()
            _export.insert(0,'Source workbook',_source_name)
            _export.insert(1,'Source revision',_source_revision or 'existing file')
            _export.insert(2,'Imported at',_source_imported)
            _export.insert(3,'Source SHA-256',_source_sha)
            st.download_button('⬇ Download material status CSV',_export.to_csv(index=False).encode('utf-8-sig'),f"Stock_On_Hand_Status_{bkk_today():%Y%m%d}.csv",'text/csv',key='material_status_export')
            st.caption('Status rule: SHORTAGE = negative source balance; ZERO / URGENT = zero balance with open-order quantity; WATCH = positive balance below 25% of open-order quantity; OK = other positive balance. This screening does not confirm a WO-specific BOM, need date, or reservation.')
        except Exception as _material_error:
            st.error(f'Could not read the active Stock on Hand workbook: {_material_error}')
            st.caption(f'Active source: {Path(_stock_file).name} · Update it from the source panel above if the workbook is revised or its controlled sheet layout changed.')

if _page == 'mrp':
    st.header('🧪 Material MRP — actual codes only / MRP วัตถุดิบ')
    if raw is None:st.warning('Load Plan-2026 in SOURCES first.')
    else:
        mat,pairs=material_mrp(raw); st.caption('Detected Plan material columns: '+(', '.join(f'{a}/{b}' for a,b in pairs) if pairs else 'NONE'))
        if mat.empty: st.error('No material demand calculated. The diagnostic above shows whether material-code/gram columns were detected.')
        else:
            tot=mat.groupby('Material Code',as_index=False)['Required kg'].sum().sort_values('Required kg',ascending=False);stock=fp('Stock-on-Hand-LATEST.xlsx')
            if stock:
                try:
                    a=pd.read_excel(stock,sheet_name='Abrasive').rename(columns={'รหัสสินค้า':'Material Code','รายละเอียดสินค้า':'Description','วัตถุดิบคงคลัง':'Stock kg','รอวัถุดิบเข้า':'Incoming kg','รอผลLAB':'LAB kg'});a['Material Code']=a['Material Code'].astype(str).str.strip();tot['Material Code']=tot['Material Code'].astype(str).str.strip();tot=tot.merge(a[[c for c in ['Material Code','Description','Stock kg','Incoming kg','LAB kg'] if c in a]].drop_duplicates('Material Code'),on='Material Code',how='left')
                except Exception as e:st.warning(f'Stock diagnostic: {e}')
            for c in ['Stock kg','Incoming kg','LAB kg']:
                if c not in tot:tot[c]=0
                tot[c]=pd.to_numeric(tot[c],errors='coerce').fillna(0)
            tot['Hard shortage kg']=(tot['Required kg']-tot['Stock kg']-tot['Incoming kg']).clip(lower=0);tot['Shortage if LAB passes kg']=(tot['Required kg']-tot['Stock kg']-tot['Incoming kg']-tot['LAB kg']).clip(lower=0)
            _req='Required kg'
            if _req not in tot.columns: tot[_req]=0.0
            st.metric('Calculated material demand',f"{pd.to_numeric(tot[_req],errors='coerce').fillna(0).sum():,.1f} kg")
            edited_mrp=_persistent_data_editor(editor_view(tot),use_container_width=True,hide_index=True,height=520,num_rows='dynamic',key='mrp_editor',disabled=not hub_can_edit(),column_config=editor_column_config(tot))
            if _req in edited_mrp.columns:
                _mg=edited_mrp.copy();_mg[_req]=pd.to_numeric(_mg[_req],errors='coerce').fillna(0)
                st.plotly_chart(px.bar(_mg.sort_values(_req,ascending=False).head(30),x='Material Code',y=_req,title='Top material requirements — kg',text_auto='.0f'),use_container_width=True)
            c1,c2=st.columns(2);
            with c1:
                if hub_can_edit() and st.button('💾 SAVE MRP CHANGES',use_container_width=True): save_editable(edited_mrp,'Material_MRP_Editable',st.session_state.get('sl_user',''),st.session_state.get('sl_section',''));st.success('MRP changes saved; graph uses edited values immediately.')
            with c2: st.download_button('⬇ DOWNLOAD EDITED MRP',to_xlsx_bytes(edited_mrp,'Material MRP'),'Material_MRP_Editable.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True);st.download_button('⬇ Material MRP trace CSV',mat.to_csv(index=False).encode('utf-8-sig'),'SL_MRP_TRACE.csv','text/csv')
if _page == 'pack':
    st.markdown("<div style='padding:12px 18px;border-left:6px solid #e76613;background:#fff6ed;border-radius:10px'><h2 style='margin:0;color:#12395b'>📦 Packaging Plan / แผนบรรจุภัณฑ์</h2></div>",unsafe_allow_html=True)
    st.caption('Due dates come from the shared Plan-2026. Default packaging comes from the latest Packaging Standard; missing standards may use a same-size alternative selected by Planning.')
    if op is None:st.warning('Load Plan-2026 first.')
    else:
        det,req=packaging_plan(op)
        if det.empty:st.warning('Packaging standard could not be matched to current open Plan-2026 products.')
        else:
            # Offer same-size matched standards when exact product code is missing.
            det['Packaging Choice']=np.where(det.get('Pcs/Box').notna(),'STANDARD — exact product','SELECT SAME-SIZE / MANUAL');det['Selected Packaging Product Code']=np.where(det.get('Pcs/Box').notna(),det.get('Product Code',det.get('Product Source','')).astype(str),'')
            matched=det['Pcs/Box'].notna().sum();c1,c2,c3=st.columns(3);c1.metric('Open WOs',len(det));c2.metric('Standard matched',matched);c3.metric('Needs choice',len(det)-matched)
            det['Include']=True
            if hub_can_edit() and st.button('⚡ APPLY SAME-SIZE PACKAGING TO ALL UNMATCHED',use_container_width=True):
                try:
                    _dims=[c for c in ['D','T','H'] if c in det.columns]
                    if len(_dims)>=2 and 'Pcs/Box' in det.columns:
                        _matched=det[det['Pcs/Box'].notna()].copy();_unmatched=det['Pcs/Box'].isna()
                        _pc='Product Code' if 'Product Code' in det.columns else ('Product Source' if 'Product Source' in det.columns else None)
                        if _pc and not _matched.empty:
                            for _c in _dims:
                                _matched[_c]=pd.to_numeric(_matched[_c],errors='coerce').round(3);det[_c]=pd.to_numeric(det[_c],errors='coerce').round(3)
                            _map=_matched.dropna(subset=_dims).drop_duplicates(_dims).set_index(_dims)[_pc].astype(str).to_dict()
                            def _same(r):
                                try:return _map.get(tuple(r[c] for c in _dims),'')
                                except:return ''
                            det.loc[_unmatched,'Selected Packaging Product Code']=det.loc[_unmatched].apply(_same,axis=1)
                            _ok=_unmatched & det['Selected Packaging Product Code'].astype(str).str.strip().ne('')
                            det.loc[_ok,'Packaging Choice']='SAME-SIZE alternative'
                            st.success(f'Same-size packaging applied to {int(_ok.sum())} unmatched row(s) using D/T/H from already controlled matched products. Untick Include for exceptions.')
                        else: st.info('No controlled matched product is available to supply a same-size packaging reference.')
                    else: st.info('D/T/H size fields are not available for controlled same-size matching.')
                except Exception as _e: st.warning(f'Same-size matching diagnostic: {_e}')
            _pcfg={'Packaging Choice':st.column_config.SelectboxColumn('Packaging Choice',options=['STANDARD — exact product','SAME-SIZE alternative','MANUAL packaging']),'Selected Packaging Product Code':st.column_config.TextColumn('Selected Packaging Product Code'),'Include':st.column_config.CheckboxColumn('Include in plan')}
            ped=_persistent_data_editor(editor_view(det),use_container_width=True,hide_index=True,height=470,num_rows='dynamic',key='pack_editor',disabled=not hub_can_edit(),column_config=editor_column_config(det,_pcfg))
            if 'Include' in ped.columns: ped=ped[ped['Include'].fillna(True)].copy()
            # Graph responds to edited table.
            if 'Due Date' in ped and 'Boxes Required' in ped:
                pg=ped.copy();pg['Due Date']=pd.to_datetime(pg['Due Date'],errors='coerce');pg['Due Date']=pg['Due Date'].dt.strftime('%Y-%m-%d');pg['Boxes Required']=pd.to_numeric(pg['Boxes Required'],errors='coerce').fillna(0);pg=pg.groupby('Due Date',as_index=False)['Boxes Required'].sum();st.plotly_chart(px.bar(pg,x='Due Date',y='Boxes Required',title='Packaging boxes required by due date'),use_container_width=True)
            c1,c2=st.columns(2)
            with c1:
                if hub_can_edit() and st.button('💾 SAVE PACKAGING PLAN',use_container_width=True):save_editable(ped,'Packaging_Plan_Editable',st.session_state.get('sl_user',''),st.session_state.get('sl_section',''));st.success('Packaging plan saved. Graph uses edited values.')
            with c2:st.download_button('⬇ DOWNLOAD PACKAGING PLAN',to_xlsx_bytes(ped,'Packaging Plan'),'Packaging_Plan_Editable.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
            if not req.empty:
                rr=req.groupby('Packaging Code',as_index=False)['Required Qty'].sum().sort_values('Required Qty',ascending=False);st.subheader('Packaging material requirement');editable_table(rr,'pack_material','Packaging_Material_Requirement',360)
if _page == 'src':
    st.markdown("<div style='padding:12px 18px;border-left:6px solid #e76613;background:#fff6ed;border-radius:10px'><h2 style='margin:0;color:#12395b'>📁 Active Files & Sources</h2></div>",unsafe_allow_html=True)
    st.header('📥 Shared Sources + QR / แหล่งข้อมูลส่วนกลาง + QR')
    from suite.source_manager_page import render as _render_sm
    _render_sm(SM,st.session_state.get('sl_user',''),hub_can_edit(),'smgr')
    st.divider()
    st.info('Home loads Plan-2026 first. Other inputs can be added or replaced from the page that uses them; active copies are shared and revisioned. Product register and training files are in Knowledge / F1.')
    with st.expander('📤 Extra specialist uploads / อัปโหลดไฟล์พิเศษ', expanded=False):
        st.session_state['upload_context']='Sources tab'
        st.caption('Product register (11 / 18 digit) and training PDFs/PPTX stay in Knowledge. Only P280526 or a revised field mapping belongs here.')
        _p280=fp('P280526-LATEST.xlsx');_p280m=_load_registry().get('P280526-LATEST.xlsx',{})
        st.caption(('P280526: '+(_p280m.get('original_name') or 'loaded')) if _p280 else 'P280526: not loaded — upload here if needed')
        _p280u=st.file_uploader('P280526 / SD Recipe Master (not on Home)',type=['xlsx','xlsm'],key='src_sd')
        if _p280u is not None:
            _p280_saved=archive_and_save(_p280u,'P280526-LATEST.xlsx')
            if _p280_saved is not None:st.success(f'Stored P280526 from {_p280u.name}')
        st.markdown('### 🗺️ Plan-2026 field mapping')
        st.caption('V16 uses your Row_3_Thai_English_Cell_Mapping. Upload a revised mapping only if you change the mapping.')
        _mapu=st.file_uploader('Replace field mapping (optional)',type=['xlsx'],key='src_mapping')
        if _mapu is not None and not _upload_seen(_mapu,'archive:Row_3_Thai_English_Cell_Mapping-LATEST.xlsx'):
            _mp=DATA/'Row_3_Thai_English_Cell_Mapping-LATEST.xlsx';_mp.write_bytes(_mapu.getbuffer());register_source(_mp.name,_mp,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),_mapu.name,'Sources tab');_mark_upload_seen(_mapu,'archive:Row_3_Thai_English_Cell_Mapping-LATEST.xlsx');st.success('Revised mapping saved in software.')

    st.subheader('Plan-2026 customer names / ชื่อลูกค้า')
    st.caption('ไทย = original Customername from Plan-2026 (same script as the workbook). English = English/Latin only.')
    if plan:
        try:
            if raw is not None and {'ProductionCode','Customername'}.issubset(set(getattr(raw,'columns',[]))):
                _keep=[c for c in ['ProductionCode','Customername','CustomernameID'] if c in raw.columns]
                _pr=raw[_keep].dropna(subset=['ProductionCode']).copy()
            else:
                _pr=pd.read_excel(plan,sheet_name='แผนการเผา',header=2,usecols=lambda c: c in ['ProductionCode','Customername','CustomernameID'])
                _pr=_pr.dropna(subset=['ProductionCode']).copy()
            _pr=_pr.rename(columns={'ProductionCode':'Work Order','Customername':'Customer','CustomernameID':'Customer ID'})
            st.dataframe(display_df(_pr.head(500)),use_container_width=True,height=360)
        except Exception as e: st.warning(f'Customer-name preview diagnostic: {e}')

    st.subheader('ACTIVE FILE REGISTRY — one source used by complete software')
    _reg=_load_registry()
    _rows=[]
    for _k,_v in _reg.items(): _rows.append({'Source':_k,'Active server file':_v.get('active_path'),'Original filename':_v.get('original_name'),'Excel document modified':_v.get('excel_document_modified_at'),'Stored copy modified':_v.get('stored_file_modified_at'),'Registered':_v.get('registered_at'),'Uploaded through':_v.get('uploaded_through'),'By':_v.get('updated_by'),'Department':_v.get('section')})
    if _rows: st.dataframe(pd.DataFrame(_rows),use_container_width=True,hide_index=True)
    else: st.info(f'Central data location: {DATA}')
    _conf=source_conflicts()
    if not _conf.empty:
        st.error('⚠ A DIFFERENT OLD COPY EXISTS. Only the CENTRAL active file is used. Identical copies are hidden and are not treated as conflicts.')
        st.dataframe(_conf,use_container_width=True,hide_index=True)
    else: st.success('No duplicate-source conflict detected in the checked program locations.')

    st.subheader('Shared edits / audit overrides')
    _aud=override_audit()
    if _aud.empty: st.info('No software edits registered yet.')
    else: st.dataframe(_aud.head(1000),use_container_width=True,hide_index=True,height=320)
    if plan:
        if st.button('🧩 BUILD UPDATED PLAN-2026 FROM SOURCE + SAVED EDITS',use_container_width=True):
            try:
                _up=export_updated_plan(plan);st.session_state['updatedplan']=str(_up);st.success(f'Controlled revised Plan created: {_up.name}')
            except Exception as _e: st.error(f'Updated Plan diagnostic: {_e}')
        _up=Path(st.session_state.get('updatedplan','')) if st.session_state.get('updatedplan') else None
        if _up and _up.exists(): st.download_button('⬇ DOWNLOAD UPDATED PLAN-2026',_up.read_bytes(),_up.name,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)

    st.subheader('Current shared sources')
    for _,target,_ in HOME_SOURCE_FILES:
        p=fp(target);st.write(('✅' if p else '❌'),target,(f'— {datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}' if p else '— not loaded'))
    c1,c2=st.columns(2)
    with c1:
        st.markdown("<div id='qr-label-generator'></div>",unsafe_allow_html=True)
        st.markdown('#### 🔳 Work Order QR Labels')
        st.caption('Active Plan-2026 only · QR encodes SLWO:<WO> · uppercase WO is printed beneath it on the same label')
        from suite.qr_labels import rows_from_plan_frame, filter_open_plan_rows
        _qrbase=rows_from_plan_frame(master)
        _qf1,_qf2,_qf3=st.columns([1,1.1,1.15])
        _qrstatus=_qf1.selectbox('Order status',['Open orders','Closed orders','All orders'],key='qr_status_filter')
        _sections=['All sections']+sorted({str(r.get('section') or 'Unassigned') for r in _qrbase})
        _qrsection=_qf2.selectbox('Plan section / location',_sections,key='qr_section_filter')
        _qrdatefield=_qf3.selectbox('Date filter',['Current due date','WO creation date'],key='qr_date_field')
        _qrdkey='due_date' if _qrdatefield=='Current due date' else 'order_date'
        _qrpool=filter_open_plan_rows(_qrbase,_qrsection,status_filter=_qrstatus,date_field=_qrdkey)
        _qrdates=[]
        for _r in _qrpool:
            _d=pd.to_datetime(_r.get(_qrdkey),errors='coerce')
            if pd.notna(_d):_qrdates.append(_d.date())
        _qmin=min(_qrdates) if _qrdates else bkk_today();_qmax=max(_qrdates) if _qrdates else bkk_today()
        # The date picker must not collapse to the only due date in the source
        # (or to today when the source has no parseable dates). Keep a broad
        # calendar range so users can query past-due and future dates; the
        # result itself remains restricted to open WOs in the active Plan-2026.
        _qr_picker_min=date(2000,1,1);_qr_picker_max=date(2100,12,31)
        _qdf,_qdt=st.columns(2)
        _qrf=_qdf.date_input(f'{_qrdatefield} from',value=_qmin,min_value=_qr_picker_min,max_value=_qr_picker_max,key='qr_due_from')
        _qrt=_qdt.date_input(f'{_qrdatefield} to',value=_qmax,min_value=_qr_picker_min,max_value=_qr_picker_max,key='qr_due_to')
        if _qrt<_qrf:_qrf,_qrt=_qrt,_qrf
        _qr_undated=st.checkbox('Include orders without this date recorded',value=False,key='qr_include_undated')
        _qrfiltered=filter_open_plan_rows(_qrbase,_qrsection,_qrf,_qrt,_qrstatus,_qrdkey,_qr_undated)
        st.caption(f'{len(_qrfiltered):,} { _qrstatus.lower() } · {_qrdatefield.lower()} {_qrf:%d %b %Y}–{_qrt:%d %b %Y}')
        if st.button('🔄 GENERATE QR STICKERS',use_container_width=True,type='primary',key='qr_open_generate'):
            with st.spinner('Generating QR stickers from active Plan-2026...'):
                try:
                    qrp,n,_src=qr_pack(True,plan_df=master,section=_qrsection,date_from=_qrf,date_to=_qrt,status_filter=_qrstatus,date_field=_qrdkey,include_undated=_qr_undated)
                    st.session_state['qrpack_all']=str(qrp) if qrp else ''
                    if n:st.success(f'{n:,} {_qrstatus.lower()} labels created from {_src}. Print “Sticker Print”; uppercase WO is directly below its QR.')
                    else:st.warning('No work orders match these filters. No stale phone database records were used.')
                except Exception as e:st.error(f'QR generation error: {e}')
        qpa=Path(st.session_state.get('qrpack_all','')) if st.session_state.get('qrpack_all') else None
        if qpa and qpa.exists():st.download_button('⬇ DOWNLOAD QR LABELS',qpa.read_bytes(),qpa.name,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='qr_open_download')
    with c2:
        if plan and st.button('🌐 CREATE PLAN-2026 WITH ENGLISH CUSTOMER NAMES',use_container_width=True):
            with st.spinner('Creating a separate English-customer copy...'):
                try: ep,n=english_plan_copy(plan);st.session_state['engplan']=str(ep);st.success(f'Created separate copy; {n:,} Thai customer-name rows converted/romanized. Original Plan-2026 unchanged.')
                except Exception as e:st.error(f'English Plan diagnostic: {e}')
        ep=Path(st.session_state.get('engplan','')) if st.session_state.get('engplan') else None
        if ep and ep.exists():st.download_button('⬇ DOWNLOAD ENGLISH-CUSTOMER PLAN-2026',ep.read_bytes(),ep.name,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    st.caption(f'Database: {DB} | Reports/QR workbooks: {REPORTS} | QR PNG cache: {REPORTS / "QR_TEMP"} | QR registry: {SHARED_ROOT / "QR_REGISTRY.json"} | Source copies: {SOURCE_ARCHIVE}')


if _page == 'capacity':
    st.header('⚖️ Capacity vs Plan')
    _cap_active=SM.active('CAPACITY_DATABASE')
    _cap_candidates=[Path(_cap_active['stored_path'])] if _cap_active and _cap_active.get('stored_path') else []
    _cap_published=_slot_published_path('CAPACITY_DATABASE')
    if _cap_published:_cap_candidates.append(_cap_published)
    _cap_candidates.append(ROOT/'apps'/'daily'/'CAPACITY_DATABASE.xlsx')
    _cp=next((p for p in _cap_candidates if p.is_file()),None)
    from suite.capacity_page import render as _render_capreg
    if _cp is None:
        st.error('Capacity source is unavailable. Upload CAPACITY_DATABASE.xlsx in this page’s Update sources panel; existing plan and audit data are unchanged.')
        st.stop()
    else:
        if _cap_active and not Path(_cap_active.get('stored_path','')).is_file():
            st.warning('The archived capacity copy is missing. Reading the active published/bundled capacity file instead; restore the missing archived copy from CENTRAL_DATA/SOURCE_COPIES when convenient.')
        _cap_sha=hashlib.sha256(_cp.read_bytes()).hexdigest()
        _render_capreg(_cp,_cap_sha,'capreg',shared_root=SHARED_ROOT,user=st.session_state.get('sl_user',''))
    st.divider()
    st.subheader('Daily Planner finite-capacity run (existing engine)')
    st.caption('Controlled source: active Plan-2026 + latest Firing Plan + the active CAPACITY_DATABASE revision above. Grinding and Cutting remain separate planning processes. This engine keeps its own unit handling; the registry above is the approved reference for units, time basis and cells.')
    _fire=fp('Firing-Plan-LATEST.xlsx')
    c1,c2,c3=st.columns(3);_start=c1.date_input('Start date',value=bkk_today(),key='cap_start');_h=c2.number_input('Horizon days',1,365,31,key='cap_h');_view=c3.selectbox('View',['Daily','Monthly'],key='cap_view')
    try:
        _mix=pd.read_excel(_cp,sheet_name='CAP ผสม',header=1)
        _active=_mix[_mix.iloc[:,1].astype(str).str.contains('ใช้',na=False) & ~_mix.iloc[:,1].astype(str).str.contains('ไม่ใช้',na=False)].copy()
        _mills=pd.to_numeric(_active.iloc[:,5],errors='coerce').fillna(0).sum();_kg=pd.to_numeric(_active.iloc[:,6],errors='coerce').fillna(0).sum()
        _planned_mills=float(pd.to_numeric(op.get('Mill Batches',0),errors='coerce').fillna(0).sum()) if op is not None and 'Mill Batches' in op else 0
        _m1,_m2,_m3=st.columns(3);_m1.metric('Open Plan mill batches (BY)',f'{_planned_mills:,.0f}');_m2.metric('Active mixing capacity',f'{_mills:,.0f} mills/day');_m3.metric('Machine nominal capacity',f'{_kg:,.0f} kg/day')
        st.caption('BY (จำนวนโม่) is a MILL COUNT, not batches or kg. The capacity database holds mills/day and machine kg/day side by side; they are shown separately and no conversion between them is invented (rule CAP-2). Open-WO mills here are not divided by mills/day.')
    except Exception as _e: st.caption(f'Mixing capacity mapping diagnostic: {_e}')
    if plan is None: st.warning('Upload Plan-2026 in Active Files / Sources.')
    elif _fire is None:
        st.warning('Latest Firing Plan is not loaded. Upload it once in Active Files / Upload.')
    elif st.button('RUN CAPACITY VS PLAN',use_container_width=True,key='run_capacity'):
        try:
            _daily=ROOT/'apps'/'daily';sys.path.insert(0,str(_daily)) if str(_daily) not in sys.path else None
            import integrated_daily_engine_v1_1 as _eng
            with st.spinner('Calculating controlled finite capacity...'):
                _res=_eng.build_detailed(str(plan),str(_fire),str(_cp),pd.Timestamp(_start),int(_h))
            st.session_state['cap_result']=_res
        except Exception as _e: st.error(f'Capacity calculation diagnostic: {_e}')
    _res=st.session_state.get('cap_result')
    if _res:
        _cv=_res.get('capacity_summary',pd.DataFrame()).copy();_all=_res.get('all',pd.DataFrame()).copy()
        if not _cv.empty:
            st.subheader('Capacity summary');st.dataframe(display_df(_cv),use_container_width=True,hide_index=True,height=360)
        if not _all.empty:
            _datecol=next((c for c in ['Plan Date','Date','Production Date'] if c in _all.columns),None)
            _qtycol=next((c for c in ['Plan Qty','Qty','Planned Qty'] if c in _all.columns),None)
            if _datecol and _qtycol:
                _g=_all.copy();_g[_datecol]=pd.to_datetime(_g[_datecol],errors='coerce');_g[_qtycol]=pd.to_numeric(_g[_qtycol],errors='coerce').fillna(0)
                if _view=='Monthly': _g['Period']=_g[_datecol].dt.to_period('M').astype(str)
                else: _g['Period']=_g[_datecol].dt.strftime('%Y-%m-%d')
                _sec='Section' if 'Section' in _g else None
                if _sec:
                    _tbl=_g.groupby(['Period',_sec],as_index=False)[_qtycol].sum();st.plotly_chart(px.bar(_tbl,x='Period',y=_qtycol,color=_sec,barmode='group',text_auto='.0f',title='Capacity planning load'),use_container_width=True);st.dataframe(display_df(_tbl),use_container_width=True,hide_index=True,height=360)
        _issues=_res.get('issues',pd.DataFrame())
        if isinstance(_issues,pd.DataFrame) and not _issues.empty: st.subheader('Capacity / scheduling issues');st.dataframe(display_df(_issues),use_container_width=True,hide_index=True,height=300)

if _page == 'newplan':
    st.header('🆕 New Order Workflow: RP → Work Order → Cover Sheet → Plan 2026')
    st.markdown('### Native P280 work-order draft builder')
    st.caption('Creates a new copy of the approved P280 workbook. Existing sheets, formulas and Cover Detial A:DA field order are retained. New WOs use the next valid P001–P050 slot and today in Bangkok. Draft only; planner review is required.')
    _p280=fp('P280526-LATEST.xlsx')
    _p280_upload=st.file_uploader('P280 template / Cover Detial workbook (.xlsx)',type=['xlsx'],key='p280_native_template')
    if _p280_upload is not None:
        try:
            if not _upload_seen(_p280_upload,'archive:P280526-LATEST.xlsx'):
                _p280=archive_and_save(_p280_upload,'P280526-LATEST.xlsx') or fp('P280526-LATEST.xlsx')
                if _p280:st.success(f'P280 source saved once for this file revision: {_p280_upload.name} → {_p280}')
            else:_p280=fp('P280526-LATEST.xlsx')
        except Exception as _ue:st.error(f'Could not save P280 template: {_ue}')
    elif not _p280:st.info('Upload P280526(1).xlsx once. The source copy remains unchanged and becomes the P280 master for drafts.')
    if _p280:
        _p280_reg=_load_registry().get('P280526-LATEST.xlsx',{})
        with st.expander('P280 source file properties & traceability',expanded=True):
            st.write(f"Original import name: {_p280_reg.get('original_name',_p280.name)} · Stored name: {_p280.name}")
            st.write(f"Imported (Thailand local time — Phan Thong, Chonburi): {_p280_reg.get('registered_at','Not recorded')} · Excel modified: {_p280_reg.get('excel_document_modified_at','Not available')} · Bytes: {_p280_reg.get('size_bytes','?')}")
            st.code(f"Active storage: {_p280.resolve()}\nArchive copy: {_p280_reg.get('archive_copy_path','Not recorded')}\nSHA-256: {_p280_reg.get('sha256','Not recorded')}\nOriginal computer folder: not exposed by browser upload",language=None)
    _ns_cols=['Order No.','PO No.','RP / document No.','External line No.','Customer code','Customer name','Requested due','Exact product code','Product / spec description','Qty','RP reference','Customer packing / mark notes']
    _native_seed=pd.DataFrame([{c:'' for c in _ns_cols}])
    _native_rows=_persistent_data_editor(_native_seed,num_rows='dynamic',use_container_width=True,hide_index=True,key='p280_native_rows',column_config={'Qty':st.column_config.NumberColumn('Qty',min_value=1,step=1)})
    _request_evidence=st.text_area('Optional — paste the original email/RP text as traceable source evidence (the app will not guess missing values)',height=110,key='p280_request_evidence')
    if st.button('CREATE NATIVE P280 WORK ORDER DRAFT + QR LABEL PACKET',type='primary',use_container_width=True,key='create_p280_native'):
        try:
            if not _p280 or not Path(_p280).exists():raise ValueError('Upload the approved P280 template first.')
            _today=datetime.now(ZoneInfo('Asia/Bangkok')).date();_token=_today.strftime('%d%m%y');_stamp=datetime.now(ZoneInfo('Asia/Bangkok')).strftime('%Y%m%d_%H%M%S_%f')
            _probe=load_workbook(_p280,read_only=True,data_only=True)
            if not all(x in _probe.sheetnames for x in ('ใบorder','Cover Detial','SD')):raise ValueError('P280 source must include ใบorder, Cover Detial and SD.')
            _osrc=_probe['ใบorder'];_next=1;_existing=set();_customer_pairs={}
            for _ordrow in _osrc.iter_rows(min_row=4,max_row=min(_osrc.max_row,100),max_col=14,values_only=True):
                _seq,_ord,_code=_ordrow[0],_ordrow[1],_ordrow[9]
                if _ord not in (None,'') and _code not in (None,'','#N/A'):
                    try:_next=max(_next,int(_seq)+1)
                    except (TypeError,ValueError):pass
                    _existing.add(str(_ord).strip().upper())
                _cid=str(_ordrow[6] or '').strip().upper();_cname=str(_ordrow[7] or '').strip()
                if _cid and _cname:_customer_pairs.setdefault(_cid,set()).add(_cname)
            _sd=_probe['SD'];_codecounts={};_sd_by_code={}
            for _sv in _sd.iter_rows(min_row=3,max_row=min(_sd.max_row,8000),max_col=76,values_only=True):
                _code=str(_sv[1] or '').strip().upper() if len(_sv)>1 else ''
                if _code:_codecounts[_code]=_codecounts.get(_code,0)+1;_sd_by_code[_code]=list(_sv)
            _groups=_probe['GROUPING'] if 'GROUPING' in _probe.sheetnames else None;_pack_by_code={}
            if _groups:
                for _gr,_gv in enumerate(_groups.iter_rows(min_row=5,max_row=min(_groups.max_row,3000),max_col=18,values_only=True),start=5):
                    _gcodes={str(_gv[_gc] or '').strip().upper() for _gc in (3,13) if len(_gv)>_gc and _gv[_gc]}
                    for _gcode in _gcodes:
                        _pack_by_code.setdefault(_gcode,[]).append({'row':_gr,'brand':_gv[7] if len(_gv)>7 else '', 'inner':_gv[8] if len(_gv)>8 else '', 'outer':_gv[9] if len(_gv)>9 else '', 'qty_per_box':_gv[10] if len(_gv)>10 else '', 'group':_gv[11] if len(_gv)>11 else '', 'packing_code':_gv[17] if len(_gv)>17 else ''})
            _base_cover_cache={}
            _cvp=_probe['Cover Detial']
            for _cr,_crow in enumerate(_cvp.iter_rows(min_row=5,max_row=54,max_col=105,values_only=True),start=5):
                for _cc,_vv in enumerate(_crow,start=1):
                    if _vv is not None:_base_cover_cache[f'{get_column_letter(_cc)}{_cr}']=_vv
            _probe.close();_records=[]
            for _,_nr in _native_rows.iterrows():
                def _get(k):
                    v=_nr.get(k,'');return '' if pd.isna(v) else str(v).strip()
                if not any(_get(k) for k in _ns_cols):continue
                _qty=pd.to_numeric(pd.Series([_nr.get('Qty','')]),errors='coerce').iloc[0]
                if not pd.isna(_qty) and _qty<=0:raise ValueError(f"{_get('Order No.') or 'Request'}: quantity must be positive when supplied.")
                _order=_get('Order No.')
                if _order and _order.upper() in _existing:raise ValueError(f'Duplicate Order No. {_order}.')
                _code=_get('Exact product code').upper();_custcode=_get('Customer code');_customer=_get('Customer name');_spec=_get('Product / spec description')
                _sdmatch=_sd_by_code.get(_code) if _codecounts.get(_code)==1 else None
                _customer_source='entered by planner' if _customer else 'not found'
                if not _customer and _custcode and len(_customer_pairs.get(_custcode.upper(),set()))==1:_customer=next(iter(_customer_pairs[_custcode.upper()]));_customer_source='unique customer-code match in P280 order history — verify'
                _spec_source='entered by planner' if _spec else 'not found'
                if not _spec and _sdmatch and len(_sdmatch)>7 and _sdmatch[7]:_spec=str(_sdmatch[7]);_spec_source='exact unique product-code match in SD — verify revision'
                _records.append({'seq':_next+len(_records),'order':_order,'po':_get('PO No.'),'rpdoc':_get('RP / document No.'),'external':_get('External line No.'),'custcode':_custcode,'customer':_customer,'customer_source':_customer_source,'due':_get('Requested due'),'code':_code,'spec':_spec,'spec_source':_spec_source,'qty':'' if pd.isna(_qty) else int(_qty),'rp':_get('RP reference'),'notes':_get('Customer packing / mark notes'),'sd':_codecounts.get(_code,0),'sdrow':_sdmatch,'pack':_pack_by_code.get(_code,[])})
                if _order:_existing.add(_order.upper())
            if not _records:raise ValueError('Enter at least one request row.')
            if _records[-1]['seq']>50:raise ValueError('All P001–P050 slots are used; extend the controlled P280 template before creating more orders.')
            _source_hash=_sha256(_p280);_reg=_load_registry().get('P280526-LATEST.xlsx',{})
            _outdir=REPORTS/'WORK_ORDER_DRAFTS';_outdir.mkdir(parents=True,exist_ok=True)
            _xlsx=_outdir/f'P280_NATIVE_WO_DRAFT_{_stamp}.xlsx';_zip=_outdir/f'P280_NATIVE_WO_DRAFT_{_stamp}_PACKET.zip';_qrdir=_outdir/f'QR_{_stamp}';_qrdir.mkdir(parents=True,exist_ok=True)
            _wb=load_workbook(_p280);_sheet=_wb['ใบorder'];_coverws=_wb['Cover Detial'];_audit=[];_formula_cache=dict(_base_cover_cache)
            for _r in _records:
                _n=_r['seq'];_row=_n+3;_tab=f'P{_n:03d}'
                if _tab not in _wb.sheetnames:raise ValueError(f'Missing native template sheet {_tab}.')
                _sheet.cell(_row,1).value=_n
                for _col,_val in {2:_r['order'],4:_r['po'],5:_r['rpdoc'],6:_r['external'],7:_r['custcode'],8:_r['customer'],10:_r['code'],11:_r['spec'],12:_r['qty'],13:_r['rp'],14:_r['notes']}.items():
                    if _val!='':_sheet.cell(_row,_col).value=_val
                if _r['due']:
                    _dt=pd.to_datetime(_r['due'],errors='coerce')
                    if pd.isna(_dt):raise ValueError(f"Invalid due date for {_r['order'] or _tab}: {_r['due']}")
                    _sheet.cell(_row,9).value=_dt.to_pydatetime();_sheet.cell(_row,9).number_format='d/m/yyyy'
                _wo=f'P{_n:03d}-{_token}';_ws=_wb[_tab];_ws['D2']=f'{_n:03d}';_ws['F2']=_token;_ws['D5']=datetime.combine(_today,time.min);_ws['D5'].number_format='d/m/yyyy';_ws['C9']=_n
                _payload=f'SLWO:{_wo}';qrcode.make(_payload).save(_qrdir/f'{_wo}.png')
                _cr=_n+4;_serial=lambda d:(d-datetime(1899,12,30).date()).days
                _sdrow=_r.get('sdrow') or []
                _formula_cache.update({f'A{_cr}':_wo,f'B{_cr}':_serial(_today),f'C{_cr}':_serial(pd.to_datetime(_r['due']).date()) if _r['due'] else None,f'D{_cr}':_r['order'] or '',f'E{_cr}':_r['po'] or '',f'F{_cr}':_r['customer'] or '',f'G{_cr}':_r['custcode'] or '',f'H{_cr}':_r['spec'] or '',f'I{_cr}':_sdrow[8] if len(_sdrow)>8 else '',f'J{_cr}':_r['qty'] if _r['qty']!='' else None,f'K{_cr}':_r['code'] or '',f'L{_cr}':_sdrow[11] if len(_sdrow)>11 else '',f'BB{_cr}':_sdrow[53] if len(_sdrow)>53 else '',f'BC{_cr}':_sdrow[54] if len(_sdrow)>54 else ''})
                _missing=[name for name,key in [('Order No.','order'),('Customer','customer'),('Customer code','custcode'),('Due date','due'),('Product code','code'),('Specification','spec'),('Quantity','qty'),('PO','po'),('RP reference','rp')] if not _r[key]]
                _audit.append({'Work Order':_wo,'Order No.':_r['order'],'Customer':_r['customer'],'Product code':_r['code'],'Exact SD matches':_r['sd'],'Customer-name source':_r['customer_source'],'Specification source':_r['spec_source'],'Exact packaging matches':len(_r['pack']),'Packaging decision':'REVIEW — no auto-application' if _r['pack'] else 'NO EXACT PACKAGING MASTER MATCH — confirm','Qty':_r['qty'],'Due date':_r['due'],'Readiness':'EXACT CODE FOUND — review full master data' if _r['sd']==1 else ('CODE NOT FOUND IN SD — technical review required' if _r['sd']==0 else 'DUPLICATE CODE IN SD — resolve'),'Missing request fields':', '.join(_missing) or 'None detected','QR payload':_payload,'Email/RP text SHA-256':hashlib.sha256(_request_evidence.encode('utf-8')).hexdigest() if _request_evidence else 'Not provided','Source filename':Path(_p280).name,'Source stored path':str(Path(_p280).resolve()),'Source SHA-256':_source_hash,'Source registered at':_reg.get('registered_at','Not recorded'),'Created Bangkok':datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds'),'Status':'DRAFT — planner review required'})
            _statusws=_wb['SL_ORDER_STATUS'] if 'SL_ORDER_STATUS' in _wb.sheetnames else _wb.create_sheet('SL_ORDER_STATUS')
            if _statusws.max_row==1 and not _statusws['A1'].value:
                for _ci,_h in enumerate(['ProductionCode','Status','Created at (Thailand local time — Phan Thong, Chonburi)','Source filename','Source path','Source SHA-256','Readiness'],1):_statusws.cell(1,_ci).value=_h
            for _a in _audit:_statusws.append([_a['Work Order'],'DRAFT',_a['Created Bangkok'],_a['Source filename'],_a['Source stored path'],_a['Source SHA-256'],_a['Readiness']])
            _statusws.freeze_panes='A2';_statusws.auto_filter.ref=_statusws.dimensions
            _packws=_wb['PACKAGING_REVIEW'] if 'PACKAGING_REVIEW' in _wb.sheetnames else _wb.create_sheet('PACKAGING_REVIEW')
            if _packws.max_row==1 and not _packws['A1'].value:
                for _ci,_h in enumerate(['Work Order','Product code','GROUPING source row','Brand','Inner box','Outer box','Pack qty / box','Group','Packing code','Review status'],1):_packws.cell(1,_ci).value=_h
            for _r in _records:
                _wo=f"P{_r['seq']:03d}-{_token}"
                if _r['pack']:
                    for _pm in _r['pack']:_packws.append([_wo,_r['code'],_pm['row'],_pm['brand'],_pm['inner'],_pm['outer'],_pm['qty_per_box'],_pm['group'],_pm['packing_code'],'EXACT CODE MATCH — planner/customer confirmation required; not applied automatically'])
                else:_packws.append([_wo,_r['code'],'','','','','','','','NO EXACT GROUPING CODE MATCH — verify against RP/customer pack specification'])
            _packws.freeze_panes='A2';_packws.auto_filter.ref=_packws.dimensions
            _wb.calculation.fullCalcOnLoad=True;_wb.calculation.forceFullCalc=True;_wb.calculation.calcMode='auto';_wb.save(_xlsx);_wb.close()
            patch_formula_caches(_xlsx,'Cover Detial',_formula_cache)
            _csv=_outdir/f'P280_TRACEABILITY_{_stamp}.csv';pd.DataFrame(_audit).to_csv(_csv,index=False,encoding='utf-8-sig')
            _readme=_outdir/f'QR_README_{_stamp}.txt';_readme.write_text('QR contains IP-independent text ID SLWO:Pnnn-DDMMYY. Scan in the SL app; no server/IP address is embedded.\nGenerated '+datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds'),encoding='utf-8')
            _evidence_file=None
            if _request_evidence.strip():
                _evidence_file=_outdir/f'REQUEST_SOURCE_{_stamp}.txt';_evidence_file.write_text(_request_evidence,encoding='utf-8')
            register_source(f'WORK_ORDER_DRAFTS/{_xlsx.name}',_xlsx,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),Path(_p280).name,'Generated native P280 WO draft')
            register_source(f'WORK_ORDER_DRAFTS/{_csv.name}',_csv,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),Path(_p280).name,'Generated P280 traceability report')
            with zipfile.ZipFile(_zip,'w',zipfile.ZIP_DEFLATED) as _zf:
                _zf.write(_xlsx,_xlsx.name);_zf.write(_csv,_csv.name);_zf.write(_readme,_readme.name)
                if _evidence_file:_zf.write(_evidence_file,_evidence_file.name)
                for _qf in _qrdir.glob('*.png'):_zf.write(_qf,'QR_LABELS/'+_qf.name)
            register_source(f'WORK_ORDER_DRAFTS/{_zip.name}',_zip,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),Path(_p280).name,'Generated P280 WO and QR packet')
            st.session_state['p280_packet']=str(_zip);st.session_state['p280_xlsx']=str(_xlsx);st.session_state['p280_audit']=_audit
            st.success(f'Created {len(_records)} native P280 draft WO(s), traceability CSV and IP-independent QR labels. Original source unchanged.')
        except Exception as _err:st.error(f'P280 draft stopped safely: {_err}')
    _packet=Path(st.session_state.get('p280_packet','')) if st.session_state.get('p280_packet') else None
    if _packet and _packet.exists():
        st.dataframe(pd.DataFrame(st.session_state.get('p280_audit',[])),use_container_width=True,hide_index=True)
        st.code(f"WO workbook: {st.session_state.get('p280_xlsx')}\nZIP packet: {_packet.resolve()}",language=None)
        st.download_button('⬇ DOWNLOAD NATIVE P280 WORK ORDER + QR PACKET',_packet.read_bytes(),_packet.name,'application/zip',use_container_width=True)
    st.divider()
    st.markdown('### RP → planning suggestion (non-native format)')
    st.markdown('**1. Sales releases RP** → **2. Planner reviews/assigns the controlled WO number** → **3. Review the cover-sheet draft and process controls** → **4. Add the approved WO to Plan 2026 and schedule it.**')
    st.caption('This page reads an RP or request workbook, keeps its source evidence, decodes fields supported by known records, and creates a downloadable draft packet. Dates/capacity are recalculated from today and current source data; historical technical similarities are hints only. It will not invent a WO number, recipe, packaging spec, machine booking or release approval.')
    _rp_upload=st.file_uploader('STEP 1 — Upload Sales RP / customer request (.xlsx)',type=['xlsx','xlsm'],key='newplan_rp_intake')
    _rp_info={};_rp_meta=None
    if _rp_upload is not None:
        try:
            _rp_bytes=_rp_upload.getvalue();_rp_sha=hashlib.sha256(_rp_bytes).hexdigest()
            _rp_meta=st.session_state.get('newplan_rp_meta')
            if not _rp_meta or _rp_meta.get('sha256')!=_rp_sha:
                _rp_dir=SOURCE_ARCHIVE/'NEW_RP';_rp_dir.mkdir(parents=True,exist_ok=True)
                _rp_name=re.sub(r'[^A-Za-z0-9._ -]','_',Path(_rp_upload.name).name)
                _rp_path=_rp_dir/f"{datetime.now(ZoneInfo('Asia/Bangkok')):%Y%m%d_%H%M%S}_{_rp_name}"
                _rp_path.write_bytes(_rp_bytes)
                register_source(f'NEW_RP/{_rp_path.name}',_rp_path,st.session_state.get('sl_user',''),st.session_state.get('sl_section',''),_rp_upload.name,'New Order Workflow — RP Intake')
                _rp_meta={'sha256':_rp_sha,'original_filename':Path(_rp_upload.name).name,'stored_filename':_rp_path.name,'stored_path':str(_rp_path.resolve()),'imported_at':datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds')}
                st.session_state['newplan_rp_meta']=_rp_meta
            _rp_info=parse_new_request_reference(_rp_meta['stored_path'])
            _rp_info.pop('Reference File',None)
            st.success(f"RP saved as evidence: {_rp_meta['original_filename']} → {_rp_meta['stored_filename']}")
            st.code(f"Stored location: {_rp_meta['stored_path']}\nImported at: {_rp_meta['imported_at']}\nSHA-256: {_rp_meta['sha256']}",language=None)
            st.markdown('#### RP fields detected — review and correct below')
            st.dataframe(pd.DataFrame([{'Field':k,'Detected value':v} for k,v in _rp_info.items()]),use_container_width=True,hide_index=True)
        except Exception as _rp_err:
            st.error(f'RP intake error: {_rp_err}')
    st.markdown('''<div class="sl-card"><b>Workflow gates</b><br>RP captured and hashed → request fields checked → WO number reviewed → cover sheet draft reviewed → Plan 2026 row approved → current-date capacity/material/schedule validated. Each gate remains visible in the downloadable workbook.</div>''',unsafe_allow_html=True)
    _ref=fp('New-Request-Reference-LATEST.xlsx')
    _refinfo=parse_new_request_reference(_ref) if _ref else {}
    _refinfo.update({k:v for k,v in _rp_info.items() if v not in (None,'')})
    if _ref:
        st.success(f'Request/test reference loaded: {_ref.name}')
        st.dataframe(pd.DataFrame([_refinfo]),use_container_width=True,hide_index=True)
    else:
        st.info('Optional: upload a test/request workbook once in Active Files / Upload. Planning still works from manually entered information if it is missing.')
    st.markdown('### STEP 2 — Review request details and assign the official Work Order')
    st.caption('Add as many rows as required. RP values seed the draft when they can be decoded. Enter the released WO number from your controlled numbering process; an empty value stays DRAFT and is never treated as a released order. Historical technical hints can populate draft fields, while execution/closure evidence is cleared.')
    _seed=pd.DataFrame([{
        'Work Order':'',
        'Customer':str(_refinfo.get('Customer','')),
        'Product / Specification':str(_refinfo.get('Specification','')),
        'Size':str(_refinfo.get('Size','')),
        'Qty':float(_refinfo.get('Qty',1) or 1),
        'Requested Due':'',
        'Material / Bond':str(_refinfo.get('Material / Bond','')),
        'Packaging':('Carton '+str(_refinfo.get('Packing Qty / Box'))+' pcs/box' if _refinfo.get('Packing Qty / Box') else ''),
        'Customer mark':str(_refinfo.get('Brand / Mark','')),
        'Finishing Route':'AUTO — learn from similar Plan-2026 rows'}])
    _reqs=_persistent_data_editor(_seed,num_rows='dynamic',use_container_width=True,hide_index=True,key='multi_new_wo',
        column_config={
          'Qty':st.column_config.NumberColumn('Qty',min_value=1,step=1),
          'Requested Due':st.column_config.TextColumn('Requested Due — YYYY-MM-DD or DD/MM/YYYY',help='05/12/2026 means 5 December 2026. Historical dates are never copied.'),
          'Finishing Route':st.column_config.SelectboxColumn('Finishing Route',options=['AUTO — learn from similar Plan-2026 rows','Grinding','Cutting','No Grinding / No Cutting'])
        })
    if st.button('CREATE MULTI-WO PLAN-2026 FORMAT SUGGESTION',type='primary',use_container_width=True,key='create_nr_multi'):
        if not plan:st.error('Active Plan-2026 is required because its exact columns and historical database are the controlled template.')
        else:
            try:
                _wb=load_workbook(plan,data_only=False,read_only=True);_ws=_wb['แผนการเผา'] if 'แผนการเผา' in _wb.sheetnames else _wb[_wb.sheetnames[0]]
                # Plan templates can report an inflated used range (~16k columns).
                # The controlled mapping ends at IA; cap the header read to 235 columns.
                _headers=list(next(_ws.iter_rows(min_row=3,max_row=3,max_col=235,values_only=True)))
                while _headers and _headers[-1] is None:_headers.pop()
                _hn={str(v).strip():i for i,v in enumerate(_headers) if v not in (None,'')}
                # The source sheet's formatting inflates max_column to ~16k; only read real header width.
                _history=[list(r) for r in _ws.iter_rows(min_row=4,max_col=len(_headers),values_only=True)]
                def _v(row,*names):
                    for n in names:
                        if n in _hn:return row[_hn[n]]
                    return None
                def _setrow(row,value,*names):
                    if value in (None,'') or (isinstance(value,float) and pd.isna(value)):return
                    for n in names:
                        if n in _hn:row[_hn[n]]=value;return
                def _dim_key(value):
                    parts=re.findall(r'\d+(?:\.\d+)?',str(value or '').replace(',',''))
                    out=[]
                    for part in parts:
                        try:
                            num=float(part);out.append(str(int(num)) if num.is_integer() else str(num).rstrip('0').rstrip('.'))
                        except (TypeError,ValueError):out.append(part.upper())
                    return 'X'.join(out)
                _outrows=[];_basis_rows=[];_material_rows=[];_draft_req_meta=[]
                _stamp=bkk_now().strftime('%Y%m%d-%H%M%S')
                _today=datetime.now(ZoneInfo('Asia/Bangkok')).date()
                _stock=fp('Stock-on-Hand-LATEST.xlsx')
                _stock_by_code={}
                if _stock:
                    try:
                        _sw=load_workbook(_stock,data_only=True,read_only=True)
                        _ss=_sw['STAbrasiveสรุปคงคลัง'] if 'STAbrasiveสรุปคงคลัง' in _sw.sheetnames else None
                        if _ss:
                            for _sr in _ss.iter_rows(min_row=5,values_only=True):
                                _code=str(_sr[3] or '').strip().upper() if len(_sr)>3 else ''
                                if _code:
                                    try:_bal=float(_sr[47] or 0)
                                    except (TypeError,ValueError):_bal=0.0
                                    _stock_by_code[_code]=_bal
                        _sw.close()
                    except Exception as _se:st.warning(f'Stock data could not be read for the draft check: {_se}')
                for _idx,_rq in _reqs.iterrows():
                    _cust=str(_rq.get('Customer','') or '').strip();_prod=str(_rq.get('Product / Specification','') or '').strip()
                    _size=str(_rq.get('Size','') or '').strip();_mat=str(_rq.get('Material / Bond','') or '').strip()
                    _pack=str(_rq.get('Packaging','') or '').strip();_mark=str(_rq.get('Customer mark','') or '').strip()
                    _route=str(_rq.get('Finishing Route','') or 'AUTO — learn from similar Plan-2026 rows')
                    _qty=float(pd.to_numeric(_rq.get('Qty',1),errors='coerce') or 1)
                    _wo=str(_rq.get('Work Order','') or '').strip()
                    _due_raw=_rq.get('Requested Due','')
                    from suite.requirements_engine import parse_date as _parse_request_date
                    _parsed_due=_parse_request_date(_due_raw)
                    _due=pd.Timestamp(_parsed_due) if _parsed_due else pd.NaT
                    if not (_wo or _cust or _prod):continue
                    _tokens=[x.upper() for x in re.findall(r'[A-Z0-9]+',f'{_prod} {_size} {_mat}') if len(x)>=2]
                    _best=None;_bestscore=-1
                    for _r in _history:
                        # Compare technical fields individually; substring matching the entire row
                        # can falsely rank a historical WO merely because of dates or status text.
                        _hist_prod=' '.join(str(_v(_r,'Specification','RealSpec','รหัสสินค้า') or '').upper().split())
                        _hist_cat=str(_v(_r,'ประเภทสินค้า') or '').strip().upper()
                        _hist_size='X'.join(_dim_key(_v(_r,_c)) for _c in ('D','T','H'))
                        _hist_cust=str(_v(_r,'Customername','Customer') or '').strip().upper()
                        _score=0
                        if _prod and _hist_prod and ' '.join(_prod.upper().split())==_hist_prod:_score+=12
                        elif _prod and _hist_prod and (_prod.upper() in _hist_prod or _hist_prod in _prod.upper()):_score+=5
                        _size_compact=_dim_key(_size)
                        if _size_compact and _hist_size==_size_compact:_score+=8
                        if _mat and _hist_cat and _mat.upper() in _hist_cat:_score+=2
                        if _cust and _hist_cust and _cust.upper()==_hist_cust:_score+=2
                        for _tok in _tokens:
                            if _tok in _hist_prod:_score+=1
                        if _score>_bestscore:_bestscore=_score;_best=list(_r)
                    _matched_history=bool(_best is not None and _bestscore>=12)
                    if not _matched_history:_best=None
                    _row=(list(_best[:len(_headers)]) if _best is not None else [None]*len(_headers))
                    if len(_row)<len(_headers):_row.extend([None]*(len(_headers)-len(_row)))
                    for _i,_h in enumerate(_headers):
                        _hs=str(_h or '')
                        # A historical date/status must never silently become the new WO schedule.
                        if any(_k in _hs for _k in ['วันที่','กำหนดเข้าคลัง','กำหนดส่งใหม่','กำหนดส่งมอบขาย','รอ','โหลดเข้า','เผา','โหลดออก','ปิด','Planning','REPORT','#VALUE!','#REF!']):_row[_i]=None
                    _id=_wo or f'DRAFT-{_stamp}-{len(_outrows)+1:03d}'
                    _setrow(_row,_id,'ProductionCode','Production Code')
                    _setrow(_row,_cust,'Customername','Customer')
                    _setrow(_row,_prod,'Specification','RealSpec','รหัสสินค้า')
                    _setrow(_row,float(_qty),'QTY')
                    _hist_qty=pd.to_numeric(pd.Series([_v(_best,'QTY') if _best else None]),errors='coerce').fillna(0).iloc[0]
                    _recipe_codes=[]
                    if _matched_history and _hist_qty>0:
                        # Plan-2026 recipe pairs occupy code/gram columns 18/19 through 26/27.
                        for _code_col in (17,19,21,23,25):
                            _code=str(_best[_code_col] or '').strip().upper() if len(_best)>_code_col else ''
                            _grams=pd.to_numeric(pd.Series([_best[_code_col+1] if len(_best)>_code_col+1 else None]),errors='coerce').fillna(0).iloc[0]
                            if _code and _code not in {'0','NAN','NONE'} and _grams>0:
                                _recipe_codes.append((_code,float(_grams)))
                    for _code,_hist_grams in _recipe_codes:
                        _need_g=_hist_grams/float(_hist_qty)*float(_qty)
                        _available=_stock_by_code.get(_code)
                        _matstatus=('CHECK — estimated shortage' if _available is not None and _available<_need_g else 'Stock record found — planner verification required' if _available is not None else 'NO EXACT STOCK RECORD')
                        _material_rows.append([_id,_code,_hist_grams,float(_hist_qty),float(_qty),_need_g,_available if _available is not None else 'TO CONFIRM',_matstatus,'Historical Plan-2026 recipe scaled by proposed qty; estimated requirement only, not a released BOM. No substitutions applied.'])
                    if not pd.isna(_due):
                        _d=_due.date()
                        if _d < _today:
                            raise ValueError(f'{_id}: requested due date {_d} is before today ({_today}). Correct the date; past historical dates are not accepted for a new plan.')
                        # Requested sales commitment remains distinct from internal receipt/revised dates.
                        _setrow(_row,_d,'กำหนดส่งมอบขาย')
                    # Preserve historical fields only as technical hints; no old execution/closure schedule.
                    _outrows.append(_row)
                    _basis_rows.append([_id,_cust or 'TO CONFIRM',_prod or 'TO CONFIRM',_size or 'TO CONFIRM',_qty,str(_due.date()) if not pd.isna(_due) else 'TO CONFIRM',_mat or 'TO CONFIRM',_route,_bestscore if _bestscore>0 else 'NO STRONG MATCH','Technical fields are suggestions only. Past schedule/execution fields were cleared. Capacity booking, machine/mould availability, WIP and route readiness are not live-booked. Material estimate is in MATERIAL_FEASIBILITY and requires approval.'])
                    _draft_req_meta.append({'Packaging':_pack or 'TO CONFIRM','Customer mark':_mark or 'TO CONFIRM'})
                if not _outrows:raise ValueError('Enter at least one Work Order/request row.')
                _out=REPORTS/f'PLAN2026_MULTI_WO_SUGGESTION_{_stamp}.xlsx'
                _ow=Workbook();_os=_ow.active;_os.title='แผนการเผา';_os.append([None]*len(_headers));_os.append([None]*len(_headers));_os.append(_headers)
                for _r in _outrows:_os.append(_r)
                _basis=_ow.create_sheet('PLANNING_BASIS');_basis.append(['WO / Reference','Customer','Requested product/spec','Requested size','Requested qty','Requested due','Material/Bond','Finishing route','Historical similarity score','Basis / limitation'])
                for _r in _basis_rows:_basis.append(_r)
                _matws=_ow.create_sheet('MATERIAL_FEASIBILITY');_matws.append(['WO / Reference','Material code','Historical total grams','Historical qty basis','Proposed qty','Estimated requirement g','Stock balance g','Check','Basis / limitation'])
                for _r in _material_rows:_matws.append(_r)
                _gate=_ow.create_sheet('READINESS_CHECK');_gate.append(['Work Order','As-of date (Thailand — Phan Thong, Chonburi)','Request fields complete','Historical technical match','Material review','Process route','Machine / mould availability','Operator skill availability','Daily capacity booking','Production schedule','Packaging / customer requirements','WO release gate'])
                for _basis in _basis_rows:
                    _wid,_bcust,_bprod,_bsize,_bqty,_bdue,_bmat,_broute,_score,_lim=_basis
                    _matched='MATCHED — REVIEW TECHNICAL DATA' if isinstance(_score,(int,float)) and _score>=12 else 'NO STRONG HISTORICAL MATCH'
                    _mcheck='ESTIMATED — SEE MATERIAL_FEASIBILITY' if any(x[0]==_wid for x in _material_rows) else 'NOT CHECKED — recipe/BOM absent'
                    _routecheck='ROUTE SELECTED — confirm against approved process' if _broute and not str(_broute).startswith('AUTO') else 'ROUTE NOT CONFIRMED'
                    _gate.append([_wid,_today.isoformat(),('COMPLETE' if all(str(x).strip() not in {'','TO CONFIRM'} for x in (_bcust,_bprod,_bsize,_bqty)) else 'MISSING REQUEST FIELDS'),_matched,_mcheck,_routecheck,'NOT VERIFIED FROM LIVE TOOLING AVAILABILITY','NOT VERIFIED FROM SHIFT / SKILL ROSTER','NOT BOOKED — run Capacity vs Plan after technical routing','NOT SCHEDULED — no dates copied from historical WOs','NOT VERIFIED — confirm approved pack spec and customer marks','DRAFT ONLY — planner approval and release remain required'])
                # Add a traceable handoff packet to the same workbook: the accepted RP evidence,
                # WO draft, cover-sheet data and Plan 2026 import row all stay together.
                _rpws=_ow.create_sheet('RP_SOURCE')
                _rpws.append(['Source original filename','Stored filename','Stored path','Imported at (Thailand local time — Phan Thong, Chonburi)','SHA-256','Client device folder'])
                if _rp_meta:_rpws.append([_rp_meta.get('original_filename'),_rp_meta.get('stored_filename'),_rp_meta.get('stored_path'),_rp_meta.get('imported_at'),_rp_meta.get('sha256'),'Not exposed by browser'])
                else:_rpws.append(['No RP uploaded — manually entered request','','','','',''])
                _rpws.append([]);_rpws.append(['Detected RP field','Detected value'])
                for _rk,_rv in _rp_info.items():_rpws.append([_rk,str(_rv)])
                _wow=_ow.create_sheet('WORK_ORDER_DRAFT')
                _wow.append(['WO / Reference','Customer','Product / Specification','Size','Quantity','Requested due date','Material / Bond','Finishing route','Status'])
                for _br in _basis_rows:_wow.append([*_br[:8],('DRAFT — official WO number required' if str(_br[0]).startswith('DRAFT-') else 'REVIEW — planner release required')])
                _cover=_ow.create_sheet('COVER_SHEET_DRAFT')
                _cover.append(['DRAFT COVER SHEET — TRANSFER INTO THE CONTROLLED BLUE-SHEET TEMPLATE','Value','Source / review instruction'])
                _cover_items=[
                    ('Request source',_rp_meta.get('original_filename') if _rp_meta else (_ref.name if _ref else 'Manual request'),'See RP_SOURCE for stored path, timestamp and SHA-256.'),
                    ('Customer',_basis_rows[0][1] if _basis_rows else 'TO CONFIRM','Confirm against RP and customer master.'),
                    ('Work Order',_basis_rows[0][0] if _basis_rows else 'TO CONFIRM','Official WO number must be assigned by controlled process.'),
                    ('Product / Specification',_basis_rows[0][2] if _basis_rows else 'TO CONFIRM','Confirm drawing/spec revision.'),
                    ('Size',_basis_rows[0][3] if _basis_rows else 'TO CONFIRM','Confirm D × T × H and tolerance.'),
                    ('Quantity',_basis_rows[0][4] if _basis_rows else 'TO CONFIRM','Confirm sales-release quantity and units.'),
                    ('Requested delivery',_basis_rows[0][5] if _basis_rows else 'TO CONFIRM','Customer request; internal dates require feasible schedule.'),
                    ('Material / Bond',_basis_rows[0][6] if _basis_rows else 'TO CONFIRM','Verify against approved recipe/BOM and live stock.'),
                    ('Process route',_basis_rows[0][7] if _basis_rows else 'TO CONFIRM','Validate every operation and process control.'),
                    ('Material, tooling, machine, operator capacity','NOT BOOKED','Review live availability and daily capacity.'),
                    ('WO release state','DRAFT — NOT RELEASED','Approval required before issuing/production.'),
                ]
                for _ci in _cover_items:_cover.append(list(_ci))
                _cover.append([]);_cover.append(['Process / Q-point','Required review / source','Owner / date / approval'])
                _cover.append(['RP → WO → Cover Sheet → Plan 2026','Sequence follows the user-defined controlled workflow.','Planner to complete and approve each gate.'])
                _cover.append(['Do not use as official controlled form','The program package does not contain the current approved blue-sheet cover template.','Copy reviewed data to the approved template; attach this draft packet as trace evidence.'])
                _cover.append([]);_cover.append(['WO-specific packaging / mark','Draft value','Review requirement'])
                for _i,_basis in enumerate(_basis_rows):
                    _dm=_draft_req_meta[_i] if _i<len(_draft_req_meta) else {}
                    _cover.append([_basis[0],_dm.get('Packaging','TO CONFIRM'),'Verify approved packaging code, pack qty, customer and vendor requirements.'])
                    _cover.append([_basis[0],_dm.get('Customer mark','TO CONFIRM'),'Verify mark/no-mark against released RP and customer print.'])
                for _sheet in (_rpws,_wow,_cover):_sheet.freeze_panes='A2';_sheet.auto_filter.ref=_sheet.dimensions
                _ow.save(_out);_ow.close();_wb.close();st.session_state['new_request_file']=str(_out)
                st.success(f'Created a traceable {len(_outrows)}-row order packet: Plan 2026 draft + RP source + WO draft + cover-sheet data + readiness/material checks. Original Plan-2026 was not modified.')
            except Exception as _e:st.error(f'New requirement planning diagnostic: {_e}')

    _nf=Path(st.session_state.get('new_request_file','')) if st.session_state.get('new_request_file') else None
    if _nf and _nf.exists():st.download_button('⬇ STEP 3–5 — DOWNLOAD RP + WO + COVER SHEET + PLAN 2026 DRAFT PACKET',_nf.read_bytes(),_nf.name,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)

if _page == 'knowledge':
    if _page == 'knowledge':
        st.header('📚 Knowledge / ความรู้โรงงาน')
        st.caption('Ask in Thai or English. Answers cite the file they came from. Missing sources stay missing.')
        _knowledge_db=ROOT/'knowledge'/'knowledge_base.sqlite'
        from suite.knowledge_page import render as _render_knowledge_status
        _render_knowledge_status(ROOT,'knpage',lang=lang)
        if not _knowledge_db.exists():
            st.info('Work Order / code / part search needs the records database; see the notice above for how to restore or rebuild it.')
        else:
            try:
                _kc=sqlite3.connect(f'file:{_knowledge_db.as_posix()}?mode=ro',uri=True)
                _src_count=_kc.execute('SELECT COUNT(*) FROM sources').fetchone()[0]
                _row_count=_kc.execute('SELECT COUNT(*) FROM records').fetchone()[0]
                _snap=_kc.execute("SELECT value FROM snapshot_info WHERE key='snapshot_time'").fetchone()[0]
                _met1,_met2,_met3=st.columns(3);_met1.metric('Reference workbooks',_src_count);_met2.metric('Indexed evidence rows',f'{_row_count:,}');_met3.metric('Snapshot captured (Thailand local time — Phan Thong, Chonburi)',datetime.fromisoformat(_snap).astimezone(ZoneInfo('Asia/Bangkok')).strftime('%Y-%m-%d %H:%M:%S'))
                _mode=st.radio('What do you need?', ['Find a code, part or work order','Create / review a WO from RP'],horizontal=True,key='knowledge_mode')
                if _mode.startswith('Find'):
                    with st.form('knowledge_search_form',clear_on_submit=False):
                        _qinput=st.text_input('Enter a full or partial work order, part, material/bond, customer, specification or packaging code, then press Enter',placeholder='Example: PBS002-011026, B0101, 2GG120B1001SAAADAF',key='knowledge_q')
                        _search_clicked=st.form_submit_button('🔎 Search reference database',use_container_width=True)
                    if _search_clicked:st.session_state['knowledge_active_query']=_qinput
                    _q=st.session_state.get('knowledge_active_query','')
                    if _q.strip():
                        _qn=re.sub(r'[^A-Z0-9ก-๙]+','',_q.upper())
                        _hits=knowledge_search_rows(str(_knowledge_db),_qn,_q.strip())
                        if not _hits: st.info('No exact source match found. Try a shorter part of the code or a customer/specification word. No code meaning is invented when the supplied sources do not define it.')
                        else:
                            st.success(f'Found {len(_hits)} source row(s). Review status and dates before treating a historical/template row as a released WO.')
                            _hit_table=pd.DataFrame([{'#':i+1,'Category':r[3],'Source file':r[7],'Sheet':r[1],'Row':r[2],'Evidence quality':r[4],'Evidence preview':r[5][:260]} for i,r in enumerate(_hits)])
                            st.dataframe(_hit_table,use_container_width=True,hide_index=True,height=min(520,40+len(_hits)*36))
                            _choice=st.selectbox('Open one evidence row for full details',range(len(_hits)),format_func=lambda i:f"{_hits[i][7]}  ›  {_hits[i][1]}!Row {_hits[i][2]}  [{_hits[i][4]}]",key='knowledge_hit')
                            _r=_hits[_choice]
                            with st.container(border=True):
                                st.subheader(f'{_r[7]} — {_r[1]}!Row {_r[2]}')
                                try: st.json(json.loads(_r[6]),expanded=False)
                                except: st.write(_r[5])
                                st.caption(f"Evidence: {_r[4]} · Source category: {_r[3]}")
                                st.code(f"Original filename: {_r[7]}\nSource path at snapshot: {_r[8]}\nFile modified: {_r[9]}\nWorkbook modified metadata: {_r[10] or 'not recorded'}\nSHA-256: {_r[11]}\nImported snapshot: {_r[12]}",language=None)
                else:
                    st.markdown('#### Create / review a WO from RP')
                    st.caption('Upload the sales RP and review request rows, linked codes, known master records and gaps before a planner issues the controlled work-order sheet. This screen saves the source and produces a CSV review aid; missing BOM, approved packaging, process or capacity rules are never invented.')
                    _rp=st.file_uploader('Choose RP / customer request workbook (.xlsx)',type=['xlsx'],key='knowledge_rp_upload')
                    if _rp:
                        try:
                            _rp_bytes=_rp.getvalue();_rp_sha=hashlib.sha256(_rp_bytes).hexdigest();_rp_time=datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds')
                            _saved=st.session_state.get('knowledge_rp_saved')
                            if not _saved or _saved.get('sha256')!=_rp_sha:
                                _rp_dir=SOURCE_ARCHIVE/'KNOWLEDGE_RP';_rp_dir.mkdir(parents=True,exist_ok=True)
                                _safe_name=re.sub(r'[^A-Za-z0-9._ -]','_',Path(_rp.name).name)
                                _rp_copy=_rp_dir/f"{datetime.now(ZoneInfo('Asia/Bangkok')).strftime('%Y%m%d_%H%M%S')}_{_safe_name}"
                                _rp_copy.write_bytes(_rp_bytes);_saved={'sha256':_rp_sha,'path':str(_rp_copy.resolve()),'imported_at':_rp_time,'filename':_rp.name};st.session_state['knowledge_rp_saved']=_saved
                            _rw=load_workbook(_rp,read_only=True,data_only=True);_rps=[]
                            for _ws in _rw.worksheets[:8]:
                                for _ri,_row in enumerate(_ws.iter_rows(min_row=1,max_row=300,max_col=80,values_only=True),1):
                                    _vals=[str(v).strip() for v in _row if v is not None and str(v).strip()]
                                    if _vals:_rps.append({'Source workbook':_rp.name,'Stored copy':_saved['path'],'Imported at (Thailand local time — Phan Thong, Chonburi)':_saved['imported_at'],'SHA-256':_rp_sha,'Sheet':_ws.title,'Source row':_ri,'Request details':' | '.join(_vals)[:1200]})
                            _rw.close()
                            st.success(f'Read {_rp.name}: {len(_rps)} populated row(s) across up to 8 sheets. Uploaded evidence saved at {_saved["path"]}')
                            if _rps: st.dataframe(pd.DataFrame(_rps[:200]),use_container_width=True,hide_index=True,height=400)
                            _blob=' '.join(x['Request details'] for x in _rps)
                            _codes=list(dict.fromkeys(re.findall(r'(?i)(?<![A-Z0-9])[A-Z0-9][A-Z0-9-]{3,}(?![A-Z0-9])',_blob)))[:100]
                            _matches=[]
                            for _code in _codes:
                                _key=re.sub(r'[^A-Z0-9ก-๙]+','',_code.upper())
                                _one=_kc.execute('''SELECT s.filename,r.sheet,r.row_number,r.quality,r.body FROM records r JOIN sources s USING(source_id) WHERE r.normalized LIKE ? LIMIT 3''',('%'+_key+'%',)).fetchall()
                                if _one:
                                    for _m in _one:_matches.append({'Request token':_code,'Found in':_m[0],'Source row':f'{_m[1]}!{_m[2]}','Evidence quality':_m[3],'Evidence preview':_m[4][:220]})
                            st.markdown('#### Reference matches and gaps')
                            if _matches:st.dataframe(pd.DataFrame(_matches),use_container_width=True,hide_index=True,height=360)
                            else:st.warning('No request codes matched the current reference snapshot. Confirm part/customer/material masters and attach their approved source.')
                            _gap_codes=[x for x in _codes if not any(m['Request token']==x for m in _matches)]
                            if _gap_codes:st.warning('Unmatched request tokens to confirm: '+', '.join(_gap_codes[:40]))
                            st.download_button('⬇ Download RP first-pass review CSV',pd.DataFrame(_rps).to_csv(index=False).encode('utf-8-sig'),f'RP_REVIEW_{Path(_rp.name).stem}.csv','text/csv')
                        except Exception as _e:st.error(f'Could not read this RP workbook: {_e}')
                with st.expander('📖 Help / Glossary — meaning, use and source rules',expanded=False):
                    _glossary=[
                        ('Work Order / ProductionCode','Unique production tracking code, such as PBS002-011026. Use it to trace order status across the cover sheet and Plan-2026. A code appearing in a template is not proof the WO was released.'),
                        ('RP / Sales release','Customer or sales request input. Review customer, requested product/specification, quantity, requested date, packaging, marks and special process controls before creating the WO.'),
                        ('S&OP / Order NO.','Planning/sales reference that connects release demand to the monthly plan. The October cover sheet has actual order rows; blank/#N/A blue-sheet rows are not treated as released.'),
                        ('Product code / Real Spec / D-T-H','Look up the complete product code and the specification fields in the supplied product master/cover. Do not infer code segments unless an approved decoding table defines them.'),
                        ('Bond code and abrasive/material code','Bond MRP lists stock, issue average, outstanding PO, demand and planned release by material code. It does not provide a complete approved recipe/BOM; confirm formula/recipe against released production instructions.'),
                        ('On hand / Average issue / On order / MRP / Safety stock','Separate stock and demand signals from the October Bond Order Release workbook. Its visible deficit formula is On Hand minus MRP; PO and safety-stock columns are not included in that formula, so treat the displayed deficit as source formula output, not a buy recommendation.'),
                        ('Packaging / customer / vendor code','Use approved packaging, customer and vendor masters. If no complete master appears in the indexed sources, the lookup shows no source-backed definition instead of guessing.'),
                        ('Source row / confidence','Every answer carries workbook, sheet, row, source timestamp and file hash. “Incomplete / formula error” or “template/blank-status possible” means confirm before use.'),
                    ]
                    for _term,_definition in _glossary:st.markdown(f'**{_term}**  \n{_definition}')
                    st.info('Planning hand-off checks: as-of date = today; customer commitment vs internal revised date; active WIP and section closure; material available and incoming PO dates; route/process sequence; capacity/machine/mould/operator availability; drying/firing/cooling/finishing lead times; packaging and quality controls. Unknown constraints remain visible for the planner to resolve.')
                with st.expander('📁 Snapshot file list and provenance',expanded=False):
                    _files=_kc.execute('SELECT filename,path,size_bytes,filesystem_modified,workbook_modified,sha256,snapshot_time FROM sources ORDER BY filename').fetchall()
                    st.dataframe(pd.DataFrame(_files,columns=['Imported original filename','Path at import','Bytes','File modified','Workbook modified','SHA-256','Snapshot captured']),use_container_width=True,hide_index=True)
                    st.caption(f'Bundled read-only reference database: {_knowledge_db.resolve()} · Refresh it when new approved source files arrive; this snapshot does not silently update itself.')
                _kc.close()
            except Exception as _e:st.error(f'Knowledge database could not be opened: {_e}')

    else:
        st.info('Open Code & Part Knowledge from the MAIN sidebar or Home shortcut to search the local index.')

if _page == 'history':
    st.header('🕘 Software Usage & Edit History')
    st.caption('Shows real saved edits/audits from the current shared database. Demo/bundled history is not treated as actual factory usage.')
    st.caption('Who used the system, what was edited/imported/scanned/exported, and when.')
    _hist=[]
    try:
        con=sqlite3.connect(OVERRIDE_DB);_a=pd.read_sql_query('SELECT user_name AS User,action AS Action,entity AS Entity,entity_id AS ID,details AS Details,created_at AS Time FROM audit_log ORDER BY created_at DESC',con);con.close();_hist.append(_a)
    except Exception as _e: st.info(f'Audit log: {_e}')
    _o=override_audit()
    if not _o.empty:
        _o2=_o.rename(columns={'Edited By':'User','Field':'Action','Work Order':'ID','Value':'Details','Edited At':'Time'});_o2['Entity']='PLAN FIELD EDIT';_hist.append(_o2[[c for c in ['User','Action','Entity','ID','Details','Time'] if c in _o2]])
    if _hist:
        _hh=pd.concat(_hist,ignore_index=True,sort=False);_hh['Time']=pd.to_datetime(_hh['Time'],errors='coerce');_hh=_hh.sort_values('Time',ascending=False);st.dataframe(_hh,use_container_width=True,hide_index=True,height=650);st.download_button('⬇ DOWNLOAD HISTORY',_hh.to_csv(index=False).encode('utf-8-sig'),'SL_Software_History.csv','text/csv')
    else: st.info('No usage/edit history yet.')

if _page == 'suite':
    try:
        from suite.suite_page import render as _suite_render
        _suite_render(fp,DATA,SHARED_ROOT,register_source,st.session_state.get('sl_user',''))
    except Exception as _se:
        st.error(f'Planning Suite error: {_se}')

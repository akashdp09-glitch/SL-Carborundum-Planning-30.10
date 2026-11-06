"""Prominent shared desktop/mobile tracking entry; no scanner-model dependency."""
import html,io,hashlib,os
from pathlib import Path
from .qr_png import make as _make_qr_png
from urllib.parse import urlsplit,urlunsplit
import qrcode
from . import production_evidence as E


def styles(st):
    st.markdown('''<style>
.sl-task-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.sl-task-card{background:#fff!important;color:#12395b!important;min-height:94px;padding:12px;border:1px solid #d7e1eb;border-left:5px solid #e76613;border-bottom:1px solid #d7e1eb;border-radius:12px;gap:3px}.sl-task-card span{font-size:2.8rem;line-height:1.1}.sl-task-card b{font-size:1.32rem;line-height:1.35}.sl-task-card strong{font-size:.83rem;font-weight:500}.sl-task-card small{font-size:.75rem;color:#43566b}.sl-track-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}.sl-track-card{display:grid;grid-template-columns:58px 1fr;align-items:center;gap:8px;text-decoration:none!important;background:#fff;color:#12395b!important;border:1px solid #d4e0eb;border-left:6px solid #e76613;border-radius:12px;padding:12px;min-height:88px}.sl-track-card .icon{font-size:2.7rem}.sl-track-card b{display:block;font-size:1.4rem;line-height:1.35}.sl-track-card small{font-size:.82rem;color:#43566b}.sl-track-card:focus-visible{outline:3px solid #e76613}.sl-quicklinks a span{font-size:2rem!important}
@media(max-width:900px){.sl-task-grid,.sl-track-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:450px){.sl-track-card{grid-template-columns:44px 1fr;padding:9px}.sl-track-card b{font-size:1.15rem}.sl-track-card .icon{font-size:2.2rem}.sl-task-card b{font-size:1.2rem}}
</style>''',unsafe_allow_html=True)


def validate_base(value):
    u=urlsplit(str(value).strip())
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment:raise ValueError('Use a server URL, e.g. http://server-address:8000; no login/query details')
    _=u.port
    path=u.path.rstrip('/')
    if path.endswith('/scan') or path.endswith('/mobile'):path=path.rsplit('/',1)[0]
    return urlunsplit((u.scheme,u.netloc,path,'',''))


def render(st,default_base,db_path,*,can_edit=False,user='',key='track'):
    evidence=Path(db_path).parent/'production_analytics.sqlite'
    with E.connect(evidence) as con:
        con.execute('CREATE TABLE IF NOT EXISTS tracking_addresses(id INTEGER PRIMARY KEY,value TEXT NOT NULL,reason TEXT NOT NULL,author TEXT NOT NULL,recorded_at TEXT NOT NULL)')
        row=con.execute('SELECT value FROM tracking_addresses ORDER BY id DESC LIMIT 1').fetchone()
    saved=row[0] if row else None
    # settings() values contain the setting payload, not the audit history.
    if isinstance(saved,dict):saved=saved.get('value')
    base=validate_base(saved or default_base)
    st.subheader('🔎 ติดตามชิ้นงานและตรวจ WIP / Track · scan · audit')
    actions=[('🔫','สแกนบนคอมพิวเตอร์','Desktop scanner','/scan'),('📸','ตรวจนับ WIP','Physical WIP audit','/mobile/find'),('📋','ทะเบียนและภาพถ่าย','Part register & photos','/register'),('🕘','ประวัติและรายงาน Excel','History & Excel reports','/tracking-reports'),('▦','สร้างและพิมพ์ QR','Create / print QR labels','/qr-generator'),('📱','ตรวจนับบนมือถือ','Mobile audit','/scan?mode=mobile')]
    cards=''.join(f'<a class="sl-track-card" target="_self" href="{html.escape(base+path,quote=True)}"><span class="icon">{icon}</span><span><b>{th}</b><small>{en}</small></span></a>' for icon,th,en,path in actions)
    st.markdown('<div class="sl-track-grid">'+cards+'</div>',unsafe_allow_html=True)
    st.code(base+'/scan',language=None)
    a,b=st.columns([1,3])
    image=_make_qr_png(base+'/scan');bio=io.BytesIO();image.save(bio,format='PNG');data=bio.getvalue()
    shared=Path(os.environ.get('SL_SHARED_ROOT',str(Path(db_path).parent.parent)))
    folder=shared/'QR'/'ACCESS';folder.mkdir(parents=True,exist_ok=True);file=folder/('desktop_scan_'+hashlib.sha256(base.encode()).hexdigest()[:12]+'.png')
    if not file.exists():file.write_bytes(data)
    a.image(data,width=160,caption='QR เปิดหน้าสแกน / Open scanner')
    b.markdown('**📱 ตรวจนับมือถือ / Mobile audit**')
    b.code(base+'/scan?mode=mobile',language=None)
    from .qr_png import make as _mobile_qr
    mobile_buf=io.BytesIO();_mobile_qr(base+'/scan?mode=mobile').save(mobile_buf,format='PNG')
    mobile_file=folder/('mobile_audit_'+hashlib.sha256(base.encode()).hexdigest()[:12]+'.png')
    if not mobile_file.exists():mobile_file.write_bytes(mobile_buf.getvalue())
    b.image(mobile_buf.getvalue(),width=160,caption='QR มือถือ / Mobile audit')
    with st.expander('ที่อยู่เซิร์ฟเวอร์และ QR / Server address'):
        st.caption('Use the address reachable from your factory devices. A container address or an example IP is not assumed to be the factory server.')
        value=st.text_input('ที่อยู่ / Server URL',base,key=key+'_server')
        reason=st.text_input('เหตุผลการเปลี่ยน / Change reason',key=key+'_server_reason')
        if st.button('บันทึกที่อยู่ / Save address',key=key+'_server_save',disabled=not can_edit):
            try:
                if not reason.strip():raise ValueError('Enter the change reason')
                from .common import bkk_now
                with E.connect(evidence) as con:con.execute('INSERT INTO tracking_addresses(value,reason,author,recorded_at) VALUES(?,?,?,?)',(validate_base(value),reason,user,bkk_now().isoformat()))
                st.rerun()
            except Exception as exc:st.error(str(exc))

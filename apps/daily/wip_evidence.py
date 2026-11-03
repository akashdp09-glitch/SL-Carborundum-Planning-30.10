"""Read physical XLSX cells, never pad inflated sheet dimensions.
Cached formula errors stay missing; source rows and original labels are retained.
No scheduling or safety overrides are applied by this review layer.
"""
from pathlib import Path
from io import BytesIO
import hashlib, zipfile, posixpath
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import pandas as pd

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
CATS=['P','R','S','T','M','PB']
FIELDS={'Fac No':'Work Order','Spec':'Specification','คงเหลือ (Pcs.)':'Production WIP pcs','Status Job':'Production status','Group (Pcs.)':'Category','Total GW (Kg)':'Production gross kg','จำนวนตัด/ก้อน':'Production cut factor'}

def payload(source):
    return source.getvalue() if hasattr(source,'getvalue') else Path(source).read_bytes()

def list_sheet_names(source):
    with zipfile.ZipFile(BytesIO(payload(source))) as z:
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        return [x.attrib.get('name','') for x in wb.find('m:sheets',NS)]

def read_wo_evidence(source,section,sheet='กันยายน'):
    b=payload(source);digest=hashlib.sha256(b).hexdigest();rows=[]
    with zipfile.ZipFile(BytesIO(b)) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                for _,e in ET.iterparse(f,events=('end',)):
                    if e.tag.endswith('}si'):
                        strings.append(''.join(t.text or '' for t in e.iter() if t.tag.endswith('}t')));e.clear()
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        sh=next((x for x in wb.find('m:sheets',NS) if x.attrib['name']==sheet),None)
        if sh is None:raise ValueError('Missing worksheet '+sheet)
        rid=sh.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        rel=next(x for x in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')) if x.attrib['Id']==rid)
        target=rel.attrib['Target'];target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        headers={}
        with z.open(target) as f:
            for _,e in ET.iterparse(f,events=('end',)):
                if not e.tag.endswith('}row'):continue
                rn=int(e.attrib['r']);vals={};errors=[]
                for c in e:
                    col=''.join(x for x in c.attrib.get('r','') if x.isalpha())
                    typ=c.attrib.get('t');v=c.find('m:v',NS);v=v.text if v is not None else None
                    if typ=='s' and v is not None:v=strings[int(v)]
                    elif typ=='inlineStr':v=''.join(t.text or '' for t in c.iter() if t.tag.endswith('}t'))
                    elif typ=='e':errors.append(col+':'+str(v));v=None
                    vals[col]=v
                if rn==3:
                    headers={c:FIELDS[str(v).strip()] for c,v in vals.items() if str(v).strip() in FIELDS}
                    missing=set(['Work Order','Production WIP pcs','Production status','Category'])-set(headers.values())
                    if missing:raise ValueError('Unrecognized WIP schema: '+', '.join(sorted(missing)))
                elif rn>3:
                    row={name:vals.get(col) for col,name in headers.items()}
                    if str(row.get('Work Order') or '').strip():
                        row.update({'Section':section,'Source file':Path(getattr(source,'name',str(source))).name,'Source sheet':sheet,'Source row':rn,'Source SHA256':digest,'Source errors':'; '.join(errors)})
                        rows.append(row)
                e.clear()
    d=pd.DataFrame(rows)
    if d.empty:return d
    d['Source category']=d['Category']
    d['Category']=d['Category'].fillna('').astype(str).str.strip().str.upper().replace({'F':'P'})
    d['Work Order']=d['Work Order'].astype(str).str.strip().str.upper()
    for c in ['Production WIP pcs','Production gross kg','Production cut factor']:
        if c in d:d[c]=pd.to_numeric(d[c],errors='coerce')
    d['Production status']=d['Production status'].fillna('').astype(str).str.strip()
    def issues(r):
        a=[]
        if r['Category'] not in CATS:a.append('Unknown category')
        if pd.isna(r['Production WIP pcs']):a.append('Missing quantity')
        elif r['Production WIP pcs']<0:a.append('Negative balance')
        if r['Source errors']:a.append('Source formula error')
        if r['Production status'] not in ['ยังไม่ปิด','ปิดใบสั่ง']:a.append('Unmapped status')
        if r['Production status']=='ปิดใบสั่ง' and r['Production WIP pcs']!=0:a.append('Closed with nonzero balance')
        return '; '.join(a)
    d['Data issues']=d.apply(issues,axis=1)
    d['Evidence ID']=d['Source SHA256']+':'+d['Source sheet']+':'+d['Source row'].astype(str)
    return d

def reconcile(master,production):
    """Preserve Production rows; ambiguous Planning WOs cannot become a false match."""
    out=production.copy()
    cols={'Mixing':['Ready for Mixing','WIP Mixing'],'Forming':['Ready for Forming','WIP Forming'],'Firing + curing':['Ready for Firing','WIP Firing'],'Grinding / Cutting (Production combined)':['Ready for Grinding / Cutting','WIP Grinding / Cutting'],'Packing':['Ready for Packing','WIP Packing']}
    if master is None or 'Work Order' not in master:
        out['Planning WIP pcs']=float('nan');out['Comparison status']='PLANNING NOT LOADED';return out
    m=master.copy();m['Work Order']=m['Work Order'].astype(str).str.strip().str.upper()
    dup=set(m.loc[m['Work Order'].duplicated(False),'Work Order']);m=m.drop_duplicates('Work Order').set_index('Work Order')
    qty=[];category=[];basis=[];status=[]
    for _,r in out.iterrows():
        wo=r['Work Order'];sec=r['Section'];c=next((c for c in cols.get(sec,[]) if c in m),None)
        q=pd.to_numeric(m.at[wo,c],errors='coerce') if wo in m.index and wo not in dup and c else float('nan')
        cat=str(m.at[wo,'Category']).strip().upper() if wo in m.index and 'Category' in m else ''
        if cat=='F':cat='P'
        qty.append(q);category.append(cat);basis.append(c or 'Missing stage column')
        issue='DUPLICATE PLANNING WO' if wo in dup else ('PLANNING WO NOT FOUND' if wo not in m.index else 'REVIEW COMMON CUTOFF / ROUTE / UNITS')
        if sec.startswith('Grinding'):issue='VERIFY CUT FACTOR / PIECE BASIS — NO AUTOMATIC CONVERSION'
        if cat and cat!=r['Category']:issue+='; CATEGORY DISAGREEMENT'
        status.append(issue)
    out['Planning category']=category;out['Planning WIP pcs']=qty;out['Planning source column']=basis
    # Difference is diagnostic; no numerical MATCH status without unit and cutoff confirmation.
    out['Recorded pcs difference (unverified basis)']=out['Production WIP pcs']-out['Planning WIP pcs']
    out['Comparison status']=status
    return out

def render_wo_review(st,master,base_dir,sources,uploads,snapshot):
    st.subheader('Work-order reconciliation and actions')
    section=st.selectbox('① Process / WO evidence source',list(sources),key='wo_evidence_section')
    source=uploads[section] or Path(base_dir)/sources[section]
    try:sheets=list_sheet_names(source)
    except Exception as exc:st.error(f'Cannot inspect WIP workbook sheets: {exc}');return
    thai_months=['มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน','กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']
    import datetime as dt
    current_month=thai_months[dt.date.today().month-1]
    default_sheet=next((x for x in sheets if current_month in x),next((x for x in sheets if any(m in x for m in thai_months)),sheets[0] if sheets else ''))
    sheet=st.selectbox('Monthly WIP detail sheet / ชีตรายละเอียดประจำเดือน',sheets,index=sheets.index(default_sheet) if default_sheet in sheets else 0,key='wo_evidence_sheet_'+section) if sheets else ''
    digest=hashlib.sha256(payload(source)).hexdigest()+':'+sheet
    key='wo_evidence_'+digest
    if key not in st.session_state:
        with st.spinner('Reading source WO cells...'):st.session_state[key]=read_wo_evidence(source,section,sheet=sheet)
    raw=st.session_state[key].copy()
    if raw.empty:st.info('No WO rows');return
    d=reconcile(master,raw)
    if isinstance(master,pd.DataFrame) and not master.empty and 'Work Order' in master:
        _md=master.copy();_md['_wo_key']=_md['Work Order'].astype(str).str.upper().str.replace(r'[^A-Z0-9]','',regex=True)
        _md=_md.drop_duplicates('_wo_key',keep='last').set_index('_wo_key')
        _dk=d['Work Order'].astype(str).str.upper().str.replace(r'[^A-Z0-9]','',regex=True)
        for _src,_dest in [('Customer','Customer'),('Product Code','Planning product'),('Due Date','Planning due date')]:
            if _src in _md:d[_dest]=_dk.map(_md[_src])
    else:d['Customer']='Planning source not loaded'
    for _col in ['Customer','Planning product','Planning due date']:
        if _col not in d:d[_col]=''
    for c in ['Confirmed cause','Corrective action','Owner','Action due','Review status']:d[c]=''
    import review_store
    if 'wo_action_notes' not in st.session_state:
        try:
            saved=review_store.load(base_dir)
            st.session_state['wo_action_notes']=saved.get('notes',{})
            st.session_state['wo_action_audit']=saved.get('audit',[])
        except Exception as exc:st.warning('Saved review could not be loaded: '+str(exc))
    notes=st.session_state.setdefault('wo_action_notes',{})
    for i,r in d.iterrows():
        for c,v in notes.get(r['Evidence ID'],{}).items():d.at[i,c]=v
    a,b,c=st.columns(3)
    mode=st.session_state.get('wo_evidence_mode','All')
    if a.button('All source rows: '+str(len(d)),key='wo_all'):mode='All'
    if b.button('Source issues: '+str(d['Data issues'].ne('').sum()),key='wo_issues'):mode='Issues'
    if c.button('Open rows: '+str(d['Production status'].eq('ยังไม่ปิด').sum()),key='wo_open'):mode='Open'
    st.session_state['wo_evidence_mode']=mode
    visible=d if mode=='All' else d[d['Data issues'].ne('') if mode=='Issues' else d['Production status'].eq('ยังไม่ปิด')]
    catpick=st.selectbox('② Product category / กลุ่มสินค้า',['All categories']+CATS,key='wo_evidence_category_v13')
    if catpick!='All categories':visible=visible[visible.Category.eq(catpick)]
    customers=sorted(visible['Customer'].fillna('Not recorded').astype(str).unique().tolist()) if 'Customer' in visible else []
    customerpick=st.selectbox('③ Customer / ลูกค้า',['All customers']+customers,key='wo_evidence_customer_v13')
    if customerpick!='All customers' and 'Customer' in visible:visible=visible[visible['Customer'].fillna('Not recorded').astype(str).eq(customerpick)]
    query=st.text_input('Find WO',key='wo_evidence_search').strip().upper()
    if query:visible=visible[visible['Work Order'].str.contains(query,regex=False)]
    st.caption(f'Hierarchy: {section} → {catpick} → {customerpick} → work orders. Filter results: {len(visible):,} rows. Firing includes curing-area evidence; Grinding/Cutting remains combined in Production records.')
    st.caption('Recorded piece differences require a common cutoff and confirmed cut factor. Source file, sheet, row, hash and evidence ID are retained.')
    fields=['Work Order','Customer','Planning product','Planning due date','Category','Production WIP pcs','Planning WIP pcs']
    fields += [c for c in ['Recorded pcs difference (unverified basis)','Comparison status','Data issues','Production status','Confirmed cause','Corrective action','Owner','Action due','Review status','Source file','Source sheet','Source row','Evidence ID'] if c in visible]
    editable=['Confirmed cause','Corrective action','Owner','Action due','Review status']
    _page_size=200;_pages=max(1,(len(visible)+_page_size-1)//_page_size)
    _page=st.number_input(f'④ Results page (up to {_page_size} rows/page)',1,_pages,1,1,key='wo_evidence_page_v13')
    _page_rows=visible.iloc[(int(_page)-1)*_page_size:int(_page)*_page_size]
    edited=st.data_editor(_page_rows[fields],disabled=[c for c in fields if c not in editable],hide_index=True,use_container_width=True,key='wo_notes_'+digest+'_'+str(int(_page)))
    changed=False
    for _,r in edited.iterrows():
        identity=r['Evidence ID'];new={c:r[c] for c in editable};old=notes.get(identity,{c:'' for c in editable})
        if new!=old:
            changed=True
            st.session_state.setdefault('wo_action_audit',[]).append({'UTC':datetime.now(timezone.utc).isoformat(),'Evidence ID':identity,'Before':str(old),'After':str(new)})
        notes[identity]=new
    if changed:
        try:review_store.save(base_dir,notes,st.session_state.get('wo_action_audit',[]))
        except Exception as exc:st.error('Review could not be saved: '+str(exc))
    for i,r in d.iterrows():
        for c,v in notes.get(r['Evidence ID'],{}).items():d.at[i,c]=v
    st.session_state.setdefault('wo_reconciliation_current',{})[section]=d
    st.download_button('Download complete WO evidence and actions',d.to_csv(index=False).encode('utf-8-sig'),'WO_reconciliation.csv','text/csv',key='wo_export')

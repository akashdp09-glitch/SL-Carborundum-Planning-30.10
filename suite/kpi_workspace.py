"""Retained workbook-based staff KPI and daily opening/closure evidence."""
from __future__ import annotations
import calendar,io,json,sqlite3
from datetime import date,datetime
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from . import production_evidence as E
from .common import bkk_today

STAFF=[('Soi / Chosita','accuracy','Planning data accuracy',15),('Soi / Chosita','staff_plan_preparation','On-time plan preparation',15),('Soi / Chosita','staff_wip_reporting','On-time WIP reporting',5),('Soi / Chosita','staff_risk_reporting','On-time risk reporting',5),('Pui / Sirinun','staff_material_readiness','Material readiness',20),('Pui / Sirinun','staff_wo_issuance','On-time WO issuance',20)]


def staff_results(path,period):
    v=E.automatic_values(path);rows=[]
    for person,measure,label,marks in STAFF:
        found=v[v.period.eq(period)&v.measure.eq(measure)] if not v.empty else pd.DataFrame()
        row=found.iloc[0].to_dict() if not found.empty else {}
        rows.append({'Person':person,'KPI':label,'Achievement %':row.get('value'),'Maximum marks':marks,
                     'Numerator':row.get('numerator'),'Denominator':row.get('denominator'),'Recorded days':row.get('observations'),
                     'Source':row.get('filename','Not recorded'),'Cells':row.get('ref',''),'Method':row.get('method','Monthly evidence not recorded'),
                     'Review':row.get('conflict',''),'Awarded HR marks':'Not calculated — HR score conversion not approved'})
    return pd.DataFrame(rows)


def count_details(path):
    """Known 31-day category matrices. Preserve blank cells as unknown, not zero."""
    sources=E.source_list(path);rows=[]
    for role in ('planning_open','planning_close'):
        selected=sources[sources.role.eq(role)] if not sources.empty else pd.DataFrame()
        if selected.empty:continue
        sid=int(selected.id.max())
        with E.connect(path) as con:
            original,filename,cfg=con.execute('SELECT original,filename,config FROM evidence_documents WHERE id=?',(sid,)).fetchone()
        config=json.loads(cfg);year=int(config.get('year',bkk_today().year))
        wb=load_workbook(io.BytesIO(original),read_only=True,data_only=True)
        try:
            sheet='Open Job' if role=='planning_open' else 'Close Job'
            if sheet not in wb.sheetnames:continue
            ws=wb[sheet];grid=list(ws.iter_rows(max_row=13,max_col=66,values_only=True))
            title=' '.join(str(x or '') for row in grid[:2] for x in row[:4])+' '+filename
            hits=[(title.casefold().find(word),m) for m,words in enumerate(E.MONTHS,1) for word in words if word in title.casefold()]
            month=min(hits)[1] if hits else int(str(config.get('month',''))[-2:])
            blocks=[(3,'Sales input','reported jobs'),(35,'Opened / issued','reported item count')] if role=='planning_open' else [(3,'Closed','reported item count')]
            for start,measure,unit in blocks:
                for r in range(3,13):
                    category=str(grid[r-1][1] or '').strip()
                    band=range(3,8) if r<8 else range(8,13)
                    labels=[str(grid[x-1][0]).strip() for x in band if grid[x-1][0] is not None]
                    group=labels[0] if len(set(labels))==1 else ('MTO' if r<8 else 'MTS')+' (template band)'
                    for day in range(1,calendar.monthrange(year,month)[1]+1):
                        c=start+day-1;raw=grid[r-1][c-1];value=E.number(raw)
                        rows.append({'Date':pd.Timestamp(date(year,month,day)),'Measure':measure,'Group':group,'Category':category,
                                     'Value':value,'Recorded':value is not None,'Unit':unit,'Source':filename,'Sheet':sheet,'Cell':f'{E.letter(c)}{r}','Source ID':sid})
        finally:wb.close()
    return pd.DataFrame(rows)


def count_summary(frame,dimensions):
    if frame.empty:return pd.DataFrame()
    return frame.groupby(dimensions+['Measure','Unit'],dropna=False).agg(Value=('Value',lambda s:s.sum(min_count=1)),Recorded_cells=('Recorded','sum'),Source_cells=('Recorded','size')).reset_index()


def workbook_report(path,period,production=None):
    from .exporters import to_workbook
    staff=staff_results(path,period);daily=count_details(path)
    if not daily.empty:daily=daily[daily.Date.dt.strftime('%Y-%m').eq(period)].copy()
    dept=E.department_results(path,period,frame=production)
    sources=E.source_list(path).drop(columns=['inventory','config'],errors='ignore')
    return to_workbook({'Soi Chosita':staff[staff.Person.str.startswith('Soi')], 'Pui Sirinun':staff[staff.Person.str.startswith('Pui')],
        'Department KPI':dept,'Daily open close':count_summary(daily,['Date']),'Category counts':count_summary(daily,['Group','Category']),
        'Source cells':daily,'Source register':sources,
        'Read first':pd.DataFrame({'Notes':['Soi=Chosita; Pui=Sirinun (owner confirmed).','Sirinun monthly October cells are blank; supporting October summary provides the ratios.','Staff maxima: Soi 15+15+5+5=40; Pui 20+20=40. HR awarded-score conversion is not invented.','Sales input jobs, issued items and closure items are distinct measures. They are not verified distinct WO identities.','Backlog closure identities cannot be recovered from category totals. Packing final actual uses Pack จ่าย only.','Section/category Production KPI workbooks are independent views; never add them together as extra actual output.']})})


def upload_center(st,db_path,can_edit,user,*,key='home',groups=('staff','counts','production')):
    from .production_analysis_page import evidence_path
    path=evidence_path(db_path)
    st.subheader('📥 เลือกไฟล์ / Upload files')
    labels={'staff':('👥 KPI สอย · ปุ้ย / Staff KPI','KPI_Chosita_completed · KPI_Sirinun_monthly · Production KPI section/category'), 'counts':('📊 เปิด–ปิดใบสั่ง / Open–close orders','October_in out · October-2026_job closure'), 'production':('🏭 สถานะการผลิต / Production status','สถานะการผลิต 2026-4 88')}
    files=[]
    columns=st.columns(len(groups))
    for col,group in zip(columns,groups):
        with col:
            title,hint=labels[group];st.markdown('**'+title+'**');st.caption(hint)
            chosen=st.file_uploader(title,type=['xlsx','xlsm'],accept_multiple_files=True,key=key+'_'+group+'_uploads',disabled=not can_edit)
            files.extend(chosen or [])
    if not can_edit:st.info('เข้าสู่ระบบเพื่ออัปโหลด / Sign in to upload')
    src=E.source_list(path)
    allowed=set()
    if 'staff' in groups:allowed.update(['analyst_kpi','staff_reference','production_kpi_section','production_kpi_category'])
    if 'counts' in groups:allowed.update(['planning_open','planning_close'])
    if 'production' in groups:allowed.update(['production_status'])
    if not src.empty:src=src[src.role.isin(allowed)]
    if not src.empty:
        with st.expander('ไฟล์ที่บันทึกแล้ว / Saved files'):
            latest=src.sort_values('id',ascending=False).drop_duplicates('role')
            st.dataframe(latest[['role','filename','revision','imported_at']],hide_index=True,use_container_width=True)
    with st.expander('รูปแบบไฟล์ฝ่ายผลิต / Production KPI format options'):
        role=st.selectbox('รูปแบบ / Format',['auto','production_kpi_section','production_kpi_category'],key=key+'_kpi_role')
        year=st.number_input('ปีรายงาน / Reporting year',2020,2100,bkk_today().year,key=key+'_kpi_year')
        month=st.text_input('เดือนของตารางรายวัน YYYY-MM / Matrix month',value='',key=key+'_kpi_month')
        unit=st.selectbox('หน่วย / Source unit',['work orders','pieces','tonnes'],key=key+'_kpi_unit')
    if st.button('💾 บันทึกไฟล์ที่เลือก / Save selected files',type='primary',key=key+'_kpi_save',disabled=not files or not can_edit):
        errors=False
        for f in files or []:
            try:
                result=E.import_workbook(path,f.getvalue(),f.name,user,role,dict(year=int(year),month=month,unit=unit,forming_unit='g',report_basis='Production plan'))
                st.success(f'{f.name}: {result["status"]} · revision {result["revision"]}')
            except Exception as exc:errors=True;st.error(f'{f.name}: {exc}')
        if not errors:st.rerun()


def render(st,db_path,*,can_edit=False,user='Unknown'):
    from .production_analysis_page import evidence_path,retained_frame,production_revision,show_table,chart
    path=evidence_path(db_path);st.header('🎯 KPI บุคลากรและเปิด–ปิดงาน / Staff KPI & open–close')
    upload_center(st,db_path,can_edit,user,key='staff60',groups=('staff',))
    values=E.automatic_values(path);periods=sorted(set(values.period)) if not values.empty else []
    if not periods:return
    period=st.selectbox('เดือน / Month',periods,index=len(periods)-1,key='staff_period')
    staff=staff_results(path,period)
    for person in ['Soi / Chosita','Pui / Sirinun']:
        subset=staff[staff.Person.eq(person)];show_table(st,person,subset)
        chart(st,subset,'KPI','Achievement %',title=person+' · achievement (not HR marks)')
    st.info('Sirinun monthly October cells are not populated. Pui’s ratios shown here come from the two October supporting summaries, not invented monthly entries. Zero and missing are different. Raw monthly/daily conflicts stay flagged.')
    daily=count_details(path)
    if not daily.empty:
        daily=daily[daily.Date.dt.strftime('%Y-%m').eq(period)].copy()
        kind=st.selectbox('ช่วงกราฟ / Chart period',['day','week','month'],key='open_close_period')
        daily['Period']=daily.Date.dt.strftime('%Y-%m-%d') if kind=='day' else daily.Date.dt.to_period('W-SUN' if kind=='week' else 'M').astype(str)
        summary=count_summary(daily,['Period'])
        chart(st,summary,'Period','Value','Measure','Reported opening / closure counts')
        show_table(st,'Source count reconciliation',count_summary(daily,['Group','Category']))
        st.caption('Input = reported jobs; issued/closed = reported item counts. Blank source cells remain unknown. Closed/opened is not proof of unique-WO or backlog closures.')
    src=E.source_list(path);prod=retained_frame(str(path),production_revision(src))
    show_table(st,'Department — derived, not a fourth staff KPI',E.department_results(path,period,frame=prod))
    st.download_button('⬇ รายงาน KPI แยกบุคคล / Separate staff & department Excel',workbook_report(path,period,prod),f'Planning_KPI_{period}.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')



def render_open_close(st,db_path,*,can_edit=False,user="Unknown"):
    from .production_analysis_page import evidence_path,chart,show_table
    path=evidence_path(db_path);st.header('📊 รายงาน MD เปิด–ปิดใบสั่ง / MD open–close report')
    st.caption('Operational report, not an additional staff KPI. Revised opening and separate closure workbooks only.')
    upload_center(st,db_path,can_edit,user,key='md60',groups=('counts',))
    d=count_details(path)
    if d.empty:st.info('ใช้ไฟล์ที่ Home → KPI และสถานะผลิต / Import the revised opening and closure originals once on Home');return
    months=sorted(d.Date.dt.strftime('%Y-%m').unique());period=st.selectbox('เดือน / Month',months,index=len(months)-1,key='md55_month')
    d=d[d.Date.dt.strftime('%Y-%m').eq(period)].copy()
    group=st.selectbox('กลุ่ม / MTO-MTS',['All']+sorted(d.Group.unique()),key='md55_band')
    if group!='All':d=d[d.Group.eq(group)]
    granularity=st.radio('ช่วงเวลา / Period',['Daily','Weekly','Monthly'],horizontal=True,key='md55_period')
    d['Period']=d.Date.dt.strftime('%Y-%m-%d') if granularity=='Daily' else d.Date.dt.to_period('W-SUN' if granularity=='Weekly' else 'M').astype(str)
    totals=count_summary(d,[])
    for col,(_,row) in zip(st.columns(3),totals.iterrows()):col.metric(row.Measure,f'{row.Value:,.0f}' if pd.notna(row.Value) else 'Not recorded')
    for measure in ['Sales input','Opened / issued','Closed']:
        subset=d[d.Measure.eq(measure)]
        plot=count_summary(subset,['Period','Category'])
        chart(st,plot,'Period','Value','Category',measure+' · category-stacked source counts')
    comparison=count_summary(d[d.Measure.isin(['Opened / issued','Closed'])],['Period'])
    chart(st,comparison,'Period','Value','Measure','Issued vs closed — reported items')
    show_table(st,'Category and MTO/MTS reconciliation',count_summary(d,['Group','Category']))
    st.caption('Source category totals reconcile directly to the selected cells. Blanks remain unrecorded; categories can have no reported activity. These files contain aggregate counts, not individual WO identities or a verifiable backlog-closure split.')
    if st.button('เตรียม Excel / Prepare Excel',key='md55_excel'):
        from .exporters import to_workbook
        st.download_button('⬇ MD open–close Excel',to_workbook({'Daily':count_summary(d,['Date']),'Categories':count_summary(d,['Group','Category']),'Source cells':d}),'MD_Open_Close_'+period+'.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

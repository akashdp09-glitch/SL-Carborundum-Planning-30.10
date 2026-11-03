"""Generate management presentation from currently loaded planner data. No fabricated metrics."""
from io import BytesIO
import pandas as pd

def period_bounds(period, report_date):
    end=pd.Timestamp(report_date).normalize()
    if period=='Weekly':start=end-pd.Timedelta(days=end.weekday())
    elif period=='Monthly':start=end.replace(day=1)
    elif period=='Mid-year':start=end.replace(month=1 if end.month<=6 else 7,day=1)
    elif period=='Yearly':start=end.replace(month=1,day=1)
    else:raise ValueError('Unknown report period: '+period)
    return start,end

def generate(period, master, risk, production, job, report_date, reconciliation=None, kpi=None, source_note=None):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5)
    orange=RGBColor(231,112,31);navy=RGBColor(29,45,67);grey=RGBColor(95,105,115)
    def slide(title, subtitle='', lines=()):
        sl=prs.slides.add_slide(prs.slide_layouts[6]);sh=sl.shapes
        sh.add_shape(1,0,0,prs.slide_width,Inches(.13)).fill.solid();sh[-1].fill.fore_color.rgb=orange
        tx=sh.add_textbox(Inches(.6),Inches(.42),Inches(12),Inches(.8)).text_frame;tx.text=title
        for p in tx.paragraphs:p.font.size=Pt(29);p.font.bold=True;p.font.color.rgb=navy
        sub=sh.add_textbox(Inches(.64),Inches(1.22),Inches(12),Inches(.5)).text_frame;sub.text=subtitle
        for p in sub.paragraphs:p.font.size=Pt(13);p.font.color.rgb=grey
        box=sh.add_textbox(Inches(.78),Inches(1.95),Inches(11.9),Inches(4.8)).text_frame;box.word_wrap=True
        for i,line in enumerate(lines):
            p=box.paragraphs[0] if i==0 else box.add_paragraph();p.text=str(line);p.font.size=Pt(21 if len(lines)<6 else 17);p.space_after=Pt(19);p.font.color.rgb=navy
        ft=sh.add_textbox(Inches(.65),Inches(7.12),Inches(12),Inches(.25)).text_frame;ft.text='SL CARBORUNDUM  |  Planning Department  |  Prepared by Akash Deep, Planning Manager  |  Verify source cutoffs'
        ft.paragraphs[0].font.size=Pt(9);ft.paragraphs[0].font.color.rgb=grey
        return sl
    dt=pd.Timestamp(report_date).strftime('%d %b %Y')
    m=master if isinstance(master,pd.DataFrame) else pd.DataFrame()
    r=risk if isinstance(risk,pd.DataFrame) else pd.DataFrame()
    prod=production if isinstance(production,pd.DataFrame) else pd.DataFrame()
    j=job.copy() if isinstance(job,pd.DataFrame) else pd.DataFrame()
    start,end=period_bounds(period,report_date)
    if not j.empty and 'Date' in j:
        j['Date']=pd.to_datetime(j['Date'],errors='coerce')
        j=j[j.Date.ge(start)&j.Date.lt(end+pd.Timedelta(days=1))].copy()
        j['WOs']=pd.to_numeric(j['WOs'],errors='coerce')
    period_label=f'{start:%d %b %Y} to {end:%d %b %Y}'
    slide(f'{period} — Management evidence review',f'{period_label} | WIP is a source snapshot, not a period total',[f'Plan2026 work-order records: {m["Work Order"].nunique():,}' if 'Work Order' in m else 'Plan2026: not uploaded','Production WIP: '+(f'{pd.to_numeric(prod["Open kg"],errors="coerce").sum()/1000:,.2f} t (source gross weight)' if 'Open kg' in prod else 'not loaded'),'Job register: '+(f'{j.WOs.notna().sum()} recorded values of {len(j)} selected rows; blanks are unknown' if not j.empty else 'no rows in selected period'),'No inferred delivery or closure results from missing evidence.'])
    slide('Delivery control and customer risk','Prioritize overdue, next three days, then physically executable recovery',[f'Risk records: {len(r):,}' if not r.empty else 'Risk register: not available','Review WO, customer, due date, bottleneck, open quantity and responsible owner.','Missing actual or status = DATA/STATUS CHECK, not confirmed production delay.'])
    if not r.empty and 'Bottleneck Process' in r:
        top=r['Bottleneck Process'].fillna('DATA/STATUS CHECK').value_counts().head(5)
        slide('Bottlenecks and recovery','Counts of risk records, not capacity-confirmed bottlenecks',[f'{k}: {v:,} risk records' for k,v in top.items()]+['Action: confirm physically ready WOs, controlled capacity and recovery owners.'])
    if not prod.empty and {'Section','Open kg'}.issubset(prod):
        vals=prod.assign(_kg=pd.to_numeric(prod['Open kg'],errors='coerce')).groupby('Section')['_kg'].sum()/1000
        slide('Production WIP by process','Gross-weight section snapshot; curing included in Firing area',[f'{k}: {v:,.2f} t' for k,v in vals.items()]+['Reconcile with Plan2026 NET estimates and common snapshot date.'])
    else:slide('Planning vs Production WIP','Source records required',['Upload Production WIP and Plan2026 at a common cutoff.','Compare section × P/R/S/T/M/PB, then drill down by WO.'])
    if not j.empty and {'Metric','WOs'}.issubset(j):
        totals=j.groupby('Metric')['WOs'].sum(min_count=1)
        slide('Open / close register',period_label+'; JOB and ITEM remain separate',[f'{k}: {v:,.0f}' if pd.notna(v) else f'{k}: no recorded values' for k,v in totals.items()]+['Do not subtract ITEM from JOB until units are confirmed.'])
    slide('Capacity: plan → actual','Controlled capacity and native-unit checks',['Mixing: verify kg/h, pcs/h, MO/h or hours by machine/product.','Firing: geometry, furniture, kiln starts and physically ready quantity.','Show source and capacity assumptions; flag missing values instead of zero.'])
    slide('Action register / management decisions','WHAT • WHY • WHO • NEXT',['Confirm mismatched Production/Planning WIP and owner.','Resolve overdue WO bottlenecks and next due-date recovery.','Confirm missing actuals, route and WO closure status.','Record approval and next review date for each correction.'])
    if period in ('Monthly','Mid-year','Yearly'):
        slide('Period trend and improvement','Only use actual historical records for the selected reporting period',['Open/close by category P/R/S/T/M/PB, period by period.','Capacity vs planned vs actual output in compatible units.','Backorder OPEN/CLOSED and root-cause recurrence.','Data completeness and approved process improvements.'])
    if period in ('Mid-year','Yearly'):
        slide('Long-term planning and capability','MPS, MRP, safety stock and system maturity',['Demand forecast vs verified process capacity.','MTS safety-stock coverage and shortage risks.','Firing and other-process plan release readiness.','Management decisions, investment and next-period priorities.'])
    if source_note:
        slide('Source dates and scope','Check these before using this report as current operating performance',[source_note,'Production summaries have no confirmed common cutoff.','Planning versus Production quantities remain unverified until column mapping is confirmed.'])
    # Native editable PowerPoint chart, using source summary amounts only.
    if not prod.empty and {'Section','Open kg'}.issubset(prod):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
        values=prod.assign(_kg=pd.to_numeric(prod['Open kg'],errors='coerce')).groupby('Section')['_kg'].sum(min_count=1).dropna()/1000
        if len(values):
            sl=slide('Production WIP snapshot by process','Bundled/uploaded source cutoff unconfirmed; gross tonnes. Firing includes curing.')
            cd=CategoryChartData();cd.categories=[str(x).replace('Grinding / Cutting (Production combined)','Grinding / Cutting') for x in values.index];cd.add_series('Gross tonnes',values.tolist())
            chart=sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(.8),Inches(2),Inches(11.6),Inches(4.7),cd).chart
            chart.has_legend=False;chart.category_axis.tick_labels.font.size=Pt(15)
            # OOXML axis identifiers are unsigned; normalize python-pptx defaults.
            for node in chart._chartSpace.iter():
                if node.tag.endswith('}axId') or node.tag.endswith('}crossAx'):
                    node.set('val',str(int(node.get('val')) % (2**32)))
    def evidence_table(title,subtitle,frame,columns,rows_per_slide=5):
        chosen=[c for c in columns if c in frame]
        if not chosen:return
        for offset in range(0,len(frame),rows_per_slide):
            part=frame.iloc[offset:offset+rows_per_slide]
            sl=slide(title+(' (continued)' if offset else ''),subtitle)
            tb=sl.shapes.add_table(len(part)+1,len(chosen), Inches(.6),Inches(1.95),Inches(12.1),Inches(4.3)).table
            for col,name in enumerate(chosen):tb.cell(0,col).text=name
            for ri,(_,row) in enumerate(part.iterrows(),1):
                for ci,col in enumerate(chosen):
                    v=row[col];tb.cell(ri,ci).text='' if pd.isna(v) else str(v)
            for ri in range(len(part)+1):
                for ci in range(len(chosen)):
                    cell=tb.cell(ri,ci);cell.fill.solid();cell.fill.fore_color.rgb=navy if ri==0 else RGBColor(241,245,249)
                    for para in cell.text_frame.paragraphs:
                        para.font.size=Pt(12);para.font.color.rgb=RGBColor(255,255,255) if ri==0 else navy
    if isinstance(reconciliation,pd.DataFrame) and not reconciliation.empty:
        columns=['Work Order','Category','Data issues','Confirmed cause','Corrective action','Owner']
        if 'Work Order' not in reconciliation:columns=['Section','Category','Confirmed cause / reason','Correction / next action','Owner']
        evidence_table('WO problems and corrective actions','Source issue is not a confirmed root cause. Blank cause/owner requires follow-up.',reconciliation,columns)
    if isinstance(kpi,pd.DataFrame) and not kpi.empty:
        evidence_table('Current-period KPI evidence',period_label+'; uploaded period-specific evidence',kpi,list(kpi.columns)[:6])
    else:slide('Current-period KPI file required',period_label,['No current-period KPI evidence was supplied.','Upload the approved KPI workbook for this reporting period.'])
    out=BytesIO();prs.save(out);return out.getvalue()

def render(st, master, risk, production, job, report_date):
    st.subheader('Management PowerPoint reports')
    period=st.selectbox('Reporting period',['Weekly','Monthly','Mid-year','Yearly'],key='ppt_period')
    day=st.date_input('Reporting through',value=pd.Timestamp(report_date).date(),key='ppt_through')
    start,end=period_bounds(period,day)
    st.caption(f'Job history: {start:%d %b %Y} to {end:%d %b %Y}. WIP remains a separately dated snapshot. Missing history does not imply zero output.')
    kfile=st.file_uploader('Current-period KPI workbook (upload each reporting period)',type=['xlsx'],key='ppt_kpi_'+period+str(start.date()))
    kpi=None
    if kfile is not None:
        try:
            xl=pd.ExcelFile(BytesIO(kfile.getvalue()))
            sheet=st.selectbox('KPI evidence sheet',xl.sheet_names,key='ppt_kpi_sheet')
            kpi=pd.read_excel(xl,sheet_name=sheet)
            st.dataframe(kpi,use_container_width=True)
        except Exception as exc:st.error('KPI import: '+str(exc))
    if st.button('Prepare selected PowerPoint report',key='ppt_prepare'):
        try:
            frames=list(st.session_state.get('wo_reconciliation_current',{}).values())
            notes=pd.concat(frames,ignore_index=True) if frames else st.session_state.get('prod_wip_comparison_current')
            if isinstance(notes,pd.DataFrame) and 'Data issues' in notes:
                notes=notes[notes['Data issues'].ne('') | notes.get('Corrective action',pd.Series('',index=notes.index)).ne('')].head(20)
            data=generate(period,master,risk,production,job,day,notes,kpi)
            st.download_button('Download '+period+' PowerPoint',data,file_name=f'SL_Planning_{period}_{day:%Y%m%d}.pptx',mime='application/vnd.openxmlformats-officedocument.presentationml.presentation',key='ppt_download')
        except Exception as exc:st.error('PowerPoint export: '+str(exc))

"""Optional Daily MD report: presentation layer only; never changes engine outputs."""
import io
from pathlib import Path
import pandas as pd

def _n(x):
    try: return float(x)
    except (ValueError,TypeError): return 0.0

def _excel(date, delivery, capacity, readiness, actions, wip, template_note, job_daily=None):
    buf=io.BytesIO()
    with pd.ExcelWriter(buf,engine='xlsxwriter',datetime_format='dd-mmm-yyyy') as writer:
        book=writer.book
        book.strings_to_formulas=False
        book.strings_to_urls=False
        book.set_properties({'title':'SL Planning Daily MD Report','author':'Akash Deep — Planning Manager'})
        title=book.add_format({'bold':True,'font_size':19,'font_color':'white','bg_color':'#F36F21','valign':'vcenter'})
        subtitle=book.add_format({'bold':True,'font_size':11,'font_color':'white','bg_color':'#343A40'})
        header=book.add_format({'bold':True,'font_size':10,'font_color':'white','bg_color':'#20354D','text_wrap':True,'valign':'vcenter','border':0})
        note=book.add_format({'font_size':10,'text_wrap':True,'valign':'top'})
        warn=book.add_format({'font_color':'#A61B1B','bg_color':'#FFF1EB','text_wrap':True})
        num=book.add_format({'num_format':'#,##0.00'})
        report=book.add_worksheet('MD Daily Summary');writer.sheets['MD Daily Summary']=report
        report.hide_gridlines(2);report.set_landscape();report.fit_to_pages(1,1);report.set_paper(9);report.set_margins(.24,.24,.35,.35)
        report.set_column('A:A',24);report.set_column('B:B',19);report.set_column('C:C',23);report.set_column('D:D',19);report.set_column('E:E',24);report.set_column('F:F',30);report.set_column('G:G',34)
        report.merge_range('A1:G2','SL CARBORUNDUM  |  PLANNING DEPARTMENT',title)
        report.merge_range('A3:G3',f'DAILY DELIVERY • CAPACITY • READINESS • RISK • RECOVERY     |     {date:%d %b %Y}',subtitle)
        report.write_row('A5',['Planned output WOs','Actual output WOs','Output attainment','Delivery confirmed?','Backorder WOs','Future risk WOs','Production WIP confirmed?'],header)
        row=delivery.iloc[0] if len(delivery) else {}
        plan=_n(row.get('Planned WOs')) if len(delivery) else 0;actual=row.get('Actual Output WOs') if len(delivery) else None
        report.write_formula('A6',"=IF(ISNUMBER('Delivery Input'!B4),'Delivery Input'!B4,\"PENDING\")",None,plan)
        report.write_formula('B6',"=IF(ISNUMBER('Delivery Input'!C4),'Delivery Input'!C4,\"PENDING\")",None,actual if pd.notna(actual) else 'PENDING')
        report.write_formula('C6','=IF(AND(ISNUMBER(A6),ISNUMBER(B6),A6>0),B6/A6,"PENDING")',book.add_format({'num_format':'0.0%'}),float(actual)/plan if pd.notna(actual) and plan>0 else 'PENDING')
        report.write('D6',row.get('Dispatch confirmed?','NO') if len(delivery) else 'NO')
        report.write('E6',None);report.write('F6',None);report.write('G6','PENDING')
        if job_daily is not None and len(job_daily):
            _j=job_daily.copy();_j['Date']=pd.to_datetime(_j['Date'],errors='coerce')
            _j=_j[_j['Date'].dt.date.eq(date)]
            _opened=float(pd.to_numeric(_j.loc[_j['Metric'].eq('Opened WOs'),'WOs'],errors='coerce').sum())
            _closed=float(pd.to_numeric(_j.loc[_j['Metric'].eq('Closed items'),'WOs'],errors='coerce').sum())
            report.merge_range('A7:G7',f'DAILY JOB REGISTER  |  Opened: {_opened:,.0f} JOB   •   Closed: {_closed:,.0f} ITEM   |  Different source units; not netted',warn)
        def table(top,label,df,maxrows):
            report.merge_range(top,0,top,6,label,subtitle)
            heads=list(df.columns)[:7];report.write_row(top+1,0,heads,header)
            for j,(_,rr) in enumerate(df.head(maxrows).iterrows()):
                for i,k in enumerate(heads):
                    v=rr[k];report.write(top+2+j,i,'' if pd.isna(v) else (v.item() if hasattr(v,'item') else v),note)
            return top+3+min(len(df),maxrows)
        t=table(8,'01  |  DELIVERY CONTROL — TODAY / D+1 / D+2',delivery,3)
        t=table(t+1,'02  |  PROCESS CAPACITY & LOAD (TON)',capacity,8)
        t=table(t+1,'03  |  MATERIAL / FIRING READINESS',readiness,5)
        t=table(t+1,'04  |  PRIORITY RISKS & REQUIRED ACTION',actions,5)
        report.merge_range(t+1,0,t+2,6,template_note,warn)
        report.print_area(0,0,t+2,6)
        for name,df in [('Delivery Input',delivery),('Capacity Input',capacity),('Readiness Input',readiness),('WIP Production',wip),('Action Register',actions)]:
            df.to_excel(writer,sheet_name=name,index=False,startrow=2)
            sh=writer.sheets[name];sh.hide_gridlines(2);sh.freeze_panes(3,1);sh.set_landscape();sh.fit_to_pages(1,0)
            sh.merge_range(0,0,0,max(len(df.columns)-1,1),f'{name.upper()}  |  {date:%d %b %Y}',title)
            for j,col in enumerate(df.columns):sh.write(2,j,col,header);sh.set_column(j,j,min(48,max(15,len(str(col))+4)))
            if len(df):sh.autofilter(2,0,len(df)+2,len(df.columns)-1)
        if job_daily is not None and len(job_daily):
            job_daily.to_excel(writer,sheet_name='Job Register Evidence',index=False)
            writer.sheets['Job Register Evidence'].set_column('A:H',20)
        # Chart uses real capacity entries; blank inputs remain blank rather than inferred.
        if len(capacity) and 'Capacity t' in capacity and 'Today load t' in capacity:
            sh=writer.sheets['Capacity Input']; chart=book.add_chart({'type':'column'})
            for ci,clr in [(1,'#8C99A5'),(2,'#F36F21')]:
                chart.add_series({'name':['Capacity Input',2,ci],'categories':['Capacity Input',3,0,len(capacity)+2,0], 'values':['Capacity Input',3,ci,len(capacity)+2,ci], 'fill':{'color':clr},'data_labels':{'value':True,'font':{'size':10}}})
            chart.set_title({'name':'Capacity vs planned load (t)'});chart.set_legend({'position':'bottom'});chart.set_size({'width':920,'height':420});sh.insert_chart('M4',chart)
    return buf.getvalue()

def render(st, allp, risk, caps, master, start, app_dir, daily_status=None, stock_df=None, firing_df=None, planning_wip=None, source_paths=None):
    st.markdown('### 📄 DAILY MD REPORT / รายงานประจำวันสำหรับผู้บริหาร')
    st.caption('Report tables start from active Plan-2026, Daily Status, capacity, stock and firing inputs where fields are available. Unknown actuals stay blank; planning targets are not reported as dispatches.')
    with st.expander('SOURCE DATA & UNIT CONTROL / แหล่งข้อมูลและหน่วย', expanded=True):
        st.info('Controlled capacity must come from the capacity workbook and be checked against machines, shift, routing and units. No automatic tonne/day conversion from machine pcs/hour without controlled product weights and mix. Unverified capacity stays blank.')
        grams=st.number_input('Warehouse material amount (grams) / วัตถุดิบ (กรัม)',min_value=0.0,value=0.0,step=1000.0,key='md_store_grams')
        st.metric('Raw material / วัตถุดิบ (tonnes)',f'{grams/1_000_000:,.6f} t')
        kg=st.number_input('Daily-status actual output (kg) / ผลผลิตจริง (กก.)',min_value=0.0,value=0.0,step=100.0,key='md_actual_kg')
        st.metric('Actual output / ผลผลิตจริง (tonnes)',f'{kg/1000:,.4f} t')
        src=st.file_uploader('Optional current Plan2026 for controlled FB2 WIP / แนบ Plan2026',type=['xlsx','xlsm'],key='md_plan_fb2')
        if src is not None:
            try:
                import pandas as _pd
                from io import BytesIO as _BIO
                _sheet=st.text_input('Sheet containing FB2',value='Plan 2026',key='md_fb2_sheet')
                _fb=_pd.read_excel(_BIO(src.getvalue()),sheet_name=_sheet,header=None,usecols='FB',nrows=2,engine='openpyxl')
                _value=_fb.iloc[1,0]
                if _pd.notna(_value):st.success(f'Plan2026 FB2 WIP (source unit must be verified): {_value:,.3f}' if isinstance(_value,(int,float)) else f'Plan2026 FB2: {_value}')
                else:st.warning('FB2 is blank. Verify sheet and source file.')
            except Exception as e:st.warning(f'FB2 not read: {e}. Check exact sheet name and workbook formula cache; do not assume zero WIP.')
        st.caption('Source conversion: grams ÷ 1,000,000 = tonnes; kg ÷ 1,000 = tonnes. FB2 source unit must be verified before combining with production WIP.')
        status=st.file_uploader('Optional daily-status evidence file (CSV/XLSX) / รายงานสถานะรายวัน',type=['csv','xlsx'],key='md_daily_status_file')
        if status is not None:
            try:
                from io import BytesIO as _BIO
                _df=pd.read_csv(_BIO(status.getvalue())) if status.name.lower().endswith('.csv') else pd.read_excel(_BIO(status.getvalue()))
                st.dataframe(_df.head(30),use_container_width=True,hide_index=True)
                cols=['-- choose --']+list(map(str,_df.columns))
                a,b=st.columns(2)
                with a:actual_col=st.selectbox('Actual output kg column',cols,key='md_status_actual_col')
                with b:problem_col=st.selectbox('Problem / issue column',cols,key='md_status_problem_col')
                action_col=st.selectbox('Production action column',cols,key='md_status_action_col')
                if actual_col!='-- choose --':
                    _series=pd.to_numeric(_df[actual_col],errors='coerce')
                    st.metric('Selected actual output total (tonnes)',f'{_series.sum()/1000:,.4f} t')
                    st.caption(f'{_series.notna().sum()} numeric rows; review duplicates and reporting date before management release.')
                if problem_col!='-- choose --' and action_col!='-- choose --':
                    st.markdown('**Problem and Production action — source evidence**')
                    st.dataframe(_df[[_df.columns[0],problem_col,action_col]].head(100),hide_index=True,use_container_width=True)
            except Exception as e:st.error(f'Cannot parse daily-status evidence: {e}')

    day=st.date_input('Report date / วันที่รายงาน',value=pd.Timestamp(start).date(),key='md_daily_date')
    def _workdays_after(d,n):
        out=[]; cur=pd.Timestamp(d).date()
        while len(out)<n:
            cur=(pd.Timestamp(cur)+pd.Timedelta(days=1)).date()
            if pd.Timestamp(cur).weekday()!=6: out.append(cur)
        return out
    _d1,_d2=_workdays_after(day,2)
    _plan=pd.DataFrame(allp).copy() if isinstance(allp,pd.DataFrame) else pd.DataFrame()
    _actual=pd.DataFrame(daily_status).copy() if isinstance(daily_status,pd.DataFrame) else pd.DataFrame()
    _cap=pd.DataFrame(caps).copy() if isinstance(caps,pd.DataFrame) else pd.DataFrame()
    _risk=pd.DataFrame(risk).copy() if isinstance(risk,pd.DataFrame) else pd.DataFrame()
    _plan_date=pd.to_datetime(_plan.get('Plan Date'),errors='coerce').dt.date if not _plan.empty and 'Plan Date' in _plan else pd.Series(dtype=object)
    def _plan_rows(d,sec=None):
        if _plan.empty or _plan_date.empty:return pd.DataFrame()
        z=_plan[_plan_date.eq(d)].copy()
        return z[z['Section'].astype(str).eq(sec)] if sec and 'Section' in z else z
    def _actual_rows(d):
        if _actual.empty:return pd.DataFrame()
        _datecol=next((c for c in ['Date','Production Date','Actual Date'] if c in _actual),None)
        if not _datecol:return pd.DataFrame()
        z=_actual[pd.to_datetime(_actual[_datecol],errors='coerce').dt.date.eq(d)].copy()
        if 'Section' in z:z=z[z['Section'].astype(str).str.contains('Packing|Pack|บรรจุ',case=False,regex=True)]
        return z
    def _sum_num(df,cols):
        for c in cols:
            if c in df:return float(pd.to_numeric(df[c],errors='coerce').fillna(0).sum())
        return 0.0
    def _uniq(df,cols):
        for c in cols:
            if c in df:return int(df[c].dropna().astype(str).str.strip().replace('',pd.NA).dropna().nunique())
        return 0
    if st.session_state.get('md_active_day') != str(day):
        fields=['md_daily_delivery','md_daily_capacity','md_daily_readiness','md_daily_wip','md_daily_actions']
        archive=st.session_state.setdefault('md_date_reviews',{})
        previous=st.session_state.get('md_active_day')
        if previous:archive[previous]={k:st.session_state[k].copy() for k in fields if k in st.session_state}
        for k in fields+['md_delivery_editor','md_capacity_editor','md_readiness_editor','md_wip_editor','md_actions_editor']:
            st.session_state.pop(k,None)
        for k,value in archive.get(str(day),{}).items():st.session_state[k]=value.copy()
        st.session_state['md_active_day']=str(day)
    plan=allp.copy() if isinstance(allp,pd.DataFrame) else pd.DataFrame()
    if not plan.empty and {'Plan Date','Section'}.issubset(plan.columns):
        plan['_date']=pd.to_datetime(plan['Plan Date'],errors='coerce').dt.date
        plan=plan[plan['_date'].eq(day)]
    def count_section(sec):
        if plan.empty or 'Section' not in plan:return 0
        z=plan[plan['Section'].astype(str).str.lower().eq(sec.lower())]
        return int(z['Work Order'].nunique()) if 'Work Order' in z else 0
    _delivery_rows=[]
    for _label,_date in [('Today',day),('D+1',_d1),('D+2',_d2)]:
        _pdrows=_plan_rows(_date,'Packing');_adrows=_actual_rows(_date)
        _delivery_rows.append({'Period':f'{_label} · {_date:%d-%b-%Y}','Planned WOs':_uniq(_pdrows,['Work Order']),'Actual Output WOs':_uniq(_adrows,['Work Order']),
            'Planned pcs':_sum_num(_pdrows,['Plan Qty','Plan Qty pcs']),'Actual pcs':_sum_num(_adrows,['Production Actual Qty','Actual Qty','Actual pcs']),
            'Dispatch confirmed?':'NOT CAPTURED','Remark / evidence':'Actual is dated Daily Status only; dispatch needs separate confirmation.'})
    delivery=pd.DataFrame(_delivery_rows)
    if 'md_daily_delivery' in st.session_state:delivery=st.session_state['md_daily_delivery']
    st.warning('Planned Packing WOs are not verified dispatches. Enter actual output and confirm delivery using Production/dispatch evidence.')
    st.markdown('#### 1. Delivery / ส่งมอบ');st.caption('Plan rows: active Plan-2026 + selected dates. Actual WOs/pcs: dated Daily Status only. Dispatch status is not inferred from production output.') ;delivery=st.data_editor(delivery,num_rows='fixed',hide_index=True,use_container_width=True,key='md_delivery_editor');st.session_state['md_daily_delivery']=delivery.copy()
    sections=['Preparation','Mixing','Forming','Firing','Grinding','Cutting','Packing']
    _capacity_rows=[]
    for _sec in sections:
        _row={'Process':_sec,'Capacity t':None,'Today load t':None,'D+1 t':None,'D+2 t':None,'Today load %':None,'Mixing plan mills':None,'Mixing capacity mills':None,'Constraint / evidence':'No matched source row'}
        for _label,_date in [('Today',day),('D+1',_d1),('D+2',_d2)]:
            _cd=pd.to_datetime(_cap.get('Plan Date'),errors='coerce').dt.date if not _cap.empty and 'Plan Date' in _cap else pd.Series(dtype=object)
            _cg=_cap[_cd.eq(_date)&_cap.get('Section',pd.Series('',index=_cap.index)).astype(str).eq(_sec)] if not _cap.empty and not _cd.empty else pd.DataFrame()
            if _cg.empty:continue
            _plan_t=_sum_num(_cg,['Plan ton']);_cap_t=_sum_num(_cg,['Capacity ton'])
            if _label=='Today':
                _row['Today load t']=_plan_t;_row['Capacity t']=_cap_t;_row['Today load %']=float(pd.to_numeric(_cg.get('Utilization %'),errors='coerce').max()) if 'Utilization %' in _cg and pd.to_numeric(_cg['Utilization %'],errors='coerce').notna().any() else None
                _row['Constraint / evidence']='; '.join(_cg.get('Capacity Basis',pd.Series(dtype=str)).dropna().astype(str).unique()[:2])
            else:_row[f'{_label} t']=_plan_t
            if _sec=='Mixing':
                if _label=='Today':
                    _row['Mixing plan mills']=_sum_num(_cg,['Mixing Plan MO'])
                    _row['Mixing capacity mills']=_sum_num(_cg,['Mixing Capacity MO'])
                if _label=='D+1':_row['D+1 Mixing plan mills']=_sum_num(_cg,['Mixing Plan MO']);_row['D+1 Mixing capacity mills']=_sum_num(_cg,['Mixing Capacity MO'])
                if _label=='D+2':_row['D+2 Mixing plan mills']=_sum_num(_cg,['Mixing Plan MO']);_row['D+2 Mixing capacity mills']=_sum_num(_cg,['Mixing Capacity MO'])
        _capacity_rows.append(_row)
    capacity=pd.DataFrame(_capacity_rows)
    if 'md_daily_capacity' in st.session_state:capacity=st.session_state['md_daily_capacity']
    st.markdown('#### 2. Process load and capacity / กำลังผลิต');st.caption('Capacity and load: current planner capacity summary. Mixing mills remain a separate native-unit measure; tonnes are not substituted for mill count.') ;capacity=st.data_editor(capacity,num_rows='fixed',hide_index=True,use_container_width=True,key='md_capacity_editor');st.session_state['md_daily_capacity']=capacity.copy()
    cf=capacity.copy();cf['Capacity t']=pd.to_numeric(cf['Capacity t'],errors='coerce');cf['Today load t']=pd.to_numeric(cf['Today load t'],errors='coerce');cf['Utilization %']=(cf['Today load t']/cf['Capacity t']*100).round(1)
    if cf['Utilization %'].notna().any():
        import plotly.express as px
        fig=px.bar(cf,x='Process',y='Utilization %',text='Utilization %',title='Process utilization / การใช้กำลังผลิต',color='Process')
        fig.update_layout(font={'size':17},height=420,showlegend=False);st.plotly_chart(fig,use_container_width=True)
        st.caption('Source: current capacity summary from the Daily Planner; tonnes are the planner’s equivalent-weight basis.')
    _mix=capacity[capacity['Process'].astype(str).eq('Mixing')].copy()
    if {'Mixing plan mills','Mixing capacity mills'}.issubset(_mix.columns):
        _mv=pd.DataFrame([{'Measure':'Planned mills','Mills':pd.to_numeric(_mix['Mixing plan mills'],errors='coerce').sum(min_count=1)},
                          {'Measure':'Available mills','Mills':pd.to_numeric(_mix['Mixing capacity mills'],errors='coerce').sum(min_count=1)}]).dropna()
        if not _mv.empty:
            import plotly.express as px
            st.markdown('##### Mixing capacity in mills / กำลังการผสมเป็นจำนวนโม่')
            st.plotly_chart(px.bar(_mv,x='Measure',y='Mills',text='Mills',title='Mixing planned vs available mill count'),use_container_width=True)
            st.caption('Source: capacity summary · Mixing Plan MO and Mixing Capacity MO · mill count stays separate from tonnes.')
    st.dataframe(cf[['Process','Utilization %','Constraint / evidence']],use_container_width=True,hide_index=True)
    _readiness_rows=[]
    _fire_today=_plan_rows(day,'Firing')
    _readiness_rows.append({'Item / WO':'Firing scheduled today','Required':_sum_num(_fire_today,['Plan Qty']),'Available / ready':_uniq(_fire_today,['Work Order']),'Gap':None,'Status':'PLAN LOADED' if not _fire_today.empty else 'NO FIRING ROWS','Owner':'Planning','Next action':'Verify released firing plan and kiln assignment.'})
    if not _risk.empty:
        for _,_rr in _risk.head(100).iterrows():
            _readiness_rows.append({'Item / WO':str(_rr.get('Work Order','')),'Required':_rr.get('Open Qty',None),'Available / ready':None,'Gap':None,'Status':str(_rr.get('Delivery Risk','RISK REVIEW')),'Owner':'Planning / Sales / Production','Next action':str(_rr.get('Bottleneck Process','Review risk and confirm recovery.'))})
    if isinstance(stock_df,pd.DataFrame) and not stock_df.empty:
        _item_col=next((c for c in ['Material Code','Material','รหัสวัตถุดิบ','รหัสสินค้า','Description'] if c in stock_df),None)
        _qty_col=next((c for c in ['Stock kg','On Hand t','On Hand kg','Available','วัตถุดิบคงคลัง'] if c in stock_df),None)
        for _,_sr in stock_df.head(30).iterrows():
            _readiness_rows.append({'Item / WO':str(_sr.get(_item_col,'Stock item') if _item_col else 'Stock item'),
                'Required':None,'Available / ready':_sr.get(_qty_col,None) if _qty_col else None,'Gap':None,
                'Status':'STOCK SNAPSHOT — REQUIREMENT NOT NETTED','Owner':'Warehouse / Planning',
                'Next action':'Compare against BOM-based MRP for affected work orders.'})
    if not _readiness_rows:_readiness_rows=[{'Item / WO':'No source rows','Required':None,'Available / ready':None,'Gap':None,'Status':'DATA CHECK','Owner':'Planning','Next action':'Upload current source files.'}]
    readiness=pd.DataFrame(_readiness_rows)
    if 'md_daily_readiness' in st.session_state:readiness=st.session_state['md_daily_readiness']
    st.markdown('#### 3. Material and firing readiness / ความพร้อม');st.caption('Firing rows come from the active plan; delivery-risk rows come from the risk engine. Stock presence alone is not declared sufficient or short without MRP.') ;readiness=st.data_editor(readiness,num_rows='dynamic',hide_index=True,use_container_width=True,key='md_readiness_editor');st.session_state['md_daily_readiness']=readiness.copy()
    _wip_rows=[]
    _wm=pd.DataFrame(master).copy() if isinstance(master,pd.DataFrame) else pd.DataFrame()
    _catcol=next((c for c in ['Category','Product Category'] if c in _wm),None)
    if not _wm.empty and _catcol:
        _cat=_wm[_catcol].fillna('').astype(str).str.upper().str.strip().replace({'F':'P','UNCLASSIFIED':'','UNKNOWN':''})
        _wip_fields={'Preparation':'Preparation Remaining Qty','Mixing':'Mixing Remaining Qty','Forming':'Forming Remaining Qty','Firing':'Firing Remaining Qty','Grinding':'Grinding / Cutting Remaining Qty','Packing':'Packing Remaining Qty'}
        for _proc,_col in _wip_fields.items():
            if _col in _wm:
                _tmp=pd.DataFrame({'Category':_cat,'Planning WIP pcs':pd.to_numeric(_wm[_col],errors='coerce')}).dropna(subset=['Planning WIP pcs'])
                for _cc,_gg in _tmp.groupby('Category'):
                    if _cc in ['P','R','S','T','M','PB']:
                        _wip_rows.append({'Process':_proc,'Category':_cc,'Planning WIP pcs':float(_gg['Planning WIP pcs'].sum()),'Production WIP pcs':None,'Production WIP kg':None,'Output actual pcs':None,'Production confirmed?':'NO — source not linked'})
    if not _wip_rows and isinstance(planning_wip,pd.DataFrame) and not planning_wip.empty:
        _wip_rows=[{'Process':r.get('Section',r.get('Process','Unknown')),'Category':r.get('Category',''),'Planning WIP pcs':r.get('WIP pcs',r.get('Planning WIP pcs',None)),'Production WIP pcs':None,'Production WIP kg':None,'Output actual pcs':None,'Production confirmed?':'NO — source not linked'} for _,r in planning_wip.iterrows()]
    wip=pd.DataFrame(_wip_rows) if _wip_rows else pd.DataFrame([{'Process':sec,'Category':cat,'Planning WIP pcs':None,'Production WIP pcs':None,'Production WIP kg':None,'Output actual pcs':None,'Production confirmed?':'NO — source not linked'} for sec in sections for cat in ['P','R','S','T','M','PB']])
    if 'md_daily_wip' in st.session_state:wip=st.session_state['md_daily_wip']

    with st.expander('📦 WIP by process and category / WIP แยกกระบวนการ',expanded=False):
        wip=st.data_editor(wip,num_rows='dynamic',hide_index=True,use_container_width=True,key='md_wip_editor');st.session_state['md_daily_wip']=wip.copy()
        v=wip.copy();v['Planning WIP pcs']=pd.to_numeric(v['Planning WIP pcs'],errors='coerce');v['Production WIP pcs']=pd.to_numeric(v['Production WIP pcs'],errors='coerce');v['Variance pcs']=v['Production WIP pcs']-v['Planning WIP pcs'];st.dataframe(v,use_container_width=True,hide_index=True)
        if v[['Planning WIP pcs','Production WIP pcs']].notna().any().any():
            import plotly.graph_objects as go
            vg=v.groupby('Process',as_index=False)[['Planning WIP pcs','Production WIP pcs']].sum(min_count=1)
            f=go.Figure()
            f.add_bar(x=vg['Process'],y=vg['Planning WIP pcs'],name='PLAN / แผน',marker_color='#94A3B8')
            f.add_bar(x=vg['Process'],y=vg['Production WIP pcs'],name='ACTUAL / ผลจริง',marker_color='#F97316')
            f.update_layout(barmode='group',font_size=17,height=410,legend_orientation='h',title='WIP — Plan first, Actual second')
            st.plotly_chart(f,use_container_width=True)
    _action_rows=[]
    for _ix,_ar in _risk.head(50).iterrows():
        _action_rows.append({'Priority':_ix+1,'WO':_ar.get('Work Order',''),'Customer':_ar.get('Customer Thai',_ar.get('Customer','')),
            'Due date':_ar.get('Due Date',''),'Root cause':_ar.get('Bottleneck Process',_ar.get('Delivery Risk','Review')),
            'Owner':'Planning / Sales / Production — confirm','Required action / due':_ar.get('Detailed Reason','Review recovery plan and record the agreed action/date.')})
    actions=pd.DataFrame(_action_rows) if _action_rows else pd.DataFrame([{'Priority':1,'WO':'','Customer':'','Due date':'','Root cause':'','Owner':'','Required action / due':''}])
    if 'md_daily_actions' in st.session_state:actions=st.session_state['md_daily_actions']
    st.markdown('#### 4. Management follow-up / การติดตาม');actions=st.data_editor(actions,num_rows='dynamic',hide_index=True,use_container_width=True,key='md_actions_editor');st.session_state['md_daily_actions']=actions.copy()
    warning='MANAGEMENT RELEASE GATE: Confirm dispatch separately from output. Confirm Production WIP and stock before presenting them as verified. Investigate missing status, process route and capacity data.'
    try:
        export_wip=st.session_state.get('prod_wip_comparison_current',wip)
        payload=_excel(day,delivery,capacity,readiness,actions,export_wip,warning,st.session_state.get('job_register_review'))
        st.download_button('⬇️ DOWNLOAD PRINTABLE DAILY MD REPORT (EXCEL) / ดาวน์โหลดรายงาน Excel',data=payload,file_name=f'SL_Planning_MD_Daily_{day:%Y%m%d}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='md_daily_download')
    except Exception as exc:st.error(f'Excel export error: {exc}')
    _source_lines=[]
    for _label,_path in (source_paths or {}).items():
        try:
            _sp=Path(str(_path))
            if _sp.is_file():_source_lines.append(f'{_label}: {_sp.name} · {_sp.resolve()}')
        except Exception:pass
    if _source_lines:
        with st.expander('📚 Source files for this report / แหล่งไฟล์รายงาน',expanded=False):
            for _line in _source_lines:st.caption(_line)
    tmpl=Path(app_dir)/'SL_Planning_Daily_MD_Report_Template.xlsx'
    if tmpl.exists():st.download_button('📘 Download linked daily management workbook',data=tmpl.read_bytes(),file_name=tmpl.name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='md_template_download')

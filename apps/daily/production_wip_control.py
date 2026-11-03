"""Production WIP views; monthly detail-derived balances, never edits source workbooks."""
from pathlib import Path
import pandas as pd
import hashlib, json, os, shutil
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from wip_evidence import read_wo_evidence, render_wo_review
from production_wip_sources import discover, candidates, root_for

GROUPS=['P','R','S','T','M','PB']
COLORS={'P':'#2563EB','R':'#16A34A','S':'#DC2626','T':'#7C3AED','M':'#0891B2','PB':'#EAB308'}
SOURCES={
 'Mixing':'PRODUCTION_WIP/Mixing_September.xlsx',
 'Forming':'PRODUCTION_WIP/Forming_September.xlsx',
 'Firing + curing':'PRODUCTION_WIP/Firing_September.xlsx',
 'Grinding / Cutting (Production combined)':'PRODUCTION_WIP/Grinding_September.xlsx',
 'Packing':'PRODUCTION_WIP/Packing_September.xlsx',
}

def read_summary(src,section=''):
    """Read the monthly WIP detail by header; retain the summary as a cross-check."""
    from suite.production_wip_data import read_production_wip
    # Path.name is only the basename. Passing it to openpyxl made every central
    # WIP workbook appear missing when the current directory differed.
    path=Path(src) if isinstance(src,(str,Path)) else Path(getattr(src,'name',''))
    if not section:
        try:
            from production_wip_sources import infer_section
            section=infer_section(path.name)
        except Exception:
            section=''
    return read_production_wip(path,section)

def render(st,master,base_dir):
    import plotly.express as px
    st.header('🏭 Production WIP reconciliation / เปรียบเทียบ WIP แผนและผลิต')
    shared_root=root_for(base_dir);shared_wip=shared_root/'PRODUCTION_WIP'
    st.caption('Production WIP uses the files uploaded once on Home. Replace or assign section files there; no second upload is needed here.')
    st.caption('Confirm the reporting cut-off dates before combining section totals.')
    snapshot=st.date_input('Production snapshot / วันที่ยืนยันข้อมูล',key='prod_wip_snapshot')
    _ranked_sources,source_metadata,errors=candidates(base_dir)
    loaded_sources={section:paths[0] for section,paths in _ranked_sources.items() if paths}
    records=[]
    for section,paths in _ranked_sources.items():
        last_error=None
        for source in paths:
            try:
                meta=source_metadata.get(str(source.resolve()),{})
                from suite.production_wip_data import read_production_wip
                d=read_production_wip(source,section,meta)
                records.append(d);loaded_sources[section]=source
                if source!=paths[0]:errors.append(f'{section}: newest file {paths[0].name} was unreadable; displaying previous readable copy {source.name}.')
                break
            except Exception as ex:last_error=ex
        else:
            if last_error is not None:errors.append(f'{section}: no readable WIP workbook. Latest file {paths[0].name}: {last_error}')
    if not records:
        st.info('Production WIP source books are not loaded yet. Upload the section files once on Home. No zero-filled or guessed WIP is shown.')
        if errors:
            with st.expander('Source availability / errors',expanded=False):st.dataframe(pd.DataFrame({'Section / source':errors}),use_container_width=True,hide_index=True)
        return
    if errors:
        with st.expander('Production WIP source details / sections needing review',expanded=False):st.dataframe(pd.DataFrame({'Section / source':errors}),use_container_width=True,hide_index=True)
    base=pd.concat(records,ignore_index=True)
    source_fingerprint=tuple((section,str(path.resolve()),path.stat().st_size,path.stat().st_mtime_ns) for section,path in sorted(loaded_sources.items()))
    if 'prod_wip_review' not in st.session_state or st.session_state.get('prod_wip_source_fingerprint')!=source_fingerprint:
        st.session_state.prod_wip_review=base.copy()
        st.session_state.prod_wip_source_fingerprint=source_fingerprint
    data=st.session_state.prod_wip_review.copy()
    data['Open kg']=pd.to_numeric(data['Open kg'],errors='coerce')
    data['Open t']=data['Open kg']/1000
    data['WO Balance Error']=pd.to_numeric(data['Total WO'],errors='coerce')-pd.to_numeric(data['Open WO'],errors='coerce')-pd.to_numeric(data['Closed WO'],errors='coerce')
    data['Category']=data['Category'].astype(str).str.strip().str.upper().replace({'F':'P'})
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Reported open WIP WOs',f'{pd.to_numeric(data["WIP WOs (source open)"],errors="coerce").sum(min_count=1):,.0f}')
    c2.metric('Production WIP',f'{data["Open t"].sum():,.2f} t')
    c3.metric('Closed WOs (section records)',f'{pd.to_numeric(data["Closed WO"],errors="coerce").sum(min_count=1):,.0f}')
    _wip_checks=(data['WO Balance Error'].fillna(0).ne(0) | data.get('Summary variance / check',pd.Series('',index=data.index)).ne('Summary matches detail') | data.get('Section title mismatch',pd.Series(False,index=data.index)).fillna(False))
    c4.metric('Source checks to review',int(_wip_checks.sum()))
    st.caption('Source of record: second sheet of each active section workbook. Reported “ยังไม่ปิด” and GW (Kg) drive WIP counts and weight. Total WO − Closed WO is shown as a validation check; when it disagrees, the sheet’s reported open count is retained and flagged. Category F is shown as P. No detail-row category fallback is added.')
    st.markdown('#### Selected current snapshot / ไฟล์ปัจจุบันของแต่ละแผนก')
    st.dataframe(pd.DataFrame([{'Section':sec,'Selected current file':p.name,'Imported at':source_metadata.get(str(p.resolve()),{}).get('registered_at',source_metadata.get(str(p.resolve()),{}).get('uploaded_at','File time only'))} for sec,p in loaded_sources.items()]),use_container_width=True,hide_index=True)
    view=st.selectbox('Process / กระบวนการ',['All sections']+list(loaded_sources),key='prod_wip_section')
    filtered=data if view=='All sections' else data[data.Section.eq(view)]
    a,b=st.columns([3,2])
    with a:
        chart=px.bar(filtered,x='Section',y='Open t',color='Category',color_discrete_map=COLORS,barmode='stack',title='Production WIP by section and category (t)')
        chart.update_layout(height=480,font_size=16,xaxis_tickangle=-18,margin=dict(l=20,r=20,t=60,b=110))
        st.plotly_chart(chart,use_container_width=True,config={'displaylogo':False,'toImageButtonOptions':{'format':'svg'}})
    with b:
        p=filtered.groupby('Category',as_index=False)['Open t'].sum()
        pie=px.pie(p,names='Category',values='Open t',hole=.5,color='Category',color_discrete_map=COLORS,title='WIP composition (t)')
        pie.update_layout(height=480,font_size=16,margin=dict(l=15,r=15,t=60,b=50))
        st.plotly_chart(pie,use_container_width=True)
    st.subheader('📊 Planning vs Production — section × category / เปรียบเทียบ WIP')
    st.caption('Planning first, Production second. Counts are section-level WO records, NOT unique factory orders. Tonnes are Planning NET estimates vs Production GROSS recorded weight; review weight basis and snapshot date.')
    # Source-derived Production review, not a blank manual table.
    prod=data.groupby(['Section','Category'],as_index=False).agg(**{'Production WIP t':('Open t','sum'),'Production open WO records':('Open WO','sum'),'Production closed WO records':('Closed WO','sum')})
    plan=pd.DataFrame()
    if isinstance(master,pd.DataFrame) and not master.empty and 'Work Order' in master.columns:
        mapping={'Mixing':['Ready for Mixing','WIP Mixing'], 'Forming':['Ready for Forming','WIP Forming'], 'Firing + curing':['Ready for Firing','WIP Firing'], 'Grinding / Cutting (Production combined)':['Ready for Grinding / Cutting','WIP Grinding / Cutting'], 'Packing':['Ready for Packing','WIP Packing']}
        m=master.copy()
        if 'Category' in m:m['Category']=m['Category'].astype(str).str.upper().str.strip().replace({'F':'P'})
        else:m['Category']='UNCLASSIFIED'
        weight=pd.to_numeric(m['Net Weight g/pc'],errors='coerce')/1000000 if 'Net Weight g/pc' in m else pd.Series(float('nan'),index=m.index)
        pieces=[]
        for section,candidates in mapping.items():
            col=next((c for c in candidates if c in m),None)
            if not col:continue
            q=pd.to_numeric(m[col],errors='coerce').clip(lower=0)
            weight=weight.where(weight.gt(0))
            t=pd.DataFrame({'Section':section,'Category':m['Category'],'Planning WIP pcs':q,'Planning WIP t':q*weight,'Work Order':m['Work Order'].astype(str)})
            t=t.loc[q.gt(0)].copy()
            pieces.append(t)
        if pieces:
            plan=pd.concat(pieces,ignore_index=True)
            plan=plan.groupby(['Section','Category'],as_index=False).agg(**{'Planning WIP pcs':('Planning WIP pcs','sum'),'Planning WIP t':('Planning WIP t',lambda x:x.sum(min_count=1) if x.notna().all() else float('nan')),'Planning open WO records':('Work Order','nunique')})
    cmp=prod.merge(plan,on=['Section','Category'],how='outer') if not plan.empty else prod.copy()
    for col in ['Production WIP t','Production open WO records','Production closed WO records','Planning WIP pcs','Planning WIP t','Planning open WO records']:
        if col not in cmp:cmp[col]=float('nan')
    cmp['Variance t (Production − Planning)']=cmp['Production WIP t']-cmp['Planning WIP t']
    cmp['WO-record variance (Production − Planning)']=cmp['Production open WO records']-cmp['Planning open WO records']
    cmp['Reconciliation status']=cmp.apply(lambda r:'MISSING PLANNING WEIGHT' if pd.isna(r['Planning WIP t']) else ('MISSING PRODUCTION' if pd.isna(r['Production WIP t']) else ('REVIEW VARIANCE' if abs(r['Variance t (Production − Planning)'])>0.01 or abs(r['WO-record variance (Production − Planning)'])>0 else 'NUMERICALLY CLOSE — BASIS / CUTOFF UNVERIFIED')),axis=1)
    cmp['Possible cause / evidence']='Check WO-level list, cutoff date, curing classification, gross/net weight, route and closure'
    cmp['Confirmed cause / reason']=''
    cmp['Correction / next action']=''
    cmp['Owner']=''
    cmp['Approval status']='PENDING'
    st.session_state['prod_wip_comparison_current']=cmp.copy()
    chart=cmp.groupby('Section',as_index=False)[['Planning WIP t','Production WIP t']].sum(min_count=1)
    if chart[['Planning WIP t','Production WIP t']].notna().any().any():
        fig=px.bar(chart,x='Section',y=['Planning WIP t','Production WIP t'],barmode='group',title='Planning → Production WIP (tonnes; verify weight basis)')
        fig.update_traces(texttemplate='%{y:.2f}',textposition='outside',cliponaxis=False)
        fig.update_layout(uniformtext_minsize=12,uniformtext_mode='hide',height=500)
        st.plotly_chart(fig,use_container_width=True)
    st.markdown('#### Section × category reconciliation — click/edit every review cell')
    st.caption('Production source quantities are editable above. Here you can record confirmed cause, owner and proposed corrections; approved source changes must be made through controlled imports/overrides.')
    fp=tuple(str(item) for item in st.session_state.get('prod_wip_source_fingerprint',()))
    if st.session_state.get('wip_cmp_fingerprint')!=fp:
        st.session_state.wip_cmp_review=cmp.copy();st.session_state.wip_cmp_fingerprint=fp
    # Retain reviewer comments across source recalculation using stable keys.
    old=st.session_state.wip_cmp_review
    for field in ['Confirmed cause / reason','Correction / next action','Owner','Approval status']:
        if field in old:
            lookup={(str(r['Section']),str(r['Category'])):r[field] for _,r in old.iterrows()}
            cmp[field]=[lookup.get((str(r.Section),str(r.Category)),r[field]) for _,r in cmp.iterrows()]
    edited=st.data_editor(cmp,num_rows='fixed',hide_index=True,use_container_width=True,key='wip_reconciliation_editor',disabled=[c for c in cmp.columns if c not in ['Confirmed cause / reason','Correction / next action','Owner','Approval status']])
    st.session_state.wip_cmp_review=edited.copy()
    st.session_state['prod_wip_comparison_current']=edited.copy()
    st.download_button('⬇️ Export WIP reconciliation CSV',edited.to_csv(index=False).encode('utf-8-sig'),'WIP_reconciliation.csv','text/csv')
    st.info('Why a variance? The summary cannot prove its root cause. Inspect matching WO rows and confirm weight basis, cutoff, curing and route with Production before editing the controlled source.')
    _display_cols=['Section','Category','Total WO','WIP WOs (source open)','Open WIP WO (Total − Closed)','Open WO','Closed WO','Open kg','Open t','Summary variance / check','Source sheet','Workbook month title','Monthly last movement day','Original filename','Uploaded at']
    st.dataframe(filtered[[c for c in _display_cols if c in filtered]],use_container_width=True,hide_index=True)
    if _wip_checks.any():
        st.warning('Source checks found: summary formulas/cached values do not fully agree with monthly detail, some categories are unclassified, or a worksheet title conflicts with its assigned section. Detail-derived values remain visible and exact evidence is below.')
        with st.expander('Source rows, summary cells and source checks',expanded=True):
            _check_cols=['Section','Category','Summary source cells','Summary variance / check','Summary grand-total source cells','Summary grand-total check','Workbook section title','Section title check','Unmapped category source value(s)','Unknown status rows','Weight error rows','Duplicate WO records','Source sheet','Source evidence','Detail source rows','Source']
            st.dataframe(data.loc[_wip_checks,[c for c in _check_cols if c in data]],use_container_width=True,hide_index=True)
    with st.expander('✏️ EDIT PRODUCTION WIP REVIEW / แก้ไขข้อมูล',expanded=False):
        st.caption('Edit the REVIEW COPY, not the Production workbook. Changes update the charts after Apply. Verify with Production before release.')
        edit=st.data_editor(data[['Section','Category','Total WO','Open WO','Closed WO','Open kg']],num_rows='fixed',hide_index=True,use_container_width=True,key='prod_wip_edit',disabled=['Section','Category'])
        if st.button('Apply reviewed WIP changes',key='prod_wip_apply'):
            out=data.copy()
            out['Section']=edit['Section'].values
            out['Category']=edit['Category'].astype(str).str.strip().str.upper().replace({'F':'P'}).values
            for c in ['Total WO','Open WO','Closed WO','Open kg']:out[c]=pd.to_numeric(edit[c],errors='coerce')
            out['WIP WOs (source open)']=out['Open WO']
            out['Open WIP WO (Total − Closed)']=out['Total WO']-out['Closed WO']
            out['Open t']=out['Open kg']/1000
            out['WO Balance Error']=out['Total WO']-out['Open WO']-out['Closed WO']
            out['Open WIP WO (Total − Closed)']=out['Total WO']-out['Closed WO']
            for i in out.index:
                for c in ['Total WO','Open WO','Closed WO','Open kg']:
                    if str(data.at[i,c]) != str(out.at[i,c]):
                        st.session_state.setdefault('prod_wip_audit',[]).append({'UTC':datetime.now(timezone.utc).isoformat(),'Section':out.at[i,'Section'],'Category':out.at[i,'Category'],'Field':c,'Before':str(data.at[i,c]),'After':str(out.at[i,c]),'Source fingerprint':str(st.session_state.prod_wip_source_fingerprint)})
            st.session_state.prod_wip_review=out
            st.rerun()
    st.download_button('⬇️ Export reviewed WIP CSV',data.to_csv(index=False).encode('utf-8-sig'),file_name='Production_WIP_review_'+str(snapshot)+'.csv',mime='text/csv')
    if st.session_state.get('prod_wip_audit'):
        st.download_button('Download Production correction audit',pd.DataFrame(st.session_state.prod_wip_audit).to_csv(index=False).encode('utf-8-sig'),'Production_correction_audit.csv','text/csv')
    evidence_sources={section:str(path) for section,path in loaded_sources.items()}
    render_wo_review(st,master,base_dir,evidence_sources,{section:None for section in SOURCES},snapshot)


def planning_production_comparison(wip_long,base_dir):
    """Compare category/section tonnes with source evidence; never equate pcs and kg."""
    rows=[]
    ranked,metadata,errors=candidates(base_dir)
    for section,paths in ranked.items():
        for path in paths:
            try:
                d=read_summary(path);d['Section']=section;d['Source']=str(path.resolve())
                rows.append(d[['Section','Category','Open t','Source']].copy());break
            except Exception:continue
    if not rows:return pd.DataFrame()
    prod=pd.concat(rows,ignore_index=True).rename(columns={'Open t':'Production WIP t'})
    if wip_long is None or wip_long.empty:return prod
    plan=wip_long.copy()
    plan['Section']=plan['Section'].replace({'Preparation Required':'Preparation','Firing':'Firing + curing','Curing':'Firing + curing','Grinding / Cutting':'Grinding / Cutting (Production combined)','Grinding':'Grinding / Cutting (Production combined)','Cutting':'Grinding / Cutting (Production combined)'})
    plan['Category']=plan['Category'].astype(str).str.upper().replace({'F':'P'})
    plan=plan.groupby(['Section','Category'],as_index=False)['WIP ton'].sum(min_count=1).rename(columns={'WIP ton':'Planning WIP t'})
    out=prod.merge(plan,on=['Section','Category'],how='outer')
    out['Variance t']=out['Production WIP t']-out['Planning WIP t']
    return out


def production_snapshot(base_dir):
    ranked,metadata,errors=candidates(base_dir);rows=[]
    for section,paths in ranked.items():
        last_error=None
        for path in paths:
            try:
                d=read_summary(path,section);d['Section']=section;d['Source']=str(path.resolve())
                meta=metadata.get(str(path.resolve()),{})
                d['Original filename']=meta.get('original_name') or meta.get('original_filename') or path.name
                d['Uploaded at']=meta.get('registered_at') or meta.get('uploaded_at') or 'Not recorded'
                rows.append(d)
                if path!=paths[0]:errors.append(f'{section}: latest copy {paths[0].name} is unreadable; used previous readable copy {path.name}.')
                break
            except Exception as ex:last_error=ex
        else:
            if last_error is not None:errors.append(f'{section}: no readable WIP workbook. Latest file {paths[0].name}: {last_error}')
    return (pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()),errors

"""Display-only, traceable selection/editor for management drilldown.
Never mutates the uploaded Plan2026 or firing source; edits are session-only.
"""
import io
import hashlib
from datetime import datetime, timezone
import pandas as pd
import plotly.express as px

CATS=['P','R','S','T','M','PB']
PALETTE={'P':'#2563EB','R':'#16A34A','S':'#DC2626','T':'#7C3AED','M':'#0891B2','PB':'#EAB308'}

def interactive(st, data, name, date_col=None, category_col=None, qty_col=None, source='Calculated planning output'):
    st.subheader(name)
    if not isinstance(data,pd.DataFrame) or data.empty:
        st.info('No verified rows / ไม่มีข้อมูลที่ตรวจสอบแล้ว');return pd.DataFrame()
    raw=data.copy().reset_index(drop=True)
    key='trace_'+''.join(c if c.isalnum() else '_' for c in name)[:55]
    fingerprint=hashlib.sha256(raw.to_csv(index=False).encode()).hexdigest()
    if st.session_state.get(key+'_source_hash') != fingerprint:
        for suffix in ['_editor','_from','_to','_categories','_plot']:
            st.session_state.pop(key+suffix,None)
        st.session_state[key+'_source_hash']=fingerprint
        st.session_state[key+'_edited']=raw.copy();st.session_state[key+'_source_shape']=tuple(raw.shape)
    view=st.session_state[key+'_edited'].copy()
    if date_col not in view:date_col=next((c for c in ['Plan Date','Due Date','Load Date','Date'] if c in view),None)
    if category_col not in view:category_col=next((c for c in ['Category','Product Category','Process','Section','Program'] if c in view),None)
    if qty_col not in view:qty_col=next((c for c in ['Plan Qty','Open Qty','Order Qty','Effective Qty','Remaining Qty','Qty'] if c in view),None)
    a,b=st.columns(2)
    if date_col:
        ds=pd.to_datetime(view[date_col],errors='coerce')
        if ds.notna().any():
            lo,hi=ds.min().date(),ds.max().date()
            with a:start=st.date_input('FROM / จาก',value=lo,min_value=lo,max_value=hi,key=key+'_from')
            with b:end=st.date_input('TO / ถึง',value=hi,min_value=lo,max_value=hi,key=key+'_to')
            view=view[ds.between(pd.Timestamp(start),pd.Timestamp(end)+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1))]
    if category_col:
        options=sorted(view[category_col].dropna().astype(str).unique().tolist())
        chosen=st.multiselect('Filter / ตัวกรอง',options,default=options,key=key+'_categories')
        view=view[view[category_col].astype(str).isin(chosen)]
    selected=view
    if category_col and qty_col and len(view):
        summary=view.assign(_qty=pd.to_numeric(view[qty_col],errors='coerce').fillna(0)).groupby(category_col,dropna=False,as_index=False)['_qty'].sum()
        if len(summary)<=4 and summary['_qty'].ge(0).all() and summary['_qty'].sum()>0:
            fig=px.pie(summary,names=category_col,values='_qty',hole=.55,color=category_col,color_discrete_map=PALETTE)
        else:
            fig=px.bar(summary,x=category_col,y='_qty',color=category_col,color_discrete_map=PALETTE,text_auto=',.0f')
        fig.update_layout(font_size=17,height=430,margin=dict(l=30,r=30,t=35,b=65),legend=dict(orientation='h',y=-.22))
        st.caption('Select a segment/bar to inspect matching source rows; editable data is session-only.')
        try:
            event=st.plotly_chart(fig,on_select='rerun',selection_mode='points',use_container_width=True,key=key+'_plot',config={'displaylogo':False,'toImageButtonOptions':{'format':'svg','filename':key}})
            points=(event.selection.points if event and event.selection else [])
            if points:
                v=points[0].get('label',points[0].get('x'))
                if v is not None:selected=view[view[category_col].astype(str).eq(str(v))]
        except TypeError:
            st.plotly_chart(fig,use_container_width=True,key=key+'_plot_fallback')
    with st.expander('✏️ Related rows / ข้อมูลต้นทาง (click to edit)',expanded=True):
        st.caption(f'SOURCE: {source}. Corrections affect this analysis only until exported; they never silently overwrite Plan2026.')
        if len(selected):
            edited=st.data_editor(selected,use_container_width=True,hide_index=True,num_rows='fixed',key=key+'_editor')
            if st.button('Apply reviewed corrections / ใช้ข้อมูลที่ตรวจสอบ',key=key+'_apply'):
                view_all=st.session_state[key+'_edited'].copy()
                for i,row in edited.iterrows():
                    if i in view_all.index:
                        for c in edited.columns:view_all.at[i,c]=row[c]
                changes=[]
                for i,row in edited.iterrows():
                    for c in edited.columns:
                        before=st.session_state[key+'_edited'].at[i,c]
                        if str(before)!=str(row[c]):
                            changes.append({'UTC':datetime.now(timezone.utc).isoformat(),'Source hash':fingerprint,'Row':str(i),'Field':c,'Before':str(before),'After':str(row[c])})
                st.session_state.setdefault(key+'_audit',[]).extend(changes)
                st.session_state[key+'_edited']=view_all
                st.rerun()
        st.download_button('⬇️ Export reviewed rows CSV',view.to_csv(index=False).encode('utf-8-sig'),file_name=key+'.csv',mime='text/csv',key=key+'_csv')
    if st.session_state.get(key+'_audit'):
        st.download_button('Download correction audit CSV',pd.DataFrame(st.session_state[key+'_audit']).to_csv(index=False).encode('utf-8-sig'),key+'_audit.csv',key=key+'_audit_download')
    return st.session_state[key+'_edited']

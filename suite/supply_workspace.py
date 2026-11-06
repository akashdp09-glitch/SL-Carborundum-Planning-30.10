"""Unit-explicit firm material demand and readable MPS demand profiles."""
from pathlib import Path
import pandas as pd
from .exporters import to_workbook
from .common import bkk_today


def material_requirements(raw,master,pairs):
    rows=[];gaps=[]
    if master is None or master.empty:return pd.DataFrame(),pd.DataFrame([{'Issue':'Active stage quantities are unavailable'}])
    for idx,r in raw.iterrows():
        wo=str(r.get('ProductionCode','')).strip()
        job=master[master['Work Order'].astype(str).eq(wo)]
        if job.empty:continue
        fields=[c for c in ['Mixing Remaining Qty','Mixing Plan Qty','Order Qty','Authoritative Closed'] if c in job]
        if len(job[fields].astype(str).drop_duplicates())>1:gaps.append({'Work Order':wo,'Issue':'Conflicting repeated WO stage quantities'});continue
        j=job.iloc[0]
        if bool(j.get('Authoritative Closed',j.get('Overall Closed',False))):continue
        remaining=pd.to_numeric(j.get('Mixing Remaining Qty'),errors='coerce')
        basis=pd.to_numeric(j.get('Mixing Plan Qty',j.get('Order Qty')),errors='coerce')
        if pd.isna(remaining) or pd.isna(basis) or basis<=0:gaps.append({'Work Order':wo,'Issue':'Missing mixing quantity / basis; no material need invented'});continue
        if remaining<=0:continue
        fraction=min(float(remaining)/float(basis),1)
        for code_col,gram_col in pairs:
            code=str(r.get(code_col,'')).strip();grams=pd.to_numeric(r.get(gram_col),errors='coerce')
            if code in {'','nan','None','0','#N/A'}:continue
            if pd.isna(grams) or grams<0:gaps.append({'Work Order':wo,'Material':code,'Issue':'Invalid source grams'});continue
            rows.append({'Work Order':wo,'Material':code,'Need date':j.get('Delivery Date',j.get('Due Date')),'Required tonnes':float(grams)*fraction/1e6,'Source grams':float(grams),'Unmixed fraction':fraction,'Plan row':idx+4,'Cells':f'{code_col} / {gram_col}','Basis':'Source order BOM grams × remaining mixing / planned mixing; not forecast demand'})
    return pd.DataFrame(rows),pd.DataFrame(gaps)


def reconcile_materials(demand,stock):
    if demand.empty:return pd.DataFrame()
    req=demand.groupby('Material',as_index=False).agg(Required_tonnes=('Required tonnes','sum'),WOs=('Work Order','nunique'))
    s=stock.rename(columns={'material':'Material'}).copy()
    if not s.empty:
        duplicated=s.Material.duplicated(keep=False);s['Duplicate stock code']=duplicated
        # A repeated stock code is not automatically an additional stock lot.
        duplicate_codes=set(s.loc[duplicated,'Material']);s=s.drop_duplicates('Material').set_index('Material')
        for c in ['stock_g','incoming_g','lab_g']:
            if c not in s:s[c]=float('nan')
            s[c]=pd.to_numeric(s[c],errors='coerce')/1e6
            s.loc[s.index.isin(duplicate_codes),c]=float('nan')
        req=req.merge(s[['stock_g','incoming_g','lab_g','Duplicate stock code']],on='Material',how='left')
    else:
        for c in ['stock_g','incoming_g','lab_g']:req[c]=float('nan')
    req=req.rename(columns={'stock_g':'Physical stock tonnes','incoming_g':'Undated incoming tonnes','lab_g':'Under test tonnes'})
    req['Hard shortage tonnes']=(req.Required_tonnes-req['Physical stock tonnes']).clip(lower=0)
    req['Potential shortage after incoming tonnes']=(req.Required_tonnes-req['Physical stock tonnes']-req['Undated incoming tonnes']).clip(lower=0)
    req['Action']=['CONFIRM STOCK — missing/duplicate basis' if pd.isna(s) else 'SHORT — confirm dated receipts or purchase' if q>0 else 'Physical stock covers undated gross need; verify timing/reservations' for s,q in zip(req['Physical stock tonnes'],req['Hard shortage tonnes'])]
    return req.sort_values('Hard shortage tonnes',ascending=False,na_position='first')


def render_mrp(st,raw,master,pairs,stock_path):
    import plotly.express as px
    from .planners import read_material_stock
    st.header('🧪 วัตถุดิบที่ต้องใช้ / Material requirements')
    d,gaps=material_requirements(raw,master,pairs)
    stock=read_material_stock(stock_path) if stock_path else pd.DataFrame()
    result=reconcile_materials(d,stock)
    st.caption('All analytical weights are metric tonnes. Physical stock, undated receipts and stock under test are separate. Forecast is not silently added to firm WO demand; dated MRP proposals require lead-time, receipt and reservation inputs.')
    if d.empty:st.info('No source-backed unmixed material demand. See diagnostics.');st.dataframe(gaps,use_container_width=True,hide_index=True);return
    st.metric('ความต้องการงานที่ยังไม่ผสม / Unmixed firm demand',f'{d["Required tonnes"].sum():,.4f} t')
    st.dataframe(result,use_container_width=True,hide_index=True)
    st.plotly_chart(px.bar(result.head(30),x='Material',y=['Required_tonnes','Physical stock tonnes','Hard shortage tonnes'],barmode='group',title='Firm demand vs physical stock — tonnes'),use_container_width=True)
    x=d.copy();x['Need month']=pd.to_datetime(x['Need date'],errors='coerce').dt.strftime('%Y-%m').fillna('NO DATE')
    monthly=x.groupby(['Need month','Material'],as_index=False)['Required tonnes'].sum()
    st.plotly_chart(px.bar(monthly,x='Need month',y='Required tonnes',color='Material',barmode='stack'),use_container_width=True)
    with st.expander('Work-order and source-cell detail / รายการอ้างอิง'):st.dataframe(d,use_container_width=True,hide_index=True);st.dataframe(gaps,use_container_width=True,hide_index=True)
    st.download_button('⬇ Excel — material demand, shortages, actions & evidence',to_workbook({'Material actions':result,'Firm WO demand':d,'Monthly demand':monthly,'Review gaps':gaps}),'Material_Requirements_Analysis.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def mps_tables(op):
    d=op.copy();d['Due Date']=pd.to_datetime(d['Due Date'],errors='coerce')
    d['Month']=d['Due Date'].dt.strftime('%Y-%m').fillna('NO DATE');d['Week']=d['Due Date'].dt.to_period('W-SUN').astype(str).replace('NaT','NO DATE')
    d['Delivery risk']=d['Due Date'].map(lambda x:'NO DUE DATE' if pd.isna(x) else 'OVERDUE' if x.date()<bkk_today() else 'UPCOMING')
    if 'Plan2026 kg/pc' in d:d.loc[pd.to_numeric(d['Plan2026 kg/pc'],errors='coerce').fillna(0).le(0),'ton']=float('nan')
    tables={'WO demand':d}
    for key,cols in [('Monthly category',['Month','Product Category']),('Weekly category',['Week','Product Category']),('Section',['Section']),('Delivery risk',['Delivery risk']),('Customer',['Customer'])]:
        if not all(c in d for c in cols):continue
        tables[key]=d.groupby(cols,dropna=False).agg(WOs=('Work Order','nunique'),Pending_pcs=('pcs','sum'),Known_tonnes=('ton',lambda s:s.sum(min_count=1)),Weight_known_rows=('ton','count')).reset_index()
    return tables


def render_mps(st,op):
    import plotly.express as px
    st.header('🗓️ วิเคราะห์แผนหลัก / Master demand analysis')
    if op is None or op.empty:st.info('No active open demand from Plan-2026');return
    tables=mps_tables(op);d=tables['WO demand']
    a,b,c=st.columns(3);a.metric('ใบสั่งคงค้าง / Open WOs',d['Work Order'].nunique());b.metric('ชิ้นคงเหลือ / Pending pcs',f'{d.pcs.sum():,.0f}');c.metric('น้ำหนักที่ทราบ / Known tonnes',f'{d.ton.sum(min_count=1):,.3f}')
    for key in ['Monthly category','Weekly category','Delivery risk','Section','Customer']:
        if key not in tables:continue
        st.subheader(key);v=tables[key];st.dataframe(v,use_container_width=True,hide_index=True)
        if key in ['Monthly category','Weekly category']:st.plotly_chart(px.bar(v,x=v.columns[0],y='Pending_pcs',color='Product Category',barmode='stack'),use_container_width=True)
    st.caption('Firm unpacked demand profile, not a capacity-approved executable schedule. Missing dates and weights remain visible. Forecast netting belongs in the dated MPS/MRP scenario; forecast is not added again to these existing WOs.')
    st.download_button('⬇ Excel — weekly/monthly/category/customer demand',to_workbook(tables),'Master_Demand_Analysis.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

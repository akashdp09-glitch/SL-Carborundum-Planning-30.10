from pathlib import Path
import sys, re, os, hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd, numpy as np, streamlit as st, plotly.express as px
ROOT=Path(__file__).resolve().parent
SHARED_ROOT=Path(os.environ.get('SL_SHARED_ROOT',str(ROOT/'CENTRAL_DATA'))).resolve()
DATA=Path(os.environ.get('SL_COMPANY_DATA',str(SHARED_ROOT/'COMPANY_DATA'))).resolve(); DATA.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'apps'/'daily'))
import sl_daily_engine_v3_22_from_v17 as eng
st.set_page_config(page_title='SL Integrated Analysis',page_icon='📊',layout='wide')
st.markdown('''<style>.block-container{padding-top:.7rem;max-width:1750px}.stTabs [data-baseweb="tab"]{font-size:1.05rem;font-weight:800}[data-testid="stMetricValue"]{font-size:1.7rem}</style>''',unsafe_allow_html=True)
st.title('SL Carborundum — Integrated Planning Analysis')
st.caption('One planning truth: this page reads the same active central files as Home and Daily Planner.')
def fp(n):
 p=DATA/n; return p if p.exists() else None
def nnum(x,idx=None):
 if isinstance(x,pd.Series): return pd.to_numeric(x,errors='coerce').fillna(0)
 if idx is None:return pd.to_numeric(pd.Series([x]),errors='coerce').fillna(0).iloc[0]
 return pd.Series(0.0,index=idx)
plan=fp('Plan-2026-LATEST.xlsx')
if not plan: st.error('Upload Plan-2026 once in Source Upload. The saved copy is reused until you replace it.');st.stop()
with open(plan,'rb') as f: master,_,_=eng.read_plan2026(f,{})
raw=pd.read_excel(plan,sheet_name='แผนการเผา',header=2)
_stat=plan.stat();_sha=hashlib.sha256(plan.read_bytes()).hexdigest()
st.caption(f"Active Plan source: {plan.resolve()} · modified {datetime.fromtimestamp(_stat.st_mtime,ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds')} · SHA-256 {_sha}")
# enrich from raw source, without changing source file
cols=['ProductionCode','ประเภทสินค้า','D','T','H']
rr=raw[[c for c in cols if c in raw.columns]].copy(); rr=rr.rename(columns={'ProductionCode':'Work Order','ประเภทสินค้า':'Product Category'})
rr['Work Order']=rr['Work Order'].astype(str).str.strip(); rr=rr.drop_duplicates('Work Order')
master=master.merge(rr,on='Work Order',how='left',suffixes=('','_raw'))
master['Due Date']=pd.to_datetime(master.get('Due Date',master.get('Delivery Date')),errors='coerce')
master['Open pcs']=nnum(master['Open Qty'],master.index) if 'Open Qty' in master.columns else nnum(master.get('Order Qty',0),master.index)
master['Order pcs']=nnum(master.get('Order Qty',0),master.index)
master['kg/pc']=nnum(master.get('Plan2026 kg/pc',0),master.index)
master['Weight kg']=master['Open pcs']*master['kg/pc']; master['Weight ton']=master['Weight kg']/1000
for c in ['D','T','H']:
 if c not in master.columns: master[c]=''
master['Product Category']=master.get('Product Category','').astype(str).str.upper().replace({'NAN':'','#N/A':''})
master['Size']=master.apply(lambda r:f"D{r.get('D','')} × T{r.get('T','')} × H{r.get('H','')}",axis=1)
def stage(r):
 if bool(r.get('Overall Closed',False)) or float(r.get('Open pcs',0) or 0)<=0:return 'Closed'
 for s in ['Preparation','Mixing','Forming','Firing','Grinding / Cutting','Packing']:
  if nnum(r.get(s+' Remaining Qty',0))>0:return s
 return 'Open / Check'
master['Current Section']=master.apply(stage,axis=1)
openm=master[(~master.get('Overall Closed',pd.Series(False,index=master.index)).fillna(False).astype(bool))&(master['Open pcs']>0)].copy()
today=pd.Timestamp.now(tz='Asia/Bangkok').tz_localize(None).normalize();bo=openm[openm['Due Date'].notna()&(openm['Due Date']<today)].copy();bo['Late days']=(today-bo['Due Date']).dt.days
m1,m2,m3,m4=st.columns(4);m1.metric('Open WOs',openm['Work Order'].nunique());m2.metric('Open pcs',f"{openm['Open pcs'].sum():,.0f}");m3.metric('Open weight',f"{openm['Weight ton'].sum():,.1f} t");m4.metric('Backorder WOs',bo['Work Order'].nunique())
t1,t2,t3,t4=st.tabs(['🏭 WIP','🚨 Backorder','🗓️ MPS / Long-term demand','🧪 Material MRP'])
with t1:
 st.subheader('WIP — section • due date • category • weight • WO • pcs')
 g=openm.groupby(['Current Section','Product Category'],as_index=False).agg(WOs=('Work Order','nunique'),pcs=('Open pcs','sum'),ton=('Weight ton','sum'))
 st.plotly_chart(px.bar(g,x='Current Section',y='ton',color='Product Category',barmode='stack',title='Physical/open WIP weight by section and category'),use_container_width=True);st.dataframe(g,use_container_width=True,hide_index=True)
 d=openm.copy();d['Due Month']=d['Due Date'].dt.strftime('%Y-%m');gd=d.groupby(['Due Month','Current Section'],as_index=False).agg(WOs=('Work Order','nunique'),pcs=('Open pcs','sum'),ton=('Weight ton','sum'));st.dataframe(gd,use_container_width=True,hide_index=True)
with t2:
 st.subheader('Backorder — SAME open-quantity rule as Daily Planner')
 st.caption('Backorder = Due Date before today + remaining qty > 0 + order not closed. Order closed = Packing (EU) closed OR Overall WO closure (FC) closed/cancelled (rule CLOSE-1). Preparation and other section closures do NOT close the order. ยังไม่ปิด=open; ปิดใบสั่ง/ปิด/ยกเลิก=closed. A closed order is excluded from backorder and new material planning.')
 if bo.empty:st.success('No overdue open work orders.')
 else:
  bc=bo.groupby(['Product Category','Size','Current Section'],as_index=False).agg(WOs=('Work Order','nunique'),pcs=('Open pcs','sum'),ton=('Weight ton','sum'),Max_Late_Days=('Late days','max')).sort_values('ton',ascending=False)
  st.dataframe(bc,use_container_width=True,hide_index=True,height=360)
  show=[c for c in ['Work Order','Customer','Product Code','Product Category','Size','Open pcs','Weight ton','Due Date','Late days','Current Section'] if c in bo.columns];st.dataframe(bo[show].sort_values(['Late days','Weight ton'],ascending=False),use_container_width=True,hide_index=True,height=430)
with t3:
 st.subheader('MPS — firm open demand / backorder recovery visibility')
 x=openm.copy();x['Due Month']=x['Due Date'].dt.strftime('%Y-%m').fillna('DATE MISSING');gm=x.groupby(['Due Month','Product Category'],as_index=False).agg(WOs=('Work Order','nunique'),pcs=('Open pcs','sum'),ton=('Weight ton','sum'))
 st.plotly_chart(px.bar(gm,x='Due Month',y='pcs',color='Product Category',barmode='stack',title='Firm open production requirement by due month'),use_container_width=True);st.dataframe(gm,use_container_width=True,hide_index=True)
 st.info('Detailed executable MPS remains in Daily Planner Long-Term Plan: backorder recovery + higher of Sales Forecast or firm future demand + capacity-feasible possible plan. This page reconciles the shared open-demand basis.')
with t4:
 st.subheader('Material MRP — actual material codes only')
 st.caption('Open Plan-2026 material requirement uses material1…material5 with g/g.1…g.4 and excludes CY/FB/FC closed/cancelled rows. Forecast conversion uses Sales Forecast IDItem → P280526/SD → recipe QTY → g/pc → kg.')
 def closed(s):
  z=s.astype(str).str.strip(); return (~z.str.contains('ยังไม่ปิด',na=False)) & (z.eq('ปิด')|z.str.contains('ปิดใบสั่ง|ยกเลิก|cancel|closed',case=False,na=False))
 mask=pd.Series(True,index=raw.index)
 if raw.shape[1]>158: mask=~(closed(raw.iloc[:,102])|closed(raw.iloc[:,157])|closed(raw.iloc[:,158]))
 rows=[]
 pairs=[('material1','g'),('material2','g.1'),('material3','g.2'),('material4','g.3'),('material5','g.4')]
 # tolerate older headers 1..5
 for _,r in raw.loc[mask].iterrows():
  wo=str(r.get('ProductionCode','')).strip();due=pd.to_datetime(r.get('กำหนดส่งใหม่'),errors='coerce');due=due if pd.notna(due) else pd.to_datetime(r.get('กำหนดเข้าคลัง'),errors='coerce')
  for i,(mc,gc) in enumerate(pairs,1):
   code=str(r.get(mc,r.get(str(i),''))).strip();grams=nnum(r.get(gc,0))
   if code and code.lower() not in {'0','nan','none','#n/a'} and grams>0:rows.append({'Source':'Open Plan-2026','Work Order':wo,'Material Code':code,'Required kg':grams/1000,'Need Date':due})
 mat=pd.DataFrame(rows)
 sales=fp('Sales-Forecast-LATEST.xlsx');pm=fp('P280526-LATEST.xlsx')
 diag=[]
 if sales and pm:
  try:
   sd=pd.read_excel(pm,sheet_name='SD',header=1);sf=pd.read_excel(sales,sheet_name='Data Item FC26 (Revised)',header=3)
   idcol='รหัสสินค้า.1' if 'รหัสสินค้า.1' in sd.columns else next((c for c in sd.columns if str(c).strip().lower() in {'รหัสสินค้า','iditem','product code','productcode'}),None)
   sid=next((c for c in sf.columns if 'IDItem' in str(c)),None);months=[c for c in sf.columns if str(c).startswith('จำนวน')]
   if not idcol or not sid: raise ValueError('IDItem/product-code column not found in Sales Forecast or SD')
   # prefer last populated SD row; keep traceable rather than inventing recipe
   sd=sd[sd[idcol].notna()].copy();lookup={str(r[idcol]).strip():r for _,r in sd.iterrows()}
   fr=[]
   for _,sr in sf.iterrows():
    pid=str(sr.get(sid,'')).strip();rr=lookup.get(pid)
    if rr is None:continue
    basis=nnum(rr.get('QTY',0))
    if basis<=0:continue
    for i,(mc,gc) in enumerate(pairs,1):
     code=str(rr.get(mc,rr.get(str(i),''))).strip();grams=nnum(rr.get(gc,0))
     if not code or code.lower() in {'0','nan','none','#n/a'} or grams<=0:continue
     for c in months:
      q=nnum(sr.get(c,0))
      if q>0:fr.append({'Source':'Sales Forecast via SD','Work Order':pid,'Material Code':code,'Required kg':q*grams/basis/1000,'Need Date':str(c)})
   if fr:mat=pd.concat([mat,pd.DataFrame(fr)],ignore_index=True)
  except Exception as ex:diag.append(str(ex))
 if mat.empty:
  st.error('Material demand is zero because no valid material-code/gram pairs were found in the currently saved sources.')
  st.write({'Plan rows checked':int(mask.sum()),'Plan material headers found':[c for c in sum(([a,b] for a,b in pairs),[]) if c in raw.columns],'Sales Forecast saved':bool(sales),'P280526 saved':bool(pm),'Diagnostics':diag})
 else:
  tot=mat.groupby('Material Code',as_index=False)['Required kg'].sum().sort_values('Required kg',ascending=False);stock=fp('Stock-on-Hand-LATEST.xlsx')
  if stock:
   try:
    a=pd.read_excel(stock,sheet_name='Abrasive').rename(columns={'รหัสสินค้า':'Material Code','รายละเอียดสินค้า':'Description','วัตถุดิบคงคลัง':'Stock kg','รอวัถุดิบเข้า':'Incoming kg','รอผลLAB':'LAB kg'});keep=[c for c in ['Material Code','Description','Stock kg','Incoming kg','LAB kg'] if c in a.columns];tot=tot.merge(a[keep].drop_duplicates('Material Code'),on='Material Code',how='left')
   except Exception as ex:st.warning('Stock file diagnostic: '+str(ex))
  for c in ['Stock kg','Incoming kg','LAB kg']:
   if c not in tot.columns:tot[c]=0
   tot[c]=nnum(tot[c],tot.index)
  tot['Confirmed shortage kg']=(tot['Required kg']-tot['Stock kg']-tot['Incoming kg']).clip(lower=0);tot['Shortage if LAB passes kg']=(tot['Required kg']-tot['Stock kg']-tot['Incoming kg']-tot['LAB kg']).clip(lower=0)
  st.metric('Total traced material demand',f"{tot['Required kg'].sum():,.1f} kg");st.dataframe(tot,use_container_width=True,hide_index=True,height=500)
  with st.expander('Material trace rows'):st.dataframe(mat,use_container_width=True,hide_index=True,height=400)

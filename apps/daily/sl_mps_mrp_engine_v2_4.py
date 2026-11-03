from __future__ import annotations
import io, re, math, calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Tuple
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
from suite.backorder_views import local_date, mps_order_buckets
from suite.closure_rules import is_closed_text
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter, column_index_from_string

# page config is controlled by the parent PPC Control Center
MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
SIZE_ORDER=['A','B','C','D','E','F','G','H','OTHER']

# ---------- utilities ----------
def txt(x): return '' if pd.isna(x) else str(x).strip()
def num(x): return pd.to_numeric(x,errors='coerce')
def norm(x): return re.sub(r'\s+','',txt(x)).upper()
def uniq(vals):
    seen={}; out=[]
    for i,v in enumerate(vals):
        k=txt(v) or f'COL_{i+1}'; n=seen.get(k,0); seen[k]=n+1; out.append(k if n==0 else f'{k}__{n+1}')
    return out
def find_header(raw, terms, max_rows=30):
    tt=[norm(t) for t in terms]
    for r in range(min(max_rows,len(raw))):
        j='|'.join(norm(v) for v in raw.iloc[r].tolist())
        if all(t in j for t in tt): return r
    raise ValueError('Header not found: '+', '.join(terms))
def from_header(raw,r):
    d=raw.iloc[r+1:].copy(); d.columns=uniq(raw.iloc[r].tolist()); return d.dropna(how='all').reset_index(drop=True)
def choose(xls, exact, contains=''):
    if exact in xls.sheet_names:return exact
    for s in xls.sheet_names:
        if contains and contains.lower() in s.lower():return s
    return xls.sheet_names[0]
def getcol(df, exact=None, contains=None):
    if exact:
        for c in df.columns:
            if norm(c)==norm(exact):return c
    if contains:
        for c in df.columns:
            if norm(contains) in norm(c):return c
    return None
def col_letter(df, letter):
    i=column_index_from_string(letter)-1
    return df.columns[i] if i < len(df.columns) else None
def month_start(y,m): return pd.Timestamp(y,m,1)
def round_up(q,multiple):
    if pd.isna(q) or q<=0:return 0.0
    if pd.isna(multiple) or multiple<=0:return float(q)
    return math.ceil(float(q)/float(multiple))*float(multiple)
def size_bucket(d, spec=''):
    s=norm(spec)
    if 'HONING' in s or 'SEGMENT' in s:return ('H','HONING/SEGMENT')
    d=pd.to_numeric(d,errors='coerce')
    if pd.isna(d) or d<=0:return ('OTHER','Unclassified')
    inch=d/25.4
    if inch<=5:return ('A','1-5 in')
    if inch<=10:return ('B','6-10 in')
    if inch<=15:return ('C','11-15 in')
    if inch<=20:return ('D','16-20 in')
    if inch<=25:return ('E','21-25 in')
    if inch<=30:return ('F','26-30 in')
    return ('G','31 in and above')
def risk_label(load):
    if pd.isna(load): return 'DATA GAP'
    if load>100:return 'RED - OVERLOAD'
    if load>85:return 'YELLOW - HIGH'
    return 'GREEN - OK'

# ---------- source parsers ----------
@st.cache_data(show_spinner=False)
def parse_sales(b:bytes):
    xls=pd.ExcelFile(io.BytesIO(b),engine='openpyxl'); sh=choose(xls,'Data Item FC26','Data Item')
    raw=pd.read_excel(xls,sh,header=None); hr=find_header(raw,['IDItem','CustomerName']); df=from_header(raw,hr)
    item=getcol(df,'IDItem'); cust=getcol(df,'CustomerName'); cid=getcol(df,'IDCustomer'); desc=getcol(df,'Description'); spec=getcol(df,'Real Spec','RealSpec'); sales=getcol(df,'SaleName'); criteria=getcol(df,'Criteria')
    base=pd.DataFrame({'Item':df[item].map(txt),'Customer':df[cust].map(txt) if cust else '', 'Customer ID':df[cid].map(txt) if cid else '', 'Description':df[desc].map(txt) if desc else '', 'Real Spec':df[spec].map(txt) if spec else '', 'Sales':df[sales].map(txt) if sales else '', 'Sales Criteria':df[criteria].map(txt) if criteria else ''})
    for i in range(1,13):
        c=next((c for c in df.columns if re.search(fr'FOR(E)?CAST.*UNIT.*M{i}$',norm(c))),None)
        if c is None:
            # known format: columns 10-21 in original sheet = positions after annual total
            annual=next((j for j,c0 in enumerate(df.columns) if 'TOTALOFYR' in norm(c0)),None)
            c=df.columns[annual+i] if annual is not None and annual+i<len(df.columns) else None
        base[MONTHS[i-1]]=num(df[c]).fillna(0) if c else 0.0
    base=base[base.Item.ne('')].copy(); base['Annual Forecast Pcs']=base[MONTHS].sum(axis=1)
    long=base.melt(id_vars=['Item','Customer','Customer ID','Description','Real Spec','Sales','Sales Criteria'],value_vars=MONTHS,var_name='Month',value_name='Forecast Pcs')
    long['Month No']=long.Month.map({m:i+1 for i,m in enumerate(MONTHS)}); long['Forecast Pcs']=num(long['Forecast Pcs']).fillna(0)
    return base,long

@st.cache_data(show_spinner=False)
def parse_product_capacity(b:bytes):
    xls=pd.ExcelFile(io.BytesIO(b),engine='openpyxl')
    # product master/BOM from Cap เจีย
    raw=pd.read_excel(xls,choose(xls,'Cap เจีย','เจีย'),header=None); hr=find_header(raw,['ProductionCode','รหัสสินค้า']); g=from_header(raw,hr); C=list(g.columns)
    cp=lambda i:C[i] if i<len(C) else None
    rows=[]; bom=[]
    for _,r in g.iterrows():
        item=txt(r.get(cp(10),'')) or txt(r.get(cp(1),'')); q=pd.to_numeric(r.get(cp(9),np.nan),errors='coerce')
        if not item:continue
        wt=pd.to_numeric(r.get(cp(33),np.nan),errors='coerce')
        D=pd.to_numeric(r.get(cp(12),np.nan),errors='coerce'); T=pd.to_numeric(r.get(cp(13),np.nan),errors='coerce'); H=pd.to_numeric(r.get(cp(14),np.nan),errors='coerce')
        spec=txt(r.get(cp(7),'')); grp=txt(r.get(cp(57),'')); sb,sl=size_bucket(D,spec)
        rows.append({'Item':item,'Specification':spec,'D':D,'T':T,'H':H,'Bond':txt(r.get(cp(15),'')),'Group':grp,'Unit Weight g':wt,'Size Code':sb,'Size Range':sl})
        for ci,gi in [(17,18),(19,20),(21,22),(23,24),(25,26)]:
            mat=txt(r.get(cp(ci),'')); grams=pd.to_numeric(r.get(cp(gi),np.nan),errors='coerce')
            if mat and mat not in {'0','NAN'} and pd.notna(grams) and grams>0 and pd.notna(q) and q>0:
                bom.append({'Item':item,'Material':mat,'g per pc':float(grams)/float(q),'BOM Source':'Cap เจีย historical/order usage'})
    master=pd.DataFrame(rows)
    if not master.empty:
        master['_score']=master[['Group','Unit Weight g','D']].notna().sum(axis=1); master=master.sort_values(['Item','_score'],ascending=[True,False]).drop_duplicates('Item').drop(columns='_score')
    bom=pd.DataFrame(bom)
    if not bom.empty:bom=bom.groupby(['Item','Material'],as_index=False).agg({'g per pc':'median','BOM Source':'first'})
    # mixing
    mix_cap=np.nan; mix_count=0
    try:
        rm=pd.read_excel(xls,choose(xls,'CAP ผสม','ผสม'),header=None); hm=find_header(rm,['ตันต่อเดือน','CAP-เครื่อง']); m=from_header(rm,hm)
        ton=next((c for c in m.columns if 'ตันต่อเดือน' in c),None); stat=next((c for c in m.columns if norm(c)==norm('สถานะ')),None)
        mask=pd.Series(True,index=m.index)
        if stat: mask=~m[stat].map(txt).str.contains('ไม่ใช้')
        mix_cap=float(num(m.loc[mask,ton]).fillna(0).sum()) if ton else np.nan; mix_count=int(mask.sum())
    except Exception: pass
    # forming rates
    fr=[]; machines=set()
    try:
        rf=pd.read_excel(xls,choose(xls,'CAP ขึ้นรูป','ขึ้นรูป'),header=None); hf=find_header(rf,['Spec & Size','Cap./ Hr.']); f=from_header(rf,hf)
        spec_c=next((c for c in f.columns if 'SPEC&SIZE' in norm(c)),None); rate_c=next((c for c in f.columns if 'CAP./HR' in norm(c) or 'CAP/HR' in norm(c)),None); group_c=next((c for c in f.columns if norm(c)=='GROUP'),None); mach_c=next((c for c in f.columns if 'MACHINE' in norm(c)),None)
        for _,r in f.iterrows():
            rate=pd.to_numeric(r.get(rate_c,np.nan),errors='coerce') if rate_c else np.nan
            mach_tokens=[]
            if mach_c:
                for x in re.split(r'[/,+&]|\s{2,}',txt(r.get(mach_c,''))):
                    if x.strip() and x.strip() not in {'-','0'}:
                        machines.add(x.strip()); mach_tokens.append(x.strip())
            if pd.notna(rate) and rate>0:
                specv=txt(r.get(spec_c,'')) if spec_c else ''
                grp=txt(r.get(group_c,'')) if group_c else ''
                fr.append({'Group':grp,'Spec & Size':specv,'Cap/hr':float(rate),'Machine Tokens':len(set(mach_tokens)) or 1,'Machines':' / '.join(mach_tokens)})
    except Exception: pass
    form=pd.DataFrame(fr)
    lead_by_group={}
    try:
        lr=pd.read_excel(xls,choose(xls,'Lead Time','Lead'),header=None)
        groups=['S','T','P','R','PB','M']
        def _days(v):
            s=txt(v).upper()
            if not s or 'ไม่ผ่าน' in s:return 0.0
            vals=re.findall(r'\d+(?:\.\d+)?',s)
            return max(float(x) for x in vals) if vals else 0.0
        for gi,gp in enumerate(groups,1):
            total=0.0
            for rr in range(2,min(len(lr),12)):
                proc=txt(lr.iat[rr,0]).upper() if lr.shape[1]>0 else ''
                # Controlled routing: PB is Resin; S/T/P/R/M are Vitrified.
                # The source sheet contains a conflicting 5-7 day Resin value under M;
                # do not double-count that conflict in material-need timing.
                if gp=='PB' and ('VITRIFIED' in proc or 'VITRIFIED' in proc.replace(' ','')): continue
                if gp!='PB' and ('RESIN' in proc): continue
                if gi < lr.shape[1]: total += _days(lr.iat[rr,gi])
            lead_by_group[gp]=total
    except Exception:
        lead_by_group={}
    meta={'Mixing Capacity t/month':mix_cap,'Mixing Rows/Machines':mix_count,'Forming Machine Tokens':len(machines),'Forming Median Rate pcs/hr':float(form['Cap/hr'].median()) if not form.empty else np.nan,'Internal Lead Days by Group':lead_by_group}
    return master,bom,form,meta

@st.cache_data(show_spinner=False)
def parse_stock(b:bytes):
    """Controlled stock parser: ONLY Abrasive, ทรายบด-ล้างR, ทรายบด-ล้างSPB.
    User-confirmed balances: Abrasive=N; R=E; SPB=E. Values are grams.
    """
    xls=pd.ExcelFile(io.BytesIO(b),engine='openpyxl')
    required={'Abrasive':'N','ทรายบด-ล้างR':'E','ทรายบด-ล้างSPB':'E'}
    missing=[sh for sh in required if sh not in xls.sheet_names]
    if missing: raise ValueError('Required stock sheet(s) missing: '+', '.join(missing))
    rows=[]
    for sh,bal_letter in required.items():
        df=pd.read_excel(xls,sh,header=0)
        # Exact workbook structures confirmed by the user.
        if sh=='Abrasive':
            code='รหัสสินค้า'; desc='รายละเอียดสินค้า'; group='Group'; typ='AbrasiveMainType'
            order='ใบงานเปิดผลิต'; physical='วัตถุดิบคงคลัง'; waiting='รอวัถุดิบเข้า'; test='รอผลLAB'; balance='BalanceStock'; movement='Move/Slow/Dead'; note='หมายเหตุ'
        else:
            code='รหัสใหม่'; desc='ชนิด'; group=None; typ='Spec.ที่กำหนด'
            order='Orderonhand'; physical='คงเหลือ'; waiting=None; test=None; balance='BalanceStock'; movement=None; note='หมายเหตุ'
        if balance not in df.columns: raise ValueError(f'{sh}: BalanceStock not found in controlled column {bal_letter}.')
        for _excel_row,(_,r) in enumerate(df.iterrows(),start=2):
            mat=txt(r.get(code,'')); name=txt(r.get(desc,''))
            if not mat and not name: continue
            def n(c): return float(pd.to_numeric(r.get(c,0),errors='coerce')) if c and pd.notna(pd.to_numeric(r.get(c,0),errors='coerce')) else 0.0
            bal=n(balance); phy=n(physical); oo=n(order); wait=n(waiting); lab=n(test)
            status='SHORTAGE' if bal<0 else ('ZERO / URGENT' if bal==0 and oo>0 else ('WATCH' if bal>0 and oo>0 and bal<0.25*oo else 'OK'))
            rows.append({'Material':mat,'Material Name':name,'Description':name,'Material Group':txt(r.get(group,'')) if group else sh,'Type':txt(r.get(typ,'')) if typ else '',
                         'Order on Hand g':oo,'Physical Stock g':phy,'Waiting to Receive g':wait,'Under Test g':lab,
                         'Balance Stock g':bal,'On Hand g':bal,'On Hand t':bal/1e6,'Balance Stock t':bal/1e6,
                         'Movement':txt(r.get(movement,'')) if movement else '', 'Remark':txt(r.get(note,'')) if note else '',
                         'Stock Source Sheet':sh,'Stock Source Row':_excel_row,'Stock Source Column':bal_letter,'Stock Source Unit':'g','Stock Status':status})
    out=pd.DataFrame(rows)
    if out.empty: raise ValueError('The three controlled stock sheets were found but no material rows were parsed.')
    return out

@st.cache_data(show_spinner=False)
def parse_plan2026(b:bytes):
    # Plan 2026 does not have a sheet literally named 'Plan2026'.  Locate the
    # detailed WO sheet by its real headers instead of guessing from sheet name.
    xls=pd.ExcelFile(io.BytesIO(b),engine='openpyxl')
    candidates=[]
    for sh0 in xls.sheet_names:
        try:
            probe=pd.read_excel(xls,sh0,header=None,nrows=12)
            hr0=find_header(probe,['ProductionCode','QTY'],max_rows=12)
            rowtxt='|'.join(norm(v) for v in probe.iloc[hr0].tolist())
            score=0
            for key in ['CUSTOMERNAME','SPECIFICATION','รหัสสินค้า','กำหนดส่งใหม่','กำหนดเข้าคลัง']:
                if norm(key) in rowtxt: score+=1
            # Prefer the full planning sheet; revised downstream packing fields are ES/ET/EU (mapping supplied 10-Sep-2026).
            score += min(probe.shape[1],500)/1000.0
            candidates.append((score,sh0,hr0))
        except Exception:
            pass
    if not candidates:
        raise ValueError('Plan 2026 mapping: no worksheet contains both ProductionCode and QTY in the first 12 rows. Please use the full Plan 2026 workbook, not a summary/export sheet.')
    _,sh,hr=max(candidates,key=lambda x:x[0])
    raw=pd.read_excel(xls,sh,header=None); df=from_header(raw,hr)
    prod=getcol(df,'ProductionCode'); qty=getcol(df,'QTY'); item=getcol(df,'รหัสสินค้า'); cust=getcol(df,'Customername'); spec=getcol(df,'Specification')
    due=getcol(df,'กำหนดส่งใหม่')
    # position fallbacks for known full Plan2026
    pack_plan=col_letter(df,'ES'); pack_actual=col_letter(df,'ET'); pack_status=col_letter(df,'EU')
    final_status=col_letter(df,'FC')
    if not pack_plan: pack_plan=getcol(df,contains='Packing Plan')
    if not pack_actual: pack_actual=getcol(df,contains='Packing Actual')
    if not pack_status: pack_status=getcol(df,contains='Packing Status')
    rows=[]
    for _,r in df.iterrows():
        wo=txt(r.get(prod,'')); it=txt(r.get(item,''));
        if not wo and not it:continue
        oq=pd.to_numeric(r.get(qty,np.nan),errors='coerce')
        pp=pd.to_numeric(r.get(pack_plan,np.nan),errors='coerce') if pack_plan else np.nan
        pa=pd.to_numeric(r.get(pack_actual,np.nan),errors='coerce') if pack_actual else np.nan
        status=txt(r.get(pack_status,'')) if pack_status else ''
        fc_status=txt(r.get(final_status,'')) if final_status else ''
        closed=is_closed_text(status) or is_closed_text(fc_status)
        if closed: rem=0.0; basis='Packing status CLOSED'
        elif pd.notna(oq): rem=max(float(oq)-(float(pa) if pd.notna(pa) else 0.0),0); basis='Plan-2026 QTY - packing actual (shared open-balance basis)'
        else: rem=np.nan; basis='Missing quantity'
        rows.append({'WO':wo,'Item':it,'Customer':txt(r.get(cust,'')) if cust else '', 'Specification':txt(r.get(spec,'')) if spec else '', 'Due Date':local_date(r.get(due,np.nan)) if due else pd.NaT, 'Order Qty':oq,'Packing Actual Qty':pa,'Open Qty':rem,'Open Qty Basis':basis,'Packing Status':status,'Final WO Status (FC)':fc_status})
    out=pd.DataFrame(rows)
    if out.empty:
        raise ValueError(f'Plan 2026 mapping found sheet {sh!r}, but no production-order rows could be read.')
    out.attrs['source_sheet']=sh
    out.attrs['header_row']=hr+1
    return out

# ---------- model ----------
def build_model(sales_long,sales_base,master,bom,stock,plan,form,meta,year,start_month,mode,working_days,hours_day,policy,as_of=None):
    ref=month_start(year,start_month)
    asof=pd.Timestamp(as_of or datetime.now(ZoneInfo('Asia/Bangkok')).date()).normalize()
    sl=sales_long.merge(master,on='Item',how='left'); sl['Year']=year; sl['Period']=pd.to_datetime(dict(year=year,month=sl['Month No'],day=1)); sl=sl[sl['Month No']>=start_month].copy()
    sl['Forecast t']=sl['Forecast Pcs']*num(sl['Unit Weight g']).fillna(0)/1e6
    p=plan.copy()
    if p.empty:
        firm_future=pd.DataFrame(columns=['Item','Month No','Firm Future Pcs']); backitem=pd.DataFrame(columns=['Item','Backorder Pcs']); backdetail=pd.DataFrame()
    else:
        # Use the same disjoint, as-of buckets as the central backorder views.
        # This avoids counting an Oct-9 overdue WO twice (once as firm October
        # demand and again as recovery), and prevents 2027 demand leaking into
        # a 2026 horizon by matching month number alone.
        backdetail,fut=mps_order_buckets(p,asof,year,start_month)
        backitem=backdetail.groupby('Item',as_index=False)['Open Qty'].sum().rename(columns={'Open Qty':'Backorder Pcs'}) if not backdetail.empty else pd.DataFrame(columns=['Item','Backorder Pcs'])
        fut=fut.copy(); fut['Month No']=fut['Due Date'].dt.month
        firm_future=fut.groupby(['Item','Month No'],as_index=False)['Open Qty'].sum().rename(columns={'Open Qty':'Firm Future Pcs'}) if not fut.empty else pd.DataFrame(columns=['Item','Month No','Firm Future Pcs'])
    mps=sl.merge(firm_future,on=['Item','Month No'],how='left').merge(backitem,on='Item',how='left'); mps['Firm Future Pcs']=mps['Firm Future Pcs'].fillna(0); mps['Backorder Pcs']=mps['Backorder Pcs'].fillna(0)
    mps['Backorder Recovery Pcs']=np.where(mps['Month No'].eq(start_month),mps['Backorder Pcs'],0.0)
    if mode.startswith('Higher'):
        mps['Base MPS Pcs']=mps[['Forecast Pcs','Firm Future Pcs']].max(axis=1); mps['MPS Pcs']=mps['Base MPS Pcs']+mps['Backorder Recovery Pcs']; mps['Demand Basis']=np.where(mps['Backorder Recovery Pcs']>0,'Backorder recovery + higher of forecast/future firm orders','Higher of forecast or future firm orders')
    else:
        mps['Base MPS Pcs']=mps['Forecast Pcs']; mps['MPS Pcs']=mps['Forecast Pcs']+mps['Backorder Recovery Pcs']; mps['Demand Basis']='Forecast + explicit backorder recovery'
    mps['MPS t']=mps['MPS Pcs']*num(mps['Unit Weight g']).fillna(0)/1e6; mps['Master Risk']=np.where(mps['Unit Weight g'].isna(),'MISSING WEIGHT',np.where(mps['Group'].fillna('').eq(''),'MISSING CATEGORY','OK'))
    sumcols=['Forecast Pcs','Firm Future Pcs','Backorder Recovery Pcs','MPS Pcs','MPS t']
    group=mps.groupby(['Month No','Month','Group'],dropna=False,as_index=False)[sumcols].sum(); size=mps.groupby(['Month No','Month','Group','Size Code','Size Range'],dropna=False,as_index=False)[sumcols].sum(); customer=mps.groupby(['Month No','Month','Customer'],as_index=False)[['MPS Pcs','MPS t']].sum(); monthly=mps.groupby(['Month No','Month'],as_index=False)[sumcols].sum().sort_values('Month No')
    mixcap=float(meta.get('Mixing Capacity t/month',np.nan)); monthly['Mixing Capacity t']=mixcap; monthly['Mixing Load %']=monthly['MPS t']/mixcap*100 if pd.notna(mixcap) and mixcap>0 else np.nan; monthly['Mixing Gap t']=np.maximum(monthly['MPS t']-mixcap,0) if pd.notna(mixcap) else np.nan
    overall=float(form['Cap/hr'].median()) if not form.empty else np.nan; rates=form.groupby('Group',as_index=False)['Cap/hr'].median().rename(columns={'Cap/hr':'Rate pcs/hr'}) if not form.empty else pd.DataFrame(columns=['Group','Rate pcs/hr'])
    fg=group.merge(rates,on='Group',how='left'); fg['Rate pcs/hr']=fg['Rate pcs/hr'].fillna(overall); fg['Required Forming hr']=fg['MPS Pcs']/fg['Rate pcs/hr']; avail=float(meta.get('Forming Machine Tokens',0))*working_days*hours_day
    fh=fg.groupby(['Month No','Month'],as_index=False)['Required Forming hr'].sum(min_count=1); fh['Available Forming hr']=avail; fh['Forming Load %']=fh['Required Forming hr']/avail*100 if avail>0 else np.nan; fh['Forming Gap hr']=np.maximum(fh['Required Forming hr']-avail,0)
    monthly=monthly.merge(fh,on=['Month No','Month'],how='left'); monthly['Mixing Risk']=monthly['Mixing Load %'].map(risk_label); monthly['Forming Risk']=monthly['Forming Load %'].map(risk_label)
    # Aggregate MPS feasibility: normal capacity first. Demand is never silently deleted;
    # Possible Plan is the capacity-feasible portion and the shortfall remains visible.
    def _factor(r):
        fs=[]
        if pd.notna(r.get('Mixing Load %')) and float(r.get('Mixing Load %'))>0: fs.append(min(1.0,100.0/float(r.get('Mixing Load %'))))
        if pd.notna(r.get('Forming Load %')) and float(r.get('Forming Load %'))>0: fs.append(min(1.0,100.0/float(r.get('Forming Load %'))))
        return min(fs) if fs else np.nan
    monthly['Capacity Factor']=monthly.apply(_factor,axis=1)
    monthly['Possible Plan Pcs']=monthly['MPS Pcs']*monthly['Capacity Factor'].fillna(0)
    monthly['Possible Plan t']=monthly['MPS t']*monthly['Capacity Factor'].fillna(0)
    monthly['Capacity Shortfall Pcs']=np.maximum(monthly['MPS Pcs']-monthly['Possible Plan Pcs'],0)
    monthly['Capacity Shortfall t']=np.maximum(monthly['MPS t']-monthly['Possible Plan t'],0)
    def _constraint(r):
        vals={'MIXING':r.get('Mixing Load %'),'FORMING':r.get('Forming Load %')}
        vals={k:float(v) for k,v in vals.items() if pd.notna(v)}
        if not vals:return 'DATA GAP - CAPACITY'
        return max(vals,key=vals.get)
    monthly['Primary Constraint']=monthly.apply(_constraint,axis=1)
    monthly['Aggregate Feasibility']=np.where(monthly['Capacity Factor'].isna(),'DATA GAP',np.where(monthly['Capacity Factor']>=.999,'FEASIBLE - NORMAL CAPACITY','CONSTRAINED - RECOVERY REQUIRED'))
    monthly['MPS Risk']=np.where(monthly['Capacity Factor'].isna(),'RED - DATA GAP',np.where(monthly['Capacity Factor']<.85,'RED - CAPACITY SHORTFALL',np.where(monthly['Capacity Factor']<1,'YELLOW - CAPACITY TIGHT','GREEN - FEASIBLE')))
    monthly['Suggested Capacity Action']=monthly.apply(lambda r: ('Validate master data before commitment' if pd.isna(r['Capacity Factor']) else ('Normal schedule feasible' if r['Capacity Factor']>=.999 else ('Review OT / manpower / compatible machine reallocation; CAPEX study if overload repeats' if r['Capacity Factor']>=.85 else 'Capacity recovery required: OT/outsource/manpower/machine investment study before accepting full forecast'))),axis=1)
    mf=monthly.set_index('Month No')['Capacity Factor'].to_dict()
    mps['Capacity Factor']=mps['Month No'].map(mf)
    mps['Possible Plan Pcs']=mps['MPS Pcs']*mps['Capacity Factor'].fillna(0);mps['Possible Plan t']=mps['MPS t']*mps['Capacity Factor'].fillna(0)
    mps['Capacity Shortfall Pcs']=np.maximum(mps['MPS Pcs']-mps['Possible Plan Pcs'],0)
    fg['Shared Available Forming hr/month']=avail; fg['Category Share of Forming Capacity %']=fg['Required Forming hr']/avail*100 if avail>0 else np.nan
    sg=size.merge(rates,on='Group',how='left'); sg['Rate pcs/hr']=sg['Rate pcs/hr'].fillna(overall); sg['Required Forming hr']=sg['MPS Pcs']/sg['Rate pcs/hr']; sg['Shared Available Forming hr/month']=avail; sg['Size Share of Forming Capacity %']=sg['Required Forming hr']/avail*100 if avail>0 else np.nan
    group['Shared Mixing Capacity t/month']=mixcap; group['Category Share of Mixing Capacity %']=group['MPS t']/mixcap*100 if pd.notna(mixcap) and mixcap>0 else np.nan; size['Shared Mixing Capacity t/month']=mixcap; size['Size Share of Mixing Capacity %']=size['MPS t']/mixcap*100 if pd.notna(mixcap) and mixcap>0 else np.nan
    for _df in (group,sg):
        _df['Capacity Factor']=_df['Month No'].map(mf)
        _df['Possible Plan Pcs']=_df['MPS Pcs']*_df['Capacity Factor'].fillna(0);_df['Possible Plan t']=_df['MPS t']*_df['Capacity Factor'].fillna(0)
        _df['Capacity Shortfall Pcs']=np.maximum(_df['MPS Pcs']-_df['Possible Plan Pcs'],0)
        _df['Feasibility']=np.where(_df['Capacity Factor'].isna(),'DATA GAP',np.where(_df['Capacity Factor']>=.999,'FEASIBLE','CONSTRAINED'))
    # Keep the externally returned size table enriched as well.
    size=sg.copy()
    leadmap=meta.get('Internal Lead Days by Group',{}) or {}; mrp=mps[['Item','Group','Month No','Month','Period','MPS Pcs']].merge(bom,on='Item',how='left'); mrp['Internal Lead days']=mrp['Group'].map(lambda g:float(leadmap.get(str(g).strip().upper(),0) or 0)); mrp['Material Need Date']=pd.to_datetime(mrp['Period'])-pd.to_timedelta(mrp['Internal Lead days'],unit='D'); mrp['Gross Requirement g']=mrp['MPS Pcs']*mrp['g per pc']; mrp['Gross Requirement t']=mrp['Gross Requirement g']/1e6; mrp=mrp.dropna(subset=['Material'])
    gross=mrp.groupby(['Material','Month No','Month','Period'],as_index=False).agg({'Gross Requirement t':'sum','Material Need Date':'min'})
    mats=sorted(set(gross.Material.tolist())|set(stock.Material.tolist())); pol=policy.set_index('Material').to_dict('index') if not policy.empty else {}; onhand=stock.set_index('Material')['On Hand t'].to_dict() if not stock.empty else {}; purchases=[]; projection=[]
    for mat in mats:
        prev=float(onhand.get(mat,0) if pd.notna(onhand.get(mat,0)) else 0); pp=pol.get(mat,{}); lead=float(pp.get('Lead Time days',0) or 0); safety=float(pp.get('Safety Stock t',0) or 0); moq=float(pp.get('MOQ t',0) or 0); mult=float(pp.get('Order Multiple t',0) or 0); supplier=txt(pp.get('Supplier','')); price=pd.to_numeric(pp.get('Price per kg',np.nan),errors='coerce')
        for mn in range(start_month,13):
            per=month_start(year,mn); reqrow=gross[(gross.Material==mat)&(gross['Month No']==mn)]; req=float(reqrow['Gross Requirement t'].sum()) if not reqrow.empty else 0; mat_need=reqrow['Material Need Date'].min() if not reqrow.empty else per; mat_need=per if pd.isna(mat_need) else mat_need; available=prev-req; shortage=max(safety-available,0); rec=round_up(max(shortage,moq if shortage>0 else 0),mult); end=available+rec; receipt=pd.Timestamp(mat_need); order_date=(receipt-pd.Timedelta(days=lead)).date(); cost=rec*1000*price if pd.notna(price) else np.nan; risk='RED - ORDER REQUIRED' if rec>0 and lead>0 else ('RED - SHORTAGE / LEAD TIME MISSING' if rec>0 else ('YELLOW - BELOW SAFETY' if end<safety else 'GREEN - OK'))
            projection.append({'Material':mat,'Month No':mn,'Month':MONTHS[mn-1],'Beginning Stock t':prev,'Gross Requirement t':req,'Safety Stock t':safety,'Planned Receipt t':rec,'Projected Ending t':end,'Material Need Date':receipt.date(),'Risk':risk})
            if rec>0:purchases.append({'Material':mat,'Supplier':supplier,'Need Month':MONTHS[mn-1],'Material Need Date':receipt.date(),'Required Receipt Date':receipt.date(),'Lead Time days':lead,'Recommended PO Date':order_date,'Gross Requirement t':req,'Beginning Stock t':prev,'Safety Stock t':safety,'Recommended Order Qty t':rec,'MOQ t':moq,'Order Multiple t':mult,'Estimated Cost':cost,'Action':'ORDER / CONFIRM SUPPLIER','Data Warning':'CONFIRM LEAD TIME' if lead<=0 else ''})
            prev=end
    projection=pd.DataFrame(projection); purchase=pd.DataFrame(purchases); openrisk=p.copy() if not p.empty else pd.DataFrame()
    if not openrisk.empty:
        openrisk['Days to Due']=(openrisk['Due Date']-ref).dt.days; openrisk['Risk']=np.select([openrisk['Due Date'].isna(),openrisk['Due Date']<ref,openrisk['Days to Due']<=14],['YELLOW - DATE MISSING','RED - OVERDUE','YELLOW - DUE <=14D'],default='GREEN - OPEN')
    backsummary=pd.DataFrame()
    if not backdetail.empty:
        backdetail=backdetail.merge(master[['Item','Group','Size Code','Size Range']].drop_duplicates('Item'),on='Item',how='left'); backsummary=backdetail.groupby(['Group','Size Code','Size Range'],dropna=False,as_index=False).agg({'Open Qty':'sum','WO':'nunique'}).rename(columns={'Open Qty':'Backorder Pcs','WO':'Backorder WOs'})
    risks=[]
    def add(level,cat,period,issue,impact,action):risks.append({'Risk':level,'Category':cat,'Period':period,'Issue':issue,'Impact':impact,'Required Action':action})
    missing_weight=mps.loc[(mps['MPS Pcs']>0)&mps['Unit Weight g'].isna(),'Item'].nunique(); missing_bom=mps.loc[(mps['MPS Pcs']>0)&~mps['Item'].isin(set(bom.Item if not bom.empty else [])),'Item'].nunique()
    if missing_weight:add('HIGH','Master Data','All future months',f'{missing_weight} forecast items have no unit weight.','Tonnage/capacity can be understated.','Complete product weight master.')
    if missing_bom:add('HIGH','MRP Master Data','All future months',f'{missing_bom} forecast items have no abrasive BOM.','Purchase plan is incomplete.','Complete item-material BOM.')
    for _,r in monthly.iterrows():
        if pd.notna(r['Mixing Load %']) and r['Mixing Load %']>100:add('HIGH','Mixing Capacity',r.Month,f"Load {r['Mixing Load %']:.0f}%",'Demand exceeds normal mixing capacity.',f"Recover {r['Mixing Gap t']:.2f} t.")
        if pd.notna(r['Forming Load %']) and r['Forming Load %']>100:add('HIGH','Forming Capacity',r.Month,f"Load {r['Forming Load %']:.0f}%",'Required forming hours exceed shared capacity.',f"Recover {r['Forming Gap hr']:.0f} hr; validate machine compatibility.")
    if not backdetail.empty:add('HIGH','Backorder','Planning start',f"{backdetail['WO'].nunique()} overdue WOs / {backdetail['Open Qty'].sum():,.0f} pcs",'Consumes current/future capacity.','Recover explicitly; do not hide in forecast.')
    if not purchase.empty:
        for _,r in purchase.iterrows():add('HIGH' if r['Lead Time days']>0 else 'CRITICAL','Material',r['Need Month'],f"{r.Material}: order {r['Recommended Order Qty t']:.3f} t",f"Material needed {r['Material Need Date']}",f"Release/confirm PO by {r['Recommended PO Date']}.")
    risk=pd.DataFrame(risks); investment=[]
    for proc,col,gap in [('Mixing','Mixing Load %','Mixing Gap t'),('Forming','Forming Load %','Forming Gap hr')]:
        over=monthly[monthly[col]>100]; peak=float(monthly[col].max()) if monthly[col].notna().any() else np.nan; investment.append({'Process':proc,'Months >100%':len(over),'Peak Load %':peak,'Total Gap':float(over[gap].sum()) if not over.empty else 0,'Signal':'CAPACITY ACTION / CAPEX STUDY' if len(over)>=2 else ('SHORT-TERM RECOVERY REVIEW' if len(over)==1 else 'NO CAPEX SIGNAL'),'Decision Note':'Validate downtime, manpower, machine compatibility, OT and outsourcing before investment.'})
    investment=pd.DataFrame(investment)
    return {'mps':mps,'mps_monthly':monthly,'group':group,'size':size,'customer':customer,'firm':p,'openrisk':openrisk,'backorder_detail':backdetail,'backorder_summary':backsummary,'mrp_detail':mrp,'mrp':gross,'projection':projection,'purchase':purchase,'capacity':monthly,'forming_detail':fg,'capacity_category':fg,'capacity_size':sg,'risk':risk,'investment':investment}

# ---------- Excel export ----------
def export_excel(model,sales_base,master,bom,stock,policy,meta):
    # Keep one physical worksheet alive from the moment ExcelWriter is created.
    # This prevents openpyxl from masking the real export problem with
    # 'At least one sheet must be visible' if any later report expression fails.
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as w:
        start_ws = w.book.create_sheet('_EXPORT_STATUS')
        start_ws['A1'] = 'PPC Long-Term MPS/MRP Control Center'
        start_ws['A2'] = 'Export initialized successfully'
        start_ws.sheet_state = 'visible'
        pd.DataFrame({'Report':['PPC Long-Term MPS/MRP Control Center'],'Version':['V2.6 AGGREGATE MPS + FEASIBLE PLAN ENGINE'],'Purpose':['Answer Sales Forecast with MPS, MRP, purchase timing, capacity, risk and resource actions']}).to_excel(w, sheet_name='README', index=False)

        cap=model['capacity']; pur=model['purchase']; risk=model['risk']; mps=model['mps']
        summary=pd.DataFrame({'Metric':['Future MPS pcs','Future MPS t (covered)','Possible Plan pcs','Possible Plan t','Materials to order','Recommended purchase t','High/Critical risks','Peak Mixing %','Peak Forming %'], 'Value':[mps['MPS Pcs'].sum(),mps['MPS t'].sum(),mps.get('Possible Plan Pcs',pd.Series(dtype=float)).sum(),mps.get('Possible Plan t',pd.Series(dtype=float)).sum(),pur.Material.nunique() if not pur.empty else 0,pur['Recommended Order Qty t'].sum() if not pur.empty else 0,int(risk.Risk.isin(['HIGH','CRITICAL']).sum()) if not risk.empty else 0,cap['Mixing Load %'].max(),cap['Forming Load %'].max()]})
        summary.to_excel(w, sheet_name='Executive Summary', index=False)
        sheets=[('mps','MPS Item Month'),('mps_monthly','MPS Monthly Summary'),('group','MPS Category'),('size','MPS Category Size'),('capacity_category','Capacity by Category'),('capacity_size','Capacity by Size'),('customer','MPS Customer'),('firm','Open Orders Plan2026'),('openrisk','Open Order Risk'),('backorder_detail','Backorder Detail'),('backorder_summary','Backorder Category Size'),('mrp_detail','MRP Detail'),('mrp','MRP Material Month'),('projection','Stock Projection'),('purchase','PURCHASE ACTION'),('capacity','Capacity Outlook'),('forming_detail','Forming Load Detail'),('risk','Risk Register'),('investment','Investment Signals')]
        for k,s in sheets:model[k].to_excel(w, sheet_name=s, index=False)
        sales_base.to_excel(w, sheet_name='Sales Forecast Source', index=False); master.to_excel(w, sheet_name='Product Master', index=False); bom.to_excel(w, sheet_name='BOM Used', index=False); stock.to_excel(w, sheet_name='Stock Used', index=False); policy.to_excel(w, sheet_name='Material Policy', index=False); pd.DataFrame(list(meta.items()),columns=['Parameter','Value']).to_excel(w, sheet_name='Model Parameters', index=False)
        for ws in w.book.worksheets:
            ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
            for cell in ws[1]: cell.font=Font(bold=True); cell.fill=PatternFill('solid',fgColor='D9EAF7'); cell.alignment=Alignment(wrap_text=True)
            for col in range(1,ws.max_column+1):
                vals=[ws.cell(r,col).value for r in range(1,min(ws.max_row,150)+1)]; width=min(max([len(str(v)) if v is not None else 0 for v in vals]+[10])+2,42); ws.column_dimensions[get_column_letter(col)].width=width
        # Remove temporary safety sheet only after every real report sheet exists.
        if '_EXPORT_STATUS' in w.book.sheetnames and len(w.book.sheetnames) > 1:
            del w.book['_EXPORT_STATUS']
        w.book.active=0
    return out.getvalue()

# ---------- UI ----------

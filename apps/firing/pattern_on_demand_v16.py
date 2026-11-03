from __future__ import annotations
import copy, math, hashlib
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager, rcParams
from matplotlib.patches import Rectangle, Circle, Polygon
import firing_engine_desktop_v2 as fire

# Mixed Thai/Myanmar/English font fallback. We do not bundle/share fonts.
# Windows normally supplies Leelawadee UI / Tahoma / Myanmar Text; Noto is used when installed.
_available={f.name for f in font_manager.fontManager.ttflist}
_font_fallback=[x for x in ("Noto Sans","Noto Sans Thai","Noto Sans Myanmar","Leelawadee UI","Tahoma","Myanmar Text","Nirmala UI","Segoe UI") if x in _available]
if _font_fallback:
    rcParams["font.family"]="sans-serif"
    rcParams["font.sans-serif"]=_font_fallback+list(rcParams.get("font.sans-serif",[]))
rcParams["axes.unicode_minus"]=False

_WO_COLORS=("#4E79A7","#F28E2B","#59A14F","#E15759","#B07AA1","#76B7B2","#EDC948","#FF9DA7","#9C755F","#BAB0AC","#8CD17D","#B6992D")
def _wo_color(wo):
    return _WO_COLORS[int(hashlib.md5(str(wo).encode("utf-8")).hexdigest()[:8],16)%len(_WO_COLORS)]



def _n(v,d=0.0):
    try:
        x=float(v); return d if math.isnan(x) else x
    except Exception:return d


def exact_pattern_for_load(fr, load_id):
    """Build the detailed physical furniture pattern for EXACTLY the released load.

    Important V1.9.4 correction:
    the operator pattern must not re-run the 30-day planner and allow it to choose a
    different WO mix.  It locks the released kiln/program/date and packs the exact
    released WO quantities directly with the detailed furniture/height/weight engine.
    This keeps the normal planner fast while making the operator sheet deterministic.
    """
    loads=fr.get('loads',pd.DataFrame()); details=fr.get('details',pd.DataFrame())
    prepared=fr.get('prepared',pd.DataFrame()); ked=fr.get('kiln_editor',pd.DataFrame())
    if loads.empty or details.empty or prepared.empty or ked.empty:
        raise ValueError('Required firing result data are missing.')
    lm=loads[loads['Load ID'].astype(str)==str(load_id)]
    if lm.empty: raise ValueError('Load not found.')
    lr=lm.iloc[0]
    dd=details[details['Load ID'].astype(str)==str(load_id)].copy()
    if dd.empty: raise ValueError('No WO detail found for this load.')
    kiln_name=str(lr['Kiln']); program=str(lr['Program'])
    load_date=pd.to_datetime(lr['Load Date'],errors='coerce')
    if pd.isna(load_date): raise ValueError('Load date missing.')
    load_date=load_date.date()

    settings=copy.copy(fr['settings'])
    settings.planning_start=load_date
    # Detailed packer helpers use CURRENT_SETTINGS when flattening floor evidence.
    fire.CURRENT_SETTINGS=settings

    one=ked.copy(); one['Enabled']=False
    mask=one['Kiln'].astype(str).str.upper().eq(kiln_name.upper())
    if not mask.any(): raise ValueError(f'Kiln {kiln_name} not found in kiln master.')
    one.loc[mask,'Enabled']=True; one.loc[mask,'Status']='AVAILABLE'; one.loc[mask,'Available From']=load_date
    km=fire.prepare_kilns(one,settings)
    km=km[km['Kiln'].astype(str).str.upper().eq(kiln_name.upper())]
    if km.empty: raise ValueError(f'Kiln {kiln_name} could not be prepared for detailed packing.')
    kiln=km.iloc[0]
    rule=fire.program_rule(program,kiln_name)
    maxkg=min(float(kiln.get('Physical kg',0) or 0),float(rule.get('maxkg',0) or 0))
    if program=='P3' and kiln_name.upper()=='T14': maxkg=min(float(kiln.get('Physical kg',0) or 0),4000.0)
    if maxkg<=0: raise ValueError(f'No valid weight limit for {kiln_name} / {program}.')

    # Lock the exact released WO quantities, but sequence PHYSICAL PACKING so circular
    # host-hole parts are placed first. This enables valid same-program P2 nesting
    # without changing kiln/date/program/WO quantities or due-date priority.
    rel=(dd.assign(_WO=dd['Work Order'].astype(str).str.strip(),
                   _Q=pd.to_numeric(dd['Planned Firing Qty'],errors='coerce').fillna(0))
           .groupby('_WO',sort=False,as_index=False)['_Q'].sum())
    prep=prepared.copy(); prep['_WO']=prep['Work Order'].astype(str).str.strip()
    host_score={}
    for _,_r in rel.iterrows():
        _wo=str(_r['_WO']); _cand=prep[prep['_WO'].eq(_wo)]
        host_score[_wo]=fire.nesting_host_score(_cand.iloc[0]) if not _cand.empty else 0.0
    rel['_Original Order']=range(len(rel)); rel['_Host Score']=rel['_WO'].map(host_score).fillna(0.0)
    pack_rel=rel.sort_values(['_Host Score','_Original Order'],ascending=[False,True],kind='stable')
    floors=[]; total_weight=0.0; packed_rows=[]; missing=[]; short=[]

    for _,rr in pack_rel.iterrows():
        wo=str(rr['_WO']); required=int(round(float(rr['_Q'])))
        if required<=0: continue
        cand=prep[prep['_WO'].eq(wo)]
        if cand.empty:
            missing.append(wo); continue
        order=cand.iloc[0].copy()
        order['Program']=program
        kgpc=float(order.get('Weight kg/pc',0) or 0)
        if kgpc<=0:
            # Gross kg/pc can exist under an alternate prepared field in older results.
            kgpc=float(order.get('Gross Weight kg/pc',0) or 0)
        if kgpc<=0:
            raise ValueError(f'DO NOT RELEASE - gross weight per piece missing for {wo}.')
        weight_cap=max(int(math.floor(max(maxkg-total_weight,0)/kgpc)),0)
        if weight_cap<=0:
            short.append(f'{wo}: released {required}, patterned 0 (weight limit reached)')
            continue
        packed,alloc=fire.pack_order(floors,order,required,weight_cap,required,kiln,settings)
        total_weight += packed*kgpc
        packed_rows.append({'Work Order':wo,'Released Qty':required,'Patterned Qty':packed})
        if packed < required:
            short.append(f'{wo}: released {required}, patterned {packed}')

    if missing:
        raise ValueError('DO NOT RELEASE - released WO not found in prepared physical data: '+', '.join(missing[:10]))
    if not floors:
        raise ValueError('DO NOT RELEASE - detailed furniture packer could not place any released part in the selected kiln.')

    floor_rows=fire.flatten_floor_plan(str(load_id),floors)
    floor2=pd.DataFrame(floor_rows)
    if floor2.empty:
        raise ValueError('DO NOT RELEASE - detailed furniture packer returned an empty physical floor pattern.')
    # Bring operator-facing identity/shape evidence onto each physical piece row.
    # The physical engine still controls dimensions; these fields are for readable
    # labels and symbolic taper indication only.
    meta_cols=[c for c in ['Work Order','Category','Shape','Specification','Product Type','Loading Family','Loading Orientation','Stack Allowed','D Raw','T Raw','H Raw','D','T','H'] if c in prepared.columns]
    if meta_cols:
        _meta=prepared[meta_cols].drop_duplicates('Work Order').copy()
        floor2=floor2.merge(_meta,on='Work Order',how='left',suffixes=('','_Master'))

    # Re-check exact physical quantity by WO from the flattened evidence.
    phy=floor2.groupby(floor2['Work Order'].astype(str))['Qty'].sum()
    bad=[]
    for _,rr in rel.iterrows():
        wo=str(rr['_WO']); rq=float(rr['_Q']); pq=float(phy.get(wo,0))
        if abs(pq-rq)>0.01: bad.append(f'{wo}: released {rq:g}, patterned {pq:g}')
    if bad:
        raise ValueError('DO NOT RELEASE - exact released load exceeds detailed physical/furniture pattern capacity: '+'; '.join(bad[:10]))

    # Return compatibility objects used only for diagnostics/operator preview.
    l2=pd.DataFrame([{'Load ID':str(load_id),'Load Date':load_date,'Kiln':kiln_name,'Program':program,
                      'Qty pcs':float(rel['_Q'].sum()),'Weight kg':total_weight,'Weight Limit kg':maxkg,
                      'Furniture Feasibility':'PASS - EXACT RELEASE-LOCKED PATTERN'}])
    d2=rel[['_WO','_Q']].rename(columns={'_WO':'Work Order','_Q':'Planned Firing Qty'}).copy()
    exc2=pd.DataFrame(columns=['Work Order','Issue'])
    return floor2,l2,d2,exc2

def validate_pattern(df, clearance=0.0):
    """Validate base collisions and real x/y nested-piece fit/collision inside host holes."""
    issues=[]
    if df is None or df.empty:return False,['Pattern is empty']
    for fno,g in df.groupby('Floor'):
        pm=g.get('Placement Mode',pd.Series('',index=g.index)).astype(str)
        base=g[~pm.str.contains('NESTED IN',case=False,na=False)].copy()
        if 'Stack ID' in base.columns: base=base.sort_values(['Stack ID','Stack Segment']).groupby('Stack ID',as_index=False).first()
        rows=list(base.to_dict('records'))
        for i,a in enumerate(rows):
            ax,ay,aw,ah=_n(a.get('x mm')),_n(a.get('y mm')),_n(a.get('Footprint W mm')),_n(a.get('Footprint H mm'))
            for b in rows[i+1:]:
                bx,by,bw,bh=_n(b.get('x mm')),_n(b.get('y mm')),_n(b.get('Footprint W mm')),_n(b.get('Footprint H mm'))
                ga=str(a.get('Base Geometry','')).upper(); gb=str(b.get('Base Geometry','')).upper()
                if ga=='CIRCULAR' and gb=='CIRCULAR':
                    d=math.hypot((ax+aw/2)-(bx+bw/2),(ay+ah/2)-(by+bh/2)); need=(min(aw,ah)+min(bw,bh))/2+clearance
                    hit=d < need-1e-6
                else:
                    hit=(ax < bx+bw+clearance-1e-6 and ax+aw+clearance > bx+1e-6 and ay < by+bh+clearance-1e-6 and ay+ah+clearance > by+1e-6)
                if hit: issues.append(f'Floor {fno}: base collision {a.get("Work Order","")} / {b.get("Work Order","")}')
        nested=g[pm.str.contains('NESTED IN',case=False,na=False)].copy()
        # each nested footprint must sit fully inside its host circle
        for _,n in nested.iterrows():
            hd=_n(n.get('Host Hole Diameter mm')); nw=_n(n.get('Footprint W mm')); nh=_n(n.get('Footprint H mm'))
            host=base[base.get('Stack ID',pd.Series('',index=base.index)).astype(str).eq(str(n.get('Stack ID','')))] if not base.empty else pd.DataFrame()
            if hd<=0 or host.empty:
                issues.append(f'Floor {fno}: nested {n.get("Work Order","")} has no valid host-hole evidence'); continue
            h=host.iloc[0]; cx=_n(h.get('x mm'))+_n(h.get('Footprint W mm'))/2; cy=_n(h.get('y mm'))+_n(h.get('Footprint H mm'))/2
            x0=_n(n.get('x mm')); y0=_n(n.get('y mm')); geom=str(n.get('Base Geometry','')).upper(); rad=hd/2
            if geom=='CIRCULAR':
                ok=math.hypot((x0+nw/2)-cx,(y0+nh/2)-cy)+max(nw,nh)/2+clearance <= rad+1e-6
            else:
                corners=((x0,y0),(x0+nw,y0),(x0,y0+nh),(x0+nw,y0+nh))
                ok=all(math.hypot(xx-cx,yy-cy)+clearance <= rad+1e-6 for xx,yy in corners)
            if not ok: issues.append(f'Floor {fno}: nested {n.get("Work Order","")} footprint does not fit host hole {hd:.1f} mm')
        # nested pieces must not overlap each other in plan view
        nr=list(nested.to_dict('records'))
        for i,a in enumerate(nr):
            ax,ay,aw,ah=_n(a.get('x mm')),_n(a.get('y mm')),_n(a.get('Footprint W mm')),_n(a.get('Footprint H mm'))
            for b in nr[i+1:]:
                if str(a.get('Stack ID',''))!=str(b.get('Stack ID','')): continue
                bx,by,bw,bh=_n(b.get('x mm')),_n(b.get('y mm')),_n(b.get('Footprint W mm')),_n(b.get('Footprint H mm'))
                hit=(ax < bx+bw+clearance-1e-6 and ax+aw+clearance > bx+1e-6 and ay < by+bh+clearance-1e-6 and ay+ah+clearance > by+1e-6)
                if hit: issues.append(f'Floor {fno}: nested collision {a.get("Work Order","")} / {b.get("Work Order","")}')
    return len(issues)==0,issues


def kiln_info_for_load(fr, load_id):
    """Return actual kiln dimensions for a released load without touching allocation logic."""
    loads=fr.get('loads',pd.DataFrame()); ked=fr.get('kiln_editor',pd.DataFrame())
    if loads is None or loads.empty or ked is None or ked.empty:
        return None
    lm=loads[loads['Load ID'].astype(str).eq(str(load_id))]
    if lm.empty:return None
    kiln=str(lm.iloc[0].get('Kiln','')).strip()
    km=ked[ked['Kiln'].astype(str).str.upper().eq(kiln.upper())]
    if km.empty:return None
    r=km.iloc[0]
    return {'Kiln':kiln,'L mm':_n(r.get('L mm')),'W mm':_n(r.get('W mm')),'H mm':_n(r.get('H mm'))}


def _floor_base(df):
    base=df[~df.get('Placement Mode',pd.Series('',index=df.index)).astype(str).str.contains('NESTED IN',case=False,na=False)].copy()
    if 'Stack ID' in base.columns:
        base=base.sort_values(['Stack ID','Stack Segment']).groupby('Stack ID',as_index=False).first()
    return base


def _short_wo(v, n=12):
    t=str(v)
    return t if len(t)<=n else t[:n-1]+'…'


def _draw_floor_furniture(ax, top, kiln_info=None):
    """Draw kiln boundary, refractory plates, plate gaps and shared I-block supports."""
    if top.empty:return
    first=top.iloc[0]
    edge=25.0
    pl=_n(first.get('Plate L mm')); pw=_n(first.get('Plate W mm'))
    cols=int(_n(first.get('Plate Cols'))); rows=int(_n(first.get('Plate Rows')))
    plate=str(first.get('Plate','')).strip()
    # Infer the plate gap from actual placement grid. The detailed engine currently uses 10 mm default.
    pgap=10.0
    if kiln_info and _n(kiln_info.get('L mm'))>0 and _n(kiln_info.get('W mm'))>0:
        L=_n(kiln_info['L mm']); W=_n(kiln_info['W mm'])
    elif pl>0 and pw>0 and cols>0 and rows>0:
        L=max(2*edge+cols*pl+max(cols-1,0)*pgap,1)
        W=max(2*edge+rows*pw+max(rows-1,0)*pgap,1)
    else:
        b=_floor_base(top)
        L=max(pd.to_numeric(b.get('x mm',pd.Series([0])),errors='coerce').fillna(0).add(pd.to_numeric(b.get('Footprint W mm',pd.Series([0])),errors='coerce').fillna(0)).max()+edge,1)
        W=max(pd.to_numeric(b.get('y mm',pd.Series([0])),errors='coerce').fillna(0).add(pd.to_numeric(b.get('Footprint H mm',pd.Series([0])),errors='coerce').fillna(0)).max()+edge,1)
    ax.add_patch(Rectangle((0,0),L,W,fill=False,linewidth=2.2))
    ax.text(L/2,W+0.018*max(L,W),f'KILN USABLE AREA / พื้นที่ใช้งานเตา  {L:.0f} × {W:.0f} mm',ha='center',va='bottom',fontsize=8,fontweight='bold')
    if plate and plate!='METAL FRAME' and pl>0 and pw>0 and cols>0 and rows>0:
        for rr in range(rows):
            for cc in range(cols):
                x0=edge+cc*(pl+pgap); y0=edge+rr*(pw+pgap)
                ax.add_patch(Rectangle((x0,y0),pl,pw,fill=False,linestyle='--',linewidth=.9))
                ax.text(x0+pl/2,y0+pw-8,f'PLATE / แผ่น {rr*cols+cc+1}',ha='center',va='top',fontsize=6.2)
        for cc in range(cols+1):
            sx=edge+cc*(pl+pgap)
            for rr in range(rows+1):
                sy=edge+rr*(pw+pgap)
                ax.plot(sx,sy,marker='s',markersize=4.5,linestyle='None')
        ax.text(0,-0.055*W,f'Furniture / อุปกรณ์เตา: Plate/แผ่น {plate} × {int(_n(first.get("Plates / Floor")))}  |  I-block/ตัวรอง {first.get("I-block","")}  |  Supports/จุดรอง {int(_n(first.get("Support Nodes / Floor")))}',fontsize=9,va='top')
    elif plate=='METAL FRAME':
        ax.text(0,-0.055*W,'Furniture / อุปกรณ์เตา: METAL FRAME / โครงโลหะ',fontsize=9,va='top')
    else:
        ax.text(0,-0.055*W,'FURNITURE NOT RESOLVED / ยังไม่ยืนยันอุปกรณ์เตา — DO NOT RELEASE / ห้ามปล่อยงาน',fontsize=7,fontweight='bold',va='top')
    return L,W


def _is_tapered_row(r):
    t=' '.join(str(r.get(c,'')) for c in ['Shape','Specification','Product Type']).upper()
    if any(k in t for k in ['TAPER','TAPERED','CONICAL','CONE']):return True
    # Preserve taper when source dimension contains two unequal values, e.g. 355/350.
    for c in ['D Raw','T Raw','H Raw']:
        vals=[float(x) for x in __import__('re').findall(r'\d+(?:\.\d+)?',str(r.get(c,'')))]
        if len(vals)>=2 and max(vals)-min(vals)>1e-6:return True
    return False


def _part_ids(top):
    ids={}; n=1
    for wo in top.get('Work Order',pd.Series(dtype=str)).astype(str):
        if wo not in ids:
            ids[wo]=f'P{n:02d}'; n+=1
    return ids


def draw_three_views(allx, selected_floor, load_id, kiln_info=None, zoom=1.0,
                     zoom_view='ALL',zoom_x_pct=50,zoom_y_pct=50,area_zoom=1.0):
    """Readable engineering TOP + FRONT view. SIDE view intentionally removed for operator clarity."""
    x=allx.copy(); x['Floor']=pd.to_numeric(x['Floor'],errors='coerce')
    top=x[x['Floor']==selected_floor].copy(); ids=_part_ids(top)
    zoom=max(float(zoom or 1.0),1.0)
    fig,axs=plt.subplots(1,2,figsize=(18*zoom,9.2*zoom))
    # identical visible rectangle for TOP / FRONT
    for _ax in axs:
        _ax.set_box_aspect(1.0)
    ax=axs[0]; ax.set_title(f'TOP VIEW / มุมมองด้านบน — Floor / ชั้น {selected_floor}',fontsize=13,fontweight='bold')
    dims=_draw_floor_furniture(ax,top,kiln_info)
    base=_floor_base(top)
    for _,r in base.iterrows():
        xx,yy,w,h=_n(r.get('x mm')),_n(r.get('y mm')),_n(r.get('Footprint W mm')),_n(r.get('Footprint H mm'))
        geom=str(r.get('Base Geometry','')).upper(); wo=str(r.get('Work Order','')); pid=ids.get(wo,'P?')
        taper=_is_tapered_row(r)
        if geom=='CIRCULAR':
            ax.add_patch(Circle((xx+w/2,yy+h/2),max(min(w,h)/2,1),facecolor=_wo_color(wo),edgecolor='black',alpha=.58,linewidth=2.0))
            hd=_n(r.get('Hole Diameter mm'))
            if 0<hd<min(w,h):
                ax.add_patch(Circle((xx+w/2,yy+h/2),hd/2,facecolor='white',edgecolor='black',linestyle='--',linewidth=1.8))
                ax.text(xx+w/2,yy+h/2+hd/2+5,f'HOLE Ø{hd:.0f}',ha='center',va='bottom',fontsize=8.5,fontweight='bold')
                # Factory-photo rule: the open centre is usable for compatible
                # nested parts and may also carry inter-floor support columns.
                # Do not draw an imaginary solid centre under a rice stone.
                ax.text(xx+w/2,yy+h/2,'OPEN CENTRE / ช่องกลาง\nPARTS / SUPPORTS / ชิ้นงาน / ตัวรอง',ha='center',va='center',
                        fontsize=7.2,fontweight='bold',alpha=.75)
            if taper:
                ax.add_patch(Circle((xx+w/2,yy+h/2),max(min(w,h)*.44,1),fill=False,linestyle=':',linewidth=1.2))
        else:
            ax.add_patch(Rectangle((xx,yy),max(w,1),max(h,1),facecolor=_wo_color(wo),edgecolor='black',alpha=.58,linewidth=1.8))
            if taper:
                ax.add_patch(Rectangle((xx+w*.08,yy+h*.08),max(w*.84,1),max(h*.84,1),fill=False,linestyle=':',linewidth=1.1))
        # Keep the host ID readable in the annulus; do not cover a usable center hole.
        hd=_n(r.get('Hole Diameter mm')) if geom=='CIRCULAR' else 0
        ly=(yy+h/2+hd/2+(h-hd)/4) if (geom=='CIRCULAR' and 0<hd<h) else (yy+h/2)
        # V1.9.19: keep physical drawing clean; WO detail remains in legend/interactive hover where available.

    pm=top.get('Placement Mode',pd.Series('',index=top.index)).astype(str)
    nested=top[pm.str.contains('NESTED IN',case=False,na=False)]
    for _,n in nested.iterrows():
        xx,yy,w,h=_n(n.get('x mm')),_n(n.get('y mm')),_n(n.get('Footprint W mm')),_n(n.get('Footprint H mm'))
        geom=str(n.get('Base Geometry','')).upper(); pid=ids.get(str(n.get('Work Order','')),'P?')
        if geom=='CIRCULAR': ax.add_patch(Circle((xx+w/2,yy+h/2),max(min(w,h)/2,1),facecolor=_wo_color(str(n.get('Work Order',''))),edgecolor='black',alpha=.72,linestyle='-.',linewidth=1.5))
        else: ax.add_patch(Rectangle((xx,yy),max(w,1),max(h,1),facecolor=_wo_color(str(n.get('Work Order',''))),edgecolor='black',alpha=.72,linestyle='-.',linewidth=1.5))
        # Very small upright pieces are clearer without repeated text; Part ID remains in the legend.
        # no permanent part text inside physical pattern

    # Part-ID legend: long WO text stays outside the physical drawing.
    lines=[]
    for wo,pid in ids.items():
        g=top[top.get('Work Order',pd.Series('',index=top.index)).astype(str).eq(wo)]
        q=int(pd.to_numeric(g.get('Qty',0),errors='coerce').fillna(0).sum()) if not g.empty else 0
        r=g.iloc[0] if not g.empty else {}
        shape=str(r.get('Shape','')).strip(); extra=[]
        hd=_n(r.get('Hole Diameter mm'))
        if hd>0: extra.append(f'hole Ø{hd:.0f}')
        if _is_tapered_row(r): extra.append('TAPER')
        if 'ขัดพื้น' in shape: extra.append('UPRIGHT / NO STACK')
        lines.append(f'{pid}  {_short_wo(wo,16)}  {q} pcs'+(('  | '+', '.join(extra)) if extra else ''))
        ax.plot([],[],marker='s',markersize=9,linestyle='None',markerfacecolor=_wo_color(wo),markeredgecolor='black',label=f'{pid} {_short_wo(wo,16)}')
    if lines:
        ax.legend(loc='upper right',fontsize=7,framealpha=.88,title='WO COLOR',ncol=1)
        ax.text(1.01,.98,'PART ID / WO / QTY / รหัสชิ้นงาน / WO / จำนวน\n'+'\n'.join(lines[:24]),transform=ax.transAxes,ha='left',va='top',fontsize=9.6,bbox=dict(boxstyle='round',facecolor='white',alpha=.95))
    if dims:
        L,W=dims; ax.set_xlim(-0.02*L,1.32*L); ax.set_ylim(-0.10*W,1.10*W)
    else: ax.autoscale_view()
    ax.set_aspect('auto'); ax.set_xlabel('Length / ความยาว (mm)',fontsize=10); ax.set_ylabel('Width / ความกว้าง (mm)',fontsize=10); ax.grid(False)

    floors=sorted(v for v in x['Floor'].dropna().unique()); zbase={}; z=0.0
    for f in floors:
        g=x[x['Floor']==f]; first=g.iloc[0]
        pitch=max(_n(first.get('Floor Pitch mm')),max(pd.to_numeric(g.get('Stack Total Height mm',pd.Series([1])),errors='coerce').fillna(1).max(),1)); zbase[f]=z; z+=pitch
    _common_span=max(_n(kiln_info.get('L mm')) if kiln_info else 0,_n(kiln_info.get('W mm')) if kiln_info else 0,1)
    for ax,axis,title in [(axs[1],'x','FRONT VIEW / มุมมองด้านหน้า — WHOLE LOAD / ทั้งโหลด')]:
        ax.set_title(title,fontsize=13,fontweight='bold')
        if kiln_info:
            span=_n(kiln_info.get('L mm' if axis=='x' else 'W mm')); kh=_n(kiln_info.get('H mm'))
            if span>0 and kh>0: ax.add_patch(Rectangle((0,0),span,kh,fill=False,linewidth=2.0))
        for f in floors:
            g=x[x['Floor']==f]; first=g.iloc[0]; basef=_floor_base(g); plate_t=max(_n(first.get('Plate T mm')),1)
            ax.axhline(zbase[f],linewidth=.9,linestyle='--'); ax.text(2,zbase[f]+2,f'F{int(f)}',fontsize=8,va='bottom',fontweight='bold')
            if not basef.empty:
                poscol='x mm' if axis=='x' else 'y mm'; wcol='Footprint W mm' if axis=='x' else 'Footprint H mm'
                for _,r in basef.iterrows():
                    pos=_n(r.get(poscol)); width=_n(r.get(wcol)); sid=str(r.get('Stack ID',''))
                    # Circular/ring part has the same diameter in front and side elevation.
                    if str(r.get('Base Geometry','')).upper()=='CIRCULAR':
                        width=max(_n(r.get('D mm')),width)
                    segs=g[g.get('Stack ID',pd.Series('',index=g.index)).astype(str).eq(sid)].sort_values('Stack Segment')
                    zcur=zbase[f]+plate_t
                    for _,sg in segs.iterrows():
                        if 'NESTED IN' in str(sg.get('Placement Mode','')).upper():continue
                        cnt=max(int(_n(sg.get('Qty'),1)),1)
                        ph=max(_n(sg.get('T mm')),_n(sg.get('Piece Height mm')),1)
                        # Segment Bottom/Top is authoritative for total packed height.
                        seg_h=max(_n(sg.get('Segment Top mm'))-_n(sg.get('Segment Bottom mm')),ph)
                        each=max(seg_h/max(cnt,1),1)
                        col=_wo_color(sg.get('Work Order',''))
                        for kk in range(min(cnt,80)):
                            # quartz is represented as the ~2 mm sand band between pieces
                            product_h=max(each-(2.0 if kk>0 else 0.0),1)
                            if kk>0:
                                ax.add_patch(Rectangle((pos,zcur),max(width,1),2.0,facecolor='#E7D8A7',edgecolor='none',alpha=.95))
                                zcur+=2.0
                            if _is_tapered_row(sg):
                                inset=min(max(width*.08,1),width*.2)
                                pts=[(pos,zcur),(pos+width,zcur),(pos+width-inset,zcur+product_h),(pos+inset,zcur+product_h)]
                                ax.add_patch(Polygon(pts,closed=True,facecolor=col,edgecolor='black',alpha=.60,linewidth=1.0))
                            else:
                                ax.add_patch(Rectangle((pos,zcur),max(width,1),product_h,facecolor=col,edgecolor='black',alpha=.60,linewidth=.9))
                            # Hole/ID in elevation is shown by dashed center edges.
                            if str(sg.get('Base Geometry','')).upper()=='CIRCULAR' and _n(sg.get('Hole Diameter mm'))>0:
                                ax.plot([pos+width*.43,pos+width*.43],[zcur,zcur+product_h],linestyle=':',linewidth=.7)
                                ax.plot([pos+width*.57,pos+width*.57],[zcur,zcur+product_h],linestyle=':',linewidth=.7)
                            zcur+=product_h
                        # Common physical mm scale makes a circular part appear same width in front and side views.
                        if kiln_info:
                            _actual_span=_n(kiln_info.get('L mm' if axis=='x' else 'W mm'))
                            _pad=max((_common_span-_actual_span)/2,0)
                            ax.set_xlim(-_pad,_actual_span+_pad)
                        if cnt>80:
                            ax.text(pos+width/2,zcur,f'×{cnt}',ha='center',va='bottom',fontsize=7,fontweight='bold')
            # nested pieces can stand higher than the ring host; show their actual envelopes.
            ng=g[g.get('Placement Mode',pd.Series('',index=g.index)).astype(str).str.contains('NESTED IN',case=False,na=False)]
            for _,r in ng.iterrows():
                pos=_n(r.get('x mm' if axis=='x' else 'y mm')); width=_n(r.get('Footprint W mm' if axis=='x' else 'Footprint H mm')); h=max(_n(r.get('Segment Top mm')),_n(r.get('T mm')),1)
                ax.add_patch(Rectangle((pos,zbase[f]+plate_t),max(width,1),h,fill=False,linestyle='-.',linewidth=.9))
        if kiln_info:
            span=_n(kiln_info.get('L mm' if axis=='x' else 'W mm')); kh=_n(kiln_info.get('H mm'))
            if span>0: ax.set_xlim(0,span)
            if kh>0: ax.set_ylim(0,kh)
            else: ax.autoscale_view()
        else: ax.autoscale_view()
        ax.set_xlabel('mm',fontsize=10); ax.set_ylabel('Height / ความสูง (mm)',fontsize=10); ax.grid(False)
    fig.suptitle(f'{load_id} — VERIFIED PHYSICAL LOAD PATTERN / รูปแบบการจัดโหลดที่ตรวจสอบแล้ว',fontsize=15,fontweight='bold')
    # Selected-area zoom. The visible panel rectangles stay identical.
    _names=['TOP','FRONT']
    if float(area_zoom or 1.0)>1.0:
        for _name,_ax in zip(_names,axs):
            if str(zoom_view).upper() in ('ALL',_name):
                x0,x1=_ax.get_xlim();y0,y1=_ax.get_ylim()
                cx=x0+(x1-x0)*float(zoom_x_pct)/100.0
                cy=y0+(y1-y0)*float(zoom_y_pct)/100.0
                hw=(x1-x0)/(2.0*float(area_zoom));hh=(y1-y0)/(2.0*float(area_zoom))
                _ax.set_xlim(cx-hw,cx+hw);_ax.set_ylim(cy-hh,cy+hh)
    fig.subplots_adjust(left=.045,right=.985,bottom=.08,top=.90,wspace=.18); return fig

from __future__ import annotations
from pathlib import Path
import io, os, math
import pandas as pd
import matplotlib.pyplot as plt
import xlsxwriter
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
import pattern_on_demand_v16 as pat16

EN_TH_MM = {
    'title':('FIRING OPERATOR SHEET','ใบงานพนักงานเตาเผา',''),
    'date':('Date','วันที่',''),'kiln':('Kiln','เตา',''),'program':('Program','โปรแกรม',''),
    'load':('Load ID','รหัสโหลด',''),'wo':('Work Order','ใบสั่งผลิต',''),
    'qty':('Quantity (pcs)','จำนวน (ชิ้น)',''),'floor':('Floor','ชั้น',''),
    'furniture':('Kiln furniture','อุปกรณ์เตา',''),'pattern':('Pattern layout','รูปแบบการจัดเรียง',''),
    'shape':('Shape / dimensions','รูปทรง / ขนาด',''),
    'check':('Operator check before loading','ตรวจสอบก่อนเข้าเตา','')
}

def _register_fonts():
    candidates={
        'Thai':['C:/Windows/Fonts/angsa.ttf','C:/Windows/Fonts/angsana.ttf','C:/Windows/Fonts/angsanaupc.ttf','C:/Windows/Fonts/tahoma.ttf','C:/Windows/Fonts/LeelawUI.ttf','C:/Windows/Fonts/leelawad.ttf'],
        'Myanmar':['C:/Windows/Fonts/mmrtext.ttf','C:/Windows/Fonts/MyanmarText.ttf','C:/Windows/Fonts/padauk.ttf'],
    }
    out={'Thai':'Helvetica','Myanmar':'Helvetica'}
    for name,paths in candidates.items():
        for p in paths:
            if Path(p).exists():
                try: pdfmetrics.registerFont(TTFont(name,p));out[name]=name;break
                except Exception: pass
    return out

def _n(v,d=0.0):
    try:
        x=float(v); return d if math.isnan(x) else x
    except Exception:return d

def _shape_desc(g):
    vals=[]
    for _,r in g.iterrows():
        geom=str(r.get('Base Geometry','')).upper()
        if geom=='CIRCULAR':
            d=_n(r.get('D mm',r.get('Footprint W mm',0))); t=_n(r.get('T mm')); h=_n(r.get('Hole Diameter mm'))
            s=f'ROUND D{d:g} × T{t:g} mm'
            if h>0:s+=f' · hole {h:g}'
        else:
            w=_n(r.get('Footprint W mm')); h=_n(r.get('Footprint H mm')); t=_n(r.get('T mm'))
            s=f'RECT {w:g} × {h:g} × T{t:g} mm'
        if s not in vals:vals.append(s)
    return ' | '.join(vals[:4])

def _part_id_map(floorx):
    ids={}; n=1
    if floorx is None or floorx.empty:return ids
    for wo in floorx['Work Order'].astype(str):
        if wo not in ids:
            ids[wo]=f'P{n:02d}'; n+=1
    return ids


def _part_legend(floorx):
    ids=_part_id_map(floorx); rows=[]
    for wo,pid in ids.items():
        g=floorx[floorx['Work Order'].astype(str).eq(wo)]
        q=int(pd.to_numeric(g.get('Qty',0),errors='coerce').fillna(0).sum())
        r=g.iloc[0]
        dims=f"D {_n(r.get('D mm')):g} / T {_n(r.get('T mm')):g} / H {_n(r.get('H mm')):g} mm"
        rows.append({'Part ID':pid,'Work Order':wo,'Qty pcs':q,'Category':str(r.get('Category','')),'Shape':str(r.get('Shape','')),'Dimensions':dims})
    return pd.DataFrame(rows)


def _floor_summary(floorx):
    if floorx is None or floorx.empty:return pd.DataFrame()
    x=floorx.copy();x['Floor']=pd.to_numeric(x['Floor'],errors='coerce').fillna(0).astype(int);x['Qty']=pd.to_numeric(x.get('Qty',0),errors='coerce').fillna(0)
    rows=[]
    for f,g in x.groupby('Floor'):
        woq=g.groupby(g['Work Order'].astype(str))['Qty'].sum().to_dict(); ids=_part_id_map(x)
        first=g.iloc[0]
        plate=str(first.get('Plate','')).strip(); pc=int(_n(first.get('Plates / Floor')))
        ib=str(first.get('I-block','')).strip(); sn=int(_n(first.get('Support Nodes / Floor')))
        if plate:
            furn=f'Plate {plate} × {pc}'
            if ib:furn+=f' · I-block {ib} · support nodes {sn}'
        else:furn='FURNITURE NOT RESOLVED - DO NOT RELEASE'
        rows.append({'Floor':f,'Work Orders':' | '.join(f'{ids.get(wo,"P??")}:{int(q)}' for wo,q in woq.items()),'Qty pcs':int(g['Qty'].sum()),'Shape':_shape_desc(g),'Furniture':furn})
    return pd.DataFrame(rows).sort_values('Floor')

def _load_meta(fr,load_id):
    loads=fr.get('loads',pd.DataFrame());details=fr.get('details',pd.DataFrame())
    lr=loads[loads['Load ID'].astype(str).eq(str(load_id))]
    if lr.empty:raise ValueError('Load not found')
    lr=lr.iloc[0]
    dd=details[details['Load ID'].astype(str).eq(str(load_id))].copy()
    return lr,dd

def _excel_formats(wb):
    return {
        'title_en':wb.add_format({'bold':True,'font_size':16,'align':'center','valign':'vcenter','font_name':'Arial'}),
        'title_th':wb.add_format({'bold':True,'font_size':18,'align':'center','valign':'vcenter','font_name':'Angsana New'}),
        'title_mm':wb.add_format({'bold':True,'font_size':13,'align':'center','valign':'vcenter','font_name':'Myanmar Text'}),
        'hdr_en':wb.add_format({'bold':True,'font_size':10.5,'align':'center','valign':'vcenter','text_wrap':True,'border':1,'bg_color':'#EAF2F8','font_name':'Arial'}),
        'hdr_th':wb.add_format({'bold':True,'font_size':14,'align':'center','valign':'vcenter','text_wrap':True,'border':1,'bg_color':'#EAF2F8','font_name':'Angsana New'}),
        'hdr_mm':wb.add_format({'bold':True,'font_size':10.5,'align':'center','valign':'vcenter','text_wrap':True,'border':1,'bg_color':'#EAF2F8','font_name':'Myanmar Text'}),
        'cell':wb.add_format({'font_size':10.5,'valign':'top','text_wrap':True,'border':1,'font_name':'Arial'}),
        'center':wb.add_format({'font_size':10.5,'align':'center','valign':'vcenter','border':1,'font_name':'Arial'}),
        'warn':wb.add_format({'bold':True,'font_size':12,'align':'center','valign':'vcenter','text_wrap':True,'border':1,'bg_color':'#FFF2CC'}),
        'important':wb.add_format({'bold':True,'font_size':12,'valign':'top','text_wrap':True,'border':1,'bg_color':'#FFF2CC','font_name':'Arial'})
    }

def _write_tri_rows(ws,row,c1,c2,key,fmts):
    vals=EN_TH_MM[key]
    if c1==c2:
        ws.write(row,c1,vals[0],fmts['hdr_en'])
        ws.write(row+1,c1,vals[1],fmts['hdr_th'])
    else:
        ws.merge_range(row,c1,row,c2,vals[0],fmts['hdr_en'])
        ws.merge_range(row+1,c1,row+1,c2,vals[1],fmts['hdr_th'])

def create_operator_files(fr,load_id,out_dir):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    floorx,_,_,_=pat16.exact_pattern_for_load(fr,load_id)
    ok,issues=pat16.validate_pattern(floorx)
    if not ok:
        raise ValueError('Pattern HOLD / ระงับรูปแบบ: '+'; '.join(issues[:5]))

    lr,dd=_load_meta(fr,load_id)
    rel=dd.groupby(dd['Work Order'].astype(str))['Planned Firing Qty'].sum()
    phy=floorx.groupby(floorx['Work Order'].astype(str))['Qty'].sum()
    bad=[]
    for wo,q in rel.items():
        pq=float(phy.get(str(wo),0)); rq=float(q)
        if abs(pq-rq)>0.01:
            bad.append(f'{wo}: released {rq:g}, patterned {pq:g}')
    if bad:
        raise ValueError(
            'DO NOT RELEASE / ห้ามปล่อยงาน - physical/furniture pattern does not account for released quantity / '
            'รูปแบบจริงและอุปกรณ์เตาไม่ครอบคลุมจำนวนที่ปล่อย: '+'; '.join(bad[:10])
        )

    fs=_floor_summary(floorx)
    kiln=str(lr.get('Kiln',''));program=str(lr.get('Program',''));ld=str(lr.get('Load Date',''))[:10]
    safe=''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in str(load_id))
    xlsx=out_dir/f'FIRING_OPERATOR_{safe}.xlsx'
    pdf=out_dir/f'FIRING_OPERATOR_{safe}.pdf'
    kiln_info=pat16.kiln_info_for_load(fr,load_id)
    lg=_part_legend(floorx)

    wb=xlsxwriter.Workbook(str(xlsx)); fm=_excel_formats(wb)
    # Larger formats specifically for the operator print.
    fm['cell'].set_font_size(12); fm['center'].set_font_size(12); fm['warn'].set_font_size(12); fm['hdr_en'].set_font_size(12)

    ws=wb.add_worksheet('Operator Print')
    ws.set_landscape();ws.set_paper(9);ws.fit_to_pages(1,0);ws.set_margins(.20,.20,.22,.22)
    ws.set_column('A:A',8);ws.set_column('B:B',27);ws.set_column('C:C',11)
    ws.set_column('D:E',20);ws.set_column('F:L',18)
    ws.merge_range('A1:L1','FIRING OPERATOR SHEET',fm['title_en'])
    ws.merge_range('A2:L2','ใบงานพนักงานเตาเผา',fm['title_th'])
    ws.merge_range('A3:L3',f'Date / วันที่: {ld}   |   Kiln / เตา: {kiln}   |   Program / โปรแกรม: {program}   |   Load / รหัสโหลด: {load_id}',fm['warn'])
    _ready=pd.to_numeric(dd.get('Ready Now pcs',pd.Series(0,index=dd.index)),errors='coerce').fillna(0)
    _make=pd.to_numeric(dd.get('MAKE pcs',pd.Series(0,index=dd.index)),errors='coerce').fillna(0)
    _planned=pd.to_numeric(dd.get('Planned Firing Qty',pd.Series(0,index=dd.index)),errors='coerce').fillna(0)
    _gate=str(lr.get('Release Gate',''))
    r=4
    ws.merge_range(r,0,r,11,
        f'READINESS / ความพร้อม: Planned {int(_planned.sum())} pcs | Ready now {int(_ready.sum())} pcs | MAKE BEFORE FIRING {int(_make.sum())} pcs | Status / สถานะ: {_gate}',
        fm['warn']); r+=1
    _reason=str(lr.get('Release Reason',''))
    ws.merge_range(r,0,r,11,f'Reason / เหตุผล: {_reason}',fm['warn']); r+=2
    ws.merge_range(r,0,r,11,'WO-SPECIFIC PULL TO RELEASE / จำนวนที่ต้องผลิตเพิ่มเพื่อปล่อยเตา',fm['hdr_en']); r+=1
    _headers=['Work Order / ใบสั่งผลิต','Product Code / รหัสสินค้า','Customer / ลูกค้า','Category / ประเภทสินค้า','Work Type / ประเภทงาน','Due Date / กำหนดส่ง','Load Date / วันที่เข้าเตา','Planned Qty / จำนวนแผน','Ready Qty / จำนวนพร้อม','MAKE Qty / ต้องผลิตเพิ่ม','Part Status / สถานะชิ้นงาน','Forming Required By / ขึ้นรูปเสร็จภายใน']
    for _c,_h in enumerate(_headers): ws.write(r,_c,_h,fm['hdr_en'])
    r+=1
    for _,_rr in dd.iterrows():
        _pc=str(_rr.get('Product Code','') or '').strip(); _first=_pc[:1]; _ov=str(_rr.get('Test Work Override','AUTO') or 'AUTO').upper(); _ist=(_first=='1'); _ist=(False if _ov=='NORMAL' else (True if _ov=='TEST' else _ist)); _wt=('TEST / งานทดสอบ' if _ist else 'NORMAL / งานปกติ'); _cat=str(_rr.get('Category','') or '').strip().upper(); _cat=('PB' if _cat.startswith('PB') else (_cat[:1] if _cat[:1] in {'P','R','S','T','M'} else 'UNCLASSIFIED')); _status=str(_rr.get('Planning Status',_rr.get('Part Status',_rr.get('Forming Status',''))) or ''); _vals=[_rr.get('Work Order',''),_pc,_rr.get('Customer',''),_cat,_wt,str(_rr.get('Due Date',''))[:10],ld,int(float(_rr.get('Planned Firing Qty',0) or 0)),int(float(_rr.get('Ready Now pcs',0) or 0)),int(float(_rr.get('MAKE pcs',0) or 0)),_status,str(_rr.get('Forming Required By',''))[:10]]
        for _c,_v in enumerate(_vals): ws.write(r,_c,_v,fm['important'] if _c in (4,5,6,7,8,9,10,11) else fm['cell'])
        r+=1
    if float(_make.sum())>0:
        ws.merge_range(r,0,r,11,'PLANNED LOAD - PRODUCE MISSING PCS BEFORE RELEASE / ยังห้ามปล่อยเตา — complete the WO-specific MAKE quantities above, then revalidate actual readiness and exact physical pattern.',fm['warn']); r+=2
    else:
        ws.merge_range(r,0,r,11,'READY QUANTITY COVERS THIS PLAN — final release still requires kiln/furniture/pattern confirmation.',fm['warn']); r+=2
    for key,(c1,c2) in [('floor',(0,0)),('wo',(1,1)),('qty',(2,2)),('shape',(3,4)),('furniture',(5,7))]:
        _write_tri_rows(ws,r,c1,c2,key,fm)
    r+=2
    for _,row in fs.iterrows():
        ws.set_row(r,42)
        ws.write(r,0,int(row['Floor']),fm['center']); ws.write(r,1,row['Work Orders'],fm['cell'])
        ws.write(r,2,int(row['Qty pcs']),fm['center']); ws.merge_range(r,3,r,4,row['Shape'],fm['cell'])
        ws.merge_range(r,5,r,7,row['Furniture'],fm['cell']); r+=1

    r+=1
    ws.merge_range(r,0,r,11,'PART ID / WORK ORDER REFERENCE / รหัสชิ้นงาน / ใบสั่งผลิต',fm['hdr_en']); r+=1
    for c,h in enumerate(['Part ID / รหัส','Work Order / ใบสั่งผลิต','Qty / จำนวน','Category / ประเภท','Shape / รูปทรง','Dimensions / ขนาด']):
        ws.write(r,c,h,fm['hdr_en'])
    r+=1
    for _,rr in lg.iterrows():
        ws.set_row(r,30)
        vals=[rr['Part ID'],rr['Work Order'],rr['Qty pcs'],rr['Category'],rr['Shape'],rr['Dimensions']]
        for c,v in enumerate(vals): ws.write(r,c,v,fm['center'] if c in (0,2) else fm['cell'])
        r+=1
    r+=1
    ws.merge_range(r,0,r,11,'Operator check / ตรวจสอบก่อนเข้าเตา: □ WO/Qty ใบสั่ง/จำนวน  □ Program โปรแกรม  □ Furniture อุปกรณ์เตา  □ Pattern รูปแบบ  □ Kiln condition สภาพเตา',fm['warn'])

    floors=sorted(int(v) for v in pd.to_numeric(floorx['Floor'],errors='coerce').dropna().unique())
    floor_png={}
    for fno in floors:
        fig=pat16.draw_three_views(floorx,fno,load_id,kiln_info=kiln_info)
        bio=io.BytesIO(); fig.savefig(bio,format='png',dpi=260,bbox_inches='tight'); plt.close(fig); bio.seek(0)
        floor_png[fno]=bio
        sh=wb.add_worksheet(f'Floor F{fno}')
        sh.set_landscape();sh.set_paper(9);sh.fit_to_pages(1,1);sh.set_margins(.15,.15,.18,.18)
        sh.set_column('A:H',15)
        sh.merge_range('A1:H1',f'LOAD PATTERN / รูปแบบการจัดโหลด — {load_id} — FLOOR / ชั้น {fno}',fm['title_en'])
        sh.merge_range('A2:H2',f'Kiln / เตา: {kiln}   |   Program / โปรแกรม: {program}   |   Date / วันที่: {ld}',fm['warn'])
        sh.set_row(2,430)
        sh.insert_image(2,0,'pattern.png',{'image_data':bio,'x_scale':.66,'y_scale':.66,'x_offset':4,'y_offset':4})
        rr=25
        frs=fs[fs['Floor'].eq(fno)]
        if not frs.empty:
            row=frs.iloc[0]
            sh.set_row(rr,45)
            sh.merge_range(rr,0,rr,7,
                f"Floor / ชั้น {fno} | Qty / จำนวน {int(row['Qty pcs'])} pcs | "
                f"Parts / ชิ้นงาน: {row['Work Orders']} | Furniture / อุปกรณ์เตา: {row['Furniture']}",
                fm['warn'])
        rr+=2
        sh.set_row(rr,55)
        sh.merge_range(rr,0,rr,7,
            'IMPORTANT / สำคัญ: Follow the verified furniture, part orientation and support arrangement shown. '
            'Top level has no upper shelf only when indicated by this verified pattern. / '
            'ให้จัดอุปกรณ์เตา ทิศทางชิ้นงาน และตัวรองตามรูปที่ตรวจสอบแล้ว ชั้นบนสุดไม่มีแผ่นด้านบนเฉพาะเมื่อรูปนี้ระบุไว้',
            fm['cell'])

    wb.close()

    if not REPORTLAB_AVAILABLE:
        return str(xlsx),None,floorx

    fonts=_register_fonts();styles=getSampleStyleSheet()
    doc=SimpleDocTemplate(str(pdf),pagesize=landscape(A4),rightMargin=12,leftMargin=12,topMargin=10,bottomMargin=10)
    story=[]
    th=ParagraphStyle('thop',parent=styles['Normal'],fontName=fonts['Thai'],fontSize=10.5,leading=12.5,alignment=TA_CENTER)
    en=ParagraphStyle('enop',parent=styles['Normal'],fontName='Helvetica',fontSize=9.5,leading=11)
    title=ParagraphStyle('enopt',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=12.5,leading=14,alignment=TA_CENTER)

    for ix,fno in enumerate(floors):
        if ix: story.append(PageBreak())
        story.append(Paragraph(f'FIRING OPERATOR SHEET — LOAD {load_id} — FLOOR {fno}',title))
        story.append(Paragraph(f'ใบงานพนักงานเตาเผา — โหลด {load_id} — ชั้น {fno}',th))
        mt=Table([['Date / วันที่',ld,'Kiln / เตา',kiln,'Program / โปรแกรม',program]],colWidths=[78,90,78,90,95,110])
        mt.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.grey),('FONTSIZE',(0,0),(-1,-1),9.5),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
        story.append(mt);story.append(Spacer(1,3))
        img=floor_png[fno];img.seek(0);story.append(Image(img,width=750,height=335));story.append(Spacer(1,3))
        frs=fs[fs['Floor'].eq(fno)]
        if not frs.empty:
            row=frs.iloc[0]
            data=[
                ['Floor / ชั้น','Part IDs / รหัส','Qty / จำนวน','Shape / รูปทรง-ขนาด','Furniture / อุปกรณ์เตา'],
                [str(fno),str(row['Work Orders']),str(int(row['Qty pcs'])),str(row['Shape']),str(row['Furniture'])]
            ]
            ft=Table(data,colWidths=[55,175,70,190,260],repeatRows=1)
            ft.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9.2),('LEADING',(0,0),(-1,-1),11),('VALIGN',(0,0),(-1,-1),'TOP')]))
            story.append(ft)
        story.append(Spacer(1,3))
        story.append(Paragraph('Operator check: WO/Qty · Program · Furniture · Pattern · Kiln condition',en))
        story.append(Paragraph('ตรวจสอบก่อนเข้าเตา: WO/จำนวน · โปรแกรม · อุปกรณ์เตา · รูปแบบ · สภาพเตา',th))
    doc.build(story)
    return str(xlsx),str(pdf),floorx

def create_large_part_review_files(fr,load_id,out_dir,error_text=''):
    """Create an A4 diagnostic/review sheet when exact furniture packing cannot be released.

    This DOES NOT convert an invalid physical pattern into a released pattern. It gives
    Production/Planning a printable dimensional review for large R/other parts so the
    missing furniture arrangement can be confirmed and entered correctly.
    """
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    lr,dd=_load_meta(fr,load_id)
    prep=fr.get('prepared',pd.DataFrame()).copy(); kiln_info=pat16.kiln_info_for_load(fr,load_id) or {}
    kiln=str(lr.get('Kiln',''));program=str(lr.get('Program',''));ld=str(lr.get('Load Date',''))[:10]
    rel=dd.groupby(dd['Work Order'].astype(str))['Planned Firing Qty'].sum().reset_index()
    rows=[]
    for _,r in rel.iterrows():
        wo=str(r['Work Order']);q=float(r['Planned Firing Qty']);cand=prep[prep['Work Order'].astype(str).eq(wo)] if not prep.empty else pd.DataFrame()
        pr=cand.iloc[0] if not cand.empty else pd.Series(dtype=object)
        fx=_n(pr.get('Footprint X'));fy=_n(pr.get('Footprint Y'));ph=_n(pr.get('Piece Height'));cat=str(pr.get('Category',''))
        L=_n(kiln_info.get('L mm'));W=_n(kiln_info.get('W mm'));H=_n(kiln_info.get('H mm'))
        chamber_fit=(fx<=max(L-50,0) and fy<=max(W-50,0) and ph<=max(H-50,0)) or (fy<=max(L-50,0) and fx<=max(W-50,0) and ph<=max(H-50,0))
        rows.append({'Work Order':wo,'Category':cat,'Released Qty pcs':q,'Footprint X mm':fx,'Footprint Y mm':fy,'Piece Height mm':ph,'Weight kg/pc':_n(pr.get('Weight kg/pc')),'Chamber Geometry Fit':'YES - DIMENSIONALLY' if chamber_fit else 'NO','Furniture / Pattern Status':'NOT VERIFIED - DO NOT RELEASE'})
    rd=pd.DataFrame(rows)
    safe=''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in str(load_id))
    xlsx=out_dir/f'FIRING_R_LARGE_PART_REVIEW_{safe}.xlsx';pdf=out_dir/f'FIRING_R_LARGE_PART_REVIEW_{safe}.pdf'

    # Simple chamber/part top-view diagnostic. This is intentionally not a released pattern.
    fig,ax=plt.subplots(figsize=(10,5.8));L=_n(kiln_info.get('L mm'),1);W=_n(kiln_info.get('W mm'),1)
    ax.add_patch(plt.Rectangle((0,0),L,W,fill=False,linewidth=2));ax.text(L/2,W*1.02,f'KILN {kiln}  {L:g}×{W:g} mm',ha='center',va='bottom',fontweight='bold')
    y=W*0.08
    for i,r in rd.iterrows():
        fx=float(r['Footprint X mm']);fy=float(r['Footprint Y mm']);
        x=max((L-fx)/2,0); yy=max((W-fy)/2,0)
        if fx>0 and fy>0:
            ax.add_patch(plt.Rectangle((x,yy),min(fx,L),min(fy,W),fill=False,linewidth=1.5));ax.text(x+min(fx,L)/2,yy+min(fy,W)/2,str(r['Work Order']),ha='center',va='center',fontsize=8)
    ax.set_xlim(-L*.04,L*1.04);ax.set_ylim(-W*.12,W*1.12);ax.set_aspect('equal');ax.axis('off');ax.set_title('R / LARGE-PART DIMENSION REVIEW — NOT A RELEASED FURNITURE PATTERN',fontweight='bold')
    png=io.BytesIO();fig.savefig(png,format='png',dpi=250,bbox_inches='tight');plt.close(fig);png.seek(0)

    wb=xlsxwriter.Workbook(str(xlsx));ws=wb.add_worksheet('Operator Print');fm=_excel_formats(wb)
    ws.set_landscape();ws.set_paper(9);ws.fit_to_pages(1,1);ws.set_margins(.22,.22,.25,.25);ws.set_column('A:A',18);ws.set_column('B:H',16)
    ws.merge_range('A1:H1','R / LARGE-PART FURNITURE REVIEW — NOT RELEASED',fm['title_en'])
    ws.merge_range('A2:H2',f'DATE {ld} | KILN {kiln} | PROGRAM {program} | LOAD {load_id}',fm['warn'])
    ws.merge_range('A3:H4','Exact physical/furniture pattern did not validate. Production/Planning must confirm the actual support/furniture arrangement before release. ERROR: '+str(error_text),fm['warn'])
    ws.set_row(4,290);ws.insert_image(4,0,'review.png',{'image_data':png,'x_scale':.55,'y_scale':.55,'x_offset':4,'y_offset':4})
    r=22;headers=list(rd.columns)
    for c,h in enumerate(headers):ws.write(r,c,h,fm['hdr_en'])
    for i,(_,rr) in enumerate(rd.iterrows(),start=r+1):
        for c,h in enumerate(headers):ws.write(i,c,rr[h],fm['cell'])
    wb.close()

    if not REPORTLAB_AVAILABLE:return str(xlsx),None
    fonts=_register_fonts();styles=getSampleStyleSheet();doc=SimpleDocTemplate(str(pdf),pagesize=landscape(A4),rightMargin=18,leftMargin=18,topMargin=16,bottomMargin=16);story=[]
    story.append(Paragraph('R / LARGE-PART FURNITURE REVIEW — NOT RELEASED',ParagraphStyle('rv',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=15,alignment=TA_CENTER)))
    story.append(Paragraph(f'Date {ld} · Kiln {kiln} · Program {program} · Load {load_id}',styles['Normal']))
    story.append(Paragraph('Exact physical/furniture pattern did not validate. Confirm actual furniture/support arrangement before release.',styles['Normal']))
    story.append(Paragraph('ERROR: '+str(error_text),styles['Normal']));story.append(Spacer(1,5));png.seek(0);story.append(Image(png,width=520,height=285));story.append(Spacer(1,4))
    data=[headers]+[[str(v) for v in rr.tolist()] for _,rr in rd.iterrows()];tab=Table(data,repeatRows=1);tab.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),('FONTSIZE',(0,0),(-1,-1),6.5)]));story.append(tab);doc.build(story)
    return str(xlsx),str(pdf)

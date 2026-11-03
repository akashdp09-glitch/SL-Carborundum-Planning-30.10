
import tkinter as tk
from tkinter import ttk
import math
import hashlib
import pandas as pd
import ppc_fast_core_v4_6 as fc

def _font(root,size=9,bold=False):
    try:
        import tkinter.font as tkfont
        fam=set(tkfont.families(root))
        for name in ("Leelawadee UI","Tahoma","Nirmala UI","Arial Unicode MS","Segoe UI"):
            if name in fam:return (name,size,"bold" if bold else "normal")
    except:pass
    return ("Tahoma",size,"bold" if bold else "normal")

_PALETTE=("#4E79A7","#F28E2B","#59A14F","#E15759","#B07AA1","#76B7B2","#EDC948","#FF9DA7","#9C755F","#BAB0AC")
def _wo_color(wo):
    return _PALETTE[int(hashlib.md5(str(wo).encode("utf-8")).hexdigest()[:8],16)%len(_PALETTE)]

def num(v,d=0.0):
    try:return float(v)
    except:return d

class Pattern3View(ttk.Frame):
    """
    V4.2:
      TOP   = selected floor only.
      FRONT = whole kiln load, every floor/level.
      SIDE  = whole kiln load, every floor/level.
    """
    def __init__(self,master):
        super().__init__(master)
        self.fr=None;self.plan=None
        self.F=_font(self,9);self.FB=_font(self,9,True);self.FS=_font(self,7);self.FSB=_font(self,7,True)
        bar=ttk.Frame(self);bar.pack(fill="x",pady=3)
        ttk.Label(bar,text="Load / โหลด").pack(side="left")
        self.load=ttk.Combobox(bar,state="readonly",width=28);self.load.pack(side="left",padx=4)
        ttk.Label(bar,text="Top floor / ชั้นสำหรับมุมบน").pack(side="left")
        self.floor=ttk.Combobox(bar,state="readonly",width=8);self.floor.pack(side="left",padx=4)
        ttk.Button(bar,text="SHOW / แสดง",command=self.draw).pack(side="left")
        ttk.Label(bar,text="  TOP = selected floor | FRONT/SIDE = whole load",
                  font=self.FB).pack(side="left",padx=8)
        self.load.bind("<<ComboboxSelected>>",lambda e:self._floors())
        self.floor.bind("<<ComboboxSelected>>",lambda e:self.draw())
        self.canvas=tk.Canvas(self,bg="white");self.canvas.pack(fill="both",expand=True)
        self.info=tk.Text(self,height=7,font=self.F);self.info.pack(fill="x")

    def set_data(self,fr,plan):
        self.fr=fr;self.plan=plan
        fp=fr.get("floor",pd.DataFrame())
        ids=list(fp["Load ID"].dropna().astype(str).unique()) if not fp.empty else []
        self.load["values"]=ids
        if ids:
            self.load.set(ids[0]);self._floors();self.draw()

    def _floors(self):
        if not self.fr:return
        fp=self.fr.get("floor",pd.DataFrame());lid=self.load.get()
        if fp.empty:return
        vals=[str(int(x)) for x in sorted(fp.loc[fp["Load ID"].astype(str)==lid,"Floor"].dropna().unique())]
        self.floor["values"]=vals
        if vals:self.floor.set(vals[0])

    def _raw(self,wo):
        if self.plan is None or self.plan.empty:return {}
        x=self.plan[self.plan["Work Order"].astype(str)==str(wo)]
        return x.iloc[0].to_dict() if not x.empty else {}

    def _whole_load_height(self,allx):
        levels=[]
        for fno in sorted(allx["Floor"].unique()):
            f=allx[allx["Floor"]==fno]
            first=f.iloc[0]
            pitch=max(num(first.get("Floor Pitch mm",0)),1)
            levels.append((fno,pitch,first))
        total=sum(x[1] for x in levels)
        return levels,max(total,1)

    def _draw_top(self,panel,x):
        x0,y0,x1,y1,_=panel
        if x.empty:return
        first=x.iloc[0]
        pl=num(first.get("Plate L mm"));pw=num(first.get("Plate W mm"))
        cols=max(int(num(first.get("Plate Cols"))),1);rows=max(int(num(first.get("Plate Rows"))),1)
        gap=10
        L=max(pl*cols+gap*max(cols-1,0),500)
        W=max(pw*rows+gap*max(rows-1,0),500)
        m=18;sc=min((x1-x0-2*m)/L,(y1-y0-2*m)/W);ox=x0+m;oy=y0+m

        if pl>0 and pw>0:
            for rr in range(rows):
                for cc in range(cols):
                    ax=ox+cc*(pl+gap)*sc;ay=oy+rr*(pw+gap)*sc
                    self.canvas.create_rectangle(ax,ay,ax+pl*sc,ay+pw*sc,dash=(3,2))
            for rr in range(rows+1):
                for cc in range(cols+1):
                    ax=ox+cc*(pl+gap)*sc;ay=oy+rr*(pw+gap)*sc
                    self.canvas.create_oval(ax-2,ay-2,ax+2,ay+2,fill="black")

        base=x[~x["Placement Mode"].astype(str).str.contains("NESTED IN",na=False)] if "Placement Mode" in x.columns else x
        stacks=base.sort_values(["Stack ID","Stack Segment"]).groupby("Stack ID",as_index=False).first()
        for _,p in stacks.iterrows():
            xx=ox+num(p.get("x mm"))*sc;yy=oy+num(p.get("y mm"))*sc
            ww=num(p.get("Footprint W mm"))*sc;hh=num(p.get("Footprint H mm"))*sc
            raw=self._raw(p.get("Work Order",""));geom=str(p.get("Base Geometry","")).upper()
            if geom=="CIRCULAR":
                self.canvas.create_oval(xx,yy,xx+ww,yy+hh,width=2,fill=_wo_color(p.get("Work Order","")))
                hd=fc.maxdim(raw.get("H",p.get("Hole Diameter mm",0)))
                od=max(fc.maxdim(raw.get("D",p.get("D mm",0))),1)
                if hd>0:
                    hr=min((hd/od)*ww/2,ww/2);cx=xx+ww/2;cy=yy+hh/2
                    self.canvas.create_oval(cx-hr,cy-hr,cx+hr,cy+hr,width=2,fill="white")
                    self.canvas.create_text(cx,cy,text="รู / HOLE",font=self.FS)
            else:
                self.canvas.create_rectangle(xx,yy,xx+ww,yy+hh,width=2,fill=_wo_color(p.get("Work Order","")))
            self.canvas.create_text(xx+ww/2,yy+hh/2,text=str(p.get("Stack ID","")),
                                    font=self.FS)

        nested=x[x["Placement Mode"].astype(str).str.contains("NESTED IN",na=False)] if "Placement Mode" in x.columns else pd.DataFrame()
        for _,n in nested.iterrows():
            host=stacks[stacks["Stack ID"].astype(str)==str(n.get("Host Stack ID",""))] if "Host Stack ID" in n else pd.DataFrame()
            if host.empty:continue
            p=host.iloc[0]
            cx=ox+(num(p.get("x mm"))+num(p.get("Footprint W mm"))/2)*sc
            cy=oy+(num(p.get("y mm"))+num(p.get("Footprint H mm"))/2)*sc
            r=min(num(n.get("Footprint W mm",20)),num(n.get("Footprint H mm",20)))*sc/2
            self.canvas.create_oval(cx-r,cy-r,cx+r,cy+r,width=2,dash=(2,2),fill=_wo_color(n.get("Work Order","")))

    def _draw_elevation(self,panel,allx,axis="front"):
        x0,y0,x1,y1,_=panel
        if allx.empty:return
        levels,totalh=self._whole_load_height(allx)
        m=18
        # Horizontal physical span comes from furniture footprint.
        first=allx.iloc[0]
        pl=num(first.get("Plate L mm"));pw=num(first.get("Plate W mm"))
        cols=max(int(num(first.get("Plate Cols"))),1);rows=max(int(num(first.get("Plate Rows"))),1)
        gap=10
        loadL=max(pl*cols+gap*max(cols-1,0),500)
        loadW=max(pw*rows+gap*max(rows-1,0),500)
        span=loadL if axis=="front" else loadW
        scx=(x1-x0-2*m)/max(span,1)
        scy=(y1-y0-2*m)/max(totalh,1)
        ox=x0+m
        # bottom-up whole-load elevation
        ybase=y1-m
        for fno,pitch,_first in levels:
            f=allx[allx["Floor"]==fno]
            plate_t=max(num(_first.get("Plate T mm",0)),3)
            ibh=max(num(_first.get("I-block Height mm",0)),0)
            fy=ybase
            self.canvas.create_line(ox,fy,x1-m,fy,width=4,fill="#777777")
            self.canvas.create_text(x0+4,fy-7,text=f"F{int(fno)}",anchor="w",font=self.FSB)
            # support/I-block markers
            for frac in (0.08,0.5,0.92):
                sx=ox+(x1-x0-2*m)*frac
                self.canvas.create_rectangle(sx-3,fy-ibh*scy,sx+3,fy,fill="#777777",outline="#555555")

            base=f[~f["Placement Mode"].astype(str).str.contains("NESTED IN",na=False)] if "Placement Mode" in f.columns else f
            stacks=base.sort_values(["Stack ID","Stack Segment"]).groupby("Stack ID",as_index=False).first()
            for _,p in stacks.iterrows():
                pos=num(p.get("x mm")) if axis=="front" else num(p.get("y mm"))
                width=num(p.get("Footprint W mm")) if axis=="front" else num(p.get("Footprint H mm"))
                h=max(num(p.get("Stack Total Height mm",0)),num(p.get("T mm",0)),5)
                xx=ox+pos*scx; ww=max(width*scx,2); hh=max(h*scy,2)
                top=fy-max(ibh*scy,0)-hh
                bottom=fy-max(ibh*scy,0)
                raw=self._raw(p.get("Work Order",""))
                dvals=fc.dim_values(raw.get("D",""));tvals=fc.dim_values(raw.get("T",""));hvals=fc.dim_values(raw.get("H",""))
                taper=(len(dvals)>=2 and max(dvals)!=min(dvals)) or (len(tvals)>=2 and max(tvals)!=min(tvals)) or (len(hvals)>=2 and max(hvals)!=min(hvals))
                segs=f[f["Stack ID"].astype(str)==str(p.get("Stack ID",""))].sort_values("Stack Segment")
                zpix=bottom
                for _,sg in segs.iterrows():
                    cnt=max(int(num(sg.get("Pieces in Segment",1),1)),1)
                    ph=max(num(sg.get("T mm",sg.get("Piece Height mm",5)),5),1)
                    col=_wo_color(sg.get("Work Order",""))
                    # bounded visual rendering only: no effect on planning speed/qty
                    show=min(cnt,60)
                    for kk in range(show):
                        hh2=max(ph*scy,2);tp=zpix-hh2
                        if taper:
                            tw=ww*.72
                            self.canvas.create_polygon(xx,zpix,xx+ww,zpix,xx+(ww+tw)/2,tp,xx+(ww-tw)/2,tp,
                                                       outline="black",fill=col)
                        else:self.canvas.create_rectangle(xx,tp,xx+ww,zpix,fill=col,outline="black")
                        if str(sg.get("Base Geometry",p.get("Base Geometry",""))).upper()=="CIRCULAR" and num(sg.get("Hole Diameter mm",p.get("Hole Diameter mm",0)))>0:
                            self.canvas.create_line(xx+ww/2,tp,xx+ww/2,zpix,dash=(2,2))
                        zpix=tp
                        if kk<show-1:
                            qh=max(2.0*scy,1);self.canvas.create_rectangle(xx,zpix-qh,xx+ww,zpix,fill="#E7D8A7",outline="");zpix-=qh
                    if cnt>show:self.canvas.create_text(xx+ww/2,zpix-6,text=f"×{cnt}",font=self.FSB)
                if segs.empty:
                    self.canvas.create_rectangle(xx,top,xx+ww,bottom,fill=_wo_color(p.get("Work Order","")),outline="black")
            ybase -= pitch*scy

    def draw(self):
        self.canvas.delete("all");self.info.delete("1.0","end")
        if not self.fr:return
        fp=self.fr.get("floor",pd.DataFrame());lid=self.load.get()
        if fp.empty or not lid:return
        allx=fp[fp["Load ID"].astype(str)==lid].copy()
        if allx.empty:return
        try:fno=int(self.floor.get())
        except:
            fno=int(sorted(allx["Floor"].unique())[0])
        topx=allx[allx["Floor"]==fno].copy()

        cw=max(self.canvas.winfo_width(),1200);ch=max(self.canvas.winfo_height(),620)
        panels=[
            (10,25,cw/3-15,ch-35,f"TOP / ด้านบน — FLOOR {fno}"),
            (cw/3+5,25,2*cw/3-10,ch-35,"FRONT / ด้านหน้า — WHOLE LOAD"),
            (2*cw/3+5,25,cw-10,ch-35,"SIDE / ด้านข้าง — WHOLE LOAD"),
        ]
        for x0,y0,x1,y1,title in panels:
            self.canvas.create_rectangle(x0,y0,x1,y1,width=2)
            self.canvas.create_text((x0+x1)/2,y0-10,text=title,font=_font(self,10,True))

        self._draw_top(panels[0],topx)
        self._draw_elevation(panels[1],allx,"front")
        self._draw_elevation(panels[2],allx,"side")

        first=allx.iloc[0]
        floors=sorted(int(x) for x in allx["Floor"].dropna().unique())
        self.info.insert("end",f"Load / โหลด: {lid} | Top view selected floor / ชั้นที่เลือก: {fno}\n")
        self.info.insert("end",f"Whole load floors / ชั้นทั้งหมด: {', '.join(map(str,floors))} ({len(floors)} levels)\n")
        self.info.insert("end",f"Furniture / อุปกรณ์เตา: Plate {first.get('Plate','')} | "
                               f"{int(num(first.get('Plates / Floor',0)))} plates/floor | "
                               f"I-block {first.get('I-block','')} | supports {int(num(first.get('Support Nodes / Floor',0)))}\n")
        self.info.insert("end","TOP = selected floor; FRONT/SIDE = complete load. Different colors = different WO; grey = furniture; "
                               "sand band = approx. 2 mm quartz between stacked parts. Hole/ID and taper are shown when source geometry provides them.\n")
        _wos=list(dict.fromkeys(allx["Work Order"].dropna().astype(str).tolist()))
        self.info.insert("end","WO / สี: "+" | ".join(_wos[:12])+(" ..." if len(_wos)>12 else "")+"\n")

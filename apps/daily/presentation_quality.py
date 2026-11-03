"""SL Planning Department presentation layer. Does not change planning calculations.

Plotly charts stay vector in browser and offline HTML; PNG/SVG exports use
Plotly's browser toolbar (no Kaleido or internet needed for exported HTML).
"""
import html
import re
import pandas as pd

PALETTE={'P':'#2563eb','R':'#16a34a','S':'#e11d48','T':'#7c3aed','M':'#0891b2','PB':'#eab308'}

def chart_layout(fig, large=False):
    fig.update_layout(
        template='plotly_white', paper_bgcolor='#ffffff', plot_bgcolor='#fafbfc',
        font={'family':'Arial, Noto Sans Thai, Tahoma, sans-serif','size':19 if large else 16,'color':'#253047'},
        title_font={'size':25 if large else 21,'color':'#202b3d'},
        legend={'orientation':'h','yanchor':'bottom','y':1.02,'x':0,'font':{'size':16 if large else 14}},
        margin={'t':120,'b':112,'l':90,'r':65},
        height=max(610 if large else 510, int(getattr(fig.layout,'height',0) or 0)),
        hoverlabel={'font_size':18 if large else 15},
        uniformtext={'minsize':12,'mode':'hide'},
        autosize=True,
    )
    fig.update_xaxes(automargin=True,tickfont={'size':16 if large else 13},title_font={'size':18 if large else 15},showgrid=False)
    fig.update_yaxes(automargin=True,tickfont={'size':16 if large else 13},title_font={'size':18 if large else 15},gridcolor='#e7ecf2',zerolinecolor='#cbd5e1')
    for tr in fig.data:
        if getattr(tr,'type',None)=='bar' and str(getattr(tr,'name','')) in PALETTE:
            tr.marker.color=PALETTE[tr.name]
    return fig

def chart_config(name):
    return {'displaylogo':False,'responsive':True,'scrollZoom':True,'displayModeBar':True,
            'modeBarButtonsToAdd':['toImage','drawline','eraseshape'],
            'toImageButtonOptions':{'format':'svg','filename':name,'height':1100,'width':1900,'scale':1}}

def offline_html(fig,title='SL Planning Department',lang='English / ไทย'):
    """Embed Plotly JS for offline use, with a separate high-res PNG export button."""
    import plotly.io as pio
    title=html.escape(str(title))
    body=pio.to_html(fig,full_html=False,include_plotlyjs=True,div_id='sl_chart',config=chart_config(re.sub('[^a-zA-Z0-9_-]','_',title)))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
    <style>body{{font-family:Arial,"Noto Sans Thai",Tahoma,sans-serif;margin:0;background:#f5f6f8;color:#263449}}
    header{{background:#fff;border-bottom:5px solid #f28c00;padding:20px 32px;display:flex;align-items:center;gap:22px;flex-wrap:wrap}}
    h1{{font-size:25px;margin:0}}.tools{{margin-left:auto;display:flex;gap:10px;flex-wrap:wrap}}
    button{{font-size:17px;font-weight:700;padding:12px 18px;border:1px solid #d1d5db;border-radius:10px;background:#fff;cursor:pointer}}
    button.primary{{background:#f28c00;color:#fff;border-color:#f28c00}}main{{padding:14px 24px}}#sl_chart{{width:100%;height:calc(100vh - 135px);min-height:650px}}
    @media print{{header .tools{{display:none}}main{{padding:0}}#sl_chart{{height:80vh}}}}
    </style></head><body><header><h1>Planning Department / แผนกวางแผน</h1>
    <div class="tools"><button onclick="zoom(1.2)">A+ Zoom / ขยาย</button>
    <button onclick="zoom(1/1.2)">A−</button><button onclick="Plotly.downloadImage('sl_chart',{{format:'svg',filename:'SL_Planning_Vector'}})">SVG Vector</button>
    <button class="primary" onclick="Plotly.downloadImage('sl_chart',{{format:'png',width:3840,height:2160,scale:1,filename:'SL_Planning_4K'}})">4K PNG</button>
    <button onclick="window.print()">Print / พิมพ์</button></div></header><main>{body}</main>
    <script>let z=1;function zoom(f){{z*=f;document.getElementById('sl_chart').style.zoom=z}}</script></body></html>'''

def is_date_axis(fig):
    """Only dates, never categorical month strings or numerical process codes."""
    try:
        if str(getattr(fig.layout.xaxis,'type',''))=='date': return True
        for tr in fig.data:
            if getattr(tr,'type','') not in ('bar','scatter'):continue
            vals=list(tr.x) if tr.x is not None else []
            if not vals:continue
            sample=[v for v in vals[:min(8,len(vals))] if v is not None]
            if not sample:continue
            if all(isinstance(v,(pd.Timestamp,)) for v in sample):return True
            if all(isinstance(v,str) and bool(re.match(r'^\d{4}-\d\d-\d\d',v)) for v in sample):return True
    except Exception:pass
    return False

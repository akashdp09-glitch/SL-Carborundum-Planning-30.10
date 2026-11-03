"""Build an auditable, searchable snapshot from operator supplied Excel sources."""
from pathlib import Path
import sqlite3, hashlib, json, zipfile, datetime, re, sys
from openpyxl import load_workbook
from zoneinfo import ZoneInfo

OUT=Path(__file__).resolve().parent/'knowledge_base.sqlite'
SRC=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'CENTRAL_DATA'/'COMPANY_DATA'
TMP=OUT.with_name('knowledge_base.building.sqlite')
TZ=ZoneInfo('Asia/Bangkok')
SNAPSHOT=datetime.datetime.now(TZ).isoformat(timespec='seconds')
PREFERRED=['Cover_S&OP10_011026.xlsx','MRP BOND2026-10.xlsx','SOP10-2026-ข้อมูลเปิดผลิตจากฝ่ายขาย.xlsx','PM_PBM_011026.xlsx','PS_PBS_011026.xlsx','P280526(2).xlsx','RP-S-011026001-216.xlsx','Plan 2026-2-Update-240926.xlsx','Stock on hand_230926(1).xlsx','Cap แต่ละแผนก(20260911-074159).xlsx','ปริมาณการใช้วัตถุดิบ 2025-2026 material usage.xlsx']

def clean(v):
 if v is None:return ''
 if isinstance(v,(datetime.date,datetime.datetime)):return v.isoformat()
 s=str(v).strip()
 return '' if s in {'#N/A','#VALUE!','#REF!','#NAME?','#DIV/0!'} else s

def colnum(col):
 n=0
 for ch in col.upper():n=n*26+ord(ch)-64
 return n-1

def main():
 OUT.parent.mkdir(parents=True,exist_ok=True)
 for stale in (TMP,TMP.with_name(TMP.name+'-wal'),TMP.with_name(TMP.name+'-shm')):
  try:stale.unlink()
  except FileNotFoundError:pass
 con=sqlite3.connect(TMP); con.execute('PRAGMA journal_mode=WAL');con.execute('PRAGMA synchronous=NORMAL')
 con.executescript('''CREATE TABLE sources(source_id INTEGER PRIMARY KEY,filename TEXT,path TEXT,size_bytes INTEGER,sha256 TEXT,filesystem_modified TEXT,workbook_modified TEXT,snapshot_time TEXT);
 CREATE TABLE records(record_id INTEGER PRIMARY KEY,source_id INTEGER,sheet TEXT,row_number INTEGER,category TEXT,quality TEXT,header_row INTEGER,body TEXT,normalized TEXT,fields_json TEXT,FOREIGN KEY(source_id) REFERENCES sources(source_id));
 CREATE INDEX idx_records_source ON records(source_id); CREATE INDEX idx_records_sheet_row ON records(sheet,row_number); CREATE INDEX idx_records_norm ON records(normalized);''')
 files=[SRC/n for n in PREFERRED if (SRC/n).exists()]
 # Add other supplied Excel reference/test files as searchable evidence.
 files += [p for p in sorted(SRC.glob('*.xlsx')) if p not in files and not p.name.startswith('~$')]
 if not files: raise SystemExit(f'No .xlsx source files found in {SRC}; existing knowledge database was left unchanged.')
 total=0
 for path in files:
  try:
   raw=path.read_bytes(); sha=hashlib.sha256(raw).hexdigest(); mt=datetime.datetime.fromtimestamp(path.stat().st_mtime,TZ).isoformat(timespec='seconds')
   modified=''
   try:
    with zipfile.ZipFile(path) as z:
     core=z.read('docProps/core.xml').decode('utf8','ignore');m=re.search(r'<dcterms:modified[^>]*>([^<]+)',core);modified=m.group(1) if m else ''
   except:pass
   cur=con.execute('INSERT INTO sources(filename,path,size_bytes,sha256,filesystem_modified,workbook_modified,snapshot_time) VALUES(?,?,?,?,?,?,?)',(path.name,str(path.resolve()),len(raw),sha,mt,modified,SNAPSHOT));sid=cur.lastrowid
   wb=load_workbook(path,read_only=True,data_only=True)
   for ws in wb.worksheets:
    title=ws.title.strip()
    # Ignore Excel's inflated used-range sheets, except the Plan master whose status fields are intentionally far right.
    _is_plan_master=path.name.startswith(('Plan 2026','Plan-2026')) and title=='แผนการเผา'
    if ((ws.max_column or 1)>2000 and not _is_plan_master) or (ws.max_row or 1)>200000: continue
    # Keep master/demand/active cover/process sheets, not hundreds of generated WO forms.
    wo_page=(bool(re.match(r'^(?:PS|PBS|PM|PBM)\d+',title,re.I)) if path.name.startswith(('PS_PBS','PM_PBM')) else bool(re.match(r'^P\d{3}$',title,re.I)) if path.name.startswith('P280') else False)
    if path.name.startswith(('PS_PBS','PM_PBM')) and title not in {'Drawing','MAT','SOP','ข้อมูลฝ่ายขาย','Sales info'} and not wo_page: continue
    if path.name.startswith('P280') and title not in {'ทะเบียนแบบ','MAT','ใบorder','GROUPING'} and not wo_page: continue
    if path.name.startswith('SOP10') and title not in {'KeyItem (2)','สรุป','S&OP2026','WIP150926','ข้อมูลฝ่ายขาย'}: continue
    if path.name.startswith(('Plan 2026','Plan-2026')) and title not in {'แผนการเผา','เตรียมจ่าย','ผสมจ่าย','ขึ้นรูปจ่าย','เจียร','PACK','เข้าเผา','ตารางเตา','กำหนดส่งมอบขาย','สรุปสถานะใบสั่งผลิต'}: continue
    if path.name.startswith(('Stock on hand','Stock-on-Hand')) and title not in {'Abrasive','STAbrasiveสรุปคงคลัง','รับเข้าABRASIVE'}: continue
    if path.name.startswith(('1.เดือน','2.เดือน','3.เดือน','4.เดือน','5.เดือน','6.เดือน')) and title not in {'Cover','แผนเข้าคลัง','แผนการเผา','S_T','PB','R','P','M'}: continue
    plan_master=path.name.startswith(('Plan 2026','Plan-2026')) and title=='แผนการเผา'
    maxc=min(ws.max_column or 1,240 if plan_master else 72)
    plan_keep={colnum(c) for c in ['CY','DH','DR','EC','EL','FB','FC','IA','HH','HI','HJ','HK','HL','HM','HN','HO','HP','HQ','HR','HS','HT','HU','HV','HW','HX']} if plan_master else set()
    prev=[]; prev_count=0
    for ridx,row in enumerate(ws.iter_rows(min_col=1,max_col=maxc,values_only=True),1):
     if ridx>20000: break
     vals=[clean(v) for v in row]
     if not any(vals):continue
     # infer a nearby header row for row-wise explanatory display
     _header_score=sum(1 for x in vals if isinstance(x,str) and any(ch.isalpha() for ch in x) and len(x.strip())<120)
     if path.name.startswith('MRP BOND') and title=='281125':
      if ridx==3:prev=vals;prev_count=_header_score
     elif ridx<=8 and _header_score>prev_count:
      prev=vals;prev_count=_header_score
     fields={}
     for ix,v in enumerate(vals):
      if not v:continue
      if len(fields)>=28 and ix not in plan_keep:continue
      key=(prev[ix] if ix<len(prev) and prev[ix] else f'Column {ix+1}')
      if plan_master and ix in plan_keep:key=f'Plan field {key} ({ix+1})'
      fields[str(key)[:70]]=str(v)[:300]
     body=' | '.join(f'{k}: {v}' for k,v in fields.items())[:5000 if plan_master else 1800]
     if len(body)<3:continue
     cat='planning reference'
     low=(path.name+' '+ws.title+' '+body[:2000]).lower()
     for key,label in [('bond','Bond / material'),('mrp','Bond / material'),('cover','Work order / S&OP'),('sop','Sales / S&OP'),('rp-','RP / request'),('plan','Plan / schedule'),('stock','Stock'),('cap','Capacity'),('test','Test / engineering'),('สรุปทบทวน','Test / engineering'),('kpi','KPI'),('daily','Daily status')]:
      if key in low:cat=label;break
     bad='#N/A' in ' '.join(str(v) for v in row) or '#REF!' in ' '.join(str(v) for v in row)
     quality='incomplete / formula error' if bad else ('blue-sheet WO page; verify release/status/date' if wo_page else 'template or blank-status possible' if len(fields)<4 else 'source row; verify release status')
     norm=re.sub(r'[^A-Z0-9ก-๙]+','',body.upper())
     con.execute('INSERT INTO records(source_id,sheet,row_number,category,quality,header_row,body,normalized,fields_json) VALUES(?,?,?,?,?,?,?,?,?)',(sid,ws.title,ridx,cat,quality,ridx if prev else None,body,norm,json.dumps(fields,ensure_ascii=False,default=str)))
     total+=1
   wb.close(); con.commit(); print(f'INDEXED {path.name}: {path.stat().st_size:,} bytes sha256={sha[:12]}')
  except Exception as e: print(f'SKIPPED {path.name}: {e}')
 # Searching the compact normalized column avoids loading source workbooks in the UI.
 # Explicit user-taught pilot reference: retained as dated evidence, with conflicts flagged.
 taught_at=datetime.datetime(2026,9,29, tzinfo=TZ).isoformat(timespec='seconds')
 taught={
  'Project':'Q26-009 · Nordencent (America) · Test 2 · replacement production',
  'Document date':'2026-09-29 (date stated in source note)',
  'Requested part/spec':'38A400P7VB0400 · 80×25×7 mm',
  'Requested quantity':'300 PCs',
  'Technical reference':'Production work order P005-110826; material WA400; Bond B04; machine H10; method STD; skilled operator required',
  'Packaging':'Outer box code สบจ0042; 600 small pieces/box; 10 pieces/wrap; unbranded; one large piece cuts into 14 small pieces',
  'Packing quantity note':'Source note also says 400 PCs packed to warehouse in one box (box not specified). Conflicts with 300 PCs request; planner/customer must confirm quantity and packaging basis.',
  'Process control':'Mix on M3/1: sand + colour 30 min; Bonding + D3 powder 60 min; spray specified water and mix 60 min; check moisture/consistency before removing; sieve #40. R&D and Production manager jointly control grinding/moisture because excess moisture was linked to cracks after thickness adjustment.',
  'Schedule':'WO 2026-10-01; preparation 2026-10-05; mixing 2026-10-06; drying finishes 2026-10-10 after four days; kiln firing Program 2 starts 2026-10-13 and finishes 2026-10-20; cutting finishes 2026-10-27; packing finishes 2026-10-28.',
  'Unscheduled step':'H10 pressing is a required process but no date/duration is stated in the supplied schedule. Do not invent its booking.',
  'Schedule review flags':'Keep firing pre-check before kiln loading. Confirm cooling and six-day cutting interpretation against the detailed Gantt, because the supplied milestone dates alone do not define overlap/durations.',
  'Source':'User-provided Q26-009 review and planning instructions in this conversation; date 2026-09-29. No independent original workbook path was included in this session.'
 }
 source_text=json.dumps(taught,ensure_ascii=False,sort_keys=True)
 source_sha=hashlib.sha256(source_text.encode('utf-8')).hexdigest()
 cur=con.execute('INSERT INTO sources(filename,path,size_bytes,sha256,filesystem_modified,workbook_modified,snapshot_time) VALUES(?,?,?,?,?,?,?)',('USER_TAUGHT_Q26-009_PROCESS_PLAN_2026-09-29_CONVERSATION_NOTE','User-provided conversation note; no physical uploaded-file path',0,source_sha,taught_at,'not applicable',SNAPSHOT));sid=cur.lastrowid
 for n,(key,value) in enumerate(taught.items(),1):
  row_fields={'Project reference':'Q26-009','Field':key,'Recorded value':value,'Teaching/source date':'2026-09-29'}
  body=' | '.join(f'{k}: {v}' for k,v in row_fields.items())
  norm=re.sub(r'[^A-Z0-9ก-๙]+','',body.upper())
  con.execute('INSERT INTO records(source_id,sheet,row_number,category,quality,header_row,body,normalized,fields_json) VALUES(?,?,?,?,?,?,?,?,?)',(sid,'Q26-009 project reference',n,'User-taught process reference','user-stated reference; review highlighted quantity/schedule conflicts',1,body,norm,json.dumps(row_fields,ensure_ascii=False)))
  total+=1
 con.execute('CREATE TABLE snapshot_info(key TEXT PRIMARY KEY,value TEXT)');con.executemany('INSERT INTO snapshot_info VALUES(?,?)',[('snapshot_time',SNAPSHOT),('record_count',str(total)),('source_folder',str(SRC.resolve()))]);con.commit()
 con.execute('PRAGMA wal_checkpoint(TRUNCATE)');con.execute('PRAGMA journal_mode=DELETE');con.close()
 TMP.replace(OUT)
 print(f'CREATED {OUT} with {total:,} searchable evidence rows from {len(files)} files')
if __name__=='__main__':main()

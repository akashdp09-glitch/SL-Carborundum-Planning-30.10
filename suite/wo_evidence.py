"""Indexed source-specific production evidence for a confirmed WO, not KPI data."""
import json,sqlite3
from pathlib import Path


def production_rows(path,wo):
    if not Path(path).exists():return {'source':None,'rows':[]}
    from .production_evidence import key
    with sqlite3.connect(path,timeout=20) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='evidence_documents'").fetchone():return {'source':None,'rows':[]}
        row=con.execute("SELECT id,filename,revision,imported_at FROM evidence_documents WHERE role='production_status' ORDER BY revision DESC,id DESC LIMIT 1").fetchone()
        if not row:return {'source':None,'rows':[]}
        con.execute("CREATE INDEX IF NOT EXISTS ix_production_wo ON production_evidence_rows(source_id,json_extract(data,'$.wo_key'))")
        data=[json.loads(r[0]) for r in con.execute("SELECT data FROM production_evidence_rows WHERE source_id=? AND json_extract(data,'$.wo_key')=? ORDER BY sheet,excel_row",(row[0],key(wo)))]
    records=[]
    for r in data:
        records.append({k:r.get(k) for k in ['section','basis','sheet','excel_row','date','quantity','weight_tonnes','valid','issues']})
    return {'source':{'filename':row[1],'revision':row[2],'imported_at':row[3]},'rows':records}

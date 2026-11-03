"""Resolve one current Production WIP workbook per section, keeping old copies traceable."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import re

SECTIONS=['Preparation','Mixing','Forming','Firing + curing','Grinding / Cutting (Production combined)','Packing']
_MONTHS={
    'january':1,'jan':1,'มกราคม':1,'february':2,'feb':2,'กุมภาพันธ์':2,
    'march':3,'mar':3,'มีนาคม':3,'april':4,'apr':4,'เมษายน':4,
    'may':5,'พฤษภาคม':5,'june':6,'jun':6,'มิถุนายน':6,
    'july':7,'jul':7,'กรกฎาคม':7,'august':8,'aug':8,'สิงหาคม':8,
    'september':9,'sept':9,'sep':9,'กันยายน':9,'october':10,'oct':10,'ตุลาคม':10,
    'november':11,'nov':11,'พฤศจิกายน':11,'december':12,'dec':12,'ธันวาคม':12,
}
_CANONICAL={
    'Preparation':'Preparation__LATEST','Mixing':'Mixing__LATEST','Forming':'Forming__LATEST',
    'Firing + curing':'Firing_Curing__LATEST','Grinding / Cutting (Production combined)':'Grinding_Cutting__LATEST',
    'Packing':'Packing__LATEST',
}

def infer_section(name):
    text=str(name).lower()
    for section,words in [('Preparation',['preparation','เตรียม']),('Mixing',['mixing','ผสม']),('Forming',['forming','ขึ้นรูป']),('Firing + curing',['firing','เผา','curing','kiln','เตา']),('Grinding / Cutting (Production combined)',['grinding','cutting','เจียร','ตัด']),('Packing',['packing','บรรจุ'])]:
        if any(w in text for w in words):return section
    return ''

def period_key(name, current_year=None):
    """Return (year, month) from Thai/English month names or an ISO/compact date."""
    text=str(name).lower()
    year=None
    for m in re.finditer(r'(?<!\d)(20\d{2}|25\d{2})(?!\d)',text):
        y=int(m.group(1));year=y-543 if y>2400 else y
    date_match=re.search(r'(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)',text)
    if date_match:return (int(date_match.group(1)),int(date_match.group(2)))
    for word,month in _MONTHS.items():
        if word in text:
            if year is None:
                year=current_year or datetime.now(ZoneInfo('Asia/Bangkok')).year
            return (year,month)
    return (0,0)

def filename_for_section(section, suffix='.xlsx'):
    """Stable current filename; Source Manager and app imports retain revisions separately."""
    if section not in _CANONICAL:return ''
    ext='.xlsm' if str(suffix).lower().endswith('.xlsm') else '.xlsx'
    return _CANONICAL[section]+ext

def root_for(base_dir):
    return Path(os.environ.get('SL_SHARED_ROOT',str(Path(base_dir).resolve().parents[1]/'CENTRAL_DATA'))).resolve()

def _uploaded_sort_key(path,record):
    original=record.get('original_name') or record.get('original_filename') or path.name
    period=period_key(original)
    stamp=record.get('registered_at') or record.get('imported_at') or record.get('uploaded_at') or record.get('stored_file_modified_at') or ''
    try: stamp_key=datetime.fromisoformat(str(stamp).replace('Z','+00:00')).timestamp()
    except Exception: stamp_key=path.stat().st_mtime if path.exists() else 0
    if not stamp_key and path.exists():stamp_key=path.stat().st_mtime
    return (period[0],period[1],stamp_key,path.name.casefold())

def candidates(base_dir):
    """Map section to ranked source paths and return path provenance plus diagnostics."""
    root=root_for(base_dir);folder=root/'PRODUCTION_WIP';metadata={};diagnostics=[]
    for file in [root/'source_registry.json',folder/'source_registry.json']:
        try:
            doc=json.loads(file.read_text(encoding='utf-8'))
            entries=doc.get('records',[]) if 'records' in doc else list(doc.values())
            for record in entries:
                if not isinstance(record,dict):continue
                path=record.get('active_path') or record.get('stored_path')
                if path:metadata[str(Path(path).resolve())]=record
        except FileNotFoundError:pass
        except Exception as ex:diagnostics.append(f'Source registry unreadable: {ex}')
    grouped={}
    if folder.exists():
        for path in folder.iterdir():
            if not path.is_file() or path.suffix.lower() not in {'.xlsx','.xlsm'} or path.name.startswith('~$'):continue
            record=metadata.get(str(path.resolve()),{})
            if record.get('wip_active') is False or record.get('active') is False:continue
            section=record.get('production_section') or record.get('section')
            if section not in SECTIONS:section=infer_section(record.get('original_name') or record.get('original_filename') or path.name)
            if not section:diagnostics.append(f'{path.name}: section unassigned; assign it on Home.');continue
            grouped.setdefault(section,[]).append(path)
    ranked={}
    for section,paths in grouped.items():
        ranked[section]=sorted(paths,key=lambda p:_uploaded_sort_key(p,metadata.get(str(p.resolve()),{})),reverse=True)
        if len(paths)>1:
            selected=ranked[section][0]
            older=', '.join(p.name for p in ranked[section][1:])
            diagnostics.append(f'{section}: selected latest report/revision {selected.name}; prior copies remain retained and were not combined: {older}')
    return ranked,metadata,diagnostics

def discover(base_dir):
    ranked,metadata,diagnostics=candidates(base_dir)
    return {section:paths[0] for section,paths in ranked.items() if paths},metadata,diagnostics

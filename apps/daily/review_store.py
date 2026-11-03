"""Local atomic review persistence; never writes source workbooks."""
from pathlib import Path
import json, os, tempfile

def load(base):
    p=Path(base)/'USER_REVIEWS'/'wip_review.json'
    if not p.exists():return {}
    data=json.loads(p.read_text(encoding='utf-8'))
    if data.get('schema')!=1:raise ValueError('Unsupported review schema; preserve file and inspect')
    return data

def save(base,notes,audit):
    directory=Path(base)/'USER_REVIEWS';directory.mkdir(exist_ok=True)
    data={'schema':1,'notes':notes,'audit':audit}
    fd,name=tempfile.mkstemp(prefix='review_',suffix='.tmp',dir=directory)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2,default=str);f.flush();os.fsync(f.fileno())
        os.replace(name,directory/'wip_review.json')
    finally:
        if Path(name).exists():Path(name).unlink()

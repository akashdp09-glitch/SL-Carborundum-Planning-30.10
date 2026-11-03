import sqlite3
from pathlib import Path
from suite.storage_migration import migrate_legacy_database,restore_missing_photo_files

def _db(path,rows=()):
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE mobile_audits(id INTEGER PRIMARY KEY,wo_id TEXT,user_name TEXT,created_at TEXT,physical_status TEXT,physical_location TEXT,verified_qty REAL,notes TEXT)')
        c.execute('CREATE TABLE mobile_audit_photos(id INTEGER PRIMARY KEY,audit_id INTEGER,filename TEXT,original_name TEXT,content_type TEXT,created_at TEXT)')
        for item in rows:
            cur=c.execute('INSERT INTO mobile_audits(wo_id,user_name,created_at,physical_status,physical_location,verified_qty,notes) VALUES(?,?,?,?,?,?,?)',item)
            c.execute('INSERT INTO mobile_audit_photos(audit_id,filename,created_at) VALUES(?,?,?)',(cur.lastrowid,'AUDIT_1.jpg','2026-10-06'))

def test_additive_audit_merge_and_photo_copy(tmp_path):
    source=tmp_path/'old.db';target=tmp_path/'new.db';oldphotos=tmp_path/'oldphotos';oldphotos.mkdir()
    _db(source,[('WO-1','operator','2026-10-01T08:00','OK','Mixing',3,'old')])
    _db(target,[('WO-2','operator','2026-10-02T08:00','SHORT','Firing',2,'new')])
    (oldphotos/'AUDIT_1.jpg').write_bytes(b'jpeg-test')
    status=migrate_legacy_database(target,[source])
    assert status['state']=='AUDIT_HISTORY_MERGED' and status['audits_added']==1
    with sqlite3.connect(target) as c: assert c.execute('SELECT COUNT(*) FROM mobile_audits').fetchone()[0]==2
    restored=restore_missing_photo_files(target,tmp_path/'activephotos',[oldphotos])
    assert restored['copied']>=1 and (tmp_path/'activephotos'/'MOBILE_AUDITS'/'AUDIT_1.jpg').read_bytes()==b'jpeg-test'
    assert (oldphotos/'AUDIT_1.jpg').exists()

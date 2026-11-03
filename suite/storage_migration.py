"""Safe, one-time recovery of the former shared SQLite DB and audit photos.

RC23 kept sl_planning.db on mapped Z: while photos were on the host PC's D: drive;
RC24/25 used D: for the active copy. RC26 returns the active root to the requested
Z: share. It merges only missing audit history when both databases have data, and
copies referenced photos; it never replaces a database or deletes source photos.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path


def _tables(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def _row_count(con, table):
    try:
        return int(con.execute(f' SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except sqlite3.Error:
        return 0


def _has_real_records(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5) as con:
            tables = _tables(con)
            return any(_row_count(con, t) for t in tables - {"users", "schema_migrations", "legacy_db_migrations"})
    except sqlite3.Error:
        # An unreadable non-empty target must be treated as valuable, never replaced.
        return path.stat().st_size > 0


def _backup_database(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30) as src:
        with sqlite3.connect(str(destination), timeout=30) as dst:
            src.backup(dst, pages=256, sleep=0.05)
            result = dst.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError("database integrity check failed after backup")


def _merge_legacy_audit_history(source: Path, target: Path):
    """Append missing old audit observations/photos without replacing new data."""
    imported_audits = imported_photos = 0
    with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30) as src, sqlite3.connect(str(target), timeout=30) as dst:
        src.row_factory = dst.row_factory = sqlite3.Row
        src_tables, dst_tables = _tables(src), _tables(dst)
        if "mobile_audits" not in src_tables:
            return 0, 0
        dst.execute("""CREATE TABLE IF NOT EXISTS mobile_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT, wo_id TEXT NOT NULL, user_name TEXT NOT NULL,
            verified_qty REAL, physical_status TEXT NOT NULL DEFAULT 'OK', physical_location TEXT,
            observed_process TEXT, notes TEXT, created_at TEXT NOT NULL)""")
        dst.execute("""CREATE TABLE IF NOT EXISTS mobile_audit_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, audit_id INTEGER NOT NULL, filename TEXT NOT NULL,
            original_name TEXT, content_type TEXT, created_at TEXT NOT NULL)""")
        dst_tables = _tables(dst)

        def ensure_compatible(table):
            old_info = src.execute(f'PRAGMA table_info("{table}")').fetchall()
            new_cols = {r[1] for r in dst.execute(f'PRAGMA table_info("{table}")')}
            for col in old_info:
                name, kind = col[1], col[2] or 'TEXT'
                if name not in new_cols and name.lower() != 'id':
                    dst.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {kind}')
            return [r[1] for r in dst.execute(f'PRAGMA table_info("{table}")')]

        audit_cols = ensure_compatible("mobile_audits")
        photo_cols = ensure_compatible("mobile_audit_photos")
        old_audits = src.execute("SELECT * FROM mobile_audits ORDER BY id").fetchall()
        existing = dst.execute("SELECT * FROM mobile_audits ORDER BY id").fetchall()
        by_submission, by_fingerprint = {}, {}
        def fingerprint(row):
            return tuple(str(row[k] or '') for k in ('wo_id','user_name','created_at','physical_status','physical_location','verified_qty','notes'))
        for row in existing:
            d = dict(row)
            sid = d.get('client_submission_id')
            if sid: by_submission[str(sid)] = int(d['id'])
            by_fingerprint[fingerprint(d)] = int(d['id'])
        id_map = {}
        for row in old_audits:
            d = dict(row); sid = d.get('client_submission_id')
            matched = by_submission.get(str(sid)) if sid else None
            matched = matched or by_fingerprint.get(fingerprint(d))
            if matched:
                id_map[int(d['id'])] = matched
                continue
            values = {k:v for k,v in d.items() if k in audit_cols and k != 'id'}
            cols = list(values)
            cur = dst.execute(f'INSERT INTO mobile_audits ({",".join(chr(34)+c+chr(34) for c in cols)}) VALUES ({",".join("?" for _ in cols)})', [values[c] for c in cols])
            new_id = int(cur.lastrowid); id_map[int(d['id'])] = new_id
            values['id'] = new_id
            if sid: by_submission[str(sid)] = new_id
            by_fingerprint[fingerprint(values)] = new_id
            imported_audits += 1

        if "mobile_audit_photos" in src_tables:
            old_photos = src.execute("SELECT * FROM mobile_audit_photos ORDER BY id").fetchall()
            for row in old_photos:
                d = dict(row); aid = id_map.get(int(d.get('audit_id') or 0))
                if not aid: continue
                filename = Path(str(d.get('filename') or '')).name
                exists = dst.execute("SELECT 1 FROM mobile_audit_photos WHERE audit_id=? AND filename=? LIMIT 1",(aid,filename)).fetchone()
                if exists: continue
                values = {k:v for k,v in d.items() if k in photo_cols and k not in {'id','audit_id'}}
                cols = ['audit_id', *values]
                vals = [aid, *[values[c] for c in values]]
                dst.execute(f'INSERT INTO mobile_audit_photos ({",".join(chr(34)+c+chr(34) for c in cols)}) VALUES ({",".join("?" for _ in cols)})', vals)
                imported_photos += 1
        dst.commit()
    return imported_audits, imported_photos


def migrate_legacy_database(target, legacy_paths=()):
    """Return status and provenance; preserve both databases on ambiguity."""
    target = Path(target).resolve()
    candidates = []
    for value in legacy_paths:
        if value:
            p = Path(value)
            try:
                p = p.resolve()
            except OSError:
                pass
            if p != target and p not in candidates and p.is_file():
                candidates.append(p)
    if not candidates:
        return {"state": "NO_LEGACY_DB", "source": "", "target": str(target), "message": "No previous database found at configured legacy locations."}

    source = next((p for p in candidates if _has_real_records(p)), candidates[0])
    if target.exists():
        try:
            with sqlite3.connect(str(target), timeout=5) as con:
                tables = _tables(con)
                if "legacy_db_migrations" in tables:
                    meta = con.execute("SELECT source_path,source_size,source_mtime_ns FROM legacy_db_migrations ORDER BY id DESC LIMIT 1").fetchone()
                    stat = source.stat()
                    if meta and Path(meta[0]) == source and int(meta[1]) == stat.st_size and int(meta[2]) == stat.st_mtime_ns:
                        return {"state": "ALREADY_MIGRATED", "source": str(source), "target": str(target), "message": "Previous database has already been restored."}
        except (sqlite3.Error, OSError, ValueError):
            pass
    target_has_records = _has_real_records(target)
    source_has_records = _has_real_records(source)
    if target_has_records and source_has_records:
        try:
            audits, photos = _merge_legacy_audit_history(source, target)
            with sqlite3.connect(str(target), timeout=30) as con:
                con.execute("CREATE TABLE IF NOT EXISTS legacy_db_migrations (id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT NOT NULL, source_size INTEGER NOT NULL, source_mtime_ns INTEGER NOT NULL, migrated_at TEXT NOT NULL)")
                stat=source.stat()
                con.execute("INSERT INTO legacy_db_migrations(source_path,source_size,source_mtime_ns,migrated_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",(str(source),stat.st_size,stat.st_mtime_ns))
            return {"state":"AUDIT_HISTORY_MERGED","source":str(source),"target":str(target),"audits_added":audits,"photos_added":photos,"message":"Missing prior audit rows and photo references were appended; neither database was replaced."}
        except (sqlite3.Error, OSError, ValueError):
            pass
        return {"state": "CONFLICT", "source": str(source), "target": str(target), "message": "Both databases contain records; neither was overwritten."}
    if target_has_records:
        return {"state": "CURRENT_DB_HAS_DATA", "source": str(source), "target": str(target), "message": "The current database already contains records; no migration was needed."}
    if not source_has_records:
        return {"state": "LEGACY_DB_EMPTY", "source": str(source), "target": str(target), "message": "Previous database has no application records."}

    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = None
    if target.exists() and target.stat().st_size:
        backup = target.with_name(f"{target.stem}_pre_legacy_recovery_{stamp}{target.suffix}.bak")
        try:
            _backup_database(target, backup)
        except sqlite3.Error:
            shutil.copy2(target, backup)
    fd, temp_name = tempfile.mkstemp(prefix=".legacy_recovery_", suffix=".db", dir=str(target.parent))
    os.close(fd)
    temp = Path(temp_name)
    try:
        _backup_database(source, temp)
        with sqlite3.connect(str(temp), timeout=30) as con:
            con.execute("CREATE TABLE IF NOT EXISTS legacy_db_migrations (id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT NOT NULL, source_size INTEGER NOT NULL, source_mtime_ns INTEGER NOT NULL, migrated_at TEXT NOT NULL)")
            stat = source.stat()
            con.execute("INSERT INTO legacy_db_migrations(source_path,source_size,source_mtime_ns,migrated_at) VALUES(?,?,?,CURRENT_TIMESTAMP)", (str(source), stat.st_size, stat.st_mtime_ns))
            con.commit()
        os.replace(temp, target)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        return {"state":"MIGRATION_FAILED","source":str(source),"target":str(target),"message":f"Migration stopped safely; both source and target were retained: {exc}"}
    return {"state": "MIGRATED", "source": str(source), "target": str(target), "backup": str(backup) if backup else "", "message": "Previous database restored with SQLite backup; source left unchanged."}


def restore_missing_photo_files(db_path, target_photo_root, legacy_photo_roots=()):
    """Copy referenced missing photos into the active root; never move/delete."""
    db_path = Path(db_path)
    target_root = Path(target_photo_root)
    if not db_path.is_file():
        return {"copied": 0, "missing": 0}
    roots = [Path(p) for p in legacy_photo_roots if p]
    copied = missing = 0
    try:
        with sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=10) as con:
            tables = _tables(con)
            items = []
            if "mobile_audit_photos" in tables:
                items += [(target_root / "MOBILE_AUDITS", r[0]) for r in con.execute("SELECT filename FROM mobile_audit_photos WHERE filename IS NOT NULL")]
            if "unidentified_photos" in tables:
                items += [(target_root / "UNIDENTIFIED_PARTS", r[0]) for r in con.execute("SELECT filename FROM unidentified_photos WHERE filename IS NOT NULL")]
    except sqlite3.Error:
        return {"copied": 0, "missing": 0}
    for destination_dir, filename in items:
        name = Path(str(filename)).name
        dest = destination_dir / name
        if dest.is_file():
            continue
        candidates = []
        for root in roots:
            candidates.extend((root / name, root / destination_dir.name / name, root / "MOBILE_AUDITS" / name, root / "UNIDENTIFIED_PARTS" / name))
        src = next((p for p in candidates if p.is_file()), None)
        if src is None:
            missing += 1
            continue
        try:
            destination_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1
        except OSError:
            missing += 1
    return {"copied": copied, "missing": missing}


def default_legacy_paths(program_root):
    """Known prior RC23 and standalone mobile database locations."""
    root = Path(program_root)
    paths = [
        os.environ.get("SL_LEGACY_DB_PATH", ""),
        str(root / "shared_database" / "sl_planning.db"),
        str(root / "apps" / "mobile" / "data" / "sl_planning.db"),
    ]
    return [p for p in paths if p]


def default_legacy_photo_roots(program_root, active_photo_root):
    root = Path(program_root)
    active = Path(active_photo_root)
    return [
        active,
        os.environ.get("SL_LEGACY_PHOTO_ROOT", ""),
        root / "apps" / "mobile" / "data" / "photos",
        root / "apps" / "mobile" / "data",
        root / "shared_database" / "photos",
    ]

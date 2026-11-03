"""Content fingerprint for Daily Planner inputs.

The publish guard must refuse a dashboard built from two different source
snapshots. It must not treat a Windows last-write timestamp change (antivirus,
OneDrive, indexer) as a new workbook when the bytes are the same.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

META_ONLY_KEYS = frozenset({"modified_ns"})


def dataframe_fingerprint(value) -> str:
    if not isinstance(value, pd.DataFrame):
        return f"not-df:{value}"
    try:
        body = value.astype(str).to_csv(index=True)
    except Exception:  # noqa: BLE001
        body = value.to_csv(index=True)
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()


def file_record(path_value, cache=None, force_hash=False) -> dict:
    if not path_value:
        return {"path": "", "state": "NOT SET"}
    path = Path(path_value)
    try:
        stat = path.stat()
        resolved = str(path.resolve())
        token = (resolved, stat.st_size, stat.st_mtime_ns)
        cache = cache if cache is not None else {}
        cached = cache.get(resolved, {})
        if cached.get("token") == token and cached.get("sha256"):
            file_hash = cached["sha256"]
        else:
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            file_hash = digest.hexdigest()
            cache[resolved] = {"token": token, "sha256": file_hash}
        return {"path": resolved, "bytes": stat.st_size, "modified_ns": stat.st_mtime_ns, "sha256": file_hash}
    except Exception:  # noqa: BLE001
        return {"path": str(path), "state": "MISSING"}


def _content_inputs(inputs: dict) -> dict:
    out = {}
    for name, rec in (inputs or {}).items():
        if isinstance(rec, dict):
            out[name] = {k: v for k, v in rec.items() if k not in META_ONLY_KEYS}
        else:
            out[name] = rec
    return out


def content_digest(inputs: dict, params: dict) -> str:
    raw = json.dumps({"inputs": _content_inputs(inputs), "parameters": params}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def describe_changes(before_inputs: dict, before_params: dict, after_inputs: dict, after_params: dict) -> list[str]:
    changes = []
    names = sorted(set(before_inputs or {}) | set(after_inputs or {}))
    for name in names:
        before = before_inputs.get(name, {}) if isinstance(before_inputs.get(name), dict) else {"value": before_inputs.get(name)}
        after = after_inputs.get(name, {}) if isinstance((after_inputs or {}).get(name), dict) else {"value": (after_inputs or {}).get(name)}
        for key in ("path", "bytes", "sha256", "state", "value"):
            if before.get(key) != after.get(key) and (key in before or key in after):
                changes.append(f"{name}: {key} changed")
    bparams = before_params or {}
    aparams = after_params or {}
    for key in sorted(set(bparams) | set(aparams)):
        if bparams.get(key) != aparams.get(key):
            changes.append(f"control {key} changed")
    return changes

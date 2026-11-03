"""Small, session-local persistence helpers for navigating the single-window UI.

Submitted business records remain in their normal database/workbook stores. These
helpers keep unfinished scalar form values and data-editor drafts during page
navigation in the same browser session; they do not persist credentials or files.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib

import pandas as pd

_CACHE_KEY = "_sl_navigation_values_v1"
_EDITOR_KEY = "_sl_navigation_editor_drafts_v1"
_NEVER_KEEP = ("password", "passwd", "secret", "token", "ticket", "cookie", "auth")


def preserve_navigation_values(state) -> None:
    """Restore removed widget keys and snapshot safe scalar inputs on each rerun."""
    cache = state.get(_CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        state[_CACHE_KEY] = cache
    # Restore before this script constructs widgets. Streamlit clears widget keys
    # when a page is hidden; these manually-owned keys survive that cleanup.
    for key, value in list(cache.items()):
        if key not in state:
            state[key] = value
    # Snapshot only ordinary input values. Button state, passwords, auth tokens,
    # uploaded files, and large objects are intentionally excluded.
    for key, value in list(state.items()):
        name = str(key).lower()
        if key in (_CACHE_KEY, _EDITOR_KEY) or name.startswith("_"):
            continue
        if any(part in name for part in _NEVER_KEEP):
            continue
        if type(value) in (str, int, float) or isinstance(value, (date, datetime)):
            cache[key] = value


def dataframe_fingerprint(frame: pd.DataFrame) -> str:
    """Content signature used to discard a draft when its active source changes."""
    digest = hashlib.sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode("utf-8", "replace"))
    digest.update(str(tuple(frame.dtypes.astype(str))).encode())
    try:
        digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    except Exception:
        digest.update(frame.astype(str).to_csv(index=True).encode("utf-8", "replace"))
    return digest.hexdigest()


def restore_editor_draft(state, key: str, source: pd.DataFrame) -> pd.DataFrame | None:
    cache = state.get(_EDITOR_KEY)
    entry = cache.get(str(key)) if isinstance(cache, dict) else None
    if not isinstance(entry, dict) or entry.get("source") != dataframe_fingerprint(source):
        return None
    value = entry.get("value")
    if not isinstance(value, pd.DataFrame) or list(value.columns) != list(source.columns):
        return None
    return value.copy(deep=True)


def save_editor_draft(state, key: str, source: pd.DataFrame, edited: pd.DataFrame) -> None:
    if not isinstance(source, pd.DataFrame) or not isinstance(edited, pd.DataFrame):
        return
    cache = state.setdefault(_EDITOR_KEY, {})
    cache[str(key)] = {
        "source": dataframe_fingerprint(source),
        "value": edited.copy(deep=True),
    }

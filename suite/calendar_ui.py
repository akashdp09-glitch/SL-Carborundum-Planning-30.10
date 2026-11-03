"""Working-calendar inputs shared by the planning pages: Sunday is non-working (owner OD-6) and holidays are selected from a traceable saved list."""
from __future__ import annotations

import datetime as dt

import streamlit as st

from .user_settings import SettingsStore, KEY_HOLIDAYS, effective_holidays

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def store_for(shared_root) -> SettingsStore:
    from pathlib import Path
    return SettingsStore(Path(shared_root) / "DATA" / "user_settings.sqlite")


def calendar_inputs(store: SettingsStore, user: str, key: str):
    """Returns (non_working_weekday_indexes, holidays as dates). The saved holiday list is shared by all plans; every change is stored with user and reason."""
    c = st.columns(2)
    off = c[0].multiselect("Non-working weekdays", DAYS, default=["Sun"], key=f"{key}_off", help="Sunday is non-working (factory owner, 2026-10-04). Change only if the factory works that day.")
    saved = effective_holidays(store)
    labels = {h["date"]: f'{h["date"]}  {h.get("label", "")}'.strip() for h in saved}
    chosen = c[1].multiselect("Holidays / shutdown days applied to this plan", sorted(labels), default=sorted(labels), format_func=lambda d: labels[d], key=f"{key}_hol")
    with st.expander("Manage the saved holiday list (changes are recorded with user and reason)"):
        d = st.columns([1, 2, 2, 1])
        new_date = d[0].date_input("Date", dt.date.today(), key=f"{key}_hd")
        new_label = d[1].text_input("Holiday name", key=f"{key}_hl")
        reason = d[2].text_input("Reason / who asked", key=f"{key}_hr")
        if d[3].button("Add", key=f"{key}_hadd", disabled=not (reason.strip() and user)):
            rows = [h for h in saved if h["date"] != new_date.isoformat()] + [{"date": new_date.isoformat(), "label": new_label.strip()}]
            store.set(KEY_HOLIDAYS, sorted(rows, key=lambda h: h["date"]), user, reason)
            st.rerun()
        drop = st.multiselect("Remove from the saved list", sorted(labels), format_func=lambda x: labels[x], key=f"{key}_hdrop")
        if drop and st.button("Remove selected", key=f"{key}_hrem", disabled=not (reason.strip() and user)):
            store.set(KEY_HOLIDAYS, [h for h in saved if h["date"] not in drop], user, reason)
            st.rerun()
        if not user:
            st.caption("Sign in to change the list: every change needs a user name and a reason.")
        h = store.history(KEY_HOLIDAYS)
        if not h.empty:
            st.dataframe(h[["changed_at", "changed_by", "reason", "value_json"]], use_container_width=True, hide_index=True, height=160)
    return tuple(DAYS.index(x) for x in off), [dt.date.fromisoformat(x) for x in chosen]

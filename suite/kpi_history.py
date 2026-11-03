"""Combine revisioned monthly KPI workbook snapshots without losing prior months."""
from __future__ import annotations

import pandas as pd


def latest_monthly_revision(entries):
    """Return rows from the latest saved revision for each calendar month.

    ``entries`` is an iterable of dictionaries with ``data`` (Date/Group/Measure/Qty
    frame), ``revision``, ``source_file`` and ``imported_at``. Revisions of the same
    month replace that month as a snapshot; earlier months remain available.
    """
    frames=[]
    for item in entries or []:
        df=item.get('data')
        if not isinstance(df,pd.DataFrame) or df.empty:
            continue
        x=df.copy()
        required={'Date','Group','Measure','Qty'}
        if not required.issubset(x.columns):
            continue
        x['Date']=pd.to_datetime(x['Date'],errors='coerce')
        x['Qty']=pd.to_numeric(x['Qty'],errors='coerce')
        x=x.dropna(subset=['Date','Qty'])
        if x.empty:
            continue
        x['Revision']=int(item.get('revision') or 0)
        x['Imported at']=str(item.get('imported_at') or 'Not recorded')
        x['Source file']=str(item.get('source_file') or 'Source unavailable')
        x['_Month']=x['Date'].dt.to_period('M').astype(str)
        frames.append(x)
    if not frames:
        return pd.DataFrame(columns=['Date','Group','Measure','Qty','Revision','Imported at','Source file'])
    all_rows=pd.concat(frames,ignore_index=True)
    # Different Source Manager revisions may describe the same month. Pick the
    # newest revision that contains that month, then use its rows as the snapshot.
    month_revision=all_rows.groupby('_Month')['Revision'].transform('max')
    all_rows=all_rows[all_rows['Revision'].eq(month_revision)].copy()
    all_rows=all_rows.sort_values(['Revision','Imported at','Source file'])
    all_rows=all_rows.drop_duplicates(['Date','Group','Measure'],keep='last')
    return all_rows.drop(columns=['_Month']).sort_values(['Date','Group','Measure']).reset_index(drop=True)

from __future__ import annotations
import io, datetime as dt
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from .plan_reader import ORDER

HEAD = PatternFill('solid', fgColor='1F3864'); ALT = PatternFill('solid', fgColor='EEF3FA'); WARN = PatternFill('solid', fgColor='FDE9D9')
def _clean(df):
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == 'category': df[c] = df[c].astype(str)
    return df
def style(ws, df, title=None, warn_col=None):
    for c in ws[1]: c.font = Font(bold=True, color='FFFFFF'); c.fill = HEAD; c.alignment = Alignment(wrap_text=True, vertical='center')
    ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions; ws.row_dimensions[1].height = 30
    for j, col in enumerate(df.columns, 1):
        w = min(48, max(10, int(df[col].astype(str).str.len().quantile(.9)) + 2 if len(df) else 10, len(str(col)) + 2))
        ws.column_dimensions[get_column_letter(j)].width = w
    for i in range(2, ws.max_row + 1):
        if i % 2 == 0:
            for c in ws[i]: c.fill = ALT
    if warn_col and warn_col in df.columns:
        j = list(df.columns).index(warn_col) + 1
        for i in range(2, ws.max_row + 1):
            if str(ws.cell(i, j).value or '').strip():
                for c in ws[i]: c.fill = WARN

def to_workbook(sheets: dict, warn: dict | None = None) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl', datetime_format='yyyy-mm-dd', date_format='yyyy-mm-dd') as xw:
        for name, df in sheets.items():
            df = _clean(df); df.to_excel(xw, sheet_name=name[:31], index=False); style(xw.sheets[name[:31]], df, warn_col=(warn or {}).get(name))
    return bio.getvalue()

# Daily Status layout = columns of the software's Daily Status editor (Section, WO, Spec, Customer, Plan, Actual, Category, Plan Weight, Problem, Action).
# ASSUMPTION: the real section workbooks may differ - send a sample Daily Status file to match it exactly.
def daily_status_format(sec_df: pd.DataFrame, section: str, plan: pd.DataFrame) -> pd.DataFrame:
    w = plan.set_index('wo')
    out = pd.DataFrame({'Section': section, 'Plan Date': sec_df['plan_date'], 'WO': sec_df['wo'], 'Spec': sec_df['spec'], 'Customer': sec_df['customer'],
                        'Plan': sec_df['remaining_qty'], 'Actual': '', 'Category': [w.at[x, 'brand'] if x in w.index else '' for x in sec_df['wo']],
                        'Plan Weight': [round(float(w.at[x, 'piece_g']) * q / 1000, 2) if x in w.index else 0 for x, q in zip(sec_df['wo'], sec_df['remaining_qty'])],
                        'Due': sec_df['due'], 'Late': sec_df['late'], 'Problem': '', 'Action': ''})
    return out

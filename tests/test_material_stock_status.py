"""Regression checks for source-linked Stock-on-Hand material status."""
from io import BytesIO
import sys
import types
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / 'apps' / 'daily'
if str(DAILY) not in sys.path:
    sys.path.insert(0, str(DAILY))

try:
    import streamlit  # noqa: F401
except ModuleNotFoundError:
    # This parser test does not exercise UI; permit testing in a minimal Python environment.
    _st = types.ModuleType('streamlit')
    _st.cache_data = lambda *args, **kwargs: (lambda fn: fn) if args and callable(args[0]) else (lambda fn: fn)
    sys.modules['streamlit'] = _st
try:
    import plotly.express  # noqa: F401
except ModuleNotFoundError:
    # Stock parsing uses pandas/openpyxl; plotting imports are not used by this test.
    _plotly = types.ModuleType('plotly')
    _px = types.ModuleType('plotly.express')
    _plotly.express = _px
    sys.modules['plotly'] = _plotly
    sys.modules['plotly.express'] = _px

from sl_mps_mrp_engine_v2_4 import parse_stock


def make_stock_workbook():
    wb = Workbook()
    abrasive = wb.active
    abrasive.title = 'Abrasive'
    headers = [''] * 14
    for col, name in {
        0: 'รหัสสินค้า', 1: 'รายละเอียดสินค้า', 2: 'Group', 3: 'AbrasiveMainType',
        4: 'ใบงานเปิดผลิต', 5: 'วัตถุดิบคงคลัง', 6: 'รอวัถุดิบเข้า', 7: 'รอผลLAB',
        8: 'Move/Slow/Dead', 9: 'หมายเหตุ', 13: 'BalanceStock',
    }.items():
        headers[col] = name
    abrasive.append(headers)
    for code, order, physical, inbound, lab, balance in [
        ('MAT-SHORT', 1000, 100, 0, 0, -50),
        ('MAT-ZERO', 1000, 0, 0, 0, 0),
        ('MAT-WATCH', 1000, 100, 0, 0, 100),
        ('MAT-OK', 1000, 500, 0, 0, 500),
    ]:
        row = [''] * 14
        row[0], row[1], row[2], row[3] = code, f'{code} desc', 'G', 'Abrasive'
        row[4], row[5], row[6], row[7], row[13] = order, physical, inbound, lab, balance
        abrasive.append(row)
    for sheet, code in [('ทรายบด-ล้างR', 'MAT-R'), ('ทรายบด-ล้างSPB', 'MAT-SPB')]:
        ws = wb.create_sheet(sheet)
        ws.append(['รหัสใหม่', 'ชนิด', 'Orderonhand', 'คงเหลือ', 'BalanceStock'])
        ws.append([code, 'sand', 100, 100, 100])
    out = BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue()


def test_stock_status_is_source_linked_and_has_excel_row():
    data = parse_stock(make_stock_workbook())
    states = data.set_index('Material')['Stock Status'].to_dict()
    assert states['MAT-SHORT'] == 'SHORTAGE'
    assert states['MAT-ZERO'] == 'ZERO / URGENT'
    assert states['MAT-WATCH'] == 'WATCH'
    assert states['MAT-OK'] == 'OK'
    short = data[data['Material'] == 'MAT-SHORT'].iloc[0]
    assert short['Stock Source Sheet'] == 'Abrasive'
    assert short['Stock Source Row'] == 2
    assert short['Stock Source Column'] == 'N'
    assert short['Stock Source Unit'] == 'g'

import pandas as pd
from suite.kpi_history import latest_monthly_revision


def test_latest_revision_replaces_same_month_and_preserves_older_months():
    march=pd.DataFrame([
        {'Date':'2026-03-01','Group':'Forming','Measure':'Plan','Qty':100},
        {'Date':'2026-03-01','Group':'Forming','Measure':'Actual','Qty':80},
    ])
    march_revised=pd.DataFrame([
        {'Date':'2026-03-01','Group':'Forming','Measure':'Plan','Qty':110},
        {'Date':'2026-03-01','Group':'Forming','Measure':'Actual','Qty':90},
    ])
    april=pd.DataFrame([
        {'Date':'2026-04-01','Group':'Forming','Measure':'Plan','Qty':120},
        {'Date':'2026-04-01','Group':'Forming','Measure':'Actual','Qty':100},
    ])
    result=latest_monthly_revision([
        {'data':march,'revision':1,'source_file':'March.xlsx','imported_at':'2026-03-02'},
        {'data':march_revised,'revision':2,'source_file':'March_revised.xlsx','imported_at':'2026-03-05'},
        {'data':april,'revision':3,'source_file':'April.xlsx','imported_at':'2026-04-02'},
    ])
    assert len(result)==4
    assert result.loc[result['Date'].dt.month.eq(3),'Qty'].sum()==200
    assert result.loc[result['Date'].dt.month.eq(4),'Qty'].sum()==220
    assert set(result.loc[result['Date'].dt.month.eq(3),'Source file'])=={'March_revised.xlsx'}


def test_empty_or_malformed_revision_data_returns_empty_frame():
    result=latest_monthly_revision([{'data':pd.DataFrame({'wrong':[1]}),'revision':1}])
    assert result.empty

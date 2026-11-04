"""SYNTHETIC evidence only; never reads factory/shared data."""
import io
import json
import sqlite3
from datetime import date,datetime

import pandas as pd
import pytest
from openpyxl import Workbook

from suite.production_evidence import (aggregate, automatic_values, connect, department_results,
    import_workbook, production_frame, source_list, set_setting, settings)


def book_bytes(w):
    b=io.BytesIO();w.save(b);return b.getvalue()


def production_book(extra_plan=False):
    w=Workbook();s=w.active;s.title="สถานะผลิต"
    s.cell(4,1,"ProductionCode")
    for n,wo in enumerate(["SYNTHETIC-WO-A","SYNTHETIC-WO-B","SYNTHETIC-WO-C"],6):
        for col,value in {1:wo,6:"SYNTHETIC CUSTOMER",8:"SYNTHETIC SPEC",11:"SYNTHETIC PART",58:"P",60:100,61:10,62:20}.items():s.cell(n,col,value)
    s=w.create_sheet("Report Pack")
    s.cell(2,9,"P/PB");s.cell(2,14,"รวม")
    for n,wo in enumerate(["SYNTHETIC-WO-A","SYNTHETIC-WO-A","SYNTHETIC-WO-B"],3):
        for col,value in {1:1,2:10,3:2026,5:"SYNTHETIC operator "+str(n),8:"P",9:wo,14:10,16:20}.items():s.cell(n,col,value)
    if extra_plan:s.cell(6,1,1);s.cell(6,2,10);s.cell(6,3,2026);s.cell(6,9,"SYNTHETIC-WO-C");s.cell(6,14,10)
    s=w.create_sheet("Pack จ่าย")
    s.cell(2,4,"รหัสสินค้า");s.cell(2,10,"Q TY.")
    for n,wo in enumerate(["SYNTHETIC-WO-A","SYNTHETIC-WO-C"],3):
        for col,value in {1:2,2:10,3:2026,4:wo,7:"P",8:"SYNTHETIC CUSTOMER",10:10,12:20}.items():s.cell(n,col,value)
    s=w.create_sheet("Report ขึ้นรูป")
    s.cell(2,9,"รหัส");s.cell(2,21,"รวมชิ้น")
    for col,value in {1:1,2:10,3:2026,8:"P",9:"SYNTHETIC-WO-A",21:10,23:20000,24:2000}.items():s.cell(3,col,value)
    s=w.create_sheet("เตรียมจ่าย")
    s.cell(2,4,"รหัส");s.cell(2,10,"Q'TY")
    for col,value in {1:1,2:1,3:2069,4:"SYNTHETIC-WO-A",10:10,11:20}.items():s.cell(3,col,value)
    s=w.create_sheet("คนชั่ง");s.cell(2,8,"รหัส");s.cell(2,12,"จำนวนก้อน");s.cell(1,16383,"SYNTHETIC formatting extent")
    return book_bytes(w)


def test_persist_original_idempotency_and_revision_isolation(tmp_path):
    db=tmp_path/"SYNTHETIC.sqlite";data=production_book()
    one=import_workbook(db,data,"SYNTHETIC.xlsx","SYNTHETIC owner",config={"year":2026})
    repeated=import_workbook(db,data,"same-content-new-name.xlsx","SYNTHETIC owner",config={"year":2026,"month":"2026-10","unit":"work orders"})
    assert repeated["status"]=="UNCHANGED" and one["id"]==repeated["id"]
    with connect(db) as con:
        assert con.execute("SELECT original FROM evidence_documents").fetchone()[0]==data
        assert con.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    two=import_workbook(db,production_book(True),"SYNTHETIC revision.xlsx","SYNTHETIC owner")
    assert two["revision"]==2 and len(source_list(db))==2
    assert department_results(db,"2026-10").iloc[1].Denominator==3


def test_owner_rules_distinct_wo_and_final_packing_only(tmp_path):
    db=tmp_path/"SYNTHETIC.sqlite";import_workbook(db,production_book(),"SYNTHETIC.xlsx","SYNTHETIC owner")
    result=department_results(db,"2026-10")
    assert list(result.Maximum_marks)==[15,10,15]
    row=result.iloc[1]
    assert row.Numerator==2 and row.Denominator==2 and row.Achievement_percent==100
    assert "Matched planned/packed WOs 1" in row.Note
    # Two operator-plan rows for A cannot create a second planned WO, and
    # plan quantities cannot be added to the final handover as actual output.
    f=production_frame(db);actual=f[(f.sheet=="Pack จ่าย") & f.valid.eq(True)]
    assert actual.quantity.sum()==20 and len(actual)==2


def test_grams_tonnes_future_dates_dimensions_and_bounded_reads(tmp_path):
    db=tmp_path/"SYNTHETIC.sqlite";import_workbook(db,production_book(),"SYNTHETIC.xlsx","SYNTHETIC owner")
    f=production_frame(db)
    forming=f[f.sheet=="Report ขึ้นรูป"].iloc[0]
    assert forming.weight_raw==20000 and forming.weight_tonnes==pytest.approx(0.02)
    assert forming.piece_weight_raw==2000 and forming.piece_weight_tonnes==pytest.approx(.002)
    assert forming.basis=="Production plan" and forming.weight_unit=="g"
    assert tuple(forming[k] for k in ("D","T","H"))==(100,10,20)
    prep=f[f.sheet=="เตรียมจ่าย"].iloc[0]
    assert not prep.valid and any("Future" in x for x in prep.issues)
    assert len(f)<20  # Formatting extent never becomes 16k fake transaction columns/rows.


def test_daily_distinct_wo_counts_are_not_added_for_month():
    f=pd.DataFrame([dict(date=pd.Timestamp("2026-10-01"),wo="SYNTHETIC A",wo_key="A",quantity=10,weight_kg=20,weight_tonnes=.02),
                    dict(date=pd.Timestamp("2026-10-02"),wo="SYNTHETIC A",wo_key="A",quantity=5,weight_kg=None,weight_tonnes=None)])
    row=aggregate(f,["month"]).iloc[0]
    assert row.distinct_WOs==1 and row.pieces==15 and row.weight_tonnes==.02 and row.weight_known_rows==1


def counts_file(title,amount,close=False):
    w=Workbook();s=w.active;s.title="Close Job" if close else "Open Job"
    s.cell(1,3,title);s.cell(2,3,1);s.cell(3,2,"P");s.cell(3,3,amount)
    if not close:s.cell(3,35,amount)
    return book_bytes(w)


def test_separate_new_count_formats_auto_month_history_and_no_old_combined(tmp_path):
    db=tmp_path/"SYNTHETIC.sqlite"
    for data,name in [(counts_file("October Input",10),"opening.xlsx"),(counts_file("October Close",12,True),"closure.xlsx")]:
        import_workbook(db,data,name,"SYNTHETIC owner",config={"year":2026})
    row=department_results(db,"2026-10").iloc[2]
    assert row.Achievement_percent==120 and row.Numerator==12 and row.Denominator==10
    import_workbook(db,counts_file("November Input",20),"November opening.xlsx","SYNTHETIC owner",config={"year":2026})
    assert set(automatic_values(db).period)=={"2026-10","2026-11"}
    w=Workbook();w.active.title="Open Job";w.create_sheet("Close Job")
    with pytest.raises(ValueError,match="Retired combined"):
        import_workbook(db,book_bytes(w),"SYNTHETIC retired.xlsx","SYNTHETIC owner")


def test_analyst_percentage_is_derived_without_inventing_inspected_counts(tmp_path):
    w=Workbook();s=w.active;s.title="DATA KPI__daily";s.cell(6,12,datetime(2026,10,1))
    for col,v in [(12,1),(13,0),(14,.5)]:s.cell(8,col,v)
    db=tmp_path/"SYNTHETIC.sqlite";import_workbook(db,book_bytes(w),"SYNTHETIC analyst.xlsx","SYNTHETIC owner")
    row=department_results(db,"2026-10").iloc[0]
    assert row.Achievement_percent==50 and pd.isna(row.Numerator) and pd.isna(row.Denominator)


def test_setting_audit_requires_reason_and_preserves_history(tmp_path):
    db=tmp_path/"SYNTHETIC.sqlite"
    with pytest.raises(ValueError):set_setting(db,"forming_unit","g","","SYNTHETIC owner")
    set_setting(db,"forming_unit","g","SYNTHETIC owner confirmation","SYNTHETIC owner")
    assert settings(db)["forming_unit"]=="g"
    with connect(db) as con:assert con.execute("SELECT count(*) FROM evidence_setting_history").fetchone()[0]==1


def test_section_and_category_matrix_are_not_added_to_packing_actual(tmp_path):
    db=tmp_path/"SYNTHETIC.sqlite"
    for role,group in [("production_kpi_section","Packing"),("production_kpi_category","P")]:
        w=Workbook();s=w.active;s.title="SYNTHETIC KPI";s.cell(3,4,1)
        for r,typ,val in [(4,"แผน",10),(5,"ผลิตจริง",8)]:s.cell(r,2,group);s.cell(r,3,typ);s.cell(r,4,val)
        import_workbook(db,book_bytes(w),role+".xlsx","SYNTHETIC owner",role,{"month":"2026-10","unit":"work orders"})
    row=department_results(db,"2026-10").iloc[1]
    assert row.Achievement_percent==80 and row.Numerator==8 and row.Denominator==10


def test_changed_column_mapping_is_rejected_before_persisting_wrong_quantities(tmp_path):
    from openpyxl import load_workbook
    w=load_workbook(io.BytesIO(production_book()))
    w['Pack จ่าย'].cell(2,10,'Different meaning - not quantity')
    db=tmp_path/'SYNTHETIC.sqlite'
    with pytest.raises(ValueError,match='quantity header changed'):
        import_workbook(db,book_bytes(w),'SYNTHETIC changed format.xlsx','SYNTHETIC owner')
    assert source_list(db).empty


def test_monthly_department_snapshots_are_idempotent_and_keep_prior_calculation(tmp_path):
    from suite.production_evidence import department_history
    db=tmp_path/'SYNTHETIC.sqlite'
    import_workbook(db,production_book(),'SYNTHETIC.xlsx','SYNTHETIC owner')
    department_results(db,'2026-10');department_results(db,'2026-10')
    assert len(department_history(db))==3
    import_workbook(db,production_book(True),'SYNTHETIC changed.xlsx','SYNTHETIC owner')
    department_results(db,'2026-10')
    hist=department_history(db)
    assert len(hist)==6
    vals=hist[hist.Code.eq('KPI-PL-02')].Achievement_percent
    assert list(vals)==[pytest.approx(200/3),100]


def test_revised_column_format_production_kpi_is_supported(tmp_path):
    w=Workbook();s=w.active;s.title='SYNTHETIC new format'
    s.append(['Date','Section','Planned WOs','Packed WOs'])
    s.append([datetime(2026,10,1),'Packing',10,8]);s.append([datetime(2026,10,2),'Packing',20,12])
    s.append([datetime(2026,10,3),'Mixing',999,999])
    db=tmp_path/'SYNTHETIC.sqlite'
    imported=import_workbook(db,book_bytes(w),'SYNTHETIC revised KPI.xlsx','SYNTHETIC owner','auto',{'unit':'work orders'})
    assert imported['role']=='production_kpi_section'
    row=department_results(db,'2026-10').iloc[1]
    assert row.Numerator==20 and row.Denominator==30 and row.Achievement_percent==pytest.approx(200/3)


def test_offline_report_contains_real_tables_and_escapes_source_text(tmp_path):
    from suite.production_report import english_report
    db=tmp_path/'SYNTHETIC.sqlite';import_workbook(db,production_book(),'SYNTHETIC.xlsx','SYNTHETIC owner')
    frame=production_frame(db)
    frame.loc[frame.basis.eq('Output'),'customer']='SYNTHETIC <script>alert(1)</script>'
    html=english_report(frame,source_list(db),date(2026,10,1),date(2026,10,31)).decode()
    assert '100.00%' in html and 'Final actual packing' in html and 'metric tonnes' in html
    assert 'SYNTHETIC &lt;script&gt;' in html and '<script>alert(1)</script>' not in html
    assert '<script src=' not in html  # All charts work offline; no CDN script dependency.


def test_owner_confirmed_short_buddhist_year_is_fixed_without_rewriting_other_years():
    from suite.production_evidence import split_date
    assert split_date([2,10,69])==date(2026,10,2)
    assert split_date([2,10,2569])==date(2026,10,2)
    assert split_date([2,10,25])==date(2025,10,2)
    assert split_date([2,10,26])==date(2026,10,2)
    assert split_date([2,10,2069])==date(2069,10,2)
    assert split_date([2.5,10,2026]) is None


def test_revised_staff_workbook_updates_older_months_and_flags_monthly_daily_conflict(tmp_path):
    db=tmp_path/'SYNTHETIC.sqlite'
    def staff(anchor,august,current):
        w=Workbook();s=w.active;s.title='DATA KPI__daily';s.cell(6,12,anchor);s.cell(8,12,.5)
        m=w.create_sheet('KPI-PL-Chosita_Monthly');m.cell(8,27,august);m.cell(8,19+anchor.month,current)
        return book_bytes(w)
    import_workbook(db,staff(datetime(2026,10,1),.8,.5),'SYNTHETIC October.xlsx','SYNTHETIC owner')
    assert department_results(db,'2026-08').iloc[0].Achievement_percent==80
    import_workbook(db,staff(datetime(2026,11,1),.9,.7),'SYNTHETIC November.xlsx','SYNTHETIC owner')
    assert department_results(db,'2026-08').iloc[0].Achievement_percent==90
    november=department_results(db,'2026-11').iloc[0]
    assert pd.isna(november.Achievement_percent) and 'reconcile' in november.Note


def test_mistyped_staff_percentage_scale_cannot_create_a_5000_percent_accuracy(tmp_path):
    w=Workbook();s=w.active;s.title='DATA KPI__daily';s.cell(6,12,datetime(2026,10,1));s.cell(8,12,50)
    db=tmp_path/'SYNTHETIC.sqlite'
    with pytest.raises(ValueError,match='expected source ratios'):
        import_workbook(db,book_bytes(w),'SYNTHETIC wrong scale.xlsx','SYNTHETIC owner')
    assert source_list(db).empty

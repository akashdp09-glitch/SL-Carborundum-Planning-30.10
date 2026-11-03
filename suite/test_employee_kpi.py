from suite.employee_kpi import add_definition,add_measurement,definitions,measurements,retire_definition

def test_employee_kpi_weekly_evidence_and_retirement_preserve_history(tmp_path):
    db=tmp_path/'employee_kpi.sqlite'
    d=add_definition(db,'On-time planning updates','Planning Analyst',95,'%','Higher is better','Percentage (numerator ÷ denominator)','On-time status entries / eligible entries, sourced from daily register.','tester')
    saved=add_measurement(db,d['id'],'Weekly','2026-10-05','2026-10-11',19,20,'Daily register, 2026-10-11','reviewed','tester')
    assert saved['actual']==95.0
    report=measurements(db)
    assert len(report)==1 and report.iloc[0]['Result']=='MEETS TARGET' and report.iloc[0]['Period']=='Weekly'
    assert retire_definition(db,d['id'],'tester')
    assert definitions(db,active_only=False).iloc[0]['active']==0
    assert len(measurements(db))==1

def test_employee_kpi_rejects_missing_evidence_and_bad_ratio(tmp_path):
    db=tmp_path/'employee_kpi.sqlite'
    d=add_definition(db,'Scrap rate','Operator',1,'%','Lower is better','Percentage (numerator ÷ denominator)','Scrap pieces / total produced.','tester')
    try: add_measurement(db,d['id'],'Monthly','2026-10-01','2026-10-31',2,1,'source','', 'tester')
    except ValueError as e: assert 'cannot exceed' in str(e)
    else: raise AssertionError('bad percentage ratio was accepted')
    try: add_measurement(db,d['id'],'Monthly','2026-10-01','2026-10-31',0,10,'','', 'tester')
    except ValueError as e: assert 'Evidence' in str(e)
    else: raise AssertionError('missing evidence was accepted')

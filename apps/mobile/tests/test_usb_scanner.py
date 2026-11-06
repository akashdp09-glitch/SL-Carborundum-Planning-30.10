"""USB-HID request flow with synthetic work orders; no physical device claim."""
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor


def payload(**kw):
    return dict(wo_id='WO-TEST-0001',section='Mixing',status='CLOSED',actual_qty=12,
        remark='SYNTHETIC scanner test',client_submission_id='usb-'+uuid.uuid4().hex,**kw)


def test_usb_stable_code_lookup_is_indexed_and_never_reopens_excel(core,operator,monkeypatch):
    monkeypatch.setattr(core,'kick_shared_plan_sync',lambda **kw:None)
    monkeypatch.setattr(core,'load_workbook',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('Excel opened during scan')))
    for value in ['SLWO:WO-TEST-0001','wo test 0001','http://old-factory/q/WO-TEST-0001']:
        r=operator.get('/api/wo/'+__import__('urllib.parse',fromlist=['quote']).quote(value,safe=''))
        assert r.status_code==200,r.text
        assert r.json()['wo']['wo_id']=='WO-TEST-0001'
    from suite.scanner_lookup import NORMALIZED_SQL
    con=core.db()
    plan=con.execute('EXPLAIN QUERY PLAN SELECT wo_id FROM work_orders WHERE '+NORMALIZED_SQL.format('wo_id')+'=?',('WOTEST0001',)).fetchall()
    con.close()
    assert any('INDEX' in str(tuple(r)).upper() for r in plan)


def test_ambiguous_or_partial_label_never_selects_first_order(core,operator):
    assert operator.get('/api/wo/SYNTH-DUP').status_code==409
    assert core.resolve_work_order_code('SLWO:SYNTH-DUP') is None
    assert operator.get('/api/wo/WO-TEST-000').status_code==404
    assert core.resolve_work_order_code('WO-TEST-000') is None


def test_usb_section_status_retry_persists_one_row_with_actor_and_source(core,operator):
    p=payload(); a=operator.post('/api/section-status',json=p);b=operator.post('/api/section-status',json=p)
    assert a.status_code==b.status_code==200,(a.text,b.text)
    assert a.json()['event_id']==b.json()['event_id']==p['client_submission_id']
    from suite.floor_open_close import load_entries
    import os
    entries=load_entries(os.environ['SL_COMPANY_DATA'])
    row=entries[entries['Event ID'].eq(p['client_submission_id'])]
    assert len(row)==1
    assert row.iloc[0]['User']=='operator'
    assert row.iloc[0]['Source reference']
    h=operator.get('/api/section-history?wo_id=WO-TEST-0001').json()
    assert any(r['Event ID']==p['client_submission_id'] for r in h['rows'])
    changed=operator.post('/api/section-status',json={**p,'actual_qty':14})
    assert changed.status_code==400
    # A physical section closure must not become an overall WO closure/packed output.
    assert core.get_current_snapshot('WO-TEST-0001')['produced']==0


def test_unknown_invalid_quantity_and_missing_retry_id(operator):
    p=payload();p['actual_qty']=None
    assert operator.post('/api/section-status',json=p).status_code==200
    p=payload();p['actual_qty']=-3
    assert operator.post('/api/section-status',json=p).status_code==400
    p=payload();p.pop('client_submission_id')
    assert operator.post('/api/section-status',json=p).status_code==400


def test_section_accounts_use_shared_database_and_preselect_section(core):
    from fastapi.testclient import TestClient
    from suite.demo_accounts import find_user
    c=TestClient(core.app,follow_redirects=False)
    assert c.post('/login',data={'username':'mixing','password':'mixing123'}).status_code==303
    assert find_user(core.DB_PATH,'mixing')['role']=='production'
    text=c.get('/scan').text
    assert 'value="Mixing" selected' in text
    assert 'value="MIX-01" selected' in text
    assert c.get('/operator').headers['location']=='/scan'
    assert 'scan.js?v=62' in text


def test_parallel_status_retries_commit_once(core,operator):
    p=payload()
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies=list(pool.map(lambda _:operator.post('/api/section-status',json=p),range(4)))
    assert all(r.status_code==200 for r in replies),[r.text for r in replies]
    import os
    from suite.floor_open_close import load_entries
    rows=load_entries(os.environ['SL_COMPANY_DATA'])
    assert rows['Event ID'].eq(p['client_submission_id']).sum()==1


def test_production_events_are_idempotent_and_section_completion_is_not_packing(core,operator):
    con=core.db()
    con.execute("INSERT OR IGNORE INTO work_orders(wo_id,production_code,qty,status,imported_at) VALUES('SYNTH-EVENT-54','SYNTH-EVENT-54',10,'RELEASED','2026-11-05')")
    con.commit();con.close()
    p={'wo_id':'SYNTH-EVENT-54','event_type':'COMPLETE','terminal_code':'FORM-01','qty':10,'reason':'SYNTHETIC completed forming','client_submission_id':'event-'+uuid.uuid4().hex}
    a=operator.post('/api/scan',json=p);b=operator.post('/api/scan',json=p)
    assert a.status_code==b.status_code==200,(a.text,b.text)
    assert a.json()['event_id']==b.json()['event_id']
    snap=core.get_current_snapshot('SYNTH-EVENT-54')
    assert snap['produced']==0 and snap['status']=='SECTION_COMPLETE'
    assert operator.post('/api/scan',json={**p,'qty':9}).status_code==400
    p.update(terminal_code='PACK-01',client_submission_id='event-'+uuid.uuid4().hex)
    assert operator.post('/api/scan',json=p).status_code==200
    assert core.get_current_snapshot('SYNTH-EVENT-54')['produced']==10


def test_production_event_cannot_guess_completion_quantity_or_silently_hold(operator):
    p={'wo_id':'WO-TEST-0001','event_type':'COMPLETE','terminal_code':'MIX-01','qty':None,'client_submission_id':'event-'+uuid.uuid4().hex}
    assert operator.post('/api/scan',json=p).status_code==400
    p.update(event_type='HOLD')
    assert operator.post('/api/scan',json=p).status_code==400
    p.update(reason='SYNTHETIC material issue')
    assert operator.post('/api/scan',json=p).status_code==200


def test_whole_order_status_shared_report_and_section_are_independent(core,operator,management):
    import io
    from openpyxl import load_workbook
    p={'wo_id':'WO-TEST-0002','status':'CLOSED','remark':'SYNTHETIC authorized whole WO decision','client_submission_id':'whole-'+uuid.uuid4().hex}
    r=operator.post('/api/order-status',json=p);assert r.status_code==200,r.text
    retry=operator.post('/api/order-status',json=p);assert retry.json()['record_id']==r.json()['record_id']
    snap=core.get_current_snapshot('WO-TEST-0002');assert snap['whole_order_decision']['status']=='CLOSED' and snap['produced']==0
    h=management.get('/api/section-history?wo_id=WO-TEST-0002').json();assert any(x['Status']=='CLOSED' for x in h['whole_rows'])
    today=core.bkk_now().date().isoformat()
    report=management.get('/tracking-reports.xlsx',params={'start':today,'end':today});assert report.status_code==200,report.text[:100]
    book=load_workbook(io.BytesIO(report.content),read_only=True)
    assert {'WIP observations','Process open-close','Whole WO decisions','Production events','Basis'}<=set(book.sheetnames)
    assert book['Whole WO decisions'].max_row>=2;book.close()
    assert operator.post('/api/order-status',json={**p,'status':'OPEN'}).status_code==400
    assert operator.post('/api/order-status',json={**p,'client_submission_id':'whole-'+uuid.uuid4().hex,'remark':''}).status_code==400

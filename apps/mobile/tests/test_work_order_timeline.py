from datetime import date

from apps.mobile.work_order_timeline import build_process_timeline, completion_percent


def test_timeline_keeps_prior_and_future_plan_dates_separate_from_actuals():
    route = [
        {'seq': 1, 'process_name': 'Preparation', 'planned_date': '2026-10-08'},
        {'seq': 2, 'process_name': 'Mixing', 'planned_date': '2026-10-12'},
        {'seq': 3, 'process_name': 'Forming', 'planned_date': None},
    ]
    events = [{'process_name': 'Preparation', 'event_type': 'COMPLETE', 'event_time': '2026-10-08 15:00:00', 'qty': 40}]
    rows = build_process_timeline(route, events, date(2026, 10, 10))
    assert [row['state'] for row in rows] == ['ACTUAL COMPLETE', 'PLANNED', 'NO PLAN DATE']
    assert rows[0]['actual_complete'] == '2026-10-08 15:00:00'
    assert rows[1]['planned_date'] == '2026-10-12'


def test_completion_percent_requires_a_recorded_quantity_event():
    assert completion_percent(100, []) is None
    events = [
        {'event_type': 'START', 'qty': None},
        {'event_type': 'PARTIAL_COMPLETE', 'qty': 35, 'process_name':'Packing'},
    ]
    assert completion_percent(100, events) == 35.0
    assert completion_percent(0, events) is None


def test_partial_section_event_does_not_mark_route_or_whole_order_complete():
    route=[{'seq':1,'process_name':'Forming','planned_date':'2026-10-30'}]
    events=[{'process_name':'Forming','event_type':'PARTIAL_COMPLETE','qty':35,'event_time':'2026-10-30 09:00:00'}]
    assert completion_percent(100,events) is None
    row=build_process_timeline(route,events,date(2026,10,30))[0]
    assert row['state']=='ACTUAL PARTIAL' and row['actual_complete']==''

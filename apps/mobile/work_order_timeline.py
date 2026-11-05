"""Read-only comparison of planned route dates and recorded production events."""
from datetime import date
import math
import pandas as pd


def process_key(value):
    return ''.join(ch for ch in str(value or '').upper() if ch.isalnum())


def build_process_timeline(route, events, today: date):
    actual = {}
    for event in events:
        key = process_key(event['process_name'])
        if not key:
            continue
        row = actual.setdefault(key, {'actual_start': '', 'actual_complete': '', 'actual_partial': '', 'event_qty': None})
        if event['event_type'] in ('RECEIVE', 'START', 'RESUME', 'MOVE') and not row['actual_start']:
            row['actual_start'] = event['event_time'] or ''
        if event['event_type'] in ('PARTIAL_COMPLETE', 'COMPLETE'):
            if event['event_type']=='COMPLETE':row['actual_complete'] = event['event_time'] or row['actual_complete']
            else:row['actual_partial']=event['event_time'] or row['actual_partial']
            if event['qty'] is not None:
                row['event_qty'] = float(event['qty'])

    timeline = []
    for route_row in route:
        planned = route_row['planned_date'] or ''
        try:
            planned_day = date.fromisoformat(str(planned)[:10]) if planned else None
        except (TypeError, ValueError):
            planned_day = None
        ev = actual.get(process_key(route_row['process_name']), {})
        if ev.get('actual_complete'):
            state = 'ACTUAL COMPLETE'
        elif ev.get('actual_partial'):
            state = 'ACTUAL PARTIAL'
        elif ev.get('actual_start'):
            state = 'ACTUAL STARTED'
        elif planned_day and planned_day < today:
            state = 'PAST PLAN DATE — no event recorded'
        elif planned_day:
            state = 'PLANNED'
        else:
            state = 'NO PLAN DATE'
        timeline.append({'seq': route_row['seq'], 'process': route_row['process_name'] or '',
                         'planned_date': planned, 'state': state,
                         'actual_start': ev.get('actual_start', ''),
                         'actual_complete': ev.get('actual_complete', ''),
                         'event_qty': ev.get('event_qty')})
    return timeline


def completion_percent(order_qty, events):
    """Only calculate when a quantity-bearing completion event exists."""
    try:
        denominator = float(order_qty)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(denominator) or denominator <= 0:
        return None
    values = []
    for event in events:
        if process_key(dict(event).get('process_name')) not in {'PACKING','PACK','บรรจุ'}:
            continue
        if event['event_type'] not in ('PARTIAL_COMPLETE', 'COMPLETE') or event['qty'] is None:
            continue
        try:
            value = float(event['qty'])
            if math.isfinite(value):
                values.append(value)
        except (TypeError, ValueError):
            continue
    return max(values) / denominator * 100.0 if values else None

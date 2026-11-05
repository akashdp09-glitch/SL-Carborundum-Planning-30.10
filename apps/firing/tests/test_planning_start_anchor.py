from datetime import date
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ppc_fast_core_v4_6 as fc


def test_selected_planning_start_is_first_candidate_date():
    # 2026-10-30 is Friday and is included in the default Mon-Sat calendar.
    start = date(2026, 10, 30)
    assert start.weekday() == 4
    assert fc._business_days(start, start) == 1
    assert fc._business_days(start, date(2026,11,2)) == 3
    assert fc._business_days(start, date(2026,10,29)) == 0


def test_planning_start_not_shifted_to_next_day_by_upstream_feasibility_guard():
    source = Path(fc.__file__).read_text(encoding='utf-8')
    assert 'candidate_date < planning_start:' in source
    assert 'candidate_date < planning_start+timedelta(days=1)' not in source

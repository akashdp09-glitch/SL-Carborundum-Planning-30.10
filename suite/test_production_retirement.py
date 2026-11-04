from suite.source_manager import SourceManager,SLOTS


def test_obsolete_combined_and_nine_measure_uploads_are_no_longer_requested(tmp_path):
    manager=SourceManager(tmp_path/'SYNTHETIC shared',bundled_capacity=tmp_path/'absent.xlsx')
    for slot in ['KPI_PLANNING_REFERENCE','KPI_PLANNING_DAILY_EXECUTION','KPI_PLANNING_JOB_CLOSURE','KPI_EMPLOYEE_REFERENCE','SEPT_OPEN_CLOSED']:
        assert SLOTS[slot].knowledge_only
        assert slot not in manager.missing()
        result=manager.import_bytes(slot,'SYNTHETIC retired.xlsx',b'SYNTHETIC invalid bytes','SYNTHETIC owner')
        assert result.status=='REJECTED'
    assert 'KPI_SECTION_PLAN_VS_ACTUAL' in manager.missing()
    assert 'KPI_DELIVERY_WAREHOUSE' in manager.missing()

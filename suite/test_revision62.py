import ast,json,sqlite3
from pathlib import Path
from suite.daily_navigation import focus_labels
from suite.wo_evidence import production_rows
from suite.production_evidence import import_workbook
from suite.test_production_evidence import production_book


def test_actual_daily_options_and_named_mapping_survive_reorder():
    tree=ast.parse(Path('apps/daily/daily_planner_app.py').read_text())
    nodes=[n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_quick_options' for t in n.targets)]
    options=ast.literal_eval(nodes[0].value)
    for n in ast.walk(tree):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='_quick_options' and n.func.attr=='append':options.append(ast.literal_eval(n.args[0]))
    a=focus_labels(options);b=focus_labels(list(reversed(options)))
    assert a==b and a['capacity_actual'].startswith('⚖️ Capacity') and a['capacity'].startswith('🏭 All-section')
    assert all(label in options for label in a.values()) and a['section'].startswith('📅 Daily plan')
    assert '_quick_options[10]' not in Path('apps/daily/daily_planner_app.py').read_text()


def test_production_lookup_is_indexed_source_specific_and_original_unchanged(tmp_path):
    db=tmp_path/'SYNTHETIC.sqlite';original=production_book()
    import_workbook(db,original,'SYNTHETIC production.xlsx','SYNTHETIC')
    result=production_rows(db,'synthetic wo a')
    assert result['source']['filename']=='SYNTHETIC production.xlsx'
    assert result['rows'] and any(r['sheet']=='Pack จ่าย' for r in result['rows'])
    assert all('raw' not in r for r in result['rows'])
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT original FROM evidence_documents').fetchone()[0]==original
        plan=c.execute("EXPLAIN QUERY PLAN SELECT data FROM production_evidence_rows WHERE source_id=? AND json_extract(data,'$.wo_key')=?",(1,'SYNTHETICWOA')).fetchall()
        assert any('ix_production_wo' in str(r) for r in plan)
    assert production_rows(db,'SYNTHETIC missing')['rows']==[]

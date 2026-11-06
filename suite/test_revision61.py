import sqlite3,json
from pathlib import Path
import pandas as pd
import pytest
from suite.demo_accounts import seed_users,check_password
from suite.account_admin import change
from suite.build_info import text
from suite.recovery_workspace import html_dashboard,with_weights
from suite import recovery_workspace as R


def test_admin_account_lifecycle_and_last_admin_history(tmp_path):
    db=tmp_path/'SYNTHETIC.db';seed_users(db)
    with pytest.raises(ValueError):change(db,'operator','Create','SYNTHETIC','pass')
    change(db,'admin','Create','SYNTHETIC','secret','production','SYNTHETIC person')
    change(db,'admin','Reset password','SYNTHETIC','updated')
    change(db,'admin','Remove / deactivate','SYNTHETIC')
    with sqlite3.connect(db) as c:
        row=c.execute("SELECT active,password_hash FROM users WHERE username='SYNTHETIC'").fetchone()
        assert row[0]==0 and check_password('updated',row[1])
        assert c.execute('SELECT COUNT(*) FROM account_admin_history').fetchone()[0]==3
    with pytest.raises(ValueError):change(db,'admin','Remove / deactivate','admin')
    change(db,'admin','Reactivate','SYNTHETIC')
    with sqlite3.connect(db) as c:assert c.execute("SELECT active FROM users WHERE username='SYNTHETIC'").fetchone()[0]==1


def test_build_identity_and_recovery_html_pending(tmp_path):
    (tmp_path/'VERSION').write_text('RC29.61')
    (tmp_path/'RELEASE_MANIFEST.json').write_text(json.dumps({'built_at_bangkok':'2026-11-06T10:00:00+07:00','commit':'12345678abcdef'}))
    assert '2026-11-06T10:00:00+07:00' in text(tmp_path) and 'RC29.61' in text(tmp_path)
    d=pd.DataFrame([{'Work Order':'SYNTH-HTML','_WO key':'SYNTHHTML','Customer':'<script>unsafe</script>','Category':'P','Reason':'SYNTHETIC pending forming','Order pcs':10,'Planned pcs':10,'Actual pcs':3,'Pending planned pcs':7,'Actual unrecorded':False,'WO status':'Pending','Quantity status':'PARTIAL','Plan date':pd.Timestamp('2026-11-06'),'Actual applied pcs':3,'Unmatched actual pcs':0}])
    html=html_dashboard(with_weights(d)).decode()
    assert 'Pending pieces' in html and 'Pending reference tonnes' in html
    assert '<script>unsafe</script>' not in html and 'SYNTHETIC pending forming' in html
    assert 'source-rows' in html and 'plotly' in html


def test_legacy_manifest_with_null_commit_does_not_break_interface(tmp_path):
    (tmp_path/'VERSION').write_text('SYNTHETIC')
    (tmp_path/'RELEASE_MANIFEST.json').write_text('{"commit":null,"built_at_bangkok":null}')
    assert 'Not recorded' in text(tmp_path)

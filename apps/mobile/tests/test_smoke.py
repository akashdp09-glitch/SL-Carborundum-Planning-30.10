from pathlib import Path
import sqlite3

def test_database_exists(core):
    # Releases intentionally exclude factory databases. The shared test fixture
    # starts the real app against a fresh, isolated configured store instead.
    DB = Path(core.DB_PATH)
    assert DB.exists()
    con=sqlite3.connect(DB)
    c=con.execute('select count(*) from work_orders').fetchone()[0]
    con.close()
    assert c >= 0

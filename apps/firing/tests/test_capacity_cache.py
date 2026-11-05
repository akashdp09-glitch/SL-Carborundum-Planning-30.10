from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).parents[1]))
import ppc_fast_core_v4_6 as fc


def test_capacity_content_is_parsed_once_and_returns_independent_tables(tmp_path,monkeypatch):
    p=tmp_path/'SYNTHETIC_capacity.xlsx';p.write_bytes(b'SYNTHETIC revision 1')
    calls=[]
    def reader(f):
        calls.append(f.read());return tuple(pd.DataFrame({'Capacity':[len(calls)]}) for _ in range(6))
    monkeypatch.setattr(fc.dailyeng,'read_capacity',reader)
    fc._CAPACITY_CACHE.clear()
    a=fc._read_capacity_cached(p);a[0].iloc[0,0]=999
    b=fc._read_capacity_cached(p)
    assert b[0].iloc[0,0]==1
    assert len(calls)==1
    p.write_bytes(b'SYNTHETIC revision 2')
    assert fc._read_capacity_cached(p)[0].iloc[0,0]==2
    assert len(calls)==2
    fc._CAPACITY_CACHE.clear()

"""One-time import of locally owned workbooks; originals persist in the evidence DB.

Run with the SAME shared root used by the application. This never modifies the
source workbooks, operational planning tables or previous evidence revisions.
"""
from pathlib import Path
import argparse
import json
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from suite.production_evidence import import_workbook, set_setting


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--shared-root",type=Path,required=True)
    p.add_argument("--files",type=Path,nargs="+",required=True)
    p.add_argument("--author",required=True)
    p.add_argument("--year",type=int,required=True)
    args=p.parse_args()
    db=args.shared_root/"DATABASE"/"production_analytics.sqlite"
    for name,value in [("kpi_order","swap"),("report_basis","Production plan"),("forming_unit","g"),("final_packing_sheet","Pack จ่าย")]:
        set_setting(db,name,value,"Owner confirmed 4 November 2026",args.author)
    failed=False
    for source in args.files:
        start=time.perf_counter()
        try:
            result=import_workbook(db,source.read_bytes(),source.name,args.author,config={"year":args.year,"forming_unit":"g","report_basis":"Production plan"})
            print(json.dumps(dict(result,seconds=round(time.perf_counter()-start,3)),ensure_ascii=False),flush=True)
        except Exception as exc:
            failed=True
            print(json.dumps(dict(file=source.name,error=str(exc)),ensure_ascii=False),flush=True)
    raise SystemExit(1 if failed else 0)


if __name__=="__main__":main()

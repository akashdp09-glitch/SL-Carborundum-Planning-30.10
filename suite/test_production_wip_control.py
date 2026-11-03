import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from openpyxl import Workbook
_daily_path=Path(__file__).resolve().parents[1]/'apps'/'daily'
if str(_daily_path) not in sys.path:sys.path.insert(0,str(_daily_path))
from apps.daily.production_wip_control import production_snapshot, read_summary


def make_wip_book(path):
    wb=Workbook();cover=wb.active;cover.title='Cover';cover.cell(1,1,'WIP workbook cover')
    summary=wb.create_sheet('สรุปใบสั่งผลิต')
    summary.append(['Group','ใบสั่งผลิตทั้งหมด','ยังไม่ปิด','GW (Kg)','ปิดใบสั่ง'])
    summary.append(['P',1,1,12.5,0]);summary.append([None,1,1,12.5,0])
    detail=wb.create_sheet('ตุลาคม');detail.cell(2,3,'กลุ่มงานผสม');detail.cell(2,4,'ตุลาคม')
    detail.cell(3,2,'Fac No');detail.cell(3,72,'Status Job');detail.cell(3,73,'Category');detail.cell(3,75,'Total GW (Kg)')
    detail.cell(4,2,'WO-001');detail.cell(4,72,'ยังไม่ปิด');detail.cell(4,73,'P');detail.cell(4,75,12.5)
    wb.save(path)


class ProductionWipControlTests(unittest.TestCase):
    def test_full_path_is_used_and_current_snapshot_is_readable(self):
        with TemporaryDirectory() as td:
            app=Path(td)/'app';base=app/'apps'/'daily';base.mkdir(parents=True)
            central=app/'CENTRAL_DATA';folder=central/'PRODUCTION_WIP';folder.mkdir(parents=True)
            path=folder/'Mixing_October.xlsx';make_wip_book(path)
            self.assertAlmostEqual(read_summary(path,'Mixing')['Open kg'].sum(),12.5)
            record={'active_path':str(path.resolve()),'original_name':'Mixing October.xlsx','section':'Mixing','registered_at':'2026-10-21T09:00:00+07:00'}
            (central/'source_registry.json').write_text(json.dumps({f'PRODUCTION_WIP/{path.name}':record}),encoding='utf-8')
            snapshot,issues=production_snapshot(base)
            self.assertEqual(snapshot['Section'].nunique(),1)
            self.assertEqual(snapshot.iloc[0]['Original filename'],'Mixing October.xlsx')
            self.assertAlmostEqual(snapshot['Open t'].sum(),0.0125)
            self.assertEqual(issues,[])


if __name__=='__main__':
    unittest.main()

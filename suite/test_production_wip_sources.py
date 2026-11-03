import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from apps.daily.production_wip_sources import candidates, discover, filename_for_section, period_key


class ProductionWipSourceTests(unittest.TestCase):
  def test_latest_month_per_section_is_selected_and_prior_copies_are_retained(self):
    with TemporaryDirectory() as td:
        base=Path(td)/'SL'/'apps'/'daily';base.mkdir(parents=True)
        root=base.parents[1]/'CENTRAL_DATA';folder=root/'PRODUCTION_WIP';folder.mkdir(parents=True)
        old=folder/'Mixing_September.xlsx';new=folder/'Mixing_October.xlsx'
        old.write_bytes(b'old source');new.write_bytes(b'new source')
        records=[
            {'stored_path':str(old.resolve()),'original_filename':'รับจ่ายสินค้ากลุ่มงานผสม เดือนกันยายน.xlsx','section':'Mixing','active':True,'uploaded_at':'2026-09-30T10:00:00+07:00'},
            {'stored_path':str(new.resolve()),'original_filename':'รับจ่ายสินค้ากลุ่มงานผสม เดือนตุลาคม.xlsx','section':'Mixing','active':True,'uploaded_at':'2026-10-21T10:00:00+07:00'},
        ]
        (folder/'source_registry.json').write_text(json.dumps({'records':records},ensure_ascii=False),encoding='utf-8')
        ranked,_,diagnostics=candidates(base)
        selected,_,_=discover(base)
        self.assertEqual(ranked['Mixing'][0],new)
        self.assertEqual(selected['Mixing'],new)
        self.assertTrue(any('prior copies remain retained' in x for x in diagnostics))


  def test_same_period_uses_most_recent_import_and_canonical_name_is_stable(self):
    self.assertEqual(period_key('รับจ่ายสินค้ากลุ่มงานเตา เดือนตุลาคม 2569.xlsx'),(2026,10))
    self.assertEqual(filename_for_section('Grinding / Cutting (Production combined)'),'Grinding_Cutting__LATEST.xlsx')
    with TemporaryDirectory() as td:
        base=Path(td)/'SL'/'apps'/'daily';base.mkdir(parents=True)
        folder=base.parents[1]/'CENTRAL_DATA'/'PRODUCTION_WIP';folder.mkdir(parents=True)
        paths=[folder/'Mixing_a.xlsx',folder/'Mixing_b.xlsx']
        for p in paths:p.write_bytes(b'x')
        rec=[{'stored_path':str(paths[0].resolve()),'original_filename':'Mixing October.xlsx','section':'Mixing','active':True,'uploaded_at':'2026-10-20T08:00:00+07:00'},
             {'stored_path':str(paths[1].resolve()),'original_filename':'Mixing October.xlsx','section':'Mixing','active':True,'uploaded_at':'2026-10-21T08:00:00+07:00'}]
        (folder/'source_registry.json').write_text(json.dumps({'records':rec}),encoding='utf-8')
        self.assertEqual(discover(base)[0]['Mixing'],paths[1])

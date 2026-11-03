import datetime as dt
import unittest
import pandas as pd
from suite.requirements_engine import *

class NettingTests(unittest.TestCase):
    def run_plan(self,needs,stock=None,receipts=None):
        return net_requirements(pd.DataFrame(needs,columns=DEMAND_COLUMNS),pd.DataFrame(stock if stock is not None else [['B04',100,10,7,50,0,'Stock row 8']],columns=STOCK_COLUMNS),pd.DataFrame(receipts or [],columns=RECEIPT_COLUMNS),dt.date(2026,10,4),dt.date(2027,12,31))
    def test_lots_do_not_double_order_and_firm_stays_separate(self):
        l,o,e=self.run_plan([['B04','2026-10-10',120,'WO1','Plan!BE4','verified'],['B04','2026-10-11',10,'WO2','Plan!BE5','verified']])
        self.assertEqual(list(o.proposal_kg),[50]);self.assertEqual(list(l.firm_balance_kg),[-20,-30]);self.assertEqual(list(l.proposed_balance_kg),[30,20]);self.assertIn('EXPEDITE',o.iloc[0].status)
    def test_future_receipt_does_not_cover_earlier_need(self):
        l,o,e=self.run_plan([['B04','2026-10-05',120,'W','source','']],receipts=[['B04','2026-10-08',100,True,'PO','supplier']]);self.assertEqual(o.iloc[0].proposal_kg,50)
    def test_same_day_confirmed_receipt(self):
        l,o,e=self.run_plan([['B04','2026-10-10',120,'W','source','']],receipts=[['B04','2026-10-10',50,True,'PO','source']]);self.assertTrue(o.empty);self.assertEqual(l.iloc[0].firm_balance_kg,30)
    def test_unknown_stock_blocks(self):
        l,o,e=self.run_plan([['B04','2026-10-10',120,'W','source','']],stock=[['B04',None,0,7,0,0,'']]);self.assertTrue(o.empty);self.assertFalse(e.empty)
    def test_duplicate_stock_blocks(self):
        row=['B04',100,0,7,0,0,''];l,o,e=self.run_plan([['B04','2026-10-10',120,'W','','']],stock=[row,row]);self.assertTrue(l.empty)
    def test_unconfirmed_and_overdue_receipts_excluded(self):
        l,o,e=self.run_plan([['B04','2026-10-10',120,'W','','']],receipts=[['B04','2026-10-08',100,False,'PO',''],['B04','2026-10-01',100,True,'PO','']]);self.assertEqual(len(e),2);self.assertEqual(o.iloc[0].proposal_kg,50)
    def test_backlog_retained_and_missing_date_visible(self):
        l,o,e=self.run_plan([['B04','2025-01-01',120,'OLD','',''],['B04','',10,'UNKNOWN','','']]);self.assertEqual(l.iloc[0].date,dt.date(2026,10,4));self.assertEqual(l.iloc[0].backlog_need_kg,120);self.assertIn('PARTIAL',o.iloc[0].status)
    def test_ambiguous_day_first(self):
        self.assertEqual(parse_date('05/12/2026'),dt.date(2026,12,5))
        self.assertEqual(parse_date('2026-12-05'),dt.date(2026,12,5))
        with self.assertRaises(ValueError):parse_date('12/31/2026')
    def test_long_horizon(self):
        l,o,e=self.run_plan([['B04','2027-12-01',500,'FORECAST','','']]);self.assertEqual(o.iloc[0].required_receipt,dt.date(2027,12,1))

if __name__=='__main__':unittest.main()

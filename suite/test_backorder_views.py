import unittest
import pandas as pd

from suite.backorder_views import overdue_backorders, overdue_month_category, overdue_backorder_totals, future_open_month_category, mps_order_buckets


class BackorderViewTests(unittest.TestCase):
  def test_only_positive_open_balance_due_before_chonburi_today_is_backorder(self):
    master = pd.DataFrame([
        {'Work Order':'LATE','Due Date':'2026-10-08','Order Qty':20,'Packing Actual Qty':5,'Category':'F','Net Weight g/pc':1000,'Overall Closed':False},
        {'Work Order':'DUE-TODAY','Due Date':'2026-10-09','Order Qty':10,'Packing Actual Qty':0,'Category':'P','Net Weight g/pc':1000,'Overall Closed':False},
        {'Work Order':'FUTURE-2027','Due Date':'2027-02-01','Order Qty':30,'Packing Actual Qty':0,'Category':'R','Net Weight g/pc':1000,'Overall Closed':False},
        {'Work Order':'CLOSED','Due Date':'2026-10-01','Order Qty':5,'Packing Actual Qty':5,'Category':'S','Net Weight g/pc':1000,'Overall Closed':True},
    ])
    result = overdue_backorders(master, pd.Timestamp('2026-10-09'))
    self.assertEqual(result['Work Order'].tolist(), ['LATE'])
    self.assertEqual(result.iloc[0]['pcs'], 15)
    self.assertEqual(result.iloc[0]['Product Category'], 'P')  # Factory rule: F maps to P.
    self.assertEqual(result.iloc[0]['Late days'], 1)
    self.assertEqual(overdue_month_category(master, pd.Timestamp('2026-10-09'))['WOs'].sum(), 1)


  def test_repeated_source_rows_do_not_double_count_work_order(self):
    row = {'Work Order':'LATE','Due Date':'2026-10-08','Order Qty':20,'Packing Actual Qty':5,'Category':'P','Overall Closed':False}
    result = overdue_backorders(pd.DataFrame([row, row]), pd.Timestamp('2026-10-09'))
    self.assertEqual(len(result), 1)
    self.assertEqual(result.iloc[0]['pcs'], 15)

  def test_dashboard_totals_equal_authoritative_detail_not_chart_grouping(self):
    master = pd.DataFrame([
      {'Work Order':'A','Due Date':'2026-10-01','pcs':12,'Category':'P','ton':0.6,'Overall Closed':False},
      {'Work Order':'A','Due Date':'2026-10-01','pcs':8,'Category':'P','ton':0.4,'Overall Closed':False},
      {'Work Order':'B','Due Date':'2026-09-25','pcs':5,'Category':'F','ton':0.2,'Overall Closed':False},
      {'Work Order':'C','Due Date':'2026-10-14','pcs':100,'Category':'R','ton':1.0,'Overall Closed':False},
    ])
    detail = overdue_backorders(master, pd.Timestamp('2026-10-13'))
    totals = overdue_backorder_totals(master, pd.Timestamp('2026-10-13'))
    chart = overdue_month_category(master, pd.Timestamp('2026-10-13'))
    assert totals['WOs'] == detail['Work Order'].nunique() == 2
    assert totals['Qty pcs'] == detail['pcs'].sum() == chart['Qty pcs'].sum() == 17
    assert totals['Weight ton'] == detail['ton'].sum() == chart['Weight ton'].sum() == 0.8

  def test_mps_buckets_are_disjoint_and_keep_2027_out_of_2026_horizon(self):
    orders = pd.DataFrame([
      {'WO':'OCT-LATE','Item':'A','Due Date':'2026-10-08','Open Qty':15},
      {'WO':'DUE-TODAY','Item':'B','Due Date':'2026-10-09','Open Qty':10},
      {'WO':'FUTURE-OCT','Item':'C','Due Date':'2026-10-20','Open Qty':20},
      {'WO':'NEXT-YEAR','Item':'D','Due Date':'2027-02-01','Open Qty':30},
      {'WO':'NO-DATE','Item':'E','Due Date':None,'Open Qty':40},
    ])
    overdue, future = mps_order_buckets(orders, pd.Timestamp('2026-10-09'), 2026, 10)
    self.assertEqual(overdue['WO'].tolist(), ['OCT-LATE'])
    self.assertEqual(future['WO'].tolist(), ['DUE-TODAY','FUTURE-OCT'])
    self.assertFalse(set(overdue['WO']) & set(future['WO']))
    _, next_year = mps_order_buckets(orders, pd.Timestamp('2026-10-09'), 2027, 1)
    self.assertEqual(next_year['WO'].tolist(), ['NEXT-YEAR'])

  def test_duplicate_work_order_counted_once_at_max_open_balance(self):
    orders = pd.DataFrame([
      {'WO':'DUP','Item':'A','Due Date':'2026-10-08','Open Qty':12},
      {'WO':'DUP','Item':'A','Due Date':'2026-10-08','Open Qty':20},
    ])
    overdue, future = mps_order_buckets(orders, pd.Timestamp('2026-10-09'), 2026, 10)
    self.assertEqual(len(overdue), 1)
    self.assertEqual(float(overdue.iloc[0]['Open Qty']), 20)
    self.assertTrue(future.empty)

  def test_future_open_graph_is_separate_from_past_due_backorders(self):
    data = pd.DataFrame([
      {'Work Order':'LATE','Due Date':'2026-10-08','pcs':7,'Authoritative Closed':False,'Category':'F','ton':0.7},
      {'Work Order':'TODAY','Due Date':'2026-10-09','pcs':5,'Authoritative Closed':False,'Category':'R','ton':0.2},
      {'Work Order':'NEXTYEAR','Due Date':'2027-01-01','pcs':3,'Authoritative Closed':False,'Category':'P','ton':0.1},
      {'Work Order':'CLOSED','Due Date':'2026-10-10','pcs':9,'Authoritative Closed':True,'Category':'P','ton':0.9},
    ])
    future = future_open_month_category(data, pd.Timestamp('2026-10-09'))
    self.assertEqual(set(future['Due Month']), {'2026-10','2027-01'})
    self.assertEqual(set(future['Product Category']), {'R','P'})
    self.assertEqual(int(future['Qty pcs'].sum()), 8)


if __name__ == '__main__':
    unittest.main()

import pandas as pd
import unittest

from suite.planning_wip import open_order_wip


class PlanningWipTests(unittest.TestCase):
  def test_plan_wip_uses_open_balance_category_and_documented_weight_conversion(self):
    master=pd.DataFrame([
        {'Work Order':'OPEN-1','Order Qty':120,'Packing Actual Qty':20,'Overall Closed':False,'Type':'F','Plan2026 kg/pc':2.0,'Due Date':'2026-10-25','Firing Remaining Qty':100},
        {'Work Order':'CLOSED-2','Order Qty':50,'Packing Actual Qty':50,'Overall Closed':True,'Type':'PB','Plan2026 kg/pc':1.0,'Due Date':'2026-10-20','Packing Remaining Qty':0},
    ])
    out=open_order_wip(master)
    self.assertEqual(out['Work Order'].tolist(),['OPEN-1'])
    self.assertEqual(out.iloc[0]['pcs'],100)
    self.assertAlmostEqual(out.iloc[0]['ton'],0.2)
    self.assertEqual(out.iloc[0]['Product Category'],'P')
    self.assertEqual(out.iloc[0]['Section'],'Firing')

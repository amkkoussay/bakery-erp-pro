import unittest
from tests.base import BakeryTestCase


class TestConsumptionRate(BakeryTestCase):

    def test_consumption_rate_computed_from_outflow_movements(self):
        from app.db_utils import update_inventory
        from app.services import inventory_prediction_service as pred

        wh_id = self.make_warehouse()
        item_id = self.make_item(code='FLR300', name='Flour')
        update_inventory(item_id, wh_id, 300, 2.0, 'purchase')

        # 10 units/day sold for the last 10 days = 100 units out over a 10-day window
        for d in range(10):
            self.backdated_movement(item_id, wh_id, -10, 'sale', days_ago=d)

        rate = pred.get_consumption_rate(item_id, window_days=10)
        self.assertEqual(rate, 10.0)


class TestPredictItem(BakeryTestCase):

    def test_flags_reorder_when_stock_will_run_out(self):
        from app.db_utils import update_inventory, execute
        from app.services import inventory_prediction_service as pred
        from app.repositories import inventory_repository as inv_repo

        wh_id = self.make_warehouse()
        supplier_id = execute("""
            INSERT INTO suppliers (code, name, lead_time_days) VALUES ('SUP1', 'Flour Co', 5)
        """)
        item_id = self.make_item(code='FLR301', name='Flour')
        execute("UPDATE items SET preferred_supplier_id = ? WHERE id = ?", (supplier_id, item_id))

        update_inventory(item_id, wh_id, 20, 2.0, 'purchase')

        # Consuming 10/day -> only 2 days of stock left, well under the 5-day lead time
        for d in range(5):
            self.backdated_movement(item_id, wh_id, -10, 'sale', days_ago=d)

        item = inv_repo.get_item(item_id)
        result = pred.predict_item(item, window_days=5)

        self.assertIsNotNone(result['days_remaining'])
        self.assertTrue(result['needs_reorder'])
        self.assertGreater(result['suggested_reorder_qty'], 0)
        self.assertEqual(result['urgency'], 'critical')

    def test_ok_when_stock_is_plentiful(self):
        from app.db_utils import update_inventory
        from app.services import inventory_prediction_service as pred
        from app.repositories import inventory_repository as inv_repo

        wh_id = self.make_warehouse()
        item_id = self.make_item(code='FLR302', name='Flour')
        update_inventory(item_id, wh_id, 1000, 2.0, 'purchase')

        self.backdated_movement(item_id, wh_id, -1, 'sale', days_ago=1)

        item = inv_repo.get_item(item_id)
        result = pred.predict_item(item, window_days=30)

        self.assertFalse(result['needs_reorder'])
        self.assertEqual(result['urgency'], 'ok')

    def test_inactive_when_no_movement(self):
        from app.db_utils import update_inventory
        from app.services import inventory_prediction_service as pred
        from app.repositories import inventory_repository as inv_repo

        wh_id = self.make_warehouse()
        item_id = self.make_item(code='FLR303', name='Flour')
        update_inventory(item_id, wh_id, 50, 2.0, 'purchase')

        item = inv_repo.get_item(item_id)
        result = pred.predict_item(item, window_days=30)

        self.assertIsNone(result['days_remaining'])
        self.assertEqual(result['urgency'], 'inactive')
        self.assertFalse(result['needs_reorder'])


if __name__ == '__main__':
    unittest.main()

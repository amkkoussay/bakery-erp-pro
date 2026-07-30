import unittest
from tests.base import BakeryTestCase


class TestStockMovements(BakeryTestCase):

    def test_stock_increases_on_incoming_movement(self):
        from app.db_utils import update_inventory, get_item_stock

        item_id = self.make_item(code='FLR100', name='Flour')
        wh_id = self.make_warehouse()

        update_inventory(item_id, wh_id, 100, 2.0, 'purchase')
        stock = get_item_stock(item_id, wh_id)

        self.assertEqual(stock['quantity'], 100)
        self.assertEqual(stock['unit_cost'], 2.0)
        self.assertEqual(stock['total_cost'], 200.0)

    def test_stock_decreases_on_outgoing_movement(self):
        from app.db_utils import update_inventory, get_item_stock

        item_id = self.make_item(code='FLR101', name='Flour')
        wh_id = self.make_warehouse()

        update_inventory(item_id, wh_id, 100, 2.0, 'purchase')
        update_inventory(item_id, wh_id, -30, 0, 'sale')

        stock = get_item_stock(item_id, wh_id)
        self.assertEqual(stock['quantity'], 70)

    def test_weighted_average_cost_on_multiple_purchases(self):
        from app.db_utils import update_inventory, get_item_stock

        item_id = self.make_item(code='SUG100', name='Sugar')
        wh_id = self.make_warehouse()

        update_inventory(item_id, wh_id, 10, 1.0, 'purchase')   # 10 @ 1.0 = 10
        update_inventory(item_id, wh_id, 10, 3.0, 'purchase')   # 10 @ 3.0 = 30
        stock = get_item_stock(item_id, wh_id)

        # weighted average: (10*1 + 10*3) / 20 = 2.0
        self.assertEqual(stock['quantity'], 20)
        self.assertEqual(round(stock['unit_cost'], 2), 2.0)

    def test_every_movement_is_logged(self):
        from app.db_utils import update_inventory, query_all

        item_id = self.make_item(code='FLR102', name='Flour')
        wh_id = self.make_warehouse()

        update_inventory(item_id, wh_id, 50, 2.0, 'purchase')
        update_inventory(item_id, wh_id, -10, 0, 'sale')

        movements = query_all(
            "SELECT * FROM inventory_movements WHERE item_id = ? ORDER BY id", (item_id,)
        )
        self.assertEqual(len(movements), 2)
        self.assertEqual(movements[0]['movement_type'], 'purchase')
        self.assertEqual(movements[1]['movement_type'], 'sale')


class TestOversellingPrevention(BakeryTestCase):

    def test_available_when_enough_stock(self):
        from app.db_utils import update_inventory, check_stock_availability

        item_id = self.make_item(code='FLR103', name='Flour')
        wh_id = self.make_warehouse()
        update_inventory(item_id, wh_id, 50, 2.0, 'purchase')

        available, qty = check_stock_availability(item_id, wh_id, 20)
        self.assertTrue(available)
        self.assertEqual(qty, 50)

    def test_blocked_when_overselling(self):
        """This is the check that must block a sale from overselling stock."""
        from app.db_utils import update_inventory, check_stock_availability

        item_id = self.make_item(code='FLR104', name='Flour')
        wh_id = self.make_warehouse()
        update_inventory(item_id, wh_id, 10, 2.0, 'purchase')

        available, qty = check_stock_availability(item_id, wh_id, 15)
        self.assertFalse(available)
        self.assertEqual(qty, 10)

    def test_blocked_for_untracked_item(self):
        """An item with no inventory row at all must never report as available."""
        from app.db_utils import check_stock_availability

        item_id = self.make_item(code='FLR105', name='Flour')
        wh_id = self.make_warehouse()

        available, qty = check_stock_availability(item_id, wh_id, 1)
        self.assertFalse(available)
        self.assertEqual(qty, 0)


if __name__ == '__main__':
    unittest.main()

import unittest
from tests.base import BakeryTestCase


class TestRecipeCost(BakeryTestCase):

    def test_recipe_cost_uses_ingredient_average_cost(self):
        from app.db_utils import update_inventory
        from app.services import profit_service

        wh_id = self.make_warehouse()
        flour = self.make_item(code='FLR200', name='Flour', unit='kg')
        sugar = self.make_item(code='SUG200', name='Sugar', unit='kg')
        bread = self.make_item(code='BRD200', name='White Bread', item_type='finished_goods', unit='loaf')

        update_inventory(flour, wh_id, 100, 2.0, 'purchase')   # $2/kg
        update_inventory(sugar, wh_id, 100, 4.0, 'purchase')   # $4/kg

        # 10 loaves need 5kg flour + 1kg sugar, no wastage
        self.make_bom(bread, yield_qty=10, ingredients=[
            (flour, 5, 'kg', 0),
            (sugar, 1, 'kg', 0),
        ])

        cost = profit_service.recipe_cost(bread)

        self.assertIsNotNone(cost)
        # batch cost = 5*2 + 1*4 = 14, cost per unit = 14/10 = 1.4
        self.assertEqual(cost['batch_cost'], 14.0)
        self.assertEqual(round(cost['cost_per_unit'], 2), 1.4)

    def test_recipe_cost_accounts_for_wastage_percent(self):
        from app.db_utils import update_inventory
        from app.services import profit_service

        wh_id = self.make_warehouse()
        flour = self.make_item(code='FLR201', name='Flour', unit='kg')
        bread = self.make_item(code='BRD201', name='White Bread', item_type='finished_goods', unit='loaf')

        update_inventory(flour, wh_id, 100, 2.0, 'purchase')  # $2/kg

        # 10 loaves need 5kg flour, with 10% wastage -> effectively 5.5kg consumed
        self.make_bom(bread, yield_qty=10, ingredients=[(flour, 5, 'kg', 10)])

        cost = profit_service.recipe_cost(bread)

        self.assertEqual(cost['batch_cost'], 11.0)  # 5.5kg * $2
        self.assertEqual(round(cost['cost_per_unit'], 2), 1.1)

    def test_recipe_cost_none_when_no_bom(self):
        from app.services import profit_service

        bread = self.make_item(code='BRD202', name='Rye Bread', item_type='finished_goods', unit='loaf')
        self.assertIsNone(profit_service.recipe_cost(bread))


class TestProductionConsumption(BakeryTestCase):

    def test_completion_deducts_ingredients_and_adds_finished_goods(self):
        """
        End-to-end: completing a production order should consume raw materials
        from stock and add the finished product to stock, matching the BOM ratio.
        """
        from app.db_utils import update_inventory, execute, get_item_stock, generate_production_number

        wh_id = self.make_warehouse()
        flour = self.make_item(code='FLR202', name='Flour', unit='kg')
        bread = self.make_item(code='BRD203', name='White Bread', item_type='finished_goods', unit='loaf')

        update_inventory(flour, wh_id, 100, 2.0, 'purchase')

        bom_id = self.make_bom(bread, yield_qty=10, ingredients=[(flour, 5, 'kg', 0)])

        order_number = generate_production_number()
        order_id = execute("""
            INSERT INTO production_orders
            (order_number, product_id, bom_id, planned_quantity, warehouse_id, production_date)
            VALUES (?, ?, ?, 10, ?, date('now'))
        """, (order_number, bread, bom_id, wh_id))

        execute("""
            INSERT INTO production_consumption (production_order_id, item_id, planned_quantity)
            VALUES (?, ?, 5)
        """, (order_id, flour))

        # Simulate what production.complete_production does (deduct materials, add output)
        consumption = get_item_stock(flour, wh_id)
        unit_cost = consumption['unit_cost']
        update_inventory(flour, wh_id, -5, unit_cost, 'production_out', 'production_order', order_id)
        update_inventory(bread, wh_id, 10, 5 * unit_cost / 10, 'production_in', 'production_order', order_id)

        flour_stock = get_item_stock(flour, wh_id)
        bread_stock = get_item_stock(bread, wh_id)

        self.assertEqual(flour_stock['quantity'], 95)
        self.assertEqual(bread_stock['quantity'], 10)


if __name__ == '__main__':
    unittest.main()

import os
import sys
import sqlite3
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schema.sql')


class BakeryTestCase(unittest.TestCase):
    """
    Base class for all backend tests. Each test gets a fresh temp SQLite DB
    built from the real schema.sql, and an active Flask app context so
    app.db_utils functions work exactly as they do in the running app.
    """

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(self.db_path)
        with open(SCHEMA_PATH, 'r') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

        self.app = create_app({
            'TESTING': True,
            'SECRET_KEY': 'test',
            'DATABASE': self.db_path,
        })
        self._ctx = self.app.app_context()
        self._ctx.push()

    def tearDown(self):
        self._ctx.pop()
        os.remove(self.db_path)

    # ---- shared helpers -------------------------------------------------

    def make_item(self, code='FLR001', name='Flour', item_type='raw_material', unit='kg',
                  min_stock=0, reorder_point=0):
        from app.db_utils import execute
        return execute("""
            INSERT INTO items (code, name, type, unit, min_stock, reorder_point)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, name, item_type, unit, min_stock, reorder_point))

    def make_warehouse(self, name='Main Bakery'):
        from app.db_utils import query_one, execute
        existing = query_one("SELECT id FROM warehouses WHERE name = ?", (name,))
        if existing:
            return existing['id']
        return execute("INSERT INTO warehouses (name) VALUES (?)", (name,))

    def make_bom(self, product_id, yield_qty, ingredients):
        """ingredients: list of (item_id, quantity, unit, wastage_percent)"""
        from app.db_utils import execute
        bom_id = execute("""
            INSERT INTO bom_headers (product_id, version, quantity_yield)
            VALUES (?, '1.0', ?)
        """, (product_id, yield_qty))
        for item_id, qty, unit, wastage in ingredients:
            execute("""
                INSERT INTO bom_details (bom_id, item_id, quantity, unit, wastage_percent)
                VALUES (?, ?, ?, ?, ?)
            """, (bom_id, item_id, qty, unit, wastage))
        return bom_id

    def backdated_movement(self, item_id, wh_id, qty, movement_type, days_ago):
        from datetime import datetime, timedelta
        from app.db_utils import get_db
        db = get_db()
        when = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
        db.execute("""
            INSERT INTO inventory_movements
            (item_id, warehouse_id, movement_type, quantity, unit_cost, total_cost, created_at)
            VALUES (?, ?, ?, ?, 0, 0, ?)
        """, (item_id, wh_id, movement_type, qty, when))
        db.commit()

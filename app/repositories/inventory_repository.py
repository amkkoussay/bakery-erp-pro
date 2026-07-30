"""
Inventory Repository
Raw data access for items, stock levels and inventory movements.
No business logic here - see app/services/inventory_prediction_service.py
"""
from app.db_utils import query_one, query_all


def get_trackable_items(item_type=None):
    """Items that can run out of stock (raw materials, semi-finished, packaging, finished goods)."""
    sql = """
        SELECT i.id, i.code, i.name, i.type, i.unit, i.min_stock, i.max_stock,
               i.reorder_point, i.safety_stock_days, i.preferred_supplier_id,
               s.name as supplier_name, s.lead_time_days
        FROM items i
        LEFT JOIN suppliers s ON i.preferred_supplier_id = s.id
        WHERE i.is_active = 1
    """
    params = []
    if item_type:
        sql += " AND i.type = ?"
        params.append(item_type)
    sql += " ORDER BY i.name"
    return query_all(sql, params)


def get_item(item_id):
    return query_one("""
        SELECT i.*, s.name as supplier_name, s.lead_time_days
        FROM items i
        LEFT JOIN suppliers s ON i.preferred_supplier_id = s.id
        WHERE i.id = ?
    """, (item_id,))


def get_current_stock(item_id):
    """Total quantity currently on hand across all warehouses for an item."""
    row = query_one("""
        SELECT COALESCE(SUM(quantity), 0) as total_qty,
               COALESCE(AVG(unit_cost), 0) as avg_cost
        FROM inventory WHERE item_id = ?
    """, (item_id,))
    return row['total_qty'] if row else 0


def get_outflow_total(item_id, since_date):
    """
    Sum of everything that left stock for an item since a given date:
    sales, POS sales, production consumption, and waste.
    Movement quantities for outflows are stored as negative numbers.
    """
    row = query_one("""
        SELECT COALESCE(SUM(-quantity), 0) as total_out
        FROM inventory_movements
        WHERE item_id = ?
          AND movement_type IN ('sale', 'production_out', 'waste')
          AND quantity < 0
          AND date(created_at) >= ?
    """, (item_id, since_date))
    return row['total_out'] if row else 0


def get_last_movement_date(item_id):
    row = query_one("""
        SELECT MAX(created_at) as last_date FROM inventory_movements WHERE item_id = ?
    """, (item_id,))
    return row['last_date'] if row else None


def get_waste_movements(date_from, date_to):
    """All waste movements (from production or manual adjustments) in a date range."""
    return query_all("""
        SELECT m.id, m.item_id, m.warehouse_id, m.movement_type, m.notes, m.created_at,
               ABS(m.quantity) as quantity, ABS(m.total_cost) as total_cost,
               i.name as item_name, i.code as item_code, i.unit
        FROM inventory_movements m
        JOIN items i ON m.item_id = i.id
        WHERE m.movement_type = 'waste'
          AND date(m.created_at) BETWEEN ? AND ?
        ORDER BY m.created_at DESC
    """, (date_from, date_to))

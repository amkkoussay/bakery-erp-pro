"""
Production Repository
Raw data access for Bills of Materials (recipes) and production waste.
"""
from app.db_utils import query_one, query_all


def get_active_bom(product_id):
    """Latest active BOM header for a product."""
    return query_one("""
        SELECT * FROM bom_headers
        WHERE product_id = ? AND is_active = 1
        ORDER BY version DESC LIMIT 1
    """, (product_id,))


def get_bom_ingredients_with_cost(bom_id):
    """
    BOM ingredients joined with their current average inventory cost,
    so a recipe cost can be computed without a production run happening.
    """
    return query_all("""
        SELECT bd.item_id, bd.quantity, bd.unit, bd.wastage_percent,
               i.name as item_name, i.code as item_code,
               COALESCE((SELECT AVG(unit_cost) FROM inventory WHERE item_id = bd.item_id), 0) as unit_cost
        FROM bom_details bd
        JOIN items i ON bd.item_id = i.id
        WHERE bd.bom_id = ?
    """, (bom_id,))


def get_production_waste(date_from, date_to):
    return query_all("""
        SELECT po.id, po.order_number, po.production_date, po.waste_quantity,
               i.name as product_name, i.unit,
               COALESCE((SELECT AVG(unit_cost) FROM inventory WHERE item_id = po.product_id), 0) as unit_cost
        FROM production_orders po
        JOIN items i ON po.product_id = i.id
        WHERE po.waste_quantity > 0
          AND po.production_date BETWEEN ? AND ?
        ORDER BY po.production_date DESC
    """, (date_from, date_to))

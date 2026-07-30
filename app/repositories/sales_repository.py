"""
Sales Repository
Raw data access for selling prices and per-product revenue,
combining sales invoices and POS transactions (the bakery's two sale channels).
"""
from app.db_utils import query_one, query_all


def get_default_price(item_id):
    """Default retail price list price for an item, if one is set."""
    row = query_one("""
        SELECT pld.unit_price
        FROM price_list_details pld
        JOIN price_lists pl ON pld.price_list_id = pl.id
        WHERE pld.item_id = ? AND pl.is_default = 1
        LIMIT 1
    """, (item_id,))
    return row['unit_price'] if row else None


def get_sales_performance(date_from, date_to):
    """
    Per-product quantity sold, revenue and cost of goods sold across both
    invoice sales and POS sales in a date range.
    """
    return query_all("""
        SELECT
            i.id as item_id, i.code, i.name, i.unit,
            COALESCE(SUM(x.qty), 0) as qty_sold,
            COALESCE(SUM(x.revenue), 0) as revenue,
            COALESCE(SUM(x.cost), 0) as cogs
        FROM items i
        LEFT JOIN (
            SELECT sid.item_id, sid.quantity as qty, sid.total_price as revenue,
                   sid.cost_price * sid.quantity as cost
            FROM sales_invoice_details sid
            JOIN sales_invoices si ON sid.invoice_id = si.id
            WHERE si.status != 'cancelled' AND si.invoice_date BETWEEN ? AND ?

            UNION ALL

            SELECT ptd.item_id, ptd.quantity as qty, ptd.total_price as revenue,
                   COALESCE((SELECT AVG(unit_cost) FROM inventory WHERE item_id = ptd.item_id), 0) * ptd.quantity as cost
            FROM pos_transaction_details ptd
            JOIN pos_transactions pt ON ptd.pos_transaction_id = pt.id
            WHERE pt.transaction_type = 'sale'
              AND date(pt.created_at) BETWEEN ? AND ?
        ) x ON x.item_id = i.id
        WHERE i.type = 'finished_goods' AND i.is_active = 1
        GROUP BY i.id, i.code, i.name, i.unit
        ORDER BY revenue DESC
    """, (date_from, date_to, date_from, date_to))

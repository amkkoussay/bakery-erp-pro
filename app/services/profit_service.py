"""
Profit & Loss Analytics
========================
Connects recipe cost (BOM) with actual selling price and actual sales
volume, so a manager can see which products make money and how much
money waste is costing the bakery - not just what was sold.
"""
from app.repositories import production_repository as prod_repo
from app.repositories import sales_repository as sales_repo
from app.repositories import inventory_repository as inv_repo
from app.db_utils import query_one


def recipe_cost(product_id):
    """
    Cost to produce one unit of a finished/semi-finished product, based on
    its active BOM and the current average cost of each ingredient.
    Wastage percent on each ingredient line is factored in.
    """
    bom = prod_repo.get_active_bom(product_id)
    if not bom:
        return None

    ingredients = prod_repo.get_bom_ingredients_with_cost(bom['id'])
    total_batch_cost = 0
    for ing in ingredients:
        qty_with_waste = ing['quantity'] * (1 + (ing['wastage_percent'] or 0) / 100)
        total_batch_cost += qty_with_waste * (ing['unit_cost'] or 0)

    yield_qty = bom['quantity_yield'] or 1
    cost_per_unit = total_batch_cost / yield_qty if yield_qty else 0

    return {
        'product_id': product_id,
        'bom_id': bom['id'],
        'batch_yield': yield_qty,
        'batch_cost': round(total_batch_cost, 2),
        'cost_per_unit': round(cost_per_unit, 4),
        'ingredients': ingredients,
    }


def product_profitability(date_from, date_to):
    """
    Per finished-good product: recipe cost, selling price, margin, and
    actual profit contributed in the period based on real sales volume.
    """
    performance = sales_repo.get_sales_performance(date_from, date_to)
    results = []

    for row in performance:
        cost_info = recipe_cost(row['item_id'])
        cost_per_unit = cost_info['cost_per_unit'] if cost_info else None

        price = sales_repo.get_default_price(row['item_id'])
        if price is None and row['qty_sold']:
            price = round(row['revenue'] / row['qty_sold'], 2)

        margin_percent = None
        profit_per_unit = None
        if price is not None and cost_per_unit is not None:
            profit_per_unit = round(price - cost_per_unit, 4)
            margin_percent = round((profit_per_unit / price) * 100, 2) if price else None

        actual_profit = None
        if row['qty_sold']:
            # Prefer actual recorded COGS from sales if we have it, else estimate.
            actual_cogs = row['cogs'] if row['cogs'] else (
                (cost_per_unit or 0) * row['qty_sold']
            )
            actual_profit = round(row['revenue'] - actual_cogs, 2)

        results.append({
            'item_id': row['item_id'],
            'code': row['code'],
            'name': row['name'],
            'unit': row['unit'],
            'qty_sold': row['qty_sold'],
            'revenue': round(row['revenue'], 2),
            'cost_per_unit': cost_per_unit,
            'selling_price': price,
            'profit_per_unit': profit_per_unit,
            'margin_percent': margin_percent,
            'actual_profit': actual_profit,
            'has_recipe': cost_info is not None,
        })

    results.sort(key=lambda r: r['actual_profit'] if r['actual_profit'] is not None else -1e9, reverse=True)
    return results


def waste_cost(date_from, date_to):
    """
    Money lost from waste in a period: raw material/finished-good waste
    logged as inventory movements, plus production-order waste quantities
    valued at the product's ingredient cost.
    """
    movements = inv_repo.get_waste_movements(date_from, date_to)
    movement_total = sum(abs(m['total_cost'] or 0) for m in movements)

    production_waste = prod_repo.get_production_waste(date_from, date_to)
    production_total = 0
    production_lines = []
    for pw in production_waste:
        line_cost = round((pw['waste_quantity'] or 0) * (pw['unit_cost'] or 0), 2)
        production_total += line_cost
        production_lines.append({
            'order_number': pw['order_number'],
            'production_date': pw['production_date'],
            'product_name': pw['product_name'],
            'unit': pw['unit'],
            'waste_quantity': pw['waste_quantity'],
            'cost': line_cost,
        })

    return {
        'inventory_waste_movements': movements,
        'inventory_waste_cost': round(movement_total, 2),
        'production_waste_lines': production_lines,
        'production_waste_cost': round(production_total, 2),
        'total_waste_cost': round(movement_total + production_total, 2),
    }

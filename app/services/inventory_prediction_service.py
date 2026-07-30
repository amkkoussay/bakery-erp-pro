"""
Smart Inventory Predictions
============================
Turns raw stock_movements history into forward-looking answers:
  - How fast is this item actually being consumed?
  - When will it run out, at the current rate?
  - How much should we reorder, given the supplier's delivery time?

Consumption rate is based on real outflow movements (sales, production
consumption, waste) over a trailing window - not on min/max stock fields,
which managers often forget to update.
"""
from datetime import datetime, timedelta
from app.repositories import inventory_repository as inv_repo

DEFAULT_WINDOW_DAYS = 30
DEFAULT_LEAD_TIME_DAYS = 3
DEFAULT_SAFETY_STOCK_DAYS = 2


def _daterange_start(window_days):
    return (datetime.now() - timedelta(days=window_days)).strftime('%Y-%m-%d')


def get_consumption_rate(item_id, window_days=DEFAULT_WINDOW_DAYS):
    """Average units consumed per day over the trailing window_days."""
    since = _daterange_start(window_days)
    total_out = inv_repo.get_outflow_total(item_id, since)
    if window_days <= 0:
        return 0
    return round(total_out / window_days, 4)


def predict_item(item, window_days=DEFAULT_WINDOW_DAYS):
    """
    Build a full prediction record for a single item (as returned by
    inventory_repository.get_trackable_items / get_item).
    """
    item_id = item['id']
    current_stock = inv_repo.get_current_stock(item_id)
    daily_rate = get_consumption_rate(item_id, window_days)

    lead_time_days = item.get('lead_time_days') or DEFAULT_LEAD_TIME_DAYS
    safety_stock_days = item.get('safety_stock_days')
    if safety_stock_days is None:
        safety_stock_days = DEFAULT_SAFETY_STOCK_DAYS

    if daily_rate > 0:
        days_remaining = round(current_stock / daily_rate, 1)
        stockout_date = (datetime.now() + timedelta(days=days_remaining)).strftime('%Y-%m-%d')
    else:
        days_remaining = None  # not moving - nothing to predict
        stockout_date = None

    # Coverage we want on hand: enough to survive the supplier's lead time
    # plus a safety buffer, restocked to a comfortable level.
    target_coverage_days = lead_time_days + safety_stock_days
    target_stock = daily_rate * target_coverage_days
    reorder_qty = max(0, round(target_stock - current_stock, 2))

    # Will run out before a fresh order could arrive, or already below the
    # manager-defined reorder point.
    will_stock_out_before_delivery = (
        days_remaining is not None and days_remaining <= lead_time_days
    )
    below_reorder_point = (
        item.get('reorder_point') and current_stock <= item['reorder_point']
    )
    needs_reorder = bool(
        reorder_qty > 0 and (will_stock_out_before_delivery or below_reorder_point)
    )

    if days_remaining is None:
        urgency = 'inactive'
    elif days_remaining <= lead_time_days:
        urgency = 'critical'
    elif days_remaining <= target_coverage_days:
        urgency = 'warning'
    else:
        urgency = 'ok'

    return {
        'item_id': item_id,
        'code': item.get('code'),
        'name': item.get('name'),
        'unit': item.get('unit'),
        'current_stock': round(current_stock, 2),
        'daily_consumption': daily_rate,
        'days_remaining': days_remaining,
        'predicted_stockout_date': stockout_date,
        'supplier_name': item.get('supplier_name'),
        'lead_time_days': lead_time_days,
        'suggested_reorder_qty': reorder_qty,
        'needs_reorder': needs_reorder,
        'urgency': urgency,
    }


def predict_all(item_type=None, window_days=DEFAULT_WINDOW_DAYS):
    """
    Predictions for every trackable item, most urgent (soonest stockout)
    first. Items with no recent movement are pushed to the end.
    """
    items = inv_repo.get_trackable_items(item_type)
    predictions = [predict_item(item, window_days) for item in items]

    def sort_key(p):
        return (p['days_remaining'] is None, p['days_remaining'] if p['days_remaining'] is not None else 0)

    predictions.sort(key=sort_key)
    return predictions


def reorder_suggestions(item_type=None, window_days=DEFAULT_WINDOW_DAYS):
    """Just the items that actually need a purchase request raised soon."""
    return [p for p in predict_all(item_type, window_days) if p['needs_reorder']]

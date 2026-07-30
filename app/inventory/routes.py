"""
Inventory Management Routes
Handles items, stock levels, movements, and adjustments
"""
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from app.inventory import bp
from app.db_utils import (
    query_one, query_all, execute, update_inventory, 
    get_item_stock, check_stock_availability, get_inventory_valuation
)
from app.services import inventory_prediction_service as prediction_service
from datetime import datetime

@bp.route('/items')
def items_list():
    """List all items"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    item_type = request.args.get('type', '')
    search = request.args.get('search', '')
    
    sql = """
        SELECT i.*, c.name as category_name,
            COALESCE((SELECT SUM(quantity) FROM inventory WHERE item_id = i.id), 0) as current_stock
        FROM items i
        LEFT JOIN item_categories c ON i.category_id = c.id
        WHERE i.is_active = 1
    """
    params = []
    
    if item_type:
        sql += " AND i.type = ?"
        params.append(item_type)
    
    if search:
        sql += " AND (i.name LIKE ? OR i.code LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    
    sql += " ORDER BY i.name"
    
    items = query_all(sql, params)
    categories = query_all("SELECT * FROM item_categories ORDER BY name")
    
    return render_template('inventory/items.html', items=items, categories=categories, 
                          item_type=item_type, search=search)

@bp.route('/items/add', methods=['GET', 'POST'])
def add_item():
    """Add new item"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        category_id = request.form.get('category_id') or None
        item_type = request.form.get('type')
        unit = request.form.get('unit', '').strip()
        min_stock = request.form.get('min_stock', 0)
        reorder_point = request.form.get('reorder_point', 0)
        
        if not code or not name or not item_type or not unit:
            flash('Please fill all required fields', 'error')
            categories = query_all("SELECT * FROM item_categories ORDER BY name")
            return render_template('inventory/add_item.html', categories=categories)
        
        # Check if code exists
        existing = query_one("SELECT id FROM items WHERE code = ?", (code,))
        if existing:
            flash('Item code already exists', 'error')
            categories = query_all("SELECT * FROM item_categories ORDER BY name")
            return render_template('inventory/add_item.html', categories=categories)
        
        item_id = execute("""
            INSERT INTO items (code, name, category_id, type, unit, min_stock, reorder_point)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (code, name, category_id, item_type, unit, min_stock, reorder_point))
        
        # Initialize inventory for all warehouses
        warehouses = query_all("SELECT id FROM warehouses")
        for wh in warehouses:
            execute("""
                INSERT INTO inventory (item_id, warehouse_id, quantity, unit_cost, total_cost)
                VALUES (?, ?, 0, 0, 0)
            """, (item_id, wh['id']))
        
        flash('Item added successfully', 'success')
        return redirect(url_for('inventory.items_list'))
    
    categories = query_all("SELECT * FROM item_categories ORDER BY name")
    return render_template('inventory/add_item.html', categories=categories)

@bp.route('/items/edit/<int:id>', methods=['GET', 'POST'])
def edit_item(id):
    """Edit item"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    item = query_one("SELECT * FROM items WHERE id = ?", (id,))
    if not item:
        flash('Item not found', 'error')
        return redirect(url_for('inventory.items_list'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category_id = request.form.get('category_id') or None
        unit = request.form.get('unit', '').strip()
        min_stock = request.form.get('min_stock', 0)
        reorder_point = request.form.get('reorder_point', 0)
        is_active = request.form.get('is_active', 1)
        
        execute("""
            UPDATE items 
            SET name = ?, category_id = ?, unit = ?, min_stock = ?, reorder_point = ?, is_active = ?
            WHERE id = ?
        """, (name, category_id, unit, min_stock, reorder_point, is_active, id))
        
        flash('Item updated successfully', 'success')
        return redirect(url_for('inventory.items_list'))
    
    categories = query_all("SELECT * FROM item_categories ORDER BY name")
    return render_template('inventory/edit_item.html', item=item, categories=categories)

@bp.route('/stock')
def stock_levels():
    """View stock levels"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    warehouse_id = request.args.get('warehouse', '')
    low_stock = request.args.get('low_stock', '')
    
    sql = """
        SELECT i.*, c.name as category_name, w.name as warehouse_name,
            inv.quantity as current_stock, inv.unit_cost, inv.total_cost
        FROM items i
        LEFT JOIN item_categories c ON i.category_id = c.id
        LEFT JOIN inventory inv ON i.id = inv.item_id
        LEFT JOIN warehouses w ON inv.warehouse_id = w.id
        WHERE i.is_active = 1
    """
    params = []
    
    if warehouse_id:
        sql += " AND inv.warehouse_id = ?"
        params.append(warehouse_id)
    
    if low_stock:
        sql += " AND inv.quantity <= i.reorder_point AND i.reorder_point > 0"
    
    sql += " ORDER BY i.name"
    
    stock = query_all(sql, params)
    warehouses = query_all("SELECT * FROM warehouses WHERE is_active = 1")
    
    return render_template('inventory/stock.html', stock=stock, warehouses=warehouses,
                          warehouse_id=warehouse_id, low_stock=low_stock)

@bp.route('/stock/adjustment', methods=['GET', 'POST'])
def stock_adjustment():
    """Stock adjustment"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        warehouse_id = request.form.get('warehouse_id')
        new_quantity = float(request.form.get('new_quantity', 0))
        reason = request.form.get('reason', '').strip()
        
        if not item_id or not warehouse_id:
            flash('Please select item and warehouse', 'error')
            return redirect(url_for('inventory.stock_adjustment'))
        
        # Get current stock
        current = get_item_stock(item_id, warehouse_id)
        current_qty = current['quantity'] if current else 0
        
        # Calculate adjustment
        adjustment = new_quantity - current_qty
        
        if adjustment != 0:
            unit_cost = current['unit_cost'] if current else 0
            update_inventory(
                item_id, warehouse_id, adjustment, unit_cost, 
                'adjustment', 'stock_adjustment', None, session['user_id']
            )
            
            flash(f'Stock adjusted from {current_qty} to {new_quantity}', 'success')
        else:
            flash('No adjustment needed', 'info')
        
        return redirect(url_for('inventory.stock_levels'))
    
    items = query_all("SELECT id, code, name FROM items WHERE is_active = 1 ORDER BY name")
    warehouses = query_all("SELECT * FROM warehouses WHERE is_active = 1")
    
    return render_template('inventory/adjustment.html', items=items, warehouses=warehouses)

@bp.route('/movements')
def movements():
    """View inventory movements"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    item_id = request.args.get('item', '')
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    
    sql = """
        SELECT m.*, i.name as item_name, i.code as item_code, w.name as warehouse_name,
            u.full_name as created_by_name
        FROM inventory_movements m
        JOIN items i ON m.item_id = i.id
        JOIN warehouses w ON m.warehouse_id = w.id
        LEFT JOIN users u ON m.created_by = u.id
        WHERE 1=1
    """
    params = []
    
    if item_id:
        sql += " AND m.item_id = ?"
        params.append(item_id)
    
    if from_date:
        sql += " AND date(m.created_at) >= ?"
        params.append(from_date)
    
    if to_date:
        sql += " AND date(m.created_at) <= ?"
        params.append(to_date)
    
    sql += " ORDER BY m.created_at DESC LIMIT 500"
    
    movements = query_all(sql, params)
    items = query_all("SELECT id, code, name FROM items WHERE is_active = 1 ORDER BY name")
    
    return render_template('inventory/movements.html', movements=movements, items=items,
                          item_id=item_id, from_date=from_date, to_date=to_date)

@bp.route('/valuation')
def valuation():
    """Inventory valuation report"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    valuation = get_inventory_valuation()
    total_value = sum(v['total_value'] or 0 for v in valuation)
    
    return render_template('inventory/valuation.html', valuation=valuation, total_value=total_value)

@bp.route('/predictions')
def predictions():
    """Smart Inventory Predictions: consumption rate, stockout forecast, reorder suggestions"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    item_type = request.args.get('type', '')
    window_days = int(request.args.get('window', 30))

    predictions = prediction_service.predict_all(item_type or None, window_days)
    reorder_needed = [p for p in predictions if p['needs_reorder']]

    return render_template('inventory/predictions.html',
                          predictions=predictions,
                          reorder_needed=reorder_needed,
                          item_type=item_type,
                          window_days=window_days)


# API Endpoints for AJAX
@bp.route('/api/predictions')
def api_predictions():
    """Predictions as JSON - reorder suggestions and stockout forecasts"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    item_type = request.args.get('type', '')
    window_days = int(request.args.get('window', 30))

    return jsonify(prediction_service.predict_all(item_type or None, window_days))


@bp.route('/api/items')
def api_items():
    """Get items as JSON"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    item_type = request.args.get('type', '')
    
    sql = "SELECT id, code, name, unit, type FROM items WHERE is_active = 1"
    params = []
    
    if item_type:
        sql += " AND type = ?"
        params.append(item_type)
    
    sql += " ORDER BY name"
    
    items = query_all(sql, params)
    return jsonify(items)

@bp.route('/api/stock/<int:item_id>')
def api_stock(item_id):
    """Get stock for item"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    warehouse_id = request.args.get('warehouse')
    stock = get_item_stock(item_id, warehouse_id)
    return jsonify(stock or {'quantity': 0, 'unit_cost': 0})

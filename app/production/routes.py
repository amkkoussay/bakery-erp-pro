"""
Production Module Routes
Handles Bill of Materials (BOM) and Production Orders
"""
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from app.production import bp
from app.db_utils import (
    query_one, query_all, execute, execute_many, 
    update_inventory, check_stock_availability, generate_production_number,
    begin_transaction, commit, rollback
)
from datetime import datetime

@bp.route('/bom')
def bom_list():
    """List all BOMs"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    boms = query_all("""
        SELECT b.*, p.name as product_name, p.code as product_code, p.unit,
            (SELECT COUNT(*) FROM bom_details WHERE bom_id = b.id) as ingredient_count
        FROM bom_headers b
        JOIN items p ON b.product_id = p.id
        WHERE b.is_active = 1
        ORDER BY p.name
    """)
    
    return render_template('production/bom_list.html', boms=boms)

@bp.route('/bom/add', methods=['GET', 'POST'])
def add_bom():
    """Add new BOM"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        version = request.form.get('version', '1.0')
        quantity_yield = float(request.form.get('quantity_yield', 1))
        
        if not product_id:
            flash('Please select a product', 'error')
            return redirect(url_for('production.add_bom'))
        
        # Check if BOM already exists for this product/version
        existing = query_one(
            "SELECT id FROM bom_headers WHERE product_id = ? AND version = ?",
            (product_id, version)
        )
        if existing:
            flash('BOM already exists for this product and version', 'error')
            return redirect(url_for('production.add_bom'))
        
        bom_id = execute("""
            INSERT INTO bom_headers (product_id, version, quantity_yield)
            VALUES (?, ?, ?)
        """, (product_id, version, quantity_yield))
        
        # Process ingredients
        ingredients = request.form.getlist('ingredient_id[]')
        quantities = request.form.getlist('quantity[]')
        units = request.form.getlist('unit[]')
        wastages = request.form.getlist('wastage[]')
        
        for i, ing_id in enumerate(ingredients):
            if ing_id and quantities[i]:
                execute("""
                    INSERT INTO bom_details (bom_id, item_id, quantity, unit, wastage_percent)
                    VALUES (?, ?, ?, ?, ?)
                """, (bom_id, ing_id, quantities[i], units[i], wastages[i] or 0))
        
        flash('BOM created successfully', 'success')
        return redirect(url_for('production.bom_list'))
    
    products = query_all("""
        SELECT id, code, name, unit FROM items 
        WHERE type IN ('finished_goods', 'semi_finished') AND is_active = 1
        ORDER BY name
    """)
    
    raw_materials = query_all("""
        SELECT id, code, name, unit FROM items 
        WHERE type = 'raw_material' AND is_active = 1
        ORDER BY name
    """)
    
    return render_template('production/add_bom.html', products=products, raw_materials=raw_materials)

@bp.route('/bom/view/<int:id>')
def view_bom(id):
    """View BOM details"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    bom = query_one("""
        SELECT b.*, p.name as product_name, p.code as product_code, p.unit
        FROM bom_headers b
        JOIN items p ON b.product_id = p.id
        WHERE b.id = ?
    """, (id,))
    
    if not bom:
        flash('BOM not found', 'error')
        return redirect(url_for('production.bom_list'))
    
    ingredients = query_all("""
        SELECT d.*, i.name as item_name, i.code as item_code
        FROM bom_details d
        JOIN items i ON d.item_id = i.id
        WHERE d.bom_id = ?
    """, (id,))
    
    return render_template('production/view_bom.html', bom=bom, ingredients=ingredients)

@bp.route('/orders')
def production_orders():
    """List production orders"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    sql = """
        SELECT po.*, p.name as product_name, p.code as product_code, w.name as warehouse_name,
            CASE 
                WHEN po.planned_quantity > 0 
                THEN ROUND((po.actual_quantity / po.planned_quantity * 100), 2)
                ELSE 0 
            END as yield_percent
        FROM production_orders po
        JOIN items p ON po.product_id = p.id
        JOIN warehouses w ON po.warehouse_id = w.id
        WHERE 1=1
    """
    params = []
    
    if status:
        sql += " AND po.status = ?"
        params.append(status)
    
    if date_from:
        sql += " AND po.production_date >= ?"
        params.append(date_from)
    
    if date_to:
        sql += " AND po.production_date <= ?"
        params.append(date_to)
    
    sql += " ORDER BY po.production_date DESC, po.order_number DESC"
    
    orders = query_all(sql, params)
    
    return render_template('production/orders.html', orders=orders, status=status,
                          date_from=date_from, date_to=date_to)

@bp.route('/orders/add', methods=['GET', 'POST'])
def add_production_order():
    """Add production order"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        bom_id = request.form.get('bom_id') or None
        planned_quantity = float(request.form.get('planned_quantity', 0))
        warehouse_id = request.form.get('warehouse_id')
        production_date = request.form.get('production_date')
        notes = request.form.get('notes', '')
        
        if not product_id or not planned_quantity or not warehouse_id or not production_date:
            flash('Please fill all required fields', 'error')
            return redirect(url_for('production.add_production_order'))
        
        order_number = generate_production_number()
        
        order_id = execute("""
            INSERT INTO production_orders 
            (order_number, product_id, bom_id, planned_quantity, warehouse_id, production_date, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_number, product_id, bom_id, planned_quantity, warehouse_id, production_date, notes, session['user_id']))
        
        # If BOM selected, create planned consumption
        if bom_id:
            bom_details = query_all("SELECT * FROM bom_details WHERE bom_id = ?", (bom_id,))
            bom_header = query_one("SELECT * FROM bom_headers WHERE id = ?", (bom_id,))
            
            if bom_header and bom_details:
                ratio = planned_quantity / bom_header['quantity_yield']
                
                for detail in bom_details:
                    planned_qty = detail['quantity'] * ratio
                    execute("""
                        INSERT INTO production_consumption 
                        (production_order_id, item_id, planned_quantity)
                        VALUES (?, ?, ?)
                    """, (order_id, detail['item_id'], planned_qty))
        
        flash(f'Production order {order_number} created', 'success')
        return redirect(url_for('production.production_orders'))
    
    products = query_all("""
        SELECT id, code, name, unit FROM items 
        WHERE type IN ('finished_goods', 'semi_finished') AND is_active = 1
        ORDER BY name
    """)
    
    warehouses = query_all("SELECT * FROM warehouses WHERE is_active = 1")
    
    return render_template('production/add_order.html', products=products, warehouses=warehouses)

@bp.route('/orders/start/<int:id>', methods=['POST'])
def start_production(id):
    """Start production order"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    order = query_one("SELECT * FROM production_orders WHERE id = ?", (id,))
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('production.production_orders'))
    
    if order['status'] != 'planned':
        flash('Order cannot be started', 'error')
        return redirect(url_for('production.production_orders'))
    
    # Check material availability
    consumption = query_all("""
        SELECT c.*, i.name as item_name, i.code as item_code
        FROM production_consumption c
        JOIN items i ON c.item_id = i.id
        WHERE c.production_order_id = ?
    """, (id,))
    
    shortages = []
    for item in consumption:
        available, qty = check_stock_availability(item['item_id'], order['warehouse_id'], item['planned_quantity'])
        if not available:
            shortages.append(f"{item['item_name']}: need {item['planned_quantity']}, have {qty}")
    
    if shortages:
        flash('Insufficient materials: ' + '; '.join(shortages), 'error')
        return redirect(url_for('production.view_order', id=id))
    
    execute("""
        UPDATE production_orders 
        SET status = 'in_progress', actual_start = datetime('now')
        WHERE id = ?
    """, (id,))
    
    flash('Production started', 'success')
    return redirect(url_for('production.view_order', id=id))

@bp.route('/orders/complete/<int:id>', methods=['GET', 'POST'])
def complete_production(id):
    """Complete production order"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    order = query_one("""
        SELECT po.*, p.name as product_name, p.code as product_code
        FROM production_orders po
        JOIN items p ON po.product_id = p.id
        WHERE po.id = ?
    """, (id,))
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('production.production_orders'))
    
    if request.method == 'POST':
        actual_quantity = float(request.form.get('actual_quantity', 0))
        waste_quantity = float(request.form.get('waste_quantity', 0))
        
        if actual_quantity <= 0:
            flash('Actual quantity must be greater than 0', 'error')
            return redirect(url_for('production.complete_production', id=id))
        
        try:
            begin_transaction()
            
            # Update order
            execute("""
                UPDATE production_orders 
                SET status = 'completed', actual_quantity = ?, waste_quantity = ?, actual_end = datetime('now')
                WHERE id = ?
            """, (actual_quantity, waste_quantity, id))
            
            # Consume materials
            consumption = query_all("""
                SELECT c.*, i.unit_cost
                FROM production_consumption c
                JOIN inventory i ON c.item_id = i.item_id AND i.warehouse_id = ?
                WHERE c.production_order_id = ?
            """, (order['warehouse_id'], id))
            
            total_cost = 0
            for item in consumption:
                actual_qty = item['planned_quantity']  # Use planned for now
                unit_cost = item['unit_cost'] or 0
                total_cost += actual_qty * unit_cost
                
                # Update consumption record
                execute("""
                    UPDATE production_consumption 
                    SET actual_quantity = ?, unit_cost = ?, total_cost = ?
                    WHERE id = ?
                """, (actual_qty, unit_cost, actual_qty * unit_cost, item['id']))
                
                # Deduct inventory
                update_inventory(
                    item['item_id'], order['warehouse_id'], -actual_qty, unit_cost,
                    'production_out', 'production_order', id, session['user_id']
                )
            
            # Add finished goods to inventory
            unit_cost = total_cost / actual_quantity if actual_quantity > 0 else 0
            update_inventory(
                order['product_id'], order['warehouse_id'], actual_quantity, unit_cost,
                'production_in', 'production_order', id, session['user_id']
            )
            
            commit()
            flash('Production completed successfully', 'success')
            return redirect(url_for('production.production_orders'))
            
        except Exception as e:
            rollback()
            flash(f'Error completing production: {str(e)}', 'error')
            return redirect(url_for('production.complete_production', id=id))
    
    consumption = query_all("""
        SELECT c.*, i.name as item_name, i.code as item_code, i.unit
        FROM production_consumption c
        JOIN items i ON c.item_id = i.id
        WHERE c.production_order_id = ?
    """, (id,))
    
    return render_template('production/complete_order.html', order=order, consumption=consumption)

@bp.route('/orders/view/<int:id>')
def view_order(id):
    """View production order"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    order = query_one("""
        SELECT po.*, p.name as product_name, p.code as product_code, p.unit,
            w.name as warehouse_name, u.full_name as created_by_name
        FROM production_orders po
        JOIN items p ON po.product_id = p.id
        JOIN warehouses w ON po.warehouse_id = w.id
        LEFT JOIN users u ON po.created_by = u.id
        WHERE po.id = ?
    """, (id,))
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('production.production_orders'))
    
    consumption = query_all("""
        SELECT c.*, i.name as item_name, i.code as item_code, i.unit
        FROM production_consumption c
        JOIN items i ON c.item_id = i.id
        WHERE c.production_order_id = ?
    """, (id,))
    
    return render_template('production/view_order.html', order=order, consumption=consumption)

@bp.route('/daily')
def daily_production():
    """Daily production report"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    production = query_all("""
        SELECT 
            po.*,
            i.name as product_name,
            i.code as product_code,
            w.name as warehouse_name,
            (po.planned_quantity - po.actual_quantity) as variance,
            CASE 
                WHEN po.planned_quantity > 0 
                THEN ROUND((po.actual_quantity / po.planned_quantity * 100), 2)
                ELSE 0 
            END as yield_percent
        FROM production_orders po
        JOIN items i ON po.product_id = i.id
        JOIN warehouses w ON po.warehouse_id = w.id
        WHERE po.production_date = ?
        ORDER BY po.order_number
    """, (date,))
    
    summary = query_one("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(planned_quantity) as total_planned,
            SUM(actual_quantity) as total_actual,
            SUM(waste_quantity) as total_waste,
            CASE 
                WHEN SUM(planned_quantity) > 0 
                THEN ROUND((SUM(actual_quantity) / SUM(planned_quantity) * 100), 2)
                ELSE 0 
            END as overall_yield
        FROM production_orders
        WHERE production_date = ? AND status != 'cancelled'
    """, (date,))
    
    return render_template('production/daily.html', production=production, summary=summary, date=date)

# API Endpoints
@bp.route('/api/bom/<int:product_id>')
def api_get_bom(product_id):
    """Get BOM for product"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    bom = query_one("""
        SELECT * FROM bom_headers 
        WHERE product_id = ? AND is_active = 1
        ORDER BY version DESC LIMIT 1
    """, (product_id,))
    
    if not bom:
        return jsonify({'error': 'No BOM found'}), 404
    
    ingredients = query_all("""
        SELECT d.*, i.name as item_name, i.code as item_code, i.unit
        FROM bom_details d
        JOIN items i ON d.item_id = i.id
        WHERE d.bom_id = ?
    """, (bom['id'],))
    
    return jsonify({
        'bom': bom,
        'ingredients': ingredients
    })

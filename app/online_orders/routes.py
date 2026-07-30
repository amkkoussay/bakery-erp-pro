"""
Online Orders Module Routes
Customer-facing ordering page and admin management
"""
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from app.online_orders import bp
from app.db_utils import query_one, query_all, execute
from datetime import datetime

# ============================================
# CUSTOMER-FACING PAGES (No login required)
# ============================================

@bp.route('/shop')
def shop():
    """Customer shop page"""
    # Check if online orders are enabled
    setting = query_one("SELECT setting_value FROM system_settings WHERE setting_key = 'online_orders_enabled'")
    if not setting or setting['setting_value'] != '1':
        return render_template('online_orders/closed.html')
    
    # Get available products
    products = query_all("""
        SELECT i.id, i.code, i.name, i.unit, pld.unit_price as price,
            c.name as category_name
        FROM items i
        LEFT JOIN price_list_details pld ON i.id = pld.item_id
        LEFT JOIN price_lists pl ON pld.price_list_id = pl.id AND pl.is_default = 1
        LEFT JOIN item_categories c ON i.category_id = c.id
        WHERE i.type = 'finished_goods' AND i.is_active = 1
        ORDER BY c.name, i.name
    """)
    
    categories = query_all("""
        SELECT DISTINCT c.id, c.name
        FROM item_categories c
        JOIN items i ON i.category_id = c.id
        WHERE i.type = 'finished_goods' AND i.is_active = 1
        ORDER BY c.name
    """)
    
    company = query_one("SELECT setting_value FROM system_settings WHERE setting_key = 'company_name'")
    
    return render_template('online_orders/shop.html', 
                          products=products, 
                          categories=categories,
                          company=company['setting_value'] if company else 'Our Bakery')

@bp.route('/order', methods=['POST'])
def place_order():
    """Place online order"""
    # Check if online orders are enabled
    setting = query_one("SELECT setting_value FROM system_settings WHERE setting_key = 'online_orders_enabled'")
    if not setting or setting['setting_value'] != '1':
        return jsonify({'error': 'Online orders are currently closed'}), 400
    
    data = request.get_json()
    
    if not data or 'items' not in data or not data['items']:
        return jsonify({'error': 'No items in cart'}), 400
    
    customer_name = data.get('customer_name', '').strip()
    customer_phone = data.get('customer_phone', '').strip()
    pickup_time = data.get('pickup_time', '')
    instructions = data.get('instructions', '')
    
    if not customer_name or not customer_phone:
        return jsonify({'error': 'Name and phone are required'}), 400
    
    try:
        order_number = f"WEB{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Calculate totals
        subtotal = 0
        for item in data['items']:
            qty = float(item.get('quantity', 1))
            price = float(item.get('price', 0))
            subtotal += qty * price
        
        order_id = execute("""
            INSERT INTO online_orders 
            (order_number, customer_name, customer_phone, customer_email, 
             pickup_time, special_instructions, subtotal, total_amount, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_number,
            customer_name,
            customer_phone,
            data.get('email', ''),
            pickup_time,
            instructions,
            subtotal,
            subtotal,
            request.remote_addr
        ))
        
        # Add order items
        for item in data['items']:
            item_id = item.get('id')
            qty = float(item.get('quantity', 1))
            price = float(item.get('price', 0))
            total = qty * price
            
            execute("""
                INSERT INTO online_order_details (online_order_id, item_id, quantity, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, item_id, qty, price, total))
        
        return jsonify({
            'success': True,
            'order_number': order_number,
            'message': 'Order placed successfully!'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/track')
def track_order():
    """Track order status"""
    order_number = request.args.get('order', '')
    order = None
    items = []
    
    if order_number:
        order = query_one("""
            SELECT * FROM online_orders WHERE order_number = ?
        """, (order_number,))
        
        if order:
            items = query_all("""
                SELECT ood.*, i.name as item_name
                FROM online_order_details ood
                JOIN items i ON ood.item_id = i.id
                WHERE ood.online_order_id = ?
            """, (order['id'],))
    
    return render_template('online_orders/track.html', order=order, items=items, order_number=order_number)

# ============================================
# ADMIN PAGES (Login required)
# ============================================

@bp.route('/admin')
def admin_orders():
    """Admin: Manage online orders"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    status = request.args.get('status', 'pending')
    
    sql = """
        SELECT oo.*, 
            (SELECT COUNT(*) FROM online_order_details WHERE online_order_id = oo.id) as item_count
        FROM online_orders oo
        WHERE 1=1
    """
    params = []
    
    if status:
        sql += " AND oo.status = ?"
        params.append(status)
    
    sql += " ORDER BY oo.created_at DESC"
    
    orders = query_all(sql, params)
    
    # Get counts for each status
    counts = query_one("""
        SELECT 
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_count,
            SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) as confirmed_count,
            SUM(CASE WHEN status = 'preparing' THEN 1 ELSE 0 END) as preparing_count,
            SUM(CASE WHEN status = 'ready' THEN 1 ELSE 0 END) as ready_count,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_count
        FROM online_orders
    """)
    
    return render_template('online_orders/admin.html', orders=orders, status=status, counts=counts)

@bp.route('/admin/view/<int:id>')
def view_order(id):
    """Admin: View order details"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    order = query_one("SELECT * FROM online_orders WHERE id = ?", (id,))
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('online_orders.admin_orders'))
    
    items = query_all("""
        SELECT ood.*, i.name as item_name, i.code as item_code
        FROM online_order_details ood
        JOIN items i ON ood.item_id = i.id
        WHERE ood.online_order_id = ?
    """, (id,))
    
    return render_template('online_orders/view.html', order=order, items=items)

@bp.route('/admin/update-status/<int:id>', methods=['POST'])
def update_status(id):
    """Admin: Update order status"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    new_status = request.form.get('status')
    if not new_status:
        flash('Status is required', 'error')
        return redirect(url_for('online_orders.view_order', id=id))
    
    execute("""
        UPDATE online_orders SET status = ?, updated_at = datetime('now') WHERE id = ?
    """, (new_status, id))
    
    flash(f'Order status updated to {new_status}', 'success')
    return redirect(url_for('online_orders.view_order', id=id))

@bp.route('/admin/convert-to-so/<int:id>', methods=['POST'])
def convert_to_so(id):
    """Admin: Convert online order to sales order"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    from app.db_utils import generate_so_number
    
    order = query_one("SELECT * FROM online_orders WHERE id = ?", (id,))
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('online_orders.admin_orders'))
    
    # Create customer if not exists
    customer = query_one("SELECT id FROM customers WHERE phone = ?", (order['customer_phone'],))
    
    if not customer:
        customer_code = f"C{datetime.now().strftime('%Y%m%d%H%M%S')}"
        customer_id = execute("""
            INSERT INTO customers (code, name, phone, email, customer_type)
            VALUES (?, ?, ?, ?, 'retail')
        """, (customer_code, order['customer_name'], order['customer_phone'], order['customer_email'] or ''))
    else:
        customer_id = customer['id']
    
    # Create sales order
    so_number = generate_so_number()
    
    so_id = execute("""
        INSERT INTO sales_orders (order_number, customer_id, order_date, notes, created_by)
        VALUES (?, ?, date('now'), ?, ?)
    """, (so_number, customer_id, f"Converted from online order {order['order_number']}", session['user_id']))
    
    # Copy items
    items = query_all("SELECT * FROM online_order_details WHERE online_order_id = ?", (id,))
    
    for item in items:
        item_detail = query_one("SELECT unit FROM items WHERE id = ?", (item['item_id'],))
        execute("""
            INSERT INTO sales_order_details (so_id, item_id, quantity_ordered, unit, unit_price, total_price)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (so_id, item['item_id'], item['quantity'], item_detail['unit'], item['unit_price'], item['total_price']))
    
    # Update totals
    execute("""
        UPDATE sales_orders 
        SET subtotal = ?, total_amount = ?
        WHERE id = ?
    """, (order['subtotal'], order['total_amount'], so_id))
    
    # Update online order
    execute("""
        UPDATE online_orders 
        SET status = 'confirmed', converted_to_so_id = ?
        WHERE id = ?
    """, (so_id, id))
    
    flash(f'Converted to Sales Order {so_number}', 'success')
    return redirect(url_for('sales.view_order', id=so_id))

@bp.route('/admin/convert-to-pos/<int:id>', methods=['POST'])
def convert_to_pos(id):
    """Admin: Convert online order to POS sale"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    order = query_one("SELECT * FROM online_orders WHERE id = ?", (id,))
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('online_orders.admin_orders'))
    
    # Get open POS session
    pos_session = query_one("""
        SELECT * FROM pos_sessions 
        WHERE user_id = ? AND status = 'open'
        ORDER BY id DESC LIMIT 1
    """, (session['user_id'],))
    
    if not pos_session:
        flash('No open POS session. Please open a session first.', 'error')
        return redirect(url_for('online_orders.view_order', id=id))
    
    # Create POS transaction
    transaction_number = f"POS{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    transaction_id = execute("""
        INSERT INTO pos_transactions 
        (transaction_number, session_id, transaction_type, 
         subtotal, total_amount, amount_paid, payment_method, notes)
        VALUES (?, ?, 'sale', ?, ?, ?, 'cash', ?)
    """, (
        transaction_number,
        pos_session['id'],
        order['subtotal'],
        order['total_amount'],
        order['total_amount'],
        f"Online order {order['order_number']}"
    ))
    
    # Copy items
    items = query_all("SELECT * FROM online_order_details WHERE online_order_id = ?", (id,))
    
    for item in items:
        execute("""
            INSERT INTO pos_transaction_details 
            (pos_transaction_id, item_id, quantity, unit_price, total_price)
            VALUES (?, ?, ?, ?, ?)
        """, (transaction_id, item['item_id'], item['quantity'], item['unit_price'], item['total_price']))
        
        # Deduct inventory
        from app.db_utils import update_inventory
        stock = query_one("""
            SELECT unit_cost FROM inventory 
            WHERE item_id = ? AND warehouse_id = ?
        """, (item['item_id'], pos_session['warehouse_id']))
        
        unit_cost = stock['unit_cost'] if stock else 0
        update_inventory(
            item['item_id'], pos_session['warehouse_id'], -item['quantity'], unit_cost,
            'sale', 'pos_transaction', transaction_id, session['user_id']
        )
    
    # Update online order
    execute("""
        UPDATE online_orders 
        SET status = 'completed', converted_to_pos_id = ?
        WHERE id = ?
    """, (transaction_id, id))
    
    flash(f'Converted to POS transaction {transaction_number}', 'success')
    return redirect(url_for('pos.print_receipt', transaction_id=transaction_id))

@bp.route('/admin/settings', methods=['GET', 'POST'])
def settings():
    """Admin: Online order settings"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        enabled = request.form.get('online_orders_enabled', '0')
        execute("""
            UPDATE system_settings SET setting_value = ? WHERE setting_key = 'online_orders_enabled'
        """, (enabled,))
        flash('Settings updated', 'success')
        return redirect(url_for('online_orders.settings'))
    
    setting = query_one("SELECT setting_value FROM system_settings WHERE setting_key = 'online_orders_enabled'")
    
    return render_template('online_orders/settings.html', enabled=setting['setting_value'] if setting else '1')

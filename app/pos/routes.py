"""
POS Module Routes
Touch-friendly Point of Sale interface
"""
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from app.pos import bp
from app.db_utils import (
    query_one, query_all, execute, update_inventory,
    check_stock_availability, begin_transaction, commit, rollback
)
from datetime import datetime

@bp.route('/')
def pos_main():
    """Main POS interface"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    # Check if session is open
    pos_session = query_one("""
        SELECT * FROM pos_sessions 
        WHERE user_id = ? AND status = 'open' AND date(session_date) = date('now')
        ORDER BY id DESC LIMIT 1
    """, (session['user_id'],))
    
    if not pos_session:
        return redirect(url_for('pos.open_session'))
    
    # Get products for POS
    products = query_all("""
        SELECT i.id, i.code, i.name, pld.unit_price as price
        FROM items i
        LEFT JOIN price_list_details pld ON i.id = pld.item_id
        LEFT JOIN price_lists pl ON pld.price_list_id = pl.id AND pl.is_default = 1
        WHERE i.type = 'finished_goods' AND i.is_active = 1
        ORDER BY i.name
    """)
    
    # Get categories for filtering
    categories = query_all("SELECT * FROM item_categories WHERE type = 'finished_goods'")
    
    # Get session transactions
    transactions = query_all("""
        SELECT * FROM pos_transactions 
        WHERE session_id = ?
        ORDER BY created_at DESC LIMIT 20
    """, (pos_session['id'],))
    
    session_totals = query_one("""
        SELECT 
            COUNT(*) as transaction_count,
            SUM(total_amount) as total_sales,
            SUM(CASE WHEN payment_method = 'cash' THEN total_amount ELSE 0 END) as cash_sales
        FROM pos_transactions
        WHERE session_id = ?
    """, (pos_session['id'],))
    
    return render_template('pos/pos.html', 
                          products=products, 
                          categories=categories,
                          pos_session=pos_session,
                          transactions=transactions,
                          session_totals=session_totals)

@bp.route('/session/open', methods=['GET', 'POST'])
def open_session():
    """Open POS session"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    # Check if already open
    existing = query_one("""
        SELECT * FROM pos_sessions 
        WHERE user_id = ? AND status = 'open' AND date(session_date) = date('now')
    """, (session['user_id'],))
    
    if existing:
        return redirect(url_for('pos.pos_main'))
    
    if request.method == 'POST':
        opening_cash = float(request.form.get('opening_cash', 0))
        warehouse_id = request.form.get('warehouse_id')
        
        if not warehouse_id:
            flash('Please select warehouse', 'error')
            return redirect(url_for('pos.open_session'))
        
        session_id = execute("""
            INSERT INTO pos_sessions (user_id, warehouse_id, session_date, opening_cash, status)
            VALUES (?, ?, date('now'), ?, 'open')
        """, (session['user_id'], warehouse_id, opening_cash))
        
        flash('Session opened', 'success')
        return redirect(url_for('pos.pos_main'))
    
    warehouses = query_all("SELECT * FROM warehouses WHERE is_active = 1")
    return render_template('pos/open_session.html', warehouses=warehouses)

@bp.route('/session/close', methods=['GET', 'POST'])
def close_session():
    """Close POS session"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    pos_session = query_one("""
        SELECT * FROM pos_sessions 
        WHERE user_id = ? AND status = 'open' AND date(session_date) = date('now')
        ORDER BY id DESC LIMIT 1
    """, (session['user_id'],))
    
    if not pos_session:
        flash('No open session found', 'error')
        return redirect(url_for('pos.pos_main'))
    
    if request.method == 'POST':
        closing_cash = float(request.form.get('closing_cash', 0))
        
        # Calculate expected cash
        sales_summary = query_one("""
            SELECT 
                COALESCE(SUM(CASE WHEN payment_method = 'cash' THEN total_amount ELSE 0 END), 0) as cash_sales,
                COALESCE(SUM(CASE WHEN payment_method = 'cash' THEN change_amount ELSE 0 END), 0) as total_change
            FROM pos_transactions
            WHERE session_id = ?
        """, (pos_session['id'],))
        
        expected_cash = pos_session['opening_cash'] + (sales_summary['cash_sales'] or 0) - (sales_summary['total_change'] or 0)
        difference = closing_cash - expected_cash
        
        execute("""
            UPDATE pos_sessions 
            SET closing_cash = ?, expected_cash = ?, cash_difference = ?, 
                closed_at = datetime('now'), status = 'closed'
            WHERE id = ?
        """, (closing_cash, expected_cash, difference, pos_session['id']))
        
        flash(f'Session closed. Difference: ${difference:.2f}', 'info')
        return redirect(url_for('dashboard'))
    
    # Get session summary
    summary = query_one("""
        SELECT 
            COUNT(*) as transaction_count,
            COALESCE(SUM(total_amount), 0) as total_sales,
            COALESCE(SUM(CASE WHEN payment_method = 'cash' THEN total_amount ELSE 0 END), 0) as cash_sales,
            COALESCE(SUM(CASE WHEN payment_method = 'card' THEN total_amount ELSE 0 END), 0) as card_sales,
            COALESCE(SUM(CASE WHEN transaction_type = 'return' THEN total_amount ELSE 0 END), 0) as returns
        FROM pos_transactions
        WHERE session_id = ?
    """, (pos_session['id'],))
    
    return render_template('pos/close_session.html', pos_session=pos_session, summary=summary)

@bp.route('/transaction', methods=['POST'])
def create_transaction():
    """Create POS transaction"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    pos_session = query_one("""
        SELECT * FROM pos_sessions 
        WHERE user_id = ? AND status = 'open'
        ORDER BY id DESC LIMIT 1
    """, (session['user_id'],))
    
    if not pos_session:
        return jsonify({'error': 'No open session'}), 400
    
    data = request.get_json()
    
    if not data or 'items' not in data or not data['items']:
        return jsonify({'error': 'No items'}), 400
    
    try:
        begin_transaction()
        
        transaction_number = f"POS{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        transaction_id = execute("""
            INSERT INTO pos_transactions 
            (transaction_number, session_id, customer_id, transaction_type, 
             subtotal, tax_amount, discount_amount, total_amount, 
             amount_paid, change_amount, payment_method, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction_number,
            pos_session['id'],
            data.get('customer_id'),
            data.get('transaction_type', 'sale'),
            data.get('subtotal', 0),
            data.get('tax', 0),
            data.get('discount', 0),
            data.get('total', 0),
            data.get('paid', 0),
            data.get('change', 0),
            data.get('payment_method', 'cash'),
            data.get('notes', '')
        ))
        
        # Process items
        for item in data['items']:
            item_id = item.get('id')
            qty = float(item.get('quantity', 1))
            price = float(item.get('price', 0))
            total = qty * price
            
            execute("""
                INSERT INTO pos_transaction_details 
                (pos_transaction_id, item_id, quantity, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?)
            """, (transaction_id, item_id, qty, price, total))
            
            # Deduct inventory
            stock = query_one("""
                SELECT unit_cost FROM inventory 
                WHERE item_id = ? AND warehouse_id = ?
            """, (item_id, pos_session['warehouse_id']))
            
            unit_cost = stock['unit_cost'] if stock else 0
            
            # Check stock
            available, current_qty = check_stock_availability(item_id, pos_session['warehouse_id'], qty)
            if not available:
                rollback()
                return jsonify({'error': f'Insufficient stock. Available: {current_qty}'}), 400
            
            update_inventory(
                item_id, pos_session['warehouse_id'], -qty, unit_cost,
                'sale', 'pos_transaction', transaction_id, session['user_id']
            )
        
        commit()
        
        return jsonify({
            'success': True,
            'transaction_number': transaction_number,
            'transaction_id': transaction_id
        })
        
    except Exception as e:
        rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/return', methods=['POST'])
def process_return():
    """Process return"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    pos_session = query_one("""
        SELECT * FROM pos_sessions 
        WHERE user_id = ? AND status = 'open'
        ORDER BY id DESC LIMIT 1
    """, (session['user_id'],))
    
    if not pos_session:
        return jsonify({'error': 'No open session'}), 400
    
    data = request.get_json()
    
    try:
        begin_transaction()
        
        transaction_number = f"RET{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        transaction_id = execute("""
            INSERT INTO pos_transactions 
            (transaction_number, session_id, transaction_type, 
             subtotal, total_amount, amount_paid, payment_method)
            VALUES (?, ?, 'return', ?, ?, ?, 'cash')
        """, (
            transaction_number,
            pos_session['id'],
            data.get('total', 0),
            data.get('total', 0),
            data.get('total', 0)
        ))
        
        # Process returned items
        for item in data['items']:
            item_id = item.get('id')
            qty = float(item.get('quantity', 1))
            price = float(item.get('price', 0))
            total = qty * price
            
            execute("""
                INSERT INTO pos_transaction_details 
                (pos_transaction_id, item_id, quantity, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?)
            """, (transaction_id, item_id, -qty, price, -total))
            
            # Add back to inventory
            stock = query_one("""
                SELECT unit_cost FROM inventory 
                WHERE item_id = ? AND warehouse_id = ?
            """, (item_id, pos_session['warehouse_id']))
            
            unit_cost = stock['unit_cost'] if stock else price
            
            update_inventory(
                item_id, pos_session['warehouse_id'], qty, unit_cost,
                'purchase', 'pos_return', transaction_id, session['user_id']
            )
        
        commit()
        
        return jsonify({
            'success': True,
            'transaction_number': transaction_number
        })
        
    except Exception as e:
        rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/receipt/<int:transaction_id>')
def print_receipt(transaction_id):
    """Print receipt"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    transaction = query_one("""
        SELECT pt.*, ps.session_date, u.full_name as cashier_name
        FROM pos_transactions pt
        JOIN pos_sessions ps ON pt.session_id = ps.id
        JOIN users u ON ps.user_id = u.id
        WHERE pt.id = ?
    """, (transaction_id,))
    
    if not transaction:
        flash('Transaction not found', 'error')
        return redirect(url_for('pos.pos_main'))
    
    items = query_all("""
        SELECT ptd.*, i.name as item_name
        FROM pos_transaction_details ptd
        JOIN items i ON ptd.item_id = i.id
        WHERE ptd.pos_transaction_id = ?
    """, (transaction_id,))
    
    company = query_one("SELECT setting_value FROM system_settings WHERE setting_key = 'company_name'")
    footer = query_one("SELECT setting_value FROM system_settings WHERE setting_key = 'receipt_footer'")
    
    return render_template('pos/receipt.html', 
                          transaction=transaction, 
                          items=items,
                          company=company['setting_value'] if company else 'Bakery',
                          footer=footer['setting_value'] if footer else 'Thank you!')

@bp.route('/history')
def history():
    """POS transaction history"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    date_from = request.args.get('date_from', datetime.now().strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    
    transactions = query_all("""
        SELECT pt.*, u.full_name as cashier_name
        FROM pos_transactions pt
        JOIN pos_sessions ps ON pt.session_id = ps.id
        JOIN users u ON ps.user_id = u.id
        WHERE date(pt.created_at) BETWEEN ? AND ?
        ORDER BY pt.created_at DESC
    """, (date_from, date_to))
    
    summary = query_one("""
        SELECT 
            COUNT(*) as transaction_count,
            COALESCE(SUM(total_amount), 0) as total_sales,
            COALESCE(SUM(CASE WHEN transaction_type = 'return' THEN total_amount ELSE 0 END), 0) as total_returns
        FROM pos_transactions pt
        JOIN pos_sessions ps ON pt.session_id = ps.id
        WHERE date(pt.created_at) BETWEEN ? AND ?
    """, (date_from, date_to))
    
    return render_template('pos/history.html', transactions=transactions, summary=summary,
                          date_from=date_from, date_to=date_to)

# API Endpoints
@bp.route('/api/product/<int:product_id>')
def api_product(product_id):
    """Get product details"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    product = query_one("""
        SELECT i.id, i.code, i.name, i.unit, pld.unit_price as price
        FROM items i
        LEFT JOIN price_list_details pld ON i.id = pld.item_id
        LEFT JOIN price_lists pl ON pld.price_list_id = pl.id AND pl.is_default = 1
        WHERE i.id = ?
    """, (product_id,))
    
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    return jsonify(product)

@bp.route('/api/check-stock/<int:product_id>')
def api_check_stock(product_id):
    """Check product stock"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    pos_session = query_one("""
        SELECT warehouse_id FROM pos_sessions 
        WHERE user_id = ? AND status = 'open'
        ORDER BY id DESC LIMIT 1
    """, (session['user_id'],))
    
    if not pos_session:
        return jsonify({'error': 'No open session'}), 400
    
    stock = query_one("""
        SELECT quantity FROM inventory 
        WHERE item_id = ? AND warehouse_id = ?
    """, (product_id, pos_session['warehouse_id']))
    
    return jsonify({'stock': stock['quantity'] if stock else 0})

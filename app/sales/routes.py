"""
Sales Module Routes
Handles Customers, Sales Orders, Invoices, and Collections
"""
from flask import render_template, request, redirect, url_for, session, flash, jsonify, Response
from app.sales import bp
from app.db_utils import (
    query_one, query_all, execute, generate_so_number, generate_invoice_number,
    update_inventory, post_sales_invoice, post_customer_payment,
    check_stock_availability, begin_transaction, commit, rollback
)
from app.services import export_service
from datetime import datetime, timedelta

@bp.route('/customers')
def customers_list():
    """List customers"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    customer_type = request.args.get('type', '')
    
    sql = """
        SELECT c.*, 
            (SELECT COUNT(*) FROM sales_orders WHERE customer_id = c.id) as order_count,
            (SELECT SUM(balance_due) FROM sales_invoices WHERE customer_id = c.id AND status IN ('open', 'partial', 'overdue')) as total_due
        FROM customers c
        WHERE c.is_active = 1
    """
    params = []
    
    if customer_type:
        sql += " AND c.customer_type = ?"
        params.append(customer_type)
    
    sql += " ORDER BY c.name"
    
    customers = query_all(sql, params)
    return render_template('sales/customers.html', customers=customers, customer_type=customer_type)

@bp.route('/customers/add', methods=['GET', 'POST'])
def add_customer():
    """Add customer"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        customer_type = request.form.get('customer_type', 'retail')
        contact = request.form.get('contact_person', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        credit_limit = request.form.get('credit_limit', 0)
        credit_days = request.form.get('credit_days', 0)
        
        if not code or not name:
            flash('Code and name are required', 'error')
            return render_template('sales/add_customer.html')
        
        existing = query_one("SELECT id FROM customers WHERE code = ?", (code,))
        if existing:
            flash('Customer code already exists', 'error')
            return render_template('sales/add_customer.html')
        
        execute("""
            INSERT INTO customers (code, name, customer_type, contact_person, phone, email, address, credit_limit, credit_days)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (code, name, customer_type, contact, phone, email, address, credit_limit, credit_days))
        
        flash('Customer added successfully', 'success')
        return redirect(url_for('sales.customers_list'))
    
    return render_template('sales/add_customer.html')

@bp.route('/price-lists')
def price_lists():
    """List price lists"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    lists = query_all("""
        SELECT pl.*, 
            (SELECT COUNT(*) FROM price_list_details WHERE price_list_id = pl.id) as item_count
        FROM price_lists pl
        ORDER BY pl.name
    """)
    return render_template('sales/price_lists.html', lists=lists)

@bp.route('/price-lists/add', methods=['GET', 'POST'])
def add_price_list():
    """Add price list"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        customer_type = request.form.get('customer_type', 'retail')
        
        if not name:
            flash('Name is required', 'error')
            return render_template('sales/add_price_list.html')
        
        pl_id = execute("""
            INSERT INTO price_lists (name, customer_type)
            VALUES (?, ?)
        """, (name, customer_type))
        
        # Process prices
        item_ids = request.form.getlist('item_id[]')
        prices = request.form.getlist('unit_price[]')
        
        for i, item_id in enumerate(item_ids):
            if item_id and prices[i]:
                execute("""
                    INSERT INTO price_list_details (price_list_id, item_id, unit_price)
                    VALUES (?, ?, ?)
                """, (pl_id, item_id, prices[i]))
        
        flash('Price list created', 'success')
        return redirect(url_for('sales.price_lists'))
    
    items = query_all("SELECT id, code, name, unit FROM items WHERE type = 'finished_goods' AND is_active = 1 ORDER BY name")
    return render_template('sales/add_price_list.html', items=items)

@bp.route('/orders')
def sales_orders():
    """List sales orders"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    status = request.args.get('status', '')
    customer = request.args.get('customer', '')
    
    sql = """
        SELECT so.*, c.name as customer_name, c.customer_type, u.full_name as created_by_name,
            (SELECT COUNT(*) FROM sales_order_details WHERE so_id = so.id) as item_count
        FROM sales_orders so
        JOIN customers c ON so.customer_id = c.id
        LEFT JOIN users u ON so.created_by = u.id
        WHERE 1=1
    """
    params = []
    
    if status:
        sql += " AND so.status = ?"
        params.append(status)
    
    if customer:
        sql += " AND so.customer_id = ?"
        params.append(customer)
    
    sql += " ORDER BY so.order_date DESC"
    
    orders = query_all(sql, params)
    customers = query_all("SELECT id, name FROM customers WHERE is_active = 1 ORDER BY name")
    
    return render_template('sales/orders.html', orders=orders, customers=customers,
                          status=status, customer_id=customer)

@bp.route('/orders/add', methods=['GET', 'POST'])
def add_order():
    """Add sales order"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        customer_id = request.form.get('customer_id')
        required_date = request.form.get('required_date')
        notes = request.form.get('notes', '')
        
        if not customer_id:
            flash('Please select a customer', 'error')
            return redirect(url_for('sales.add_order'))
        
        # Check credit limit
        customer = query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
        if customer['credit_limit'] > 0 and customer['balance'] >= customer['credit_limit']:
            flash('Customer has exceeded credit limit', 'error')
            return redirect(url_for('sales.add_order'))
        
        order_number = generate_so_number()
        
        so_id = execute("""
            INSERT INTO sales_orders (order_number, customer_id, order_date, required_date, notes, created_by)
            VALUES (?, ?, date('now'), ?, ?, ?)
        """, (order_number, customer_id, required_date, notes, session['user_id']))
        
        # Process items
        item_ids = request.form.getlist('item_id[]')
        quantities = request.form.getlist('quantity[]')
        prices = request.form.getlist('unit_price[]')
        
        subtotal = 0
        for i, item_id in enumerate(item_ids):
            if item_id and quantities[i] and prices[i]:
                qty = float(quantities[i])
                price = float(prices[i])
                total = qty * price
                subtotal += total
                
                item = query_one("SELECT unit FROM items WHERE id = ?", (item_id,))
                
                execute("""
                    INSERT INTO sales_order_details (so_id, item_id, quantity_ordered, unit, unit_price, total_price)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (so_id, item_id, qty, item['unit'], price, total))
        
        # Update totals
        execute("UPDATE sales_orders SET subtotal = ?, total_amount = ? WHERE id = ?",
                (subtotal, subtotal, so_id))
        
        flash(f'Sales order {order_number} created', 'success')
        return redirect(url_for('sales.sales_orders'))
    
    customers = query_all("SELECT id, name, customer_type FROM customers WHERE is_active = 1 ORDER BY name")
    items = query_all("""
        SELECT i.id, i.code, i.name, i.unit, pld.unit_price
        FROM items i
        LEFT JOIN price_list_details pld ON i.id = pld.item_id
        LEFT JOIN price_lists pl ON pld.price_list_id = pl.id AND pl.is_default = 1
        WHERE i.type = 'finished_goods' AND i.is_active = 1
        ORDER BY i.name
    """)
    
    return render_template('sales/add_order.html', customers=customers, items=items)

@bp.route('/orders/confirm/<int:id>', methods=['POST'])
def confirm_order(id):
    """Confirm sales order"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    order = query_one("SELECT * FROM sales_orders WHERE id = ?", (id,))
    if not order or order['status'] != 'draft':
        flash('Order not found or cannot be confirmed', 'error')
        return redirect(url_for('sales.sales_orders'))
    
    execute("UPDATE sales_orders SET status = 'confirmed' WHERE id = ?", (id,))
    flash('Sales order confirmed', 'success')
    return redirect(url_for('sales.sales_orders'))

@bp.route('/orders/ready/<int:id>', methods=['POST'])
def mark_ready(id):
    """Mark order as ready"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    order = query_one("SELECT * FROM sales_orders WHERE id = ?", (id,))
    if not order or order['status'] not in ('confirmed', 'in_progress'):
        flash('Order not found or cannot be marked ready', 'error')
        return redirect(url_for('sales.sales_orders'))
    
    execute("UPDATE sales_orders SET status = 'ready' WHERE id = ?", (id,))
    flash('Order marked as ready', 'success')
    return redirect(url_for('sales.sales_orders'))

@bp.route('/invoices')
def sales_invoices():
    """List sales invoices"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    status = request.args.get('status', '')
    invoice_type = request.args.get('type', '')
    
    sql = """
        SELECT si.*, c.name as customer_name, c.customer_type, u.full_name as created_by_name
        FROM sales_invoices si
        JOIN customers c ON si.customer_id = c.id
        LEFT JOIN users u ON si.created_by = u.id
        WHERE 1=1
    """
    params = []
    
    if status:
        sql += " AND si.status = ?"
        params.append(status)
    
    if invoice_type:
        sql += " AND si.invoice_type = ?"
        params.append(invoice_type)
    
    sql += " ORDER BY si.invoice_date DESC"
    
    invoices = query_all(sql, params)
    return render_template('sales/invoices.html', invoices=invoices, status=status, invoice_type=invoice_type)

@bp.route('/invoices/add', methods=['GET', 'POST'])
def add_invoice():
    """Add sales invoice"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        customer_id = request.form.get('customer_id')
        so_id = request.form.get('so_id') or None
        invoice_type = request.form.get('invoice_type', 'cash')
        invoice_date = request.form.get('invoice_date')
        due_date = request.form.get('due_date')
        warehouse_id = request.form.get('warehouse_id')
        notes = request.form.get('notes', '')
        
        if not customer_id or not invoice_date or not warehouse_id:
            flash('Please fill required fields', 'error')
            return redirect(url_for('sales.add_invoice'))
        
        # Check credit limit for credit sales
        if invoice_type == 'credit':
            customer = query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
            if customer['credit_limit'] > 0:
                current_balance = query_one("""
                    SELECT SUM(balance_due) as total FROM sales_invoices 
                    WHERE customer_id = ? AND status IN ('open', 'partial', 'overdue')
                """, (customer_id,))
                current_due = current_balance['total'] or 0 if current_balance else 0
        
        invoice_number = generate_invoice_number()
        
        try:
            begin_transaction()
            
            invoice_id = execute("""
                INSERT INTO sales_invoices 
                (invoice_number, customer_id, so_id, invoice_type, invoice_date, due_date, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (invoice_number, customer_id, so_id, invoice_type, invoice_date, due_date, notes, session['user_id']))
            
            # Process items
            item_ids = request.form.getlist('item_id[]')
            quantities = request.form.getlist('quantity[]')
            prices = request.form.getlist('unit_price[]')
            
            subtotal = 0
            total_cost = 0
            
            for i, item_id in enumerate(item_ids):
                if item_id and quantities[i] and prices[i]:
                    qty = float(quantities[i])
                    price = float(prices[i])
                    total = qty * price
                    subtotal += total
                    
                    # Get item cost from inventory
                    stock = query_one("""
                        SELECT unit_cost FROM inventory 
                        WHERE item_id = ? AND warehouse_id = ?
                    """, (item_id, warehouse_id))
                    unit_cost = stock['unit_cost'] if stock else 0
                    item_cost = qty * unit_cost
                    total_cost += item_cost
                    
                    item = query_one("SELECT unit FROM items WHERE id = ?", (item_id,))
                    
                    execute("""
                        INSERT INTO sales_invoice_details (invoice_id, item_id, quantity, unit, unit_price, cost_price, total_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (invoice_id, item_id, qty, item['unit'], price, unit_cost, total))
                    
                    # Deduct inventory
                    available, _ = check_stock_availability(item_id, warehouse_id, qty)
                    if not available:
                        rollback()
                        flash(f'Insufficient stock for item', 'error')
                        return redirect(url_for('sales.add_invoice'))
                    
                    update_inventory(
                        item_id, warehouse_id, -qty, unit_cost,
                        'sale', 'sales_invoice', invoice_id, session['user_id']
                    )
            
            # Update invoice totals
            execute("""
                UPDATE sales_invoices 
                SET subtotal = ?, total_amount = ?, balance_due = ?
                WHERE id = ?
            """, (subtotal, subtotal, subtotal, invoice_id))
            
            # Post to accounting
            post_sales_invoice(invoice_id, customer_id, subtotal, total_cost)
            
            # Update SO if linked
            if so_id:
                execute("UPDATE sales_orders SET status = 'delivered' WHERE id = ?", (so_id,))
            
            commit()
            flash(f'Invoice {invoice_number} created', 'success')
            return redirect(url_for('sales.sales_invoices'))
            
        except Exception as e:
            rollback()
            flash(f'Error creating invoice: {str(e)}', 'error')
            return redirect(url_for('sales.add_invoice'))
    
    customers = query_all("SELECT id, name, customer_type FROM customers WHERE is_active = 1 ORDER BY name")
    items = query_all("""
        SELECT i.id, i.code, i.name, i.unit, pld.unit_price
        FROM items i
        LEFT JOIN price_list_details pld ON i.id = pld.item_id
        LEFT JOIN price_lists pl ON pld.price_list_id = pl.id AND pl.is_default = 1
        WHERE i.type = 'finished_goods' AND i.is_active = 1
        ORDER BY i.name
    """)
    warehouses = query_all("SELECT * FROM warehouses WHERE is_active = 1")
    sos = query_all("""
        SELECT so.id, so.order_number, c.name as customer_name
        FROM sales_orders so
        JOIN customers c ON so.customer_id = c.id
        WHERE so.status IN ('confirmed', 'ready')
    """)
    
    return render_template('sales/add_invoice.html', customers=customers, items=items, 
                          warehouses=warehouses, sos=sos)

@bp.route('/collections')
def collections():
    """List customer collections"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    payments = query_all("""
        SELECT cp.*, c.name as customer_name, si.invoice_number
        FROM customer_payments cp
        JOIN customers c ON cp.customer_id = c.id
        LEFT JOIN sales_invoices si ON cp.invoice_id = si.id
        ORDER BY cp.payment_date DESC
    """)
    return render_template('sales/collections.html', payments=payments)

@bp.route('/collections/add', methods=['GET', 'POST'])
def add_collection():
    """Add customer collection"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        customer_id = request.form.get('customer_id')
        invoice_id = request.form.get('invoice_id') or None
        amount = float(request.form.get('amount', 0))
        payment_date = request.form.get('payment_date')
        payment_method = request.form.get('payment_method')
        reference = request.form.get('reference_number', '')
        notes = request.form.get('notes', '')
        
        if not customer_id or amount <= 0 or not payment_date:
            flash('Please fill required fields', 'error')
            return redirect(url_for('sales.add_collection'))
        
        receipt_number = f"RC{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        payment_id = execute("""
            INSERT INTO customer_payments 
            (receipt_number, customer_id, invoice_id, payment_date, amount, payment_method, reference_number, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (receipt_number, customer_id, invoice_id, payment_date, amount, payment_method, reference, notes, session['user_id']))
        
        # Update invoice if linked
        if invoice_id:
            invoice = query_one("SELECT * FROM sales_invoices WHERE id = ?", (invoice_id,))
            new_paid = invoice['amount_paid'] + amount
            new_balance = invoice['total_amount'] - new_paid
            
            if new_balance <= 0:
                new_status = 'paid'
            else:
                new_status = 'partial'
            
            execute("""
                UPDATE sales_invoices 
                SET amount_paid = ?, balance_due = ?, status = ?
                WHERE id = ?
            """, (new_paid, new_balance, new_status, invoice_id))
        
        # Post to accounting
        post_customer_payment(payment_id, customer_id, amount)
        
        flash('Payment recorded successfully', 'success')
        return redirect(url_for('sales.collections'))
    
    customers = query_all("SELECT id, name, balance FROM customers WHERE is_active = 1 ORDER BY name")
    invoices = query_all("""
        SELECT si.id, si.invoice_number, c.name as customer_name, si.balance_due
        FROM sales_invoices si
        JOIN customers c ON si.customer_id = c.id
        WHERE si.status IN ('open', 'partial', 'overdue')
    """)
    
    return render_template('sales/add_collection.html', customers=customers, invoices=invoices)

@bp.route('/statements/<int:customer_id>')
def customer_statement(customer_id):
    """Customer account statement"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    customer = query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
    if not customer:
        flash('Customer not found', 'error')
        return redirect(url_for('sales.customers_list'))
    
    transactions = query_all("""
        SELECT 
            'invoice' as type,
            si.invoice_date as date,
            si.invoice_number as reference,
            si.total_amount as debit,
            0 as credit,
            si.balance_due as balance
        FROM sales_invoices si
        WHERE si.customer_id = ?
        
        UNION ALL
        
        SELECT 
            'payment' as type,
            cp.payment_date as date,
            cp.receipt_number as reference,
            0 as debit,
            cp.amount as credit,
            0 as balance
        FROM customer_payments cp
        WHERE cp.customer_id = ?
        
        ORDER BY date
    """, (customer_id, customer_id))
    
    return render_template('sales/statement.html', customer=customer, transactions=transactions)

@bp.route('/statements/<int:customer_id>/export')
def export_customer_statement(customer_id):
    """Export customer account statement to CSV"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    content, filename = export_service.customer_statement_csv(customer_id)
    if content is None:
        flash('Customer not found', 'error')
        return redirect(url_for('sales.customers_list'))

    return Response(content, mimetype='text/csv',
                   headers={'Content-Disposition': f'attachment; filename={filename}'})

@bp.route('/invoices/<int:invoice_id>/export')
def export_invoice(invoice_id):
    """Export a single sales invoice to CSV"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    content, filename = export_service.sales_invoice_csv(invoice_id)
    if content is None:
        flash('Invoice not found', 'error')
        return redirect(url_for('sales.sales_invoices'))

    return Response(content, mimetype='text/csv',
                   headers={'Content-Disposition': f'attachment; filename={filename}'})

# API Endpoints
@bp.route('/api/customer/<int:customer_id>/price-list')
def api_customer_prices(customer_id):
    """Get price list for customer"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    customer = query_one("SELECT customer_type FROM customers WHERE id = ?", (customer_id,))
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    
    prices = query_all("""
        SELECT pld.item_id, pld.unit_price
        FROM price_list_details pld
        JOIN price_lists pl ON pld.price_list_id = pl.id
        WHERE pl.customer_type = ?
    """, (customer['customer_type'],))
    
    return jsonify(prices)

@bp.route('/api/customer/<int:customer_id>/invoices')
def api_customer_invoices(customer_id):
    """Get open invoices for customer"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    invoices = query_all("""
        SELECT id, invoice_number, balance_due
        FROM sales_invoices
        WHERE customer_id = ? AND status IN ('open', 'partial', 'overdue')
    """, (customer_id,))
    
    return jsonify(invoices)

"""
Purchasing Module Routes
Handles Purchase Requests, Orders, Invoices, and Payments
"""
from flask import render_template, request, redirect, url_for, session, flash, jsonify, Response
from app.purchases import bp
from app.db_utils import (
    query_one, query_all, execute, generate_pr_number, generate_po_number,
    update_inventory, post_purchase_invoice, post_supplier_payment,
    begin_transaction, commit, rollback, get_supplier_balance
)
from app.services import export_service
from datetime import datetime, timedelta

@bp.route('/suppliers')
def suppliers_list():
    """List suppliers"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    suppliers = query_all("""
        SELECT s.*, 
            (SELECT COUNT(*) FROM purchase_orders WHERE supplier_id = s.id) as order_count,
            (SELECT SUM(balance_due) FROM supplier_invoices WHERE supplier_id = s.id AND status IN ('open', 'partial', 'overdue')) as total_due
        FROM suppliers s
        WHERE s.is_active = 1
        ORDER BY s.name
    """)
    
    return render_template('purchases/suppliers.html', suppliers=suppliers)

@bp.route('/suppliers/add', methods=['GET', 'POST'])
def add_supplier():
    """Add supplier"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        contact = request.form.get('contact_person', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        payment_terms = request.form.get('payment_terms', 0)
        credit_limit = request.form.get('credit_limit', 0)
        
        if not code or not name:
            flash('Code and name are required', 'error')
            return render_template('purchases/add_supplier.html')
        
        existing = query_one("SELECT id FROM suppliers WHERE code = ?", (code,))
        if existing:
            flash('Supplier code already exists', 'error')
            return render_template('purchases/add_supplier.html')
        
        execute("""
            INSERT INTO suppliers (code, name, contact_person, phone, email, address, payment_terms, credit_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (code, name, contact, phone, email, address, payment_terms, credit_limit))
        
        flash('Supplier added successfully', 'success')
        return redirect(url_for('purchases.suppliers_list'))
    
    return render_template('purchases/add_supplier.html')

@bp.route('/requests')
def purchase_requests():
    """List purchase requests"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    status = request.args.get('status', '')
    
    sql = """
        SELECT pr.*, u.full_name as created_by_name,
            (SELECT COUNT(*) FROM purchase_request_details WHERE pr_id = pr.id) as item_count
        FROM purchase_requests pr
        LEFT JOIN users u ON pr.created_by = u.id
        WHERE 1=1
    """
    params = []
    
    if status:
        sql += " AND pr.status = ?"
        params.append(status)
    
    sql += " ORDER BY pr.request_date DESC"
    
    requests = query_all(sql, params)
    return render_template('purchases/requests.html', requests=requests, status=status)

@bp.route('/requests/add', methods=['GET', 'POST'])
def add_request():
    """Add purchase request"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        required_date = request.form.get('required_date')
        notes = request.form.get('notes', '')
        
        pr_number = generate_pr_number()
        
        pr_id = execute("""
            INSERT INTO purchase_requests (pr_number, request_date, required_date, notes, created_by)
            VALUES (?, date('now'), ?, ?, ?)
        """, (pr_number, required_date, notes, session['user_id']))
        
        # Process items
        item_ids = request.form.getlist('item_id[]')
        quantities = request.form.getlist('quantity[]')
        units = request.form.getlist('unit[]')
        item_notes = request.form.getlist('item_notes[]')
        
        for i, item_id in enumerate(item_ids):
            if item_id and quantities[i]:
                execute("""
                    INSERT INTO purchase_request_details (pr_id, item_id, quantity_requested, unit, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (pr_id, item_id, quantities[i], units[i], item_notes[i] if i < len(item_notes) else ''))
        
        flash(f'Purchase request {pr_number} created', 'success')
        return redirect(url_for('purchases.purchase_requests'))
    
    items = query_all("SELECT id, code, name, unit FROM items WHERE is_active = 1 ORDER BY name")
    return render_template('purchases/add_request.html', items=items)

@bp.route('/requests/approve/<int:id>', methods=['POST'])
def approve_request(id):
    """Approve purchase request"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    pr = query_one("SELECT * FROM purchase_requests WHERE id = ?", (id,))
    if not pr or pr['status'] != 'draft':
        flash('Request not found or cannot be approved', 'error')
        return redirect(url_for('purchases.purchase_requests'))
    
    execute("UPDATE purchase_requests SET status = 'approved' WHERE id = ?", (id,))
    flash('Purchase request approved', 'success')
    return redirect(url_for('purchases.purchase_requests'))

@bp.route('/orders')
def purchase_orders():
    """List purchase orders"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    status = request.args.get('status', '')
    supplier = request.args.get('supplier', '')
    
    sql = """
        SELECT po.*, s.name as supplier_name, u.full_name as created_by_name,
            (SELECT COUNT(*) FROM purchase_order_details WHERE po_id = po.id) as item_count
        FROM purchase_orders po
        JOIN suppliers s ON po.supplier_id = s.id
        LEFT JOIN users u ON po.created_by = u.id
        WHERE 1=1
    """
    params = []
    
    if status:
        sql += " AND po.status = ?"
        params.append(status)
    
    if supplier:
        sql += " AND po.supplier_id = ?"
        params.append(supplier)
    
    sql += " ORDER BY po.order_date DESC"
    
    orders = query_all(sql, params)
    suppliers = query_all("SELECT id, name FROM suppliers WHERE is_active = 1 ORDER BY name")
    
    return render_template('purchases/orders.html', orders=orders, suppliers=suppliers, 
                          status=status, supplier_id=supplier)

@bp.route('/orders/add', methods=['GET', 'POST'])
def add_order():
    """Add purchase order"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        supplier_id = request.form.get('supplier_id')
        pr_id = request.form.get('pr_id') or None
        expected_delivery = request.form.get('expected_delivery')
        notes = request.form.get('notes', '')
        
        if not supplier_id:
            flash('Please select a supplier', 'error')
            return redirect(url_for('purchases.add_order'))
        
        po_number = generate_po_number()
        
        po_id = execute("""
            INSERT INTO purchase_orders (po_number, supplier_id, pr_id, order_date, expected_delivery, notes, created_by)
            VALUES (?, ?, ?, date('now'), ?, ?, ?)
        """, (po_number, supplier_id, pr_id, expected_delivery, notes, session['user_id']))
        
        # Process items
        item_ids = request.form.getlist('item_id[]')
        quantities = request.form.getlist('quantity[]')
        units = request.form.getlist('unit[]')
        prices = request.form.getlist('unit_price[]')
        
        subtotal = 0
        for i, item_id in enumerate(item_ids):
            if item_id and quantities[i] and prices[i]:
                qty = float(quantities[i])
                price = float(prices[i])
                total = qty * price
                subtotal += total
                
                execute("""
                    INSERT INTO purchase_order_details (po_id, item_id, quantity_ordered, unit, unit_price, total_price)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (po_id, item_id, qty, units[i], price, total))
        
        # Update PO totals
        execute("UPDATE purchase_orders SET subtotal = ?, total_amount = ? WHERE id = ?",
                (subtotal, subtotal, po_id))
        
        # Update PR status if linked
        if pr_id:
            execute("UPDATE purchase_requests SET status = 'converted' WHERE id = ?", (pr_id,))
        
        flash(f'Purchase order {po_number} created', 'success')
        return redirect(url_for('purchases.purchase_orders'))
    
    suppliers = query_all("SELECT id, name FROM suppliers WHERE is_active = 1 ORDER BY name")
    items = query_all("SELECT id, code, name, unit FROM items WHERE is_active = 1 ORDER BY name")
    prs = query_all("SELECT id, pr_number FROM purchase_requests WHERE status = 'approved'")
    
    return render_template('purchases/add_order.html', suppliers=suppliers, items=items, prs=prs)

@bp.route('/orders/receive/<int:id>', methods=['GET', 'POST'])
def receive_order(id):
    """Receive purchase order"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    order = query_one("""
        SELECT po.*, s.name as supplier_name
        FROM purchase_orders po
        JOIN suppliers s ON po.supplier_id = s.id
        WHERE po.id = ?
    """, (id,))
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('purchases.purchase_orders'))
    
    if request.method == 'POST':
        warehouse_id = request.form.get('warehouse_id')
        
        if not warehouse_id:
            flash('Please select warehouse', 'error')
            return redirect(url_for('purchases.receive_order', id=id))
        
        try:
            begin_transaction()
            
            details = query_all("SELECT * FROM purchase_order_details WHERE po_id = ?", (id,))
            
            for detail in details:
                received_qty = float(request.form.get(f'received_{detail["id"]}', 0))
                unit_cost = float(request.form.get(f'cost_{detail["id"]}', detail['unit_price']))
                
                if received_qty > 0:
                    # Update received quantity
                    new_received = detail['quantity_received'] + received_qty
                    execute("""
                        UPDATE purchase_order_details 
                        SET quantity_received = ?
                        WHERE id = ?
                    """, (new_received, detail['id']))
                    
                    # Add to inventory
                    update_inventory(
                        detail['item_id'], warehouse_id, received_qty, unit_cost,
                        'purchase', 'purchase_order', id, session['user_id']
                    )
            
            # Update PO status
            total_ordered = sum(d['quantity_ordered'] for d in details)
            total_received = sum(d['quantity_received'] for d in details) + \
                           sum(float(request.form.get(f'received_{d["id"]}', 0)) for d in details)
            
            if total_received >= total_ordered:
                new_status = 'received'
            else:
                new_status = 'partial'
            
            execute("UPDATE purchase_orders SET status = ? WHERE id = ?", (new_status, id))
            
            commit()
            flash('Goods received successfully', 'success')
            return redirect(url_for('purchases.purchase_orders'))
            
        except Exception as e:
            rollback()
            flash(f'Error receiving goods: {str(e)}', 'error')
            return redirect(url_for('purchases.receive_order', id=id))
    
    details = query_all("""
        SELECT d.*, i.name as item_name, i.code as item_code
        FROM purchase_order_details d
        JOIN items i ON d.item_id = i.id
        WHERE d.po_id = ?
    """, (id,))
    
    warehouses = query_all("SELECT * FROM warehouses WHERE is_active = 1")
    
    return render_template('purchases/receive_order.html', order=order, details=details, warehouses=warehouses)

@bp.route('/invoices')
def supplier_invoices():
    """List supplier invoices"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    status = request.args.get('status', '')
    supplier = request.args.get('supplier', '')
    
    sql = """
        SELECT si.*, s.name as supplier_name, s.code as supplier_code,
            po.po_number
        FROM supplier_invoices si
        JOIN suppliers s ON si.supplier_id = s.id
        LEFT JOIN purchase_orders po ON si.po_id = po.id
        WHERE 1=1
    """
    params = []
    
    if status:
        sql += " AND si.status = ?"
        params.append(status)
    
    if supplier:
        sql += " AND si.supplier_id = ?"
        params.append(supplier)
    
    sql += " ORDER BY si.invoice_date DESC"
    
    invoices = query_all(sql, params)
    suppliers = query_all("SELECT id, name FROM suppliers WHERE is_active = 1 ORDER BY name")
    
    return render_template('purchases/invoices.html', invoices=invoices, suppliers=suppliers,
                          status=status, supplier_id=supplier)

@bp.route('/invoices/add', methods=['GET', 'POST'])
def add_invoice():
    """Add supplier invoice"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        supplier_id = request.form.get('supplier_id')
        po_id = request.form.get('po_id') or None
        invoice_number = request.form.get('invoice_number', '').strip()
        invoice_date = request.form.get('invoice_date')
        due_date = request.form.get('due_date')
        notes = request.form.get('notes', '')
        
        if not supplier_id or not invoice_number or not invoice_date:
            flash('Please fill required fields', 'error')
            return redirect(url_for('purchases.add_invoice'))
        
        # Calculate totals from items
        item_ids = request.form.getlist('item_id[]')
        quantities = request.form.getlist('quantity[]')
        prices = request.form.getlist('unit_price[]')
        
        subtotal = 0
        invoice_id = execute("""
            INSERT INTO supplier_invoices 
            (invoice_number, supplier_id, po_id, invoice_date, due_date, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (invoice_number, supplier_id, po_id, invoice_date, due_date, notes))
        
        for i, item_id in enumerate(item_ids):
            if item_id and quantities[i] and prices[i]:
                qty = float(quantities[i])
                price = float(prices[i])
                total = qty * price
                subtotal += total
                
                execute("""
                    INSERT INTO supplier_invoice_details (invoice_id, item_id, quantity, unit, unit_price, total_price)
                    VALUES (?, ?, ?, 'unit', ?, ?)
                """, (invoice_id, item_id, qty, price, total))
        
        # Update invoice totals
        execute("""
            UPDATE supplier_invoices 
            SET subtotal = ?, total_amount = ?, balance_due = ?
            WHERE id = ?
        """, (subtotal, subtotal, subtotal, invoice_id))
        
        # Post to accounting
        post_purchase_invoice(invoice_id, supplier_id, subtotal)
        
        flash('Invoice created successfully', 'success')
        return redirect(url_for('purchases.supplier_invoices'))
    
    suppliers = query_all("SELECT id, name FROM suppliers WHERE is_active = 1 ORDER BY name")
    items = query_all("SELECT id, code, name FROM items WHERE is_active = 1 ORDER BY name")
    pos = query_all("""
        SELECT po.id, po.po_number, s.name as supplier_name
        FROM purchase_orders po
        JOIN suppliers s ON po.supplier_id = s.id
        WHERE po.status IN ('partial', 'received')
    """)
    
    return render_template('purchases/add_invoice.html', suppliers=suppliers, items=items, pos=pos)

@bp.route('/payments')
def supplier_payments():
    """List supplier payments"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    payments = query_all("""
        SELECT sp.*, s.name as supplier_name, si.invoice_number
        FROM supplier_payments sp
        JOIN suppliers s ON sp.supplier_id = s.id
        LEFT JOIN supplier_invoices si ON sp.invoice_id = si.id
        ORDER BY sp.payment_date DESC
    """)
    
    return render_template('purchases/payments.html', payments=payments)

@bp.route('/payments/add', methods=['GET', 'POST'])
def add_payment():
    """Add supplier payment"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        supplier_id = request.form.get('supplier_id')
        invoice_id = request.form.get('invoice_id') or None
        amount = float(request.form.get('amount', 0))
        payment_date = request.form.get('payment_date')
        payment_method = request.form.get('payment_method')
        reference = request.form.get('reference_number', '')
        notes = request.form.get('notes', '')
        
        if not supplier_id or amount <= 0 or not payment_date:
            flash('Please fill required fields', 'error')
            return redirect(url_for('purchases.add_payment'))
        
        payment_number = f"SP{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        payment_id = execute("""
            INSERT INTO supplier_payments 
            (payment_number, supplier_id, invoice_id, payment_date, amount, payment_method, reference_number, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (payment_number, supplier_id, invoice_id, payment_date, amount, payment_method, reference, notes, session['user_id']))
        
        # Update invoice if linked
        if invoice_id:
            invoice = query_one("SELECT * FROM supplier_invoices WHERE id = ?", (invoice_id,))
            new_paid = invoice['amount_paid'] + amount
            new_balance = invoice['total_amount'] - new_paid
            
            if new_balance <= 0:
                new_status = 'paid'
            else:
                new_status = 'partial'
            
            execute("""
                UPDATE supplier_invoices 
                SET amount_paid = ?, balance_due = ?, status = ?
                WHERE id = ?
            """, (new_paid, new_balance, new_status, invoice_id))
        
        # Post to accounting
        post_supplier_payment(payment_id, supplier_id, amount)
        
        flash('Payment recorded successfully', 'success')
        return redirect(url_for('purchases.supplier_payments'))
    
    suppliers = query_all("SELECT id, name, balance FROM suppliers WHERE is_active = 1 ORDER BY name")
    invoices = query_all("""
        SELECT si.id, si.invoice_number, s.name as supplier_name, si.balance_due
        FROM supplier_invoices si
        JOIN suppliers s ON si.supplier_id = s.id
        WHERE si.status IN ('open', 'partial', 'overdue')
    """)
    
    return render_template('purchases/add_payment.html', suppliers=suppliers, invoices=invoices)

@bp.route('/statements/<int:supplier_id>')
def supplier_statement(supplier_id):
    """Supplier account statement"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    supplier = query_one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
    if not supplier:
        flash('Supplier not found', 'error')
        return redirect(url_for('purchases.suppliers_list'))
    
    # Get all transactions
    transactions = query_all("""
        SELECT 
            'invoice' as type,
            si.invoice_date as date,
            si.invoice_number as reference,
            si.total_amount as debit,
            0 as credit,
            si.balance_due as balance
        FROM supplier_invoices si
        WHERE si.supplier_id = ?
        
        UNION ALL
        
        SELECT 
            'payment' as type,
            sp.payment_date as date,
            sp.payment_number as reference,
            0 as debit,
            sp.amount as credit,
            0 as balance
        FROM supplier_payments sp
        WHERE sp.supplier_id = ?
        
        ORDER BY date
    """, (supplier_id, supplier_id))
    
    return render_template('purchases/statement.html', supplier=supplier, transactions=transactions)

@bp.route('/statements/<int:supplier_id>/export')
def export_supplier_statement(supplier_id):
    """Export supplier account statement to CSV"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    content, filename = export_service.supplier_statement_csv(supplier_id)
    if content is None:
        flash('Supplier not found', 'error')
        return redirect(url_for('purchases.suppliers_list'))

    return Response(content, mimetype='text/csv',
                   headers={'Content-Disposition': f'attachment; filename={filename}'})

# API Endpoints
@bp.route('/api/supplier/<int:supplier_id>/invoices')
def api_supplier_invoices(supplier_id):
    """Get open invoices for supplier"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    invoices = query_all("""
        SELECT id, invoice_number, balance_due
        FROM supplier_invoices
        WHERE supplier_id = ? AND status IN ('open', 'partial', 'overdue')
    """, (supplier_id,))
    
    return jsonify(invoices)

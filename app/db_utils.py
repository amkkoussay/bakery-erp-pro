"""
Database Utilities - Lightweight SQLite Helpers
No heavy ORMs - just plain SQL with helper functions
"""
from flask import g, current_app
import sqlite3
from datetime import datetime

def get_db():
    """Get database connection"""
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def query_one(sql, params=()):
    """Execute query and return single row"""
    db = get_db()
    cursor = db.execute(sql, params)
    row = cursor.fetchone()
    cursor.close()
    return dict(row) if row else None

def query_all(sql, params=()):
    """Execute query and return all rows"""
    db = get_db()
    cursor = db.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return [dict(row) for row in rows]

def execute(sql, params=()):
    """Execute INSERT/UPDATE/DELETE and return lastrowid"""
    db = get_db()
    cursor = db.execute(sql, params)
    lastrowid = cursor.lastrowid
    db.commit()
    cursor.close()
    return lastrowid

def execute_many(sql, params_list):
    """Execute many INSERT/UPDATE/DELETE"""
    db = get_db()
    db.executemany(sql, params_list)
    db.commit()

def begin_transaction():
    """Begin transaction"""
    db = get_db()
    db.execute("BEGIN TRANSACTION")

def commit():
    """Commit transaction"""
    db = get_db()
    db.commit()

def rollback():
    """Rollback transaction"""
    db = get_db()
    db.rollback()

# ============================================
# INVENTORY HELPERS
# ============================================

def get_item_stock(item_id, warehouse_id=None):
    """Get current stock for an item"""
    if warehouse_id:
        sql = """
            SELECT i.*, w.name as warehouse_name 
            FROM inventory i 
            JOIN warehouses w ON i.warehouse_id = w.id 
            WHERE i.item_id = ? AND i.warehouse_id = ?
        """
        return query_one(sql, (item_id, warehouse_id))
    else:
        sql = """
            SELECT SUM(quantity) as total_qty, AVG(unit_cost) as avg_cost
            FROM inventory 
            WHERE item_id = ?
        """
        return query_one(sql, (item_id,))

def update_inventory(item_id, warehouse_id, quantity, unit_cost, movement_type, 
                     reference_type=None, reference_id=None, created_by=None):
    """Update inventory with weighted average costing"""
    db = get_db()
    
    # Get current inventory
    current = query_one(
        "SELECT * FROM inventory WHERE item_id = ? AND warehouse_id = ?",
        (item_id, warehouse_id)
    )
    
    if current:
        current_qty = current['quantity'] or 0
        current_cost = current['unit_cost'] or 0
        
        if quantity > 0:  # Incoming
            # Weighted average calculation
            new_total_qty = current_qty + quantity
            if new_total_qty > 0:
                new_avg_cost = ((current_qty * current_cost) + (quantity * unit_cost)) / new_total_qty
            else:
                new_avg_cost = unit_cost
        else:  # Outgoing - use current cost
            new_total_qty = current_qty + quantity
            new_avg_cost = current_cost
        
        new_total_cost = new_total_qty * new_avg_cost
        
        db.execute("""
            UPDATE inventory 
            SET quantity = ?, unit_cost = ?, total_cost = ?, last_movement = date('now')
            WHERE item_id = ? AND warehouse_id = ?
        """, (new_total_qty, new_avg_cost, new_total_cost, item_id, warehouse_id))
    else:
        # New inventory record
        total_cost = quantity * unit_cost
        db.execute("""
            INSERT INTO inventory (item_id, warehouse_id, quantity, unit_cost, total_cost, last_movement)
            VALUES (?, ?, ?, ?, ?, date('now'))
        """, (item_id, warehouse_id, quantity, unit_cost, total_cost))
    
    # Log movement
    total_cost = quantity * unit_cost
    db.execute("""
        INSERT INTO inventory_movements 
        (item_id, warehouse_id, movement_type, quantity, unit_cost, total_cost, 
         reference_type, reference_id, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (item_id, warehouse_id, movement_type, quantity, unit_cost, total_cost,
          reference_type, reference_id, created_by))
    
    db.commit()

def check_stock_availability(item_id, warehouse_id, required_qty):
    """Check if stock is available"""
    stock = get_item_stock(item_id, warehouse_id)
    if not stock:
        return False, 0
    available = stock.get('quantity', 0) or 0
    return available >= required_qty, available

# ============================================
# ACCOUNTING HELPERS (Auto-posting)
# ============================================

def create_journal_entry(entry_date, description, reference_type=None, reference_id=None):
    """Create journal entry header"""
    entry_number = generate_number('JE', 'journal_entries', 'entry_number')
    sql = """
        INSERT INTO journal_entries (entry_number, entry_date, reference_type, reference_id, description)
        VALUES (?, ?, ?, ?, ?)
    """
    return execute(sql, (entry_number, entry_date, reference_type, reference_id, description))

def add_journal_line(entry_id, account_code, debit=0, credit=0, description=''):
    """Add journal entry line"""
    account = query_one("SELECT id FROM accounts WHERE code = ?", (account_code,))
    if not account:
        return None
    sql = """
        INSERT INTO journal_entry_details (journal_entry_id, account_id, debit_amount, credit_amount, description)
        VALUES (?, ?, ?, ?, ?)
    """
    return execute(sql, (entry_id, account['id'], debit, credit, description))

def post_purchase_invoice(invoice_id, supplier_id, total_amount):
    """Auto-post purchase invoice to accounting"""
    entry_id = create_journal_entry(
        datetime.now().strftime('%Y-%m-%d'),
        f'Purchase Invoice #{invoice_id}',
        'supplier_invoice', invoice_id
    )
    # Debit Inventory, Credit Accounts Payable
    add_journal_line(entry_id, '1300', debit=total_amount, description='Inventory')
    add_journal_line(entry_id, '2000', credit=total_amount, description='Accounts Payable')
    
    # Update supplier balance
    execute("UPDATE suppliers SET balance = balance + ? WHERE id = ?", (total_amount, supplier_id))

def post_supplier_payment(payment_id, supplier_id, amount):
    """Auto-post supplier payment"""
    entry_id = create_journal_entry(
        datetime.now().strftime('%Y-%m-%d'),
        f'Supplier Payment #{payment_id}',
        'supplier_payment', payment_id
    )
    # Debit Accounts Payable, Credit Cash/Bank
    add_journal_line(entry_id, '2000', debit=amount, description='Accounts Payable')
    add_journal_line(entry_id, '1000', credit=amount, description='Cash')
    
    # Update supplier balance
    execute("UPDATE suppliers SET balance = balance - ? WHERE id = ?", (amount, supplier_id))

def post_sales_invoice(invoice_id, customer_id, total_amount, cost_amount):
    """Auto-post sales invoice"""
    entry_id = create_journal_entry(
        datetime.now().strftime('%Y-%m-%d'),
        f'Sales Invoice #{invoice_id}',
        'sales_invoice', invoice_id
    )
    # Debit AR/Cash, Credit Revenue
    add_journal_line(entry_id, '1200', debit=total_amount, description='Accounts Receivable')
    add_journal_line(entry_id, '4000', credit=total_amount, description='Sales Revenue')
    
    # Cost of goods sold
    add_journal_line(entry_id, '5000', debit=cost_amount, description='COGS')
    add_journal_line(entry_id, '1300', credit=cost_amount, description='Inventory')
    
    # Update customer balance
    execute("UPDATE customers SET balance = balance + ? WHERE id = ?", (total_amount, customer_id))

def post_customer_payment(payment_id, customer_id, amount):
    """Auto-post customer payment"""
    entry_id = create_journal_entry(
        datetime.now().strftime('%Y-%m-%d'),
        f'Customer Payment #{payment_id}',
        'customer_payment', payment_id
    )
    # Debit Cash, Credit AR
    add_journal_line(entry_id, '1000', debit=amount, description='Cash')
    add_journal_line(entry_id, '1200', credit=amount, description='Accounts Receivable')
    
    # Update customer balance
    execute("UPDATE customers SET balance = balance - ? WHERE id = ?", (amount, customer_id))

# ============================================
# NUMBERING HELPERS
# ============================================

def generate_number(prefix, table, column):
    """Generate sequential number with prefix"""
    sql = f"SELECT {column} FROM {table} WHERE {column} LIKE ? ORDER BY id DESC LIMIT 1"
    last = query_one(sql, (f'{prefix}%',))
    
    if last:
        # Extract number from last code
        last_code = last[column]
        try:
            last_num = int(''.join(filter(str.isdigit, last_code)))
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1
    
    return f"{prefix}{new_num:06d}"

def generate_po_number():
    return generate_number('PO', 'purchase_orders', 'po_number')

def generate_pr_number():
    return generate_number('PR', 'purchase_requests', 'pr_number')

def generate_so_number():
    return generate_number('SO', 'sales_orders', 'order_number')

def generate_invoice_number():
    return generate_number('INV', 'sales_invoices', 'invoice_number')

def generate_production_number():
    return generate_number('PROD', 'production_orders', 'order_number')

# ============================================
# REPORTING HELPERS
# ============================================

def get_daily_sales(date=None):
    """Get daily sales summary"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    sql = """
        SELECT 
            COUNT(*) as transaction_count,
            SUM(total_amount) as total_sales,
            SUM(amount_paid) as cash_received,
            SUM(total_amount - amount_paid) as credit_sales
        FROM sales_invoices
        WHERE invoice_date = ? AND status != 'cancelled'
    """
    return query_one(sql, (date,))

def get_customer_balance(customer_id=None):
    """Get customer balance"""
    if customer_id:
        return query_one("SELECT balance FROM customers WHERE id = ?", (customer_id,))
    else:
        return query_all("""
            SELECT c.*, 
                (SELECT SUM(balance_due) FROM sales_invoices 
                 WHERE customer_id = c.id AND status IN ('open', 'partial', 'overdue')) as total_due
            FROM customers c
            WHERE c.balance != 0
            ORDER BY c.name
        """)

def get_supplier_balance(supplier_id=None):
    """Get supplier balance"""
    if supplier_id:
        return query_one("SELECT balance FROM suppliers WHERE id = ?", (supplier_id,))
    else:
        return query_all("""
            SELECT s.*, 
                (SELECT SUM(balance_due) FROM supplier_invoices 
                 WHERE supplier_id = s.id AND status IN ('open', 'partial', 'overdue')) as total_due
            FROM suppliers s
            WHERE s.balance != 0
            ORDER BY s.name
        """)

def get_inventory_valuation():
    """Get inventory valuation report"""
    return query_all("""
        SELECT 
            i.id, i.code, i.name, i.type, i.unit,
            COALESCE(SUM(inv.quantity), 0) as total_qty,
            COALESCE(AVG(inv.unit_cost), 0) as avg_cost,
            COALESCE(SUM(inv.total_cost), 0) as total_value
        FROM items i
        LEFT JOIN inventory inv ON i.id = inv.item_id
        WHERE i.is_active = 1
        GROUP BY i.id, i.code, i.name, i.type, i.unit
        ORDER BY i.name
    """)

def get_daily_production(date=None):
    """Get daily production report"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    return query_all("""
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

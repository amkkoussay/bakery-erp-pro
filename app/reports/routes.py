"""
Reports Module Routes
Daily production, inventory valuation, sales summary, balances, profit
"""
from flask import render_template, request, redirect, url_for, session, flash, jsonify, Response
from app.reports import bp
from app.db_utils import query_one, query_all
from app.services import profit_service, export_service
from datetime import datetime, timedelta
import csv
import io

@bp.route('/')
def reports_dashboard():
    """Reports dashboard"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Quick stats
    daily_sales = query_one("""
        SELECT COALESCE(SUM(total_amount), 0) as total
        FROM sales_invoices
        WHERE invoice_date = ? AND status != 'cancelled'
    """, (today,))
    
    pos_sales = query_one("""
        SELECT COALESCE(SUM(total_amount), 0) as total
        FROM pos_transactions
        WHERE date(created_at) = ? AND transaction_type = 'sale'
    """, (today,))
    
    production = query_one("""
        SELECT COALESCE(SUM(actual_quantity), 0) as total
        FROM production_orders
        WHERE production_date = ? AND status = 'completed'
    """, (today,))
    
    inventory_value = query_one("""
        SELECT COALESCE(SUM(total_cost), 0) as total
        FROM inventory
    """)
    
    return render_template('reports/dashboard.html',
                          daily_sales=daily_sales['total'] if daily_sales else 0,
                          pos_sales=pos_sales['total'] if pos_sales else 0,
                          production=production['total'] if production else 0,
                          inventory_value=inventory_value['total'] if inventory_value else 0,
                          today=today)

@bp.route('/daily-production')
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
            i.unit,
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
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_orders,
            SUM(planned_quantity) as total_planned,
            SUM(actual_quantity) as total_actual,
            SUM(waste_quantity) as total_waste,
            CASE 
                WHEN SUM(planned_quantity) > 0 
                THEN ROUND((SUM(actual_quantity) / SUM(planned_quantity) * 100), 2)
                ELSE 0 
            END as overall_yield
        FROM production_orders
        WHERE production_date = ?
    """, (date,))
    
    # Material usage
    materials = query_all("""
        SELECT 
            i.name as material_name,
            i.unit,
            SUM(pc.actual_quantity) as total_used,
            SUM(pc.total_cost) as total_cost
        FROM production_consumption pc
        JOIN production_orders po ON pc.production_order_id = po.id
        JOIN items i ON pc.item_id = i.id
        WHERE po.production_date = ?
        GROUP BY i.id, i.name, i.unit
        ORDER BY total_cost DESC
    """, (date,))
    
    return render_template('reports/daily_production.html', 
                          production=production, 
                          summary=summary,
                          materials=materials,
                          date=date)

@bp.route('/inventory-valuation')
def inventory_valuation():
    """Inventory valuation report"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    category = request.args.get('category', '')
    
    sql = """
        SELECT 
            i.id, i.code, i.name, i.type, i.unit,
            c.name as category_name,
            COALESCE(SUM(inv.quantity), 0) as total_qty,
            COALESCE(AVG(inv.unit_cost), 0) as avg_cost,
            COALESCE(SUM(inv.total_cost), 0) as total_value
        FROM items i
        LEFT JOIN item_categories c ON i.category_id = c.id
        LEFT JOIN inventory inv ON i.id = inv.item_id
        WHERE i.is_active = 1
    """
    params = []
    
    if category:
        sql += " AND i.category_id = ?"
        params.append(category)
    
    sql += " GROUP BY i.id, i.code, i.name, i.type, i.unit, c.name ORDER BY i.name"
    
    items = query_all(sql, params)
    
    # Summary by type
    summary = query_all("""
        SELECT 
            i.type,
            COUNT(*) as item_count,
            COALESCE(SUM(inv.total_cost), 0) as total_value
        FROM items i
        LEFT JOIN inventory inv ON i.id = inv.item_id
        WHERE i.is_active = 1
        GROUP BY i.type
        ORDER BY total_value DESC
    """)
    
    total_value = sum(s['total_value'] for s in summary)
    
    categories = query_all("SELECT * FROM item_categories ORDER BY name")
    
    return render_template('reports/inventory_valuation.html',
                          items=items,
                          summary=summary,
                          total_value=total_value,
                          categories=categories,
                          selected_category=category)

@bp.route('/sales-summary')
def sales_summary():
    """Sales summary report"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    date_from = request.args.get('date_from', datetime.now().strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    
    # Sales invoices
    invoices = query_all("""
        SELECT 
            si.*,
            c.name as customer_name,
            c.customer_type
        FROM sales_invoices si
        JOIN customers c ON si.customer_id = c.id
        WHERE si.invoice_date BETWEEN ? AND ?
        AND si.status != 'cancelled'
        ORDER BY si.invoice_date DESC
    """, (date_from, date_to))
    
    # Summary
    summary = query_one("""
        SELECT 
            COUNT(*) as invoice_count,
            COALESCE(SUM(total_amount), 0) as total_sales,
            COALESCE(SUM(amount_paid), 0) as total_paid,
            COALESCE(SUM(balance_due), 0) as total_balance
        FROM sales_invoices
        WHERE invoice_date BETWEEN ? AND ?
        AND status != 'cancelled'
    """, (date_from, date_to))
    
    # By customer type
    by_type = query_all("""
        SELECT 
            c.customer_type,
            COUNT(*) as invoice_count,
            COALESCE(SUM(si.total_amount), 0) as total_sales
        FROM sales_invoices si
        JOIN customers c ON si.customer_id = c.id
        WHERE si.invoice_date BETWEEN ? AND ?
        AND si.status != 'cancelled'
        GROUP BY c.customer_type
    """, (date_from, date_to))
    
    # POS sales
    pos = query_one("""
        SELECT 
            COUNT(*) as transaction_count,
            COALESCE(SUM(total_amount), 0) as total_sales
        FROM pos_transactions
        WHERE date(created_at) BETWEEN ? AND ?
        AND transaction_type = 'sale'
    """, (date_from, date_to))
    
    # Top products
    top_products = query_all("""
        SELECT 
            i.name as product_name,
            SUM(sid.quantity) as total_qty,
            SUM(sid.total_price) as total_sales
        FROM sales_invoice_details sid
        JOIN items i ON sid.item_id = i.id
        JOIN sales_invoices si ON sid.invoice_id = si.id
        WHERE si.invoice_date BETWEEN ? AND ?
        AND si.status != 'cancelled'
        GROUP BY i.id, i.name
        ORDER BY total_sales DESC
        LIMIT 10
    """, (date_from, date_to))
    
    return render_template('reports/sales_summary.html',
                          invoices=invoices,
                          summary=summary,
                          by_type=by_type,
                          pos=pos,
                          top_products=top_products,
                          date_from=date_from,
                          date_to=date_to)

@bp.route('/customer-balances')
def customer_balances():
    """Customer balances report"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    customers = query_all("""
        SELECT 
            c.*,
            COALESCE((
                SELECT SUM(balance_due) 
                FROM sales_invoices 
                WHERE customer_id = c.id AND status IN ('open', 'partial', 'overdue')
            ), 0) as total_due,
            COALESCE((
                SELECT SUM(total_amount)
                FROM sales_invoices
                WHERE customer_id = c.id AND status != 'cancelled'
                AND invoice_date >= date('now', '-30 days')
            ), 0) as sales_30d
        FROM customers c
        WHERE c.is_active = 1
        ORDER BY total_due DESC
    """)
    
    summary = query_one("""
        SELECT 
            COUNT(*) as customer_count,
            COALESCE(SUM(balance), 0) as total_balance,
            COALESCE(SUM((
                SELECT SUM(balance_due) 
                FROM sales_invoices 
                WHERE customer_id = c.id AND status IN ('open', 'partial', 'overdue')
            )), 0) as total_due
        FROM customers c
        WHERE c.is_active = 1
    """)
    
    # Aging
    aging = query_all("""
        SELECT 
            c.name as customer_name,
            COALESCE(SUM(CASE WHEN julianday('now') - julianday(si.invoice_date) <= 30 THEN si.balance_due ELSE 0 END), 0) as days_0_30,
            COALESCE(SUM(CASE WHEN julianday('now') - julianday(si.invoice_date) BETWEEN 31 AND 60 THEN si.balance_due ELSE 0 END), 0) as days_31_60,
            COALESCE(SUM(CASE WHEN julianday('now') - julianday(si.invoice_date) BETWEEN 61 AND 90 THEN si.balance_due ELSE 0 END), 0) as days_61_90,
            COALESCE(SUM(CASE WHEN julianday('now') - julianday(si.invoice_date) > 90 THEN si.balance_due ELSE 0 END), 0) as days_over_90
        FROM customers c
        LEFT JOIN sales_invoices si ON c.id = si.customer_id AND si.status IN ('open', 'partial', 'overdue')
        WHERE c.is_active = 1
        GROUP BY c.id, c.name
        HAVING (days_0_30 + days_31_60 + days_61_90 + days_over_90) > 0
        ORDER BY (days_0_30 + days_31_60 + days_61_90 + days_over_90) DESC
    """)
    
    return render_template('reports/customer_balances.html',
                          customers=customers,
                          summary=summary,
                          aging=aging)

@bp.route('/supplier-balances')
def supplier_balances():
    """Supplier balances report"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    suppliers = query_all("""
        SELECT 
            s.*,
            COALESCE((
                SELECT SUM(balance_due) 
                FROM supplier_invoices 
                WHERE supplier_id = s.id AND status IN ('open', 'partial', 'overdue')
            ), 0) as total_due
        FROM suppliers s
        WHERE s.is_active = 1
        ORDER BY total_due DESC
    """)
    
    summary = query_one("""
        SELECT 
            COUNT(*) as supplier_count,
            COALESCE(SUM(balance), 0) as total_balance,
            COALESCE(SUM((
                SELECT SUM(balance_due) 
                FROM supplier_invoices 
                WHERE supplier_id = s.id AND status IN ('open', 'partial', 'overdue')
            )), 0) as total_due
        FROM suppliers s
        WHERE s.is_active = 1
    """)
    
    return render_template('reports/supplier_balances.html',
                          suppliers=suppliers,
                          summary=summary)

@bp.route('/profit-overview')
def profit_overview():
    """Profit overview report"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    date_from = request.args.get('date_from', datetime.now().strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    
    # Revenue
    revenue = query_one("""
        SELECT COALESCE(SUM(total_amount), 0) as total
        FROM sales_invoices
        WHERE invoice_date BETWEEN ? AND ?
        AND status != 'cancelled'
    """, (date_from, date_to))
    
    pos_revenue = query_one("""
        SELECT COALESCE(SUM(total_amount), 0) as total
        FROM pos_transactions
        WHERE date(created_at) BETWEEN ? AND ?
        AND transaction_type = 'sale'
    """, (date_from, date_to))
    
    # Cost of goods sold
    cogs = query_one("""
        SELECT COALESCE(SUM(sid.cost_price * sid.quantity), 0) as total
        FROM sales_invoice_details sid
        JOIN sales_invoices si ON sid.invoice_id = si.id
        WHERE si.invoice_date BETWEEN ? AND ?
        AND si.status != 'cancelled'
    """, (date_from, date_to))
    
    # Purchases
    purchases = query_one("""
        SELECT COALESCE(SUM(total_amount), 0) as total
        FROM supplier_invoices
        WHERE invoice_date BETWEEN ? AND ?
        AND status != 'cancelled'
    """, (date_from, date_to))
    
    # Production costs
    production_cost = query_one("""
        SELECT COALESCE(SUM(pc.total_cost), 0) as total
        FROM production_consumption pc
        JOIN production_orders po ON pc.production_order_id = po.id
        WHERE po.production_date BETWEEN ? AND ?
        AND po.status = 'completed'
    """, (date_from, date_to))
    
    total_revenue = (revenue['total'] or 0) + (pos_revenue['total'] or 0)
    total_cogs = (cogs['total'] or 0)
    gross_profit = total_revenue - total_cogs
    gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    return render_template('reports/profit_overview.html',
                          revenue=total_revenue,
                          pos_revenue=pos_revenue['total'] or 0,
                          invoice_revenue=revenue['total'] or 0,
                          cogs=total_cogs,
                          purchases=purchases['total'] or 0,
                          production_cost=production_cost['total'] or 0,
                          gross_profit=gross_profit,
                          gross_margin=gross_margin,
                          date_from=date_from,
                          date_to=date_to)

@bp.route('/best-sellers')
def best_sellers():
    """Best selling products"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    
    # From sales invoices
    invoice_products = query_all("""
        SELECT 
            i.id,
            i.code,
            i.name,
            SUM(sid.quantity) as total_qty,
            SUM(sid.total_price) as total_revenue,
            AVG(sid.unit_price) as avg_price
        FROM sales_invoice_details sid
        JOIN items i ON sid.item_id = i.id
        JOIN sales_invoices si ON sid.invoice_id = si.id
        WHERE si.invoice_date BETWEEN ? AND ?
        AND si.status != 'cancelled'
        GROUP BY i.id, i.code, i.name
        ORDER BY total_qty DESC
        LIMIT 20
    """, (date_from, date_to))
    
    # From POS
    pos_products = query_all("""
        SELECT 
            i.id,
            i.code,
            i.name,
            SUM(ptd.quantity) as total_qty,
            SUM(ptd.total_price) as total_revenue
        FROM pos_transaction_details ptd
        JOIN items i ON ptd.item_id = i.id
        JOIN pos_transactions pt ON ptd.pos_transaction_id = pt.id
        WHERE date(pt.created_at) BETWEEN ? AND ?
        AND pt.transaction_type = 'sale'
        GROUP BY i.id, i.code, i.name
        ORDER BY total_qty DESC
        LIMIT 20
    """, (date_from, date_to))
    
    return render_template('reports/best_sellers.html',
                          invoice_products=invoice_products,
                          pos_products=pos_products,
                          date_from=date_from,
                          date_to=date_to)

@bp.route('/profitability')
def profitability():
    """Product profit margins: recipe cost vs. selling price, real sales volume"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))

    products = profit_service.product_profitability(date_from, date_to)
    total_revenue = sum(p['revenue'] or 0 for p in products)
    total_profit = sum(p['actual_profit'] or 0 for p in products if p['actual_profit'] is not None)
    missing_recipe = [p for p in products if not p['has_recipe'] and p['qty_sold']]

    return render_template('reports/profitability.html',
                          products=products,
                          total_revenue=total_revenue,
                          total_profit=total_profit,
                          missing_recipe=missing_recipe,
                          date_from=date_from,
                          date_to=date_to)


@bp.route('/waste')
def waste_report():
    """Money lost from waste - inventory waste movements + production waste"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))

    waste = profit_service.waste_cost(date_from, date_to)

    return render_template('reports/waste.html',
                          waste=waste,
                          date_from=date_from,
                          date_to=date_to)


@bp.route('/export/<report_type>')
def export_report(report_type):
    """Export report to CSV"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    if report_type == 'inventory':
        writer.writerow(['Code', 'Name', 'Type', 'Category', 'Unit', 'Quantity', 'Unit Cost', 'Total Value'])
        
        items = query_all("""
            SELECT i.code, i.name, i.type, c.name as category, i.unit,
                COALESCE(SUM(inv.quantity), 0) as qty,
                COALESCE(AVG(inv.unit_cost), 0) as cost,
                COALESCE(SUM(inv.total_cost), 0) as value
            FROM items i
            LEFT JOIN item_categories c ON i.category_id = c.id
            LEFT JOIN inventory inv ON i.id = inv.item_id
            WHERE i.is_active = 1
            GROUP BY i.id, i.code, i.name, i.type, c.name, i.unit
            ORDER BY i.name
        """)
        
        for item in items:
            writer.writerow([
                item['code'], item['name'], item['type'], item['category'],
                item['unit'], item['qty'], item['cost'], item['value']
            ])
        
        filename = f"inventory_valuation_{datetime.now().strftime('%Y%m%d')}.csv"
    
    elif report_type == 'customers':
        writer.writerow(['Code', 'Name', 'Type', 'Phone', 'Credit Limit', 'Balance', 'Total Due'])
        
        customers = query_all("""
            SELECT c.code, c.name, c.customer_type, c.phone, c.credit_limit, c.balance,
                COALESCE((
                    SELECT SUM(balance_due) 
                    FROM sales_invoices 
                    WHERE customer_id = c.id AND status IN ('open', 'partial', 'overdue')
                ), 0) as total_due
            FROM customers c
            WHERE c.is_active = 1
            ORDER BY c.name
        """)
        
        for c in customers:
            writer.writerow([
                c['code'], c['name'], c['customer_type'], c['phone'],
                c['credit_limit'], c['balance'], c['total_due']
            ])
        
        filename = f"customer_balances_{datetime.now().strftime('%Y%m%d')}.csv"
    
    elif report_type == 'production':
        date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
        content, filename = export_service.production_report_csv(date_from, date_to)
        return Response(content, mimetype='text/csv',
                       headers={'Content-Disposition': f'attachment; filename={filename}'})

    elif report_type == 'profitability':
        date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
        products = profit_service.product_profitability(date_from, date_to)
        content, filename = export_service.profitability_csv(products, date_from, date_to)
        return Response(content, mimetype='text/csv',
                       headers={'Content-Disposition': f'attachment; filename={filename}'})

    else:
        flash('Unknown report type', 'error')
        return redirect(url_for('reports.reports_dashboard'))
    
    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

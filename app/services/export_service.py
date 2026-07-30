"""
Reports & Export
==================
Turns report data into downloadable CSV files. Kept deliberately simple
(stdlib csv module) so it works offline on low-memory devices with no
extra dependencies.
"""
import csv
import io
from datetime import datetime
from app.db_utils import query_one, query_all


def _csv_response_data(rows_with_header):
    """rows_with_header: list of rows, first row is the header."""
    output = io.StringIO()
    writer = csv.writer(output)
    for row in rows_with_header:
        writer.writerow(row)
    output.seek(0)
    return output.getvalue()


def customer_statement_csv(customer_id):
    customer = query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
    if not customer:
        return None, None

    transactions = query_all("""
        SELECT 'invoice' as type, si.invoice_date as date, si.invoice_number as reference,
               si.total_amount as debit, 0 as credit
        FROM sales_invoices si
        WHERE si.customer_id = ?
        UNION ALL
        SELECT 'payment' as type, cp.payment_date as date, cp.receipt_number as reference,
               0 as debit, cp.amount as credit
        FROM customer_payments cp
        WHERE cp.customer_id = ?
        ORDER BY date
    """, (customer_id, customer_id))

    rows = [['Date', 'Type', 'Reference', 'Debit', 'Credit', 'Running Balance']]
    balance = 0
    for t in transactions:
        balance += (t['debit'] or 0) - (t['credit'] or 0)
        rows.append([t['date'], t['type'], t['reference'], t['debit'], t['credit'], round(balance, 2)])
    rows.append([])
    rows.append(['Current Account Balance', '', '', '', '', customer['balance']])

    filename = f"customer_statement_{customer['code']}_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response_data(rows), filename


def supplier_statement_csv(supplier_id):
    supplier = query_one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
    if not supplier:
        return None, None

    transactions = query_all("""
        SELECT 'invoice' as type, si.invoice_date as date, si.invoice_number as reference,
               si.total_amount as debit, 0 as credit
        FROM supplier_invoices si
        WHERE si.supplier_id = ?
        UNION ALL
        SELECT 'payment' as type, sp.payment_date as date, sp.payment_number as reference,
               0 as debit, sp.amount as credit
        FROM supplier_payments sp
        WHERE sp.supplier_id = ?
        ORDER BY date
    """, (supplier_id, supplier_id))

    rows = [['Date', 'Type', 'Reference', 'Debit', 'Credit', 'Running Balance']]
    balance = 0
    for t in transactions:
        balance += (t['debit'] or 0) - (t['credit'] or 0)
        rows.append([t['date'], t['type'], t['reference'], t['debit'], t['credit'], round(balance, 2)])
    rows.append([])
    rows.append(['Current Account Balance', '', '', '', '', supplier['balance']])

    filename = f"supplier_statement_{supplier['code']}_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response_data(rows), filename


def sales_invoice_csv(invoice_id):
    invoice = query_one("""
        SELECT si.*, c.name as customer_name, c.code as customer_code
        FROM sales_invoices si
        JOIN customers c ON si.customer_id = c.id
        WHERE si.id = ?
    """, (invoice_id,))
    if not invoice:
        return None, None

    lines = query_all("""
        SELECT sid.*, i.name as item_name, i.code as item_code
        FROM sales_invoice_details sid
        JOIN items i ON sid.item_id = i.id
        WHERE sid.invoice_id = ?
    """, (invoice_id,))

    rows = [
        ['Invoice', invoice['invoice_number']],
        ['Customer', invoice['customer_name']],
        ['Date', invoice['invoice_date']],
        ['Status', invoice['status']],
        [],
        ['Item Code', 'Item', 'Quantity', 'Unit', 'Unit Price', 'Total'],
    ]
    for l in lines:
        rows.append([l['item_code'], l['item_name'], l['quantity'], l['unit'], l['unit_price'], l['total_price']])
    rows.append([])
    rows.append(['Subtotal', invoice['subtotal']])
    rows.append(['Tax', invoice['tax_amount']])
    rows.append(['Discount', invoice['discount_amount']])
    rows.append(['Total', invoice['total_amount']])
    rows.append(['Paid', invoice['amount_paid']])
    rows.append(['Balance Due', invoice['balance_due']])

    filename = f"invoice_{invoice['invoice_number']}.csv"
    return _csv_response_data(rows), filename


def production_report_csv(date_from, date_to):
    orders = query_all("""
        SELECT po.order_number, po.production_date, i.name as product_name, i.unit,
               po.planned_quantity, po.actual_quantity, po.waste_quantity, po.status
        FROM production_orders po
        JOIN items i ON po.product_id = i.id
        WHERE po.production_date BETWEEN ? AND ?
        ORDER BY po.production_date, po.order_number
    """, (date_from, date_to))

    rows = [['Order Number', 'Date', 'Product', 'Unit', 'Planned Qty', 'Actual Qty', 'Waste Qty', 'Status']]
    for o in orders:
        rows.append([
            o['order_number'], o['production_date'], o['product_name'], o['unit'],
            o['planned_quantity'], o['actual_quantity'], o['waste_quantity'], o['status']
        ])

    filename = f"production_report_{date_from}_to_{date_to}.csv"
    return _csv_response_data(rows), filename


def profitability_csv(product_rows, date_from, date_to):
    """product_rows: output of profit_service.product_profitability()"""
    rows = [['Code', 'Name', 'Qty Sold', 'Revenue', 'Cost/Unit', 'Selling Price',
              'Profit/Unit', 'Margin %', 'Actual Profit']]
    for r in product_rows:
        rows.append([
            r['code'], r['name'], r['qty_sold'], r['revenue'],
            r['cost_per_unit'], r['selling_price'], r['profit_per_unit'],
            r['margin_percent'], r['actual_profit']
        ])
    filename = f"profitability_{date_from}_to_{date_to}.csv"
    return _csv_response_data(rows), filename

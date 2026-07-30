-- Bakery ERP Database Schema
-- SQLite with foreign keys and optimized indexes
-- Designed for low-memory, offline-first operation

PRAGMA foreign_keys = ON;

-- ============================================
-- CORE TABLES
-- ============================================

-- Users & Authentication
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'manager', 'cashier', 'production')),
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Warehouses/Locations
CREATE TABLE warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT,
    is_active INTEGER DEFAULT 1
);

-- ============================================
-- INVENTORY TABLES
-- ============================================

-- Item Categories
CREATE TABLE item_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('raw_material', 'semi_finished', 'finished_goods', 'packaging', 'other'))
);

-- Items/Products Master
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category_id INTEGER REFERENCES item_categories(id),
    type TEXT NOT NULL CHECK(type IN ('raw_material', 'semi_finished', 'finished_goods', 'packaging', 'other')),
    unit TEXT NOT NULL,
    min_stock REAL DEFAULT 0,
    max_stock REAL DEFAULT 0,
    reorder_point REAL DEFAULT 0,
    preferred_supplier_id INTEGER REFERENCES suppliers(id),
    safety_stock_days INTEGER DEFAULT 2,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inventory Stock (current quantities by warehouse)
CREATE TABLE inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    quantity REAL NOT NULL DEFAULT 0,
    unit_cost REAL DEFAULT 0,
    total_cost REAL DEFAULT 0,
    last_movement DATE,
    UNIQUE(item_id, warehouse_id)
);

-- Inventory Movements (transaction log)
CREATE TABLE inventory_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    movement_type TEXT NOT NULL CHECK(movement_type IN ('purchase', 'production_in', 'production_out', 'sale', 'transfer_in', 'transfer_out', 'adjustment', 'waste')),
    quantity REAL NOT NULL,
    unit_cost REAL DEFAULT 0,
    total_cost REAL DEFAULT 0,
    reference_type TEXT,
    reference_id INTEGER,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster movement queries
CREATE INDEX idx_movements_item ON inventory_movements(item_id);
CREATE INDEX idx_movements_date ON inventory_movements(created_at);
CREATE INDEX idx_movements_reference ON inventory_movements(reference_type, reference_id);

-- ============================================
-- PRODUCTION TABLES
-- ============================================

-- Bill of Materials (BOM)
CREATE TABLE bom_headers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES items(id),
    version TEXT DEFAULT '1.0',
    quantity_yield REAL NOT NULL DEFAULT 1,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_id, version)
);

-- BOM Details (ingredients)
CREATE TABLE bom_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bom_id INTEGER NOT NULL REFERENCES bom_headers(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    wastage_percent REAL DEFAULT 0
);

CREATE INDEX idx_bom_details_bom ON bom_details(bom_id);

-- Production Orders
CREATE TABLE production_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT UNIQUE NOT NULL,
    product_id INTEGER NOT NULL REFERENCES items(id),
    bom_id INTEGER REFERENCES bom_headers(id),
    planned_quantity REAL NOT NULL,
    actual_quantity REAL DEFAULT 0,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned', 'in_progress', 'completed', 'cancelled')),
    production_date DATE NOT NULL,
    planned_start DATE,
    actual_start TIMESTAMP,
    actual_end TIMESTAMP,
    waste_quantity REAL DEFAULT 0,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_production_date ON production_orders(production_date);
CREATE INDEX idx_production_status ON production_orders(status);

-- Production Material Consumption
CREATE TABLE production_consumption (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_order_id INTEGER NOT NULL REFERENCES production_orders(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    planned_quantity REAL NOT NULL,
    actual_quantity REAL DEFAULT 0,
    unit_cost REAL DEFAULT 0,
    total_cost REAL DEFAULT 0
);

-- ============================================
-- PURCHASING TABLES
-- ============================================

-- Suppliers
CREATE TABLE suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    contact_person TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    payment_terms INTEGER DEFAULT 0,
    credit_limit REAL DEFAULT 0,
    balance REAL DEFAULT 0,
    lead_time_days INTEGER DEFAULT 3,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Purchase Requests
CREATE TABLE purchase_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_number TEXT UNIQUE NOT NULL,
    request_date DATE NOT NULL,
    required_date DATE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'approved', 'rejected', 'converted')),
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Purchase Request Details
CREATE TABLE purchase_request_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL REFERENCES purchase_requests(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity_requested REAL NOT NULL,
    quantity_approved REAL DEFAULT 0,
    unit TEXT NOT NULL,
    notes TEXT
);

-- Purchase Orders
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number TEXT UNIQUE NOT NULL,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    pr_id INTEGER REFERENCES purchase_requests(id),
    order_date DATE NOT NULL,
    expected_delivery DATE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'sent', 'partial', 'received', 'cancelled')),
    subtotal REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    discount_amount REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_po_supplier ON purchase_orders(supplier_id);
CREATE INDEX idx_po_status ON purchase_orders(status);

-- Purchase Order Details
CREATE TABLE purchase_order_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity_ordered REAL NOT NULL,
    quantity_received REAL DEFAULT 0,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL,
    discount_percent REAL DEFAULT 0,
    total_price REAL DEFAULT 0
);

-- Supplier Invoices
CREATE TABLE supplier_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    po_id INTEGER REFERENCES purchase_orders(id),
    invoice_date DATE NOT NULL,
    due_date DATE,
    subtotal REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    amount_paid REAL DEFAULT 0,
    balance_due REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'partial', 'paid', 'overdue', 'cancelled')),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(supplier_id, invoice_number)
);

CREATE INDEX idx_inv_supplier ON supplier_invoices(supplier_id);
CREATE INDEX idx_inv_status ON supplier_invoices(status);
CREATE INDEX idx_inv_due_date ON supplier_invoices(due_date);

-- Supplier Invoice Details
CREATE TABLE supplier_invoice_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES supplier_invoices(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL,
    total_price REAL DEFAULT 0
);

-- Supplier Payments
CREATE TABLE supplier_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_number TEXT UNIQUE NOT NULL,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    invoice_id INTEGER REFERENCES supplier_invoices(id),
    payment_date DATE NOT NULL,
    amount REAL NOT NULL,
    payment_method TEXT NOT NULL CHECK(payment_method IN ('cash', 'bank_transfer', 'check', 'other')),
    reference_number TEXT,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- SALES TABLES
-- ============================================

-- Customers
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    contact_person TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    customer_type TEXT NOT NULL DEFAULT 'retail' CHECK(customer_type IN ('retail', 'wholesale', 'corporate')),
    credit_limit REAL DEFAULT 0,
    credit_days INTEGER DEFAULT 0,
    balance REAL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Price Lists
CREATE TABLE price_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    customer_type TEXT NOT NULL DEFAULT 'retail',
    is_default INTEGER DEFAULT 0
);

-- Price List Details
CREATE TABLE price_list_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    price_list_id INTEGER NOT NULL REFERENCES price_lists(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    unit_price REAL NOT NULL,
    min_quantity REAL DEFAULT 1,
    UNIQUE(price_list_id, item_id)
);

-- Sales Orders (for wholesale/corporate)
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date DATE NOT NULL,
    required_date DATE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'confirmed', 'in_progress', 'ready', 'delivered', 'cancelled')),
    subtotal REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    discount_amount REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_so_customer ON sales_orders(customer_id);
CREATE INDEX idx_so_status ON sales_orders(status);

-- Sales Order Details
CREATE TABLE sales_order_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    so_id INTEGER NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity_ordered REAL NOT NULL,
    quantity_delivered REAL DEFAULT 0,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL,
    discount_percent REAL DEFAULT 0,
    total_price REAL DEFAULT 0
);

-- Sales Invoices
CREATE TABLE sales_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    so_id INTEGER REFERENCES sales_orders(id),
    invoice_type TEXT NOT NULL DEFAULT 'cash' CHECK(invoice_type IN ('cash', 'credit')),
    invoice_date DATE NOT NULL,
    due_date DATE,
    subtotal REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    discount_amount REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    amount_paid REAL DEFAULT 0,
    balance_due REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'partial', 'paid', 'overdue', 'cancelled')),
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_si_customer ON sales_invoices(customer_id);
CREATE INDEX idx_si_status ON sales_invoices(status);
CREATE INDEX idx_si_date ON sales_invoices(invoice_date);

-- Sales Invoice Details
CREATE TABLE sales_invoice_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES sales_invoices(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL,
    cost_price REAL DEFAULT 0,
    total_price REAL DEFAULT 0
);

-- Customer Collections/Payments
CREATE TABLE customer_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    invoice_id INTEGER REFERENCES sales_invoices(id),
    payment_date DATE NOT NULL,
    amount REAL NOT NULL,
    payment_method TEXT NOT NULL CHECK(payment_method IN ('cash', 'bank_transfer', 'check', 'other')),
    reference_number TEXT,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- POS TABLES
-- ============================================

-- POS Sessions (daily cash register sessions)
CREATE TABLE pos_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    session_date DATE NOT NULL,
    opening_cash REAL NOT NULL DEFAULT 0,
    closing_cash REAL DEFAULT 0,
    expected_cash REAL DEFAULT 0,
    cash_difference REAL DEFAULT 0,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'closed'))
);

-- POS Transactions
CREATE TABLE pos_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_number TEXT UNIQUE NOT NULL,
    session_id INTEGER NOT NULL REFERENCES pos_sessions(id),
    customer_id INTEGER REFERENCES customers(id),
    transaction_type TEXT NOT NULL DEFAULT 'sale' CHECK(transaction_type IN ('sale', 'return')),
    subtotal REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    discount_amount REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    amount_paid REAL DEFAULT 0,
    change_amount REAL DEFAULT 0,
    payment_method TEXT NOT NULL CHECK(payment_method IN ('cash', 'card', 'mixed')),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pos_session ON pos_transactions(session_id);
CREATE INDEX idx_pos_date ON pos_transactions(created_at);

-- POS Transaction Details
CREATE TABLE pos_transaction_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pos_transaction_id INTEGER NOT NULL REFERENCES pos_transactions(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    discount_percent REAL DEFAULT 0,
    total_price REAL DEFAULT 0
);

-- ============================================
-- ONLINE ORDERS TABLES
-- ============================================

-- Online Orders (customer web orders)
CREATE TABLE online_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    customer_email TEXT,
    pickup_time TEXT,
    special_instructions TEXT,
    subtotal REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'preparing', 'ready', 'completed', 'cancelled')),
    converted_to_so_id INTEGER REFERENCES sales_orders(id),
    converted_to_pos_id INTEGER REFERENCES pos_transactions(id),
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_online_status ON online_orders(status);
CREATE INDEX idx_online_created ON online_orders(created_at);

-- Online Order Details
CREATE TABLE online_order_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    online_order_id INTEGER NOT NULL REFERENCES online_orders(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id),
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    total_price REAL DEFAULT 0
);

-- ============================================
-- ACCOUNTING TABLES (Lightweight)
-- ============================================

-- Chart of Accounts (simplified)
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK(account_type IN ('asset', 'liability', 'equity', 'revenue', 'expense')),
    parent_id INTEGER REFERENCES accounts(id),
    is_active INTEGER DEFAULT 1
);

-- Journal Entries (auto-generated)
CREATE TABLE journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_number TEXT UNIQUE NOT NULL,
    entry_date DATE NOT NULL,
    reference_type TEXT,
    reference_id INTEGER,
    description TEXT NOT NULL,
    total_debit REAL DEFAULT 0,
    total_credit REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_je_date ON journal_entries(entry_date);
CREATE INDEX idx_je_reference ON journal_entries(reference_type, reference_id);

-- Journal Entry Details
CREATE TABLE journal_entry_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    debit_amount REAL DEFAULT 0,
    credit_amount REAL DEFAULT 0,
    description TEXT
);

-- ============================================
-- SYSTEM TABLES
-- ============================================

-- System Settings
CREATE TABLE system_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT UNIQUE NOT NULL,
    setting_value TEXT,
    description TEXT
);

-- Activity Log
CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    details TEXT,
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_log_user ON activity_log(user_id);
CREATE INDEX idx_log_created ON activity_log(created_at);

-- ============================================
-- INSERT DEFAULT DATA
-- ============================================

-- Default admin user (password: admin123)
INSERT INTO users (username, password_hash, full_name, role) 
VALUES ('admin', 'scrypt:32768:8:1$Z0W7PNUrzUSfjist$05a4605220a1c1ad94f352ea06a73e9e46fec86ab552c2aa37e1811509729f1e49716edf469c50970dab6e04c31ae06aceb7beaf1e1928bd366ee6bbf11fab3b', 'System Administrator', 'admin');

-- Default warehouse
INSERT INTO warehouses (name, location) VALUES ('Main Bakery', 'Main Location');
INSERT INTO warehouses (name, location) VALUES ('Retail Store', 'Front Store');

-- Item categories
INSERT INTO item_categories (name, type) VALUES 
('Flours', 'raw_material'),
('Sugars & Sweeteners', 'raw_material'),
('Fats & Oils', 'raw_material'),
('Dairy & Eggs', 'raw_material'),
('Leavening Agents', 'raw_material'),
('Flavorings', 'raw_material'),
('Packaging Materials', 'packaging'),
('Breads', 'finished_goods'),
('Pastries', 'finished_goods'),
('Cakes', 'finished_goods'),
('Cookies', 'finished_goods');

-- Default price list
INSERT INTO price_lists (name, customer_type, is_default) VALUES ('Retail Price List', 'retail', 1);
INSERT INTO price_lists (name, customer_type, is_default) VALUES ('Wholesale Price List', 'wholesale', 0);

-- Chart of Accounts
INSERT INTO accounts (code, name, account_type) VALUES
-- Assets
('1000', 'Cash', 'asset'),
('1100', 'Bank', 'asset'),
('1200', 'Accounts Receivable', 'asset'),
('1300', 'Inventory', 'asset'),
-- Liabilities
('2000', 'Accounts Payable', 'liability'),
('2100', 'Accrued Expenses', 'liability'),
-- Equity
('3000', 'Owner Equity', 'equity'),
('3100', 'Retained Earnings', 'equity'),
-- Revenue
('4000', 'Sales Revenue', 'revenue'),
('4100', 'Online Sales', 'revenue'),
-- Expenses
('5000', 'Cost of Goods Sold', 'expense'),
('5100', 'Raw Materials', 'expense'),
('5200', 'Production Costs', 'expense'),
('5300', 'Operating Expenses', 'expense');

-- System settings
INSERT INTO system_settings (setting_key, setting_value, description) VALUES
('company_name', 'My Bakery', 'Company name for receipts and reports'),
('tax_rate', '0', 'Default tax rate (0 for no tax)'),
('currency', 'USD', 'Currency symbol'),
('receipt_footer', 'Thank you for your business!', 'Footer text on receipts'),
('online_orders_enabled', '1', 'Enable online ordering');

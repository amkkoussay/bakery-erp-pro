#!/usr/bin/env python3
"""
Bakery ERP - Sample Data Generator
Creates sample data for testing the system
"""
import sqlite3
from datetime import datetime, timedelta
import random

def get_db():
    conn = sqlite3.connect('bakery_erp.db')
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def add_sample_items():
    """Add sample bakery items"""
    conn = get_db()
    
    items = [
        # Raw Materials
        ('RM001', 'All Purpose Flour', 'raw_material', 'kg', 1, 50, 10),
        ('RM002', 'Bread Flour', 'raw_material', 'kg', 1, 30, 5),
        ('RM003', 'Sugar', 'raw_material', 'kg', 1, 25, 5),
        ('RM004', 'Butter', 'raw_material', 'kg', 1, 20, 3),
        ('RM005', 'Eggs', 'raw_material', 'dozen', 1, 10, 2),
        ('RM006', 'Yeast', 'raw_material', 'g', 500, 2000, 500),
        ('RM007', 'Salt', 'raw_material', 'kg', 1, 10, 2),
        ('RM008', 'Milk', 'raw_material', 'L', 2, 20, 5),
        ('RM009', 'Vanilla Extract', 'raw_material', 'ml', 100, 500, 100),
        ('RM010', 'Cocoa Powder', 'raw_material', 'kg', 1, 5, 1),
        
        # Finished Goods
        ('FG001', 'White Bread', 'finished_goods', 'loaf', 10, 50, 20),
        ('FG002', 'Whole Wheat Bread', 'finished_goods', 'loaf', 5, 30, 10),
        ('FG003', 'Croissant', 'finished_goods', 'piece', 20, 100, 50),
        ('FG004', 'Chocolate Muffin', 'finished_goods', 'piece', 15, 60, 30),
        ('FG005', 'Blueberry Muffin', 'finished_goods', 'piece', 15, 60, 30),
        ('FG006', 'Cinnamon Roll', 'finished_goods', 'piece', 12, 48, 24),
        ('FG007', 'Chocolate Cake', 'finished_goods', 'cake', 2, 10, 5),
        ('FG008', 'Vanilla Cake', 'finished_goods', 'cake', 2, 10, 5),
        ('FG009', 'Sugar Cookie', 'finished_goods', 'piece', 30, 120, 60),
        ('FG010', 'Chocolate Chip Cookie', 'finished_goods', 'piece', 40, 160, 80),
        ('FG011', 'Baguette', 'finished_goods', 'piece', 15, 45, 20),
        ('FG012', 'Sourdough Bread', 'finished_goods', 'loaf', 5, 20, 8),
    ]
    
    cursor = conn.cursor()
    
    # Get category IDs
    cat_map = {}
    for row in cursor.execute("SELECT id, name FROM item_categories"):
        cat_map[row['name']] = row['id']
    
    for code, name, item_type, unit, min_stock, max_stock, reorder in items:
        category = None
        if 'Flour' in name or 'Sugar' in name or 'Butter' in name or 'Yeast' in name or 'Salt' in name or 'Milk' in name:
            category = cat_map.get('Flours') if 'Flour' in name else cat_map.get('Sugars & Sweeteners')
        elif 'Bread' in name or 'Baguette' in name:
            category = cat_map.get('Breads')
        elif 'Cake' in name:
            category = cat_map.get('Cakes')
        elif 'Cookie' in name:
            category = cat_map.get('Cookies')
        elif 'Muffin' in name or 'Croissant' in name or 'Cinnamon' in name:
            category = cat_map.get('Pastries')
        
        try:
            cursor.execute("""
                INSERT INTO items (code, name, category_id, type, unit, min_stock, max_stock, reorder_point)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (code, name, category, item_type, unit, min_stock, max_stock, reorder))
            
            item_id = cursor.lastrowid
            
            # Initialize inventory
            for wh_id in [1, 2]:
                cursor.execute("""
                    INSERT INTO inventory (item_id, warehouse_id, quantity, unit_cost, total_cost)
                    VALUES (?, ?, 0, 0, 0)
                """, (item_id, wh_id))
                
        except sqlite3.IntegrityError:
            print(f"Item {code} already exists, skipping...")
    
    conn.commit()
    print("Sample items added!")
    
def add_sample_boms():
    """Add sample Bill of Materials"""
    conn = get_db()
    cursor = conn.cursor()
    
    # White Bread BOM
    white_bread = cursor.execute("SELECT id FROM items WHERE code = 'FG001'").fetchone()
    flour = cursor.execute("SELECT id FROM items WHERE code = 'RM001'").fetchone()
    water = cursor.execute("SELECT id FROM items WHERE code = 'RM008'").fetchone()
    yeast = cursor.execute("SELECT id FROM items WHERE code = 'RM006'").fetchone()
    salt = cursor.execute("SELECT id FROM items WHERE code = 'RM007'").fetchone()
    
    if white_bread and flour and water and yeast and salt:
        try:
            cursor.execute("""
                INSERT INTO bom_headers (product_id, version, quantity_yield)
                VALUES (?, '1.0', 1)
            """, (white_bread['id'],))
            bom_id = cursor.lastrowid
            
            ingredients = [
                (flour['id'], 0.5, 'kg', 0),
                (water['id'], 0.3, 'L', 0),
                (yeast['id'], 7, 'g', 0),
                (salt['id'], 10, 'g', 0),
            ]
            
            for item_id, qty, unit, waste in ingredients:
                cursor.execute("""
                    INSERT INTO bom_details (bom_id, item_id, quantity, unit, wastage_percent)
                    VALUES (?, ?, ?, ?, ?)
                """, (bom_id, item_id, qty, unit, waste))
            
            print("White Bread BOM added!")
        except sqlite3.IntegrityError:
            print("White Bread BOM already exists")
    
    # Chocolate Muffin BOM
    muffin = cursor.execute("SELECT id FROM items WHERE code = 'FG004'").fetchone()
    sugar = cursor.execute("SELECT id FROM items WHERE code = 'RM003'").fetchone()
    butter = cursor.execute("SELECT id FROM items WHERE code = 'RM004'").fetchone()
    eggs = cursor.execute("SELECT id FROM items WHERE code = 'RM005'").fetchone()
    cocoa = cursor.execute("SELECT id FROM items WHERE code = 'RM010'").fetchone()
    
    if muffin and flour and sugar and butter and eggs and cocoa:
        try:
            cursor.execute("""
                INSERT INTO bom_headers (product_id, version, quantity_yield)
                VALUES (?, '1.0', 12)
            """, (muffin['id'],))
            bom_id = cursor.lastrowid
            
            ingredients = [
                (flour['id'], 0.25, 'kg', 5),
                (sugar['id'], 0.15, 'kg', 0),
                (butter['id'], 0.1, 'kg', 0),
                (eggs['id'], 2, 'piece', 0),
                (cocoa['id'], 0.05, 'kg', 0),
            ]
            
            for item_id, qty, unit, waste in ingredients:
                cursor.execute("""
                    INSERT INTO bom_details (bom_id, item_id, quantity, unit, wastage_percent)
                    VALUES (?, ?, ?, ?, ?)
                """, (bom_id, item_id, qty, unit, waste))
            
            print("Chocolate Muffin BOM added!")
        except sqlite3.IntegrityError:
            print("Chocolate Muffin BOM already exists")
    
    conn.commit()

def add_sample_suppliers():
    """Add sample suppliers"""
    conn = get_db()
    cursor = conn.cursor()
    
    suppliers = [
        ('SUP001', 'Flour Mill Co.', 'John Smith', '555-0101', 'john@flourmill.com', '123 Mill St', 30, 5000),
        ('SUP002', 'Dairy Fresh Ltd.', 'Jane Doe', '555-0102', 'jane@dairyfresh.com', '456 Farm Rd', 15, 3000),
        ('SUP003', 'Sweet Supplies Inc.', 'Bob Johnson', '555-0103', 'bob@sweetsupplies.com', '789 Sugar Ave', 30, 2000),
        ('SUP004', 'Bakery Packaging Co.', 'Alice Brown', '555-0104', 'alice@bakerypack.com', '321 Box Ln', 0, 1000),
    ]
    
    for code, name, contact, phone, email, address, terms, credit in suppliers:
        try:
            cursor.execute("""
                INSERT INTO suppliers (code, name, contact_person, phone, email, address, payment_terms, credit_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (code, name, contact, phone, email, address, terms, credit))
        except sqlite3.IntegrityError:
            print(f"Supplier {code} already exists")
    
    conn.commit()
    print("Sample suppliers added!")

def add_sample_customers():
    """Add sample customers"""
    conn = get_db()
    cursor = conn.cursor()
    
    customers = [
        ('CUST001', 'Local Cafe', 'wholesale', 'Mike Wilson', '555-0201', 'mike@localcafe.com', '100 Main St', 5000, 30),
        ('CUST002', 'Restaurant ABC', 'wholesale', 'Sarah Lee', '555-0202', 'sarah@restaurantabc.com', '200 Oak Ave', 3000, 15),
        ('CUST003', 'Hotel Grand', 'corporate', 'David Chen', '555-0203', 'david@hotelgrand.com', '300 Park Blvd', 10000, 45),
        ('CUST004', 'John Smith', 'retail', '', '555-0204', '', '', 0, 0),
        ('CUST005', 'Mary Johnson', 'retail', '', '555-0205', '', '', 0, 0),
    ]
    
    for code, name, cust_type, contact, phone, email, address, credit_limit, credit_days in customers:
        try:
            cursor.execute("""
                INSERT INTO customers (code, name, customer_type, contact_person, phone, email, address, credit_limit, credit_days)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (code, name, cust_type, contact, phone, email, address, credit_limit, credit_days))
        except sqlite3.IntegrityError:
            print(f"Customer {code} already exists")
    
    conn.commit()
    print("Sample customers added!")

def add_sample_prices():
    """Add sample price list"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get default price list
    price_list = cursor.execute("SELECT id FROM price_lists WHERE is_default = 1").fetchone()
    if not price_list:
        return
    
    prices = [
        ('FG001', 3.50),  # White Bread
        ('FG002', 4.00),  # Whole Wheat Bread
        ('FG003', 2.50),  # Croissant
        ('FG004', 2.75),  # Chocolate Muffin
        ('FG005', 2.75),  # Blueberry Muffin
        ('FG006', 3.25),  # Cinnamon Roll
        ('FG007', 25.00), # Chocolate Cake
        ('FG008', 22.00), # Vanilla Cake
        ('FG009', 1.50),  # Sugar Cookie
        ('FG010', 1.75),  # Chocolate Chip Cookie
        ('FG011', 2.00),  # Baguette
        ('FG012', 5.50),  # Sourdough Bread
    ]
    
    for code, price in prices:
        item = cursor.execute("SELECT id FROM items WHERE code = ?", (code,)).fetchone()
        if item:
            try:
                cursor.execute("""
                    INSERT INTO price_list_details (price_list_id, item_id, unit_price)
                    VALUES (?, ?, ?)
                """, (price_list['id'], item['id'], price))
            except sqlite3.IntegrityError:
                pass
    
    conn.commit()
    print("Sample prices added!")

def add_sample_inventory():
    """Add sample inventory stock"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Add some stock to main warehouse
    raw_materials = cursor.execute("SELECT id FROM items WHERE type = 'raw_material'").fetchall()
    
    for item in raw_materials:
        qty = random.randint(10, 50)
        cost = random.uniform(1, 10)
        
        cursor.execute("""
            UPDATE inventory 
            SET quantity = ?, unit_cost = ?, total_cost = ?, last_movement = date('now')
            WHERE item_id = ? AND warehouse_id = 1
        """, (qty, cost, qty * cost, item['id']))
    
    conn.commit()
    print("Sample inventory added!")

def main():
    print("=" * 50)
    print("Bakery ERP - Sample Data Generator")
    print("=" * 50)
    
    add_sample_items()
    add_sample_boms()
    add_sample_suppliers()
    add_sample_customers()
    add_sample_prices()
    add_sample_inventory()
    
    print("=" * 50)
    print("Sample data generation complete!")
    print("=" * 50)

if __name__ == '__main__':
    main()

"""
Settings Module Routes
Company settings, users, warehouses, categories
"""
from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from app.settings import bp
from app.db_utils import query_one, query_all, execute
from app.auth.routes import require_role

@bp.route('/')
def settings_dashboard():
    """Settings dashboard"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    return render_template('settings/dashboard.html')

@bp.route('/company', methods=['GET', 'POST'])
def company_settings():
    """Company settings"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        tax_rate = request.form.get('tax_rate', 0)
        currency = request.form.get('currency', 'USD')
        receipt_footer = request.form.get('receipt_footer', '')
        
        settings = {
            'company_name': company_name,
            'tax_rate': tax_rate,
            'currency': currency,
            'receipt_footer': receipt_footer
        }
        
        for key, value in settings.items():
            existing = query_one("SELECT id FROM system_settings WHERE setting_key = ?", (key,))
            if existing:
                execute("UPDATE system_settings SET setting_value = ? WHERE setting_key = ?", (value, key))
            else:
                execute("INSERT INTO system_settings (setting_key, setting_value) VALUES (?, ?)", (key, value))
        
        flash('Company settings updated', 'success')
        return redirect(url_for('settings.company_settings'))
    
    settings = {}
    rows = query_all("SELECT setting_key, setting_value FROM system_settings")
    for row in rows:
        settings[row['setting_key']] = row['setting_value']
    
    return render_template('settings/company.html', settings=settings)

@bp.route('/users')
def users_list():
    """List users"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    users = query_all("""
        SELECT u.*, 
            (SELECT COUNT(*) FROM activity_log WHERE user_id = u.id) as activity_count
        FROM users u
        ORDER BY u.full_name
    """)
    
    return render_template('settings/users.html', users=users)

@bp.route('/users/add', methods=['GET', 'POST'])
@require_role('admin')
def add_user():
    """Add user"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role')
        
        if not username or not password or not full_name or not role:
            flash('All fields are required', 'error')
            return render_template('settings/add_user.html')
        
        # Check if username exists
        existing = query_one("SELECT id FROM users WHERE username = ?", (username,))
        if existing:
            flash('Username already exists', 'error')
            return render_template('settings/add_user.html')
        
        password_hash = generate_password_hash(password)
        
        execute("""
            INSERT INTO users (username, password_hash, full_name, role)
            VALUES (?, ?, ?, ?)
        """, (username, password_hash, full_name, role))
        
        flash('User created successfully', 'success')
        return redirect(url_for('settings.users_list'))
    
    return render_template('settings/add_user.html')

@bp.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@require_role('admin')
def edit_user(id):
    """Edit user"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user = query_one("SELECT * FROM users WHERE id = ?", (id,))
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('settings.users_list'))
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role')
        is_active = request.form.get('is_active', 0)
        new_password = request.form.get('new_password', '').strip()
        
        if not full_name or not role:
            flash('Full name and role are required', 'error')
            return render_template('settings/edit_user.html', user=user)
        
        if new_password:
            password_hash = generate_password_hash(new_password)
            execute("""
                UPDATE users SET full_name = ?, role = ?, is_active = ?, password_hash = ?
                WHERE id = ?
            """, (full_name, role, is_active, password_hash, id))
        else:
            execute("""
                UPDATE users SET full_name = ?, role = ?, is_active = ?
                WHERE id = ?
            """, (full_name, role, is_active, id))
        
        flash('User updated successfully', 'success')
        return redirect(url_for('settings.users_list'))
    
    return render_template('settings/edit_user.html', user=user)

@bp.route('/warehouses')
def warehouses_list():
    """List warehouses"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    warehouses = query_all("""
        SELECT w.*, 
            (SELECT COUNT(*) FROM inventory WHERE warehouse_id = w.id AND quantity > 0) as items_count
        FROM warehouses w
        ORDER BY w.name
    """)
    
    return render_template('settings/warehouses.html', warehouses=warehouses)

@bp.route('/warehouses/add', methods=['GET', 'POST'])
def add_warehouse():
    """Add warehouse"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        location = request.form.get('location', '').strip()
        
        if not name:
            flash('Name is required', 'error')
            return render_template('settings/add_warehouse.html')
        
        wh_id = execute("""
            INSERT INTO warehouses (name, location)
            VALUES (?, ?)
        """, (name, location))
        
        # Initialize inventory for all items
        items = query_all("SELECT id FROM items WHERE is_active = 1")
        for item in items:
            execute("""
                INSERT INTO inventory (item_id, warehouse_id, quantity, unit_cost, total_cost)
                VALUES (?, ?, 0, 0, 0)
            """, (item['id'], wh_id))
        
        flash('Warehouse created successfully', 'success')
        return redirect(url_for('settings.warehouses_list'))
    
    return render_template('settings/add_warehouse.html')

@bp.route('/categories')
def categories_list():
    """List item categories"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    categories = query_all("""
        SELECT c.*, 
            (SELECT COUNT(*) FROM items WHERE category_id = c.id) as item_count
        FROM item_categories c
        ORDER BY c.name
    """)
    
    return render_template('settings/categories.html', categories=categories)

@bp.route('/categories/add', methods=['GET', 'POST'])
def add_category():
    """Add category"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        cat_type = request.form.get('type')
        
        if not name or not cat_type:
            flash('Name and type are required', 'error')
            return render_template('settings/add_category.html')
        
        execute("""
            INSERT INTO item_categories (name, type)
            VALUES (?, ?)
        """, (name, cat_type))
        
        flash('Category created successfully', 'success')
        return redirect(url_for('settings.categories_list'))
    
    return render_template('settings/add_category.html')

@bp.route('/activity-log')
def activity_log():
    """View activity log"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_filter = request.args.get('user', '')
    
    sql = """
        SELECT al.*, u.full_name as user_name
        FROM activity_log al
        LEFT JOIN users u ON al.user_id = u.id
        WHERE 1=1
    """
    params = []
    
    if user_filter:
        sql += " AND al.user_id = ?"
        params.append(user_filter)
    
    sql += " ORDER BY al.created_at DESC LIMIT 500"
    
    logs = query_all(sql, params)
    users = query_all("SELECT id, full_name FROM users WHERE is_active = 1 ORDER BY full_name")
    
    return render_template('settings/activity_log.html', logs=logs, users=users, user_filter=user_filter)

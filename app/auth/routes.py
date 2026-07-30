"""
Authentication Routes
Simple login/logout with session management
"""
from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from app.auth import bp
from app.db_utils import get_db, query_one, execute

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Please enter username and password', 'error')
            return render_template('auth/login.html')
        
        db = get_db()
        user = query_one("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,))
        
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_role'] = user['role']
            
            # Log activity
            execute("""
                INSERT INTO activity_log (user_id, action, entity_type, details)
                VALUES (?, 'login', 'user', ?)
            """, (user['id'], f"User {username} logged in"))
            
            flash(f'Welcome, {user["full_name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    """User logout"""
    if 'user_id' in session:
        execute("""
            INSERT INTO activity_log (user_id, action, entity_type, details)
            VALUES (?, 'logout', 'user', ?)
        """, (session['user_id'], f"User {session.get('user_name')} logged out"))
    
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    """Change password"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new_pass = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        
        if not current or not new_pass or not confirm:
            flash('All fields are required', 'error')
            return render_template('auth/change_password.html')
        
        if new_pass != confirm:
            flash('New passwords do not match', 'error')
            return render_template('auth/change_password.html')
        
        user = query_one("SELECT * FROM users WHERE id = ?", (session['user_id'],))
        if not check_password_hash(user['password_hash'], current):
            flash('Current password is incorrect', 'error')
            return render_template('auth/change_password.html')
        
        new_hash = generate_password_hash(new_pass)
        execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, session['user_id']))
        
        flash('Password changed successfully', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('auth/change_password.html')

@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration / Sign up"""
    # If user is already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        full_name = request.form.get('full_name', '').strip()
        
        # Validation
        if not username or not password or not full_name:
            flash('Please fill in all required fields', 'error')
            return render_template('auth/signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/signup.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template('auth/signup.html')
        
        # Check if username already exists
        existing = query_one("SELECT id FROM users WHERE username = ?", (username,))
        if existing:
            flash('Username already exists. Please choose another.', 'error')
            return render_template('auth/signup.html')
        
        # Create new user (default role: cashier)
        password_hash = generate_password_hash(password)
        
        try:
            user_id = execute("""
                INSERT INTO users (username, password_hash, full_name, role, is_active)
                VALUES (?, ?, ?, 'cashier', 1)
            """, (username, password_hash, full_name))
            
            # Log the registration
            execute("""
                INSERT INTO activity_log (user_id, action, entity_type, details)
                VALUES (?, 'signup', 'user', ?)
            """, (user_id, f"New user registered: {username}"))
            
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            flash('Error creating account. Please try again.', 'error')
            return render_template('auth/signup.html')
    
    return render_template('auth/signup.html')


# Decorator for role-based access
def require_role(*roles):
    """Decorator to require specific role(s)"""
    from functools import wraps
    from flask import abort
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_role' not in session:
                return redirect(url_for('auth.login'))
            if session['user_role'] not in roles and session['user_role'] != 'admin':
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

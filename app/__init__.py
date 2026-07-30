# Bakery ERP - Flask Application Factory
from flask import Flask, g
import sqlite3
import os

DATABASE = 'bakery_erp.db'

def get_db():
    """Get database connection for current request"""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(e=None):
    """Close database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initialize database with schema"""
    db = get_db()
    with open('schema.sql', 'r') as f:
        db.executescript(f.read())
    db.commit()

def create_app(test_config=None):
    """Application factory"""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='bakery-erp-secret-key-change-in-production',
        DATABASE=DATABASE,
    )
    
    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)
    
    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    # Register database teardown
    app.teardown_appcontext(close_db)
    
    # Register blueprints
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.inventory import bp as inventory_bp
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    
    from app.production import bp as production_bp
    app.register_blueprint(production_bp, url_prefix='/production')
    
    from app.purchases import bp as purchases_bp
    app.register_blueprint(purchases_bp, url_prefix='/purchases')
    
    from app.sales import bp as sales_bp
    app.register_blueprint(sales_bp, url_prefix='/sales')
    
    from app.pos import bp as pos_bp
    app.register_blueprint(pos_bp, url_prefix='/pos')
    
    from app.online_orders import bp as online_orders_bp
    app.register_blueprint(online_orders_bp, url_prefix='/online')
    
    from app.reports import bp as reports_bp
    app.register_blueprint(reports_bp, url_prefix='/reports')
    
    from app.settings import bp as settings_bp
    app.register_blueprint(settings_bp, url_prefix='/settings')
    
    # Main dashboard route
    @app.route('/')
    def index():
        from flask import render_template, session, redirect, url_for
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return render_template('dashboard.html')
    
    @app.route('/dashboard')
    def dashboard():
        from flask import render_template, session, redirect, url_for
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return render_template('dashboard.html')
    
    # Template filters
    @app.template_filter('format_currency')
    def format_currency(value):
        if value is None:
            return "$0.00"
        return f"${value:,.2f}"
    
    @app.template_filter('format_date')
    def format_date(value):
        if value is None:
            return ""
        from datetime import datetime
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, '%Y-%m-%d')
            except:
                return value
        return value.strftime('%Y-%m-%d')
    
    # Context processor for common template variables
    @app.context_processor
    def inject_globals():
        from flask import session
        return {
            'app_name': 'Bakery ERP',
            'app_version': '1.0.0',
            'current_user': session.get('user_name', 'Guest')
        }
    
    return app

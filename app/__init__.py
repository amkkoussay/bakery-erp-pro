# Bakery ERP - Flask Application Factory
from datetime import datetime
import os
from pathlib import Path
import sqlite3

from flask import Flask, current_app, g


ROOT = Path(__file__).resolve().parent.parent
DATABASE = str(ROOT / "bakery_erp.db")


def get_db():
    """Get database connection for current request."""
    if "db" not in g:
        g.db = sqlite3.connect(g.get("_database_path", current_app.config["_DATABASE_PATH"]))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    """Close database connection."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Initialize database with schema."""
    db = get_db()
    schema_path = ROOT / "schema.sql"
    with schema_path.open(encoding="utf-8") as schema:
        db.executescript(schema.read())
    db.commit()


def create_app(test_config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=DATABASE,
    )

    if test_config is None:
        app.config.from_pyfile("config.py", silent=True)
    else:
        app.config.from_mapping(test_config)

    if not app.config.get("SECRET_KEY"):
        if app.config.get("TESTING"):
            app.config["SECRET_KEY"] = "test-only-secret"
        else:
            raise RuntimeError(
                "Set SECRET_KEY in the environment or instance/config.py before starting the app."
            )

    app.config["DATABASE"] = os.path.abspath(app.config["DATABASE"])
    app.config["_DATABASE_PATH"] = app.config["DATABASE"]

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    @app.before_request
    def bind_database_path():
        g._database_path = app.config["_DATABASE_PATH"]

    @app.before_request
    def bind_database_path():
        g._database_path = app.config["_DATABASE_PATH"]

    app.teardown_appcontext(close_db)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from app.inventory import bp as inventory_bp
    app.register_blueprint(inventory_bp, url_prefix="/inventory")

    from app.production import bp as production_bp
    app.register_blueprint(production_bp, url_prefix="/production")

    from app.purchases import bp as purchases_bp
    app.register_blueprint(purchases_bp, url_prefix="/purchases")

    from app.sales import bp as sales_bp
    app.register_blueprint(sales_bp, url_prefix="/sales")

    from app.pos import bp as pos_bp
    app.register_blueprint(pos_bp, url_prefix="/pos")

    from app.online_orders import bp as online_orders_bp
    app.register_blueprint(online_orders_bp, url_prefix="/online")

    from app.reports import bp as reports_bp
    app.register_blueprint(reports_bp, url_prefix="/reports")

    from app.settings import bp as settings_bp
    app.register_blueprint(settings_bp, url_prefix="/settings")

    @app.route("/")
    def index():
        from flask import redirect, render_template, session, url_for
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return render_template("dashboard.html")

    @app.route("/dashboard")
    def dashboard():
        from flask import redirect, render_template, session, url_for
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return render_template("dashboard.html")

    @app.template_filter("format_currency")
    def format_currency(value):
        if value is None:
            return "$0.00"
        return f"${value:,.2f}"

    @app.template_filter("format_date")
    def format_date(value):
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                return value
        return value.strftime("%Y-%m-%d")

    @app.context_processor
    def inject_globals():
        from flask import session
        return {
            "app_name": "Bakery ERP",
            "app_version": "1.0.0",
            "current_user": session.get("user_name", "Guest"),
        }

    return app

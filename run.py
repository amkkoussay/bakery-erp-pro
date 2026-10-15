#!/usr/bin/env python3
"""Bakery ERP application entry point."""

import os

from app import create_app, init_db


def main():
    """Initialize a missing database and start the local development server."""
    database = os.environ.get("DATABASE", "bakery_erp.db")
    if not os.path.exists(database):
        app = create_app({"DATABASE": database})
        with app.app_context():
            init_db()
        print("Database initialized. Create the first user through the signup page.")

    app = create_app({"DATABASE": database})
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=debug,
        threaded=True,
    )


if __name__ == "__main__":
    main()

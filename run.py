#!/usr/bin/env python3
"""
Bakery ERP - Main Entry Point
Run this file to start the Flask application
"""
import os
import sys
from app import create_app, init_db

def main():
    """Main entry point"""
    # Check if database exists, if not initialize it
    db_path = 'bakery_erp.db'
    if not os.path.exists(db_path):
        print("Database not found. Initializing...")
        try:
            app = create_app()
            with app.app_context():
                init_db()
            print("Database initialized successfully!")
            print("Default login: admin / admin123")
        except Exception as e:
            print(f"Error initializing database: {e}")
            sys.exit(1)
    
    # Create and run app
    app = create_app()
    
    print("=" * 50)
    print("Bakery ERP System")
    print("=" * 50)
    print("Server starting on http://127.0.0.1:5000")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    # Run with Flask development server
    # For production, use gunicorn or waitress
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )

if __name__ == '__main__':
    main()

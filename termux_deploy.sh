#!/bin/bash
# Bakery ERP - Termux Deployment Script
# Run this script in Termux to set up the Bakery ERP system

echo "=========================================="
echo "Bakery ERP - Termux Deployment"
echo "=========================================="

# Update packages
echo "[1/6] Updating packages..."
pkg update -y

# Install Python and required packages
echo "[2/6] Installing Python..."
pkg install python -y

# Install SQLite (usually pre-installed, but ensure it's there)
echo "[3/6] Checking SQLite..."
pkg install sqlite -y

# Create project directory
echo "[4/6] Setting up project directory..."
PROJECT_DIR="$HOME/bakery_erp"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Install Python dependencies
echo "[5/6] Installing Python dependencies..."
pip install --upgrade pip
pip install Flask Werkzeug

# Initialize database
echo "[6/6] Initializing database..."
python3 -c "
import sqlite3
conn = sqlite3.connect('bakery_erp.db')
conn.execute('PRAGMA foreign_keys = ON')

# Read and execute schema
with open('schema.sql', 'r') as f:
    conn.executescript(f.read())

conn.commit()
conn.close()
print('Database initialized!')
"

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "To start the server:"
echo "  cd $PROJECT_DIR"
echo "  python3 run.py"
echo ""
echo "Then open your browser to:"
echo "  http://localhost:5000"
echo ""
echo "Default login:"
echo "  Username: admin"
echo "  Password: admin123"
echo ""
echo "=========================================="

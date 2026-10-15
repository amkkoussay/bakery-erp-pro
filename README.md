# Bakery ERP

A Flask and SQLite application for bakery operations: point of sale, inventory, production, purchasing, online orders, and reporting. This is a development/demo project; review authentication, deployment settings, and business workflows before using it with live operational or financial data.

## Features

- Point of sale and sales management
- Inventory, bills of materials, and production orders
- Purchasing, suppliers, and customer records
- Online ordering
- Profitability, waste, and inventory prediction reports

## Stack and layout

- Python and Flask
- SQLite with hand-written SQL
- HTML templates, CSS, and JavaScript
- Feature blueprints, service/repository modules, SQL schema and migrations

## Local setup

Use Python 3.10 or newer.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set a strong secret before starting. Keep it outside Git:

```bash
# Linux/macOS
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
# Windows PowerShell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
```

Initialize the database and start the local server:

```bash
python run.py
```

Open http://127.0.0.1:5000. The database is created from `schema.sql` when missing. Create an initial account through the signup page; no default administrator password is provided.

For development-only debug mode, explicitly set `FLASK_DEBUG=1`. Do not enable the Flask development server or debug mode for production. Configure `DATABASE`, `HOST`, and `PORT` through environment variables as needed.

## Tests

The tests use Python's built-in `unittest` framework and a temporary SQLite database:

```bash
python -m unittest discover -s tests -v
```

Optional pytest output is available after installing `requirements-dev.txt`.

## Repository hygiene

Local databases, logs, virtual environments, bytecode, and secrets are excluded by `.gitignore`. The existing tracked database, logs, and bytecode should be removed from version control in a cleanup commit; changing ignore rules alone does not remove already tracked files.

## License

No license file is currently present. Contact the repository owner before reusing or redistributing this project.

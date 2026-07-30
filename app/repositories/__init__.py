"""
Repositories Layer
===================
Repositories are the ONLY place in the codebase that should contain raw SQL
for the domains they own. They return plain dicts/lists (via app.db_utils)
and know nothing about Flask, HTTP, or business rules.

Services (app/services/*) call repositories and apply business logic.
Controllers (app/<module>/routes.py) call services and handle HTTP/templates.

This layer was introduced alongside the Smart Inventory Predictions and
Profit & Loss features. Existing modules were left as-is to avoid
destabilizing a working app; new/updated modules should follow this
pattern going forward. See ARCHITECTURE.md at the project root.
"""

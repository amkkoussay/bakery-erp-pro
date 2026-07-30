"""
Services Layer
===============
Services hold business rules and orchestrate one or more repositories.
They return plain Python data (dicts/lists) so both routes (HTML) and
API endpoints (JSON) can reuse the same logic without duplicating it.
"""

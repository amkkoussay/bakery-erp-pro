-- Migration 001: Smart Inventory Predictions + Profit Analytics
-- Safe to run once on an existing bakery_erp.db (new installs already get
-- these columns from schema.sql). Run with:
--   sqlite3 bakery_erp.db < migrations/001_predictions_and_profit.sql

ALTER TABLE suppliers ADD COLUMN lead_time_days INTEGER DEFAULT 3;
ALTER TABLE items ADD COLUMN preferred_supplier_id INTEGER REFERENCES suppliers(id);
ALTER TABLE items ADD COLUMN safety_stock_days INTEGER DEFAULT 2;

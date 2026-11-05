-- ==============================================================================
-- The Ghost Inventory Auto-Reconciliation Pipeline: Database Schema
-- Zero-LLM Deterministic State Machine for Storefront (Shopify) vs WMS (3PL)
-- Compatible with SQLite3 and PostgreSQL
-- ==============================================================================

-- 1. Product Catalog
CREATE TABLE IF NOT EXISTS ecom_products (
    sku VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    barcode VARCHAR(64),
    unit_price NUMERIC(10, 2) NOT NULL,
    cost_price NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- 2. Storefront Inventory (Shopify Digital State)
CREATE TABLE IF NOT EXISTS ecom_storefront_inventory (
    sku VARCHAR(64) PRIMARY KEY,
    shopify_quantity INTEGER NOT NULL DEFAULT 0,
    location_id VARCHAR(64) DEFAULT 'loc_primary',
    tracked BOOLEAN DEFAULT 1,
    last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sku) REFERENCES ecom_products(sku)
);

-- 3. Warehouse Physical Inventory (3PL / WMS Physical State)
CREATE TABLE IF NOT EXISTS ecom_wms_inventory (
    sku VARCHAR(64) PRIMARY KEY,
    wms_quantity INTEGER NOT NULL DEFAULT 0,
    in_transit_quantity INTEGER NOT NULL DEFAULT 0,
    bin_location VARCHAR(32) NOT NULL DEFAULT 'BIN-01A',
    is_in_transit BOOLEAN DEFAULT 0,
    last_counted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sku) REFERENCES ecom_products(sku)
);

-- 4. Sales Orders (Telemetry for Velocity Heuristics)
CREATE TABLE IF NOT EXISTS ecom_orders (
    order_id VARCHAR(64) PRIMARY KEY,
    order_date DATE NOT NULL,
    customer_email VARCHAR(255),
    total_amount NUMERIC(10, 2) NOT NULL,
    channel VARCHAR(32) DEFAULT 'shopify_online',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Order Line Items
CREATE TABLE IF NOT EXISTS ecom_order_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id VARCHAR(64) NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES ecom_orders(order_id),
    FOREIGN KEY (sku) REFERENCES ecom_products(sku)
);

-- 6. Reverse Logistics (Returns & Cancellations)
CREATE TABLE IF NOT EXISTS ecom_returns_cancellations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id VARCHAR(64) NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    event_type VARCHAR(32) NOT NULL, -- 'return' or 'cancellation'
    reason VARCHAR(255),
    event_date DATE NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sku) REFERENCES ecom_products(sku)
);

-- 7. Audit Execution Runs (Tracks each daily sensor run)
CREATE TABLE IF NOT EXISTS ecom_audit_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    trigger_type VARCHAR(32) NOT NULL, -- 'scheduled_2am', 'manual_webhook', 'test'
    target_count INTEGER NOT NULL DEFAULT 0,
    state_a_count INTEGER NOT NULL DEFAULT 0, -- Perfect Match
    state_b_count INTEGER NOT NULL DEFAULT 0, -- Safe Hidden Stock
    state_c_count INTEGER NOT NULL DEFAULT 0, -- Ghost Stock Danger
    state_d_count INTEGER NOT NULL DEFAULT 0, -- Transit Noise
    status VARCHAR(32) NOT NULL, -- 'STARTED', 'PENDING_APPROVAL', 'COMPLETED', 'BLIND_ABORTED', 'LOCKDOWN_SKIPPED'
    ghost_stock_prevented INTEGER NOT NULL DEFAULT 0,
    hidden_revenue_unlocked NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- 8. Audit Drift Records (Per-SKU decisions & audit trails)
CREATE TABLE IF NOT EXISTS ecom_audit_drift_records (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(64) NOT NULL,
    sku VARCHAR(64) NOT NULL,
    shopify_qty INTEGER NOT NULL,
    wms_qty INTEGER NOT NULL,
    drift_score INTEGER NOT NULL, -- shopify_qty - wms_qty
    state_category VARCHAR(16) NOT NULL, -- 'STATE_A', 'STATE_B', 'STATE_C', 'STATE_D'
    resolution_action VARCHAR(64) NOT NULL, -- 'NO_ACTION', 'AUTO_INCREASE_SHOPIFY', 'SUSPEND_FOR_HITL', 'TIMEOUT_ZERO_OUT', 'TRANSIT_NOISE_DISMISSED'
    approved_physical_qty INTEGER,
    final_synced_qty INTEGER,
    operator_notes TEXT,
    resolved_at TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES ecom_audit_runs(run_id),
    FOREIGN KEY (sku) REFERENCES ecom_products(sku)
);

-- 9. System Configuration & Reflex Flags
CREATE TABLE IF NOT EXISTS ecom_system_config (
    config_key VARCHAR(64) PRIMARY KEY,
    config_value VARCHAR(255) NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. Performance Indexes for 100k+ Scale
CREATE INDEX IF NOT EXISTS idx_orders_date ON ecom_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_covering ON ecom_orders(order_date, order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_sku ON ecom_order_items(sku);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON ecom_order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_covering ON ecom_order_items(order_id, sku, quantity);
CREATE INDEX IF NOT EXISTS idx_returns_event_date ON ecom_returns_cancellations(event_date);
CREATE INDEX IF NOT EXISTS idx_returns_sku ON ecom_returns_cancellations(sku);
CREATE INDEX IF NOT EXISTS idx_drift_run_id ON ecom_audit_drift_records(run_id);
CREATE INDEX IF NOT EXISTS idx_drift_sku ON ecom_audit_drift_records(sku);

-- Default system configuration values
INSERT OR IGNORE INTO ecom_system_config (config_key, config_value, description) VALUES
('is_lockdown', 'false', 'Flash sale lockdown mode: freezes downward inventory mutations'),
('transit_noise_margin_pct', '0.02', 'Allowable percentage margin for in-transit inventory (e.g. 0.02 = 2%)'),
('high_velocity_sales_threshold', '5', 'Yesterday sales count threshold to trigger mandatory SKU audit'),
('dead_stock_sample_rate', '0.05', 'Percentage of slow-moving inventory to audit randomly each cycle (0.05 = 5%)'),
('wms_api_timeout_seconds', '15', 'WMS API HTTP timeout threshold'),
('hitl_timeout_hours', '12', 'Grace period before unverified ghost inventory is automatically zeroed out');


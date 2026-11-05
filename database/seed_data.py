"""
Seed data generator for the Ghost Inventory Auto-Reconciliation Pipeline.
Generates a realistic SQLite database with 120 SKUs and planted drift scenarios
across all 4 state machine categories (State A, State B, State C, State D).
"""

import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory_recon.db")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

CATEGORIES = {
    "Footwear": [
        ("SHOE-AIR-001", "Air Trail Running Sneaker - Men US 10", 129.99, 52.00),
        ("SHOE-AIR-002", "Air Trail Running Sneaker - Men US 11", 129.99, 52.00),
        ("SHOE-BOOT-101", "Weatherproof Hiking Boot - Unisex 9", 189.50, 75.00),
        ("SHOE-BOOT-102", "Weatherproof Hiking Boot - Unisex 10", 189.50, 75.00),
        ("SHOE-SLIP-201", "Cloudfoam Minimalist Slip-On - 8", 65.00, 24.00),
    ],
    "Apparel": [
        ("APP-HOOD-BLK-M", "Heavyweight Organic Hoodie - Black M", 78.00, 28.00),
        ("APP-HOOD-BLK-L", "Heavyweight Organic Hoodie - Black L", 78.00, 28.00),
        ("APP-TEE-WHT-S", "Essential Supima Cotton T-Shirt - White S", 34.00, 11.50),
        ("APP-TEE-WHT-M", "Essential Supima Cotton T-Shirt - White M", 34.00, 11.50),
        ("APP-TEE-WHT-L", "Essential Supima Cotton T-Shirt - White L", 34.00, 11.50),
        ("APP-JOG-NVY-M", "Technical French Terry Joggers - Navy M", 88.00, 31.00),
    ],
    "Electronics": [
        ("ELEC-ANC-HEAD-01", "Studio Wireless ANC Headphones", 249.99, 98.00),
        ("ELEC-MAG-CHRG-02", "3-in-1 MagSafe Fast Charging Dock", 89.95, 34.00),
        ("ELEC-USB-HUB-03", "10-in-1 USB-C Hub Thunderbolt 4", 79.99, 29.00),
        ("ELEC-CAM-4K-04", "Ultra-HD Streaming Webcam 4K 60FPS", 119.00, 44.00),
    ],
    "Accessories": [
        ("ACC-LEATH-WLT-01", "RFID Blocking Bi-fold Leather Wallet", 45.00, 16.00),
        ("ACC-BACK-30L-02", "Urban Commuter Waterproof Backpack 30L", 110.00, 42.00),
        ("ACC-CAP-WOOL-03", "Merino Wool Thermal Beanie - Charcoal", 32.00, 10.50),
        ("ACC-SUN-POL-04", "Polarized Titanium Sunglasses - Matte Black", 95.00, 33.00),
    ],
    "Home Goods": [
        ("HOME-LINEN-QUILT-01", "Washed French Linen Duvet - Queen Slate", 195.00, 72.00),
        ("HOME-DIFF-CER-02", "Ultrasonic Ceramic Aroma Diffuser 300ml", 55.00, 19.00),
        ("HOME-CANDLE-SOY-03", "Hand-Poured Amber & Sandalwood Soy Candle", 28.00, 9.00),
    ]
}

def init_db():
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass
            
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

def seed_catalog():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    sku_list = []
    
    # 1. Insert predefined core SKUs
    for cat, items in CATEGORIES.items():
        for sku, title, price, cost in items:
            cur.execute("""
                INSERT INTO ecom_products (sku, title, category, barcode, unit_price, cost_price, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (sku, title, cat, f"UPC-{hash(sku) % 100000000:08d}", price, cost))
            sku_list.append((sku, title, cat, price, cost))
            
    # 2. Generate additional filler SKUs up to 100 SKUs (to support high volume tests and 5% dead stock sampling)
    for i in range(1, 80):
        cat = random.choice(list(CATEGORIES.keys()))
        sku = f"SKU-{cat[:3].upper()}-{i:04d}"
        title = f"Commercial Grade {cat} Variant #{i:03d}"
        price = round(random.uniform(25.0, 350.0), 2)
        cost = round(price * 0.4, 2)
        cur.execute("""
            INSERT INTO ecom_products (sku, title, category, barcode, unit_price, cost_price, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (sku, title, cat, f"UPC-{10000000 + i}", price, cost))
        sku_list.append((sku, title, cat, price, cost))
        
    conn.commit()
    conn.close()
    return sku_list

def seed_inventory_and_telemetry(sku_list):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    
    # Pre-defined planted drift scenarios to guarantee predictable agent behaviors:
    # 1. State C (Ghost Stock Danger) - High velocity sale + severe phantom inventory
    planted_scenarios = {
        # SKU: (Shopify_Qty, WMS_Qty, In_Transit, Is_Transit_Flag, Yesterday_Sales, Yesterday_Returns)
        "SHOE-AIR-001": (48, 8, 0, 0, 14, 0),    # State C: Drift = +40 (Ghost Stock Danger!). 14 sales yesterday (>5)
        "APP-HOOD-BLK-L": (35, 2, 0, 0, 9, 0),    # State C: Drift = +33 (Ghost Stock Danger!). 9 sales yesterday (>5)
        "ELEC-ANC-HEAD-01": (22, 0, 0, 0, 6, 1), # State C: Drift = +22 (Ghost Stock Danger!). 6 sales + 1 return yesterday
        
        # 2. State B (Safe Hidden Stock) - Warehouse has more physical units than website
        "SHOE-BOOT-101": (12, 45, 0, 0, 8, 0),   # State B: Drift = -33 (Safe Hidden Stock!). WMS has +33. Auto-increase.
        "APP-TEE-WHT-M": (10, 80, 0, 0, 12, 0),  # State B: Drift = -70 (Safe Hidden Stock!). WMS has +70. Auto-increase.
        "ACC-BACK-30L-02": (5, 25, 0, 0, 0, 1),  # State B: Drift = -20 (Safe Hidden Stock!). Return yesterday.
        
        # 3. State D (Transit Noise) - Discrepancy is within 2% margin and flagged in_transit
        "HOME-LINEN-QUILT-01": (500, 495, 5, 1, 7, 0), # State D: Drift = +5 out of 500 = 1.0% (<= 2%). Flagged in-transit!
        "ACC-LEATH-WLT-01": (200, 198, 2, 1, 0, 1),   # State D: Drift = +2 out of 200 = 1.0% (<= 2%). Flagged in-transit!
        
        # 4. State A (Perfect Match) - Perfectly aligned stock
        "ELEC-MAG-CHRG-02": (40, 40, 0, 0, 11, 0),     # State A: Drift = 0. Velocity = 11.
        "APP-JOG-NVY-M": (65, 65, 0, 0, 7, 0),         # State A: Drift = 0. Velocity = 7.
        "SHOE-SLIP-201": (30, 30, 0, 0, 0, 2),         # State A: Drift = 0. Return yesterday.
    }
    
    order_counter = 1000
    
    for idx, (sku, title, cat, price, cost) in enumerate(sku_list):
        bin_loc = f"AISLE-{chr(65 + (idx % 8))}-B{(idx % 25) + 1:02d}"
        
        if sku in planted_scenarios:
            shop_qty, wms_qty, in_transit, is_transit_flag, sales_cnt, ret_cnt = planted_scenarios[sku]
        else:
            # General inventory distribution
            # 80% perfect match, 10% slight safe stock, 10% slight ghost
            rand_type = random.random()
            base_qty = random.randint(15, 120)
            in_transit = 0
            is_transit_flag = 0
            
            if rand_type < 0.75:
                # State A
                shop_qty = base_qty
                wms_qty = base_qty
            elif rand_type < 0.88:
                # State B
                shop_qty = base_qty
                wms_qty = base_qty + random.randint(3, 12)
            else:
                # State C
                shop_qty = base_qty + random.randint(2, 6)
                wms_qty = base_qty
                
            # Random sales count: mostly 0-3 (dead/normal), few > 5
            if random.random() < 0.08:
                sales_cnt = random.randint(6, 12) # high velocity
            elif random.random() < 0.35:
                sales_cnt = random.randint(1, 3)  # normal
            else:
                sales_cnt = 0                      # dead stock
                
            ret_cnt = 1 if (random.random() < 0.05 and sales_cnt > 0) else 0

        # Insert Storefront Inventory
        cur.execute("""
            INSERT INTO ecom_storefront_inventory (sku, shopify_quantity, location_id, tracked, last_synced_at)
            VALUES (?, ?, 'loc_primary_warehouse', 1, CURRENT_TIMESTAMP)
        """, (sku, shop_qty))
        
        # Insert WMS Inventory
        cur.execute("""
            INSERT INTO ecom_wms_inventory (sku, wms_quantity, in_transit_quantity, bin_location, is_in_transit, last_counted_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (sku, wms_qty, in_transit, bin_loc, is_transit_flag))
        
        # Generate Orders Telemetry if sales_cnt > 0
        if sales_cnt > 0:
            order_id = f"ORD-{yesterday.replace('-', '')}-{order_counter}"
            order_counter += 1
            cur.execute("""
                INSERT INTO ecom_orders (order_id, order_date, customer_email, total_amount, channel)
                VALUES (?, ?, ?, ?, 'shopify_online')
            """, (order_id, yesterday, f"customer_{order_counter}@example.com", round(sales_cnt * price, 2)))
            
            cur.execute("""
                INSERT INTO ecom_order_items (order_id, sku, quantity, unit_price)
                VALUES (?, ?, ?, ?)
            """, (order_id, sku, sales_cnt, price))
            
        # Generate Returns / Cancellations Telemetry if ret_cnt > 0
        if ret_cnt > 0:
            cur.execute("""
                INSERT INTO ecom_returns_cancellations (order_id, sku, quantity, event_type, reason, event_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"ORD-{two_days_ago.replace('-', '')}-{order_counter - 1}", sku, ret_cnt, 
                  "return" if random.random() > 0.4 else "cancellation",
                  "Customer requested return - size mismatch", yesterday))

    conn.commit()
    conn.close()
    print(f"[Seed] Successfully seeded {len(sku_list)} SKUs into {DB_PATH}")

if __name__ == "__main__":
    init_db()
    skus = seed_catalog()
    seed_inventory_and_telemetry(skus)


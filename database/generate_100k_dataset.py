"""
High-Performance Synthetic Data Generator: 100,000 Orders & 100 Curated SKUs.
Generates realistic sales velocity, returns, multi-item carts, and ground-truth drift states.
Optimized for ultra-fast SQLite WAL chunked ingestion (< 5 seconds for 100k orders).
"""

import sqlite3
import os
import sys
import random
import time
import json
from datetime import datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "database", "inventory_recon.db")
SCHEMA_PATH = os.path.join(PROJECT_DIR, "database", "schema.sql")
REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")

CATEGORIES_SPEC = {
    "Footwear": [
        ("SHOE-AIR-001", "Air Trail Running Sneaker - Men US 10", 129.99, 48.00),
        ("SHOE-AIR-002", "Air Trail Running Sneaker - Men US 11", 129.99, 48.00),
        ("SHOE-AIR-003", "Air Trail Running Sneaker - Women US 7", 124.99, 46.00),
        ("SHOE-AIR-004", "Air Trail Running Sneaker - Women US 8", 124.99, 46.00),
        ("SHOE-BOOT-101", "Weatherproof Hiking Boot - Unisex 9", 189.50, 72.00),
        ("SHOE-BOOT-102", "Weatherproof Hiking Boot - Unisex 10", 189.50, 72.00),
        ("SHOE-BOOT-103", "Weatherproof Hiking Boot - Unisex 11", 189.50, 72.00),
        ("SHOE-SLIP-201", "Cloudfoam Minimalist Slip-On - 8", 65.00, 22.00),
        ("SHOE-SLIP-202", "Cloudfoam Minimalist Slip-On - 9", 65.00, 22.00),
        ("SHOE-SLIP-203", "Cloudfoam Minimalist Slip-On - 10", 65.00, 22.00),
        ("SHOE-DERB-301", "Handcrafted Leather Derby - Black 9", 220.00, 85.00),
        ("SHOE-DERB-302", "Handcrafted Leather Derby - Brown 10", 220.00, 85.00),
        ("SHOE-SAND-401", "Ergonomic Recovery Slide Sandal - 8", 45.00, 14.00),
        ("SHOE-SAND-402", "Ergonomic Recovery Slide Sandal - 10", 45.00, 14.00),
        ("SHOE-COURT-501", "Pro Low-Top Court Tennis Shoe - 9.5", 115.00, 42.00)
    ],
    "Apparel": [
        ("APP-HOOD-BLK-M", "Heavyweight Organic Hoodie - Black M", 78.00, 26.00),
        ("APP-HOOD-BLK-L", "Heavyweight Organic Hoodie - Black L", 78.00, 26.00),
        ("APP-HOOD-BLK-XL", "Heavyweight Organic Hoodie - Black XL", 78.00, 26.00),
        ("APP-HOOD-GRY-M", "Heavyweight Organic Hoodie - Heather Grey M", 78.00, 26.00),
        ("APP-HOOD-GRY-L", "Heavyweight Organic Hoodie - Heather Grey L", 78.00, 26.00),
        ("APP-TEE-WHT-S", "Essential Supima Cotton T-Shirt - White S", 34.00, 10.50),
        ("APP-TEE-WHT-M", "Essential Supima Cotton T-Shirt - White M", 34.00, 10.50),
        ("APP-TEE-WHT-L", "Essential Supima Cotton T-Shirt - White L", 34.00, 10.50),
        ("APP-TEE-BLK-M", "Essential Supima Cotton T-Shirt - Black M", 34.00, 10.50),
        ("APP-TEE-BLK-L", "Essential Supima Cotton T-Shirt - Black L", 34.00, 10.50),
        ("APP-JOG-NVY-M", "Technical French Terry Joggers - Navy M", 88.00, 30.00),
        ("APP-JOG-NVY-L", "Technical French Terry Joggers - Navy L", 88.00, 30.00),
        ("APP-JOG-BLK-M", "Technical French Terry Joggers - Black M", 88.00, 30.00),
        ("APP-JOG-BLK-L", "Technical French Terry Joggers - Black L", 88.00, 30.00),
        ("APP-PARKA-COAT", "All-Weather Technical Storm Parka - L", 295.00, 110.00),
        ("APP-WOOL-SWTR", "Seamless Merino Crewneck Sweater - M", 125.00, 44.00),
        ("APP-CHINO-KHK", "Performance Stretch Chino Pant - 32x32", 92.00, 32.00),
        ("APP-SHIRT-OXF", "Tailored Oxford Button-Down - White M", 72.00, 24.00),
        ("APP-ACTIVE-SHRT", "Moisture-Wicking Athletic Shorts - M", 42.00, 13.00),
        ("APP-THERM-BASE", "Base Layer Thermal Compression Top - L", 52.00, 17.00)
    ],
    "Electronics": [
        ("ELEC-ANC-HEAD-01", "Studio Wireless ANC Headphones", 249.99, 92.00),
        ("ELEC-ANC-HEAD-02", "Studio Pro ANC Headphones Silver", 279.99, 105.00),
        ("ELEC-EAR-BUD-01", "True Wireless Noise-Cancelling Earbuds", 149.99, 52.00),
        ("ELEC-EAR-BUD-02", "Sport Fit Waterproof Wireless Earbuds", 99.95, 33.00),
        ("ELEC-MAG-CHRG-02", "3-in-1 MagSafe Fast Charging Dock", 89.95, 31.00),
        ("ELEC-USB-HUB-03", "10-in-1 USB-C Hub Thunderbolt 4", 79.99, 27.00),
        ("ELEC-CAM-4K-04", "Ultra-HD Streaming Webcam 4K 60FPS", 119.00, 41.00),
        ("ELEC-MECH-KEY-01", "Wireless Low-Profile Mechanical Keyboard", 139.00, 48.00),
        ("ELEC-ERG-MOUSE", "Precision Ergonomic Bluetooth Mouse", 79.00, 26.00),
        ("ELEC-PWR-BNK-20K", "20,000mAh 65W PD Laptop Power Bank", 69.95, 23.00),
        ("ELEC-MIC-POD-01", "Broadcast Dynamic USB/XLR Microphone", 159.00, 56.00),
        ("ELEC-SPK-BLU-01", "Rugged IP67 Waterproof Bluetooth Speaker", 89.00, 29.00),
        ("ELEC-MON-ARM-01", "Heavy-Duty Dual Monitor Desk Mount Arm", 110.00, 38.00),
        ("ELEC-LED-BAR-01", "ScreenBar Smart Monitor Light Lamp", 59.00, 19.00),
        ("ELEC-CBL-THUN-01", "Braided Thunderbolt 4 Cable 2M (40Gbps)", 35.00, 9.50),
        ("ELEC-WALL-GAN-65", "65W Dual Port GaN Nano Wall Charger", 39.99, 11.00),
        ("ELEC-SMART-PLUG", "Energy Monitoring WiFi Smart Plug 4-Pack", 42.00, 13.00),
        ("ELEC-VR-PAD-01", "Anti-Fatigue Standing Desk Active Mat", 65.00, 21.00),
        ("ELEC-LAP-STND-01", "Foldable Anodized Aluminum Laptop Riser", 48.00, 15.00),
        ("ELEC-DESK-PAD-XL", "Micro-Weave Hydrophobic Desk Mat XXL", 32.00, 9.00)
    ],
    "Accessories": [
        ("ACC-LEATH-WLT-01", "RFID Blocking Bi-fold Leather Wallet", 45.00, 15.00),
        ("ACC-CARD-HOLD-02", "Slim Titanium Cardholder Money Clip", 38.00, 12.00),
        ("ACC-BACK-30L-02", "Urban Commuter Waterproof Backpack 30L", 110.00, 39.00),
        ("ACC-DUFF-45L-03", "Weekend Travel Duffle Bag Water-Resistant", 135.00, 48.00),
        ("ACC-SLING-8L-04", "Crossbody Everyday Tech Sling Bag 8L", 65.00, 22.00),
        ("ACC-CAP-WOOL-03", "Merino Wool Thermal Beanie - Charcoal", 32.00, 9.50),
        ("ACC-CAP-WOOL-04", "Merino Wool Thermal Beanie - Olive", 32.00, 9.50),
        ("ACC-SUN-POL-04", "Polarized Titanium Sunglasses - Matte Black", 95.00, 30.00),
        ("ACC-SUN-POL-05", "Polarized Aviator Sunglasses - Gold Frame", 105.00, 33.00),
        ("ACC-PASSP-CASE", "Full Grain Leather Passport Travel Wallet", 48.00, 16.00),
        ("ACC-KEY-ORG-01", "Silent Magnetic Key Organizer Keychain", 28.00, 8.50),
        ("ACC-LEATH-BELT", "Hand-Stitched Italian Bridle Leather Belt", 55.00, 18.00),
        ("ACC-WATCH-ROLL", "Triple Watch Storage Travel Case Suede", 75.00, 24.00),
        ("ACC-DOPP-KIT-01", "Waterproof Ballistic Nylon Toiletry Kit", 39.00, 12.50),
        ("ACC-TECH-POUCH", "Cable & Tech Accessory Organizer Pouch", 34.00, 10.00)
    ],
    "Beauty & Wellness": [
        ("BEAUT-SERUM-VITC", "Triple Active Vitamin C Brightening Serum 30ml", 48.00, 12.00),
        ("BEAUT-RETINOL-01", "Encapsulated Retinol Night Repair Cream 50ml", 58.00, 15.00),
        ("BEAUT-HA-HYDRA-02", "Multi-Molecular Hyaluronic Acid Essence", 36.00, 8.50),
        ("BEAUT-SUN-SPF50", "Mineral Invisible Shield Sunscreen SPF 50+", 32.00, 7.50),
        ("BEAUT-CLEAN-OIL", "Gentle Botanical Cleansing Oil 150ml", 28.00, 7.00),
        ("BEAUT-LIP-TREAT", "Overnight Peptide Nourishing Lip Butter", 19.00, 4.50),
        ("BEAUT-EXFOL-AHA", "AHA/BHA Chemical Exfoliating Toner 100ml", 26.00, 6.00),
        ("BEAUT-CLAY-MASK", "Purifying French Green Clay Detox Mask", 29.00, 7.00),
        ("BEAUT-EYE-PEPT", "Caffeine & Matrixyl Peptide Eye Gel", 38.00, 9.00),
        ("BEAUT-FACIAL-OIL", "Pure Cold-Pressed Squalane Balancing Oil", 34.00, 8.00),
        ("BEAUT-BODY-WASH", "Eucalyptus & Cedarwood Aromatherapy Wash", 24.00, 5.50),
        ("BEAUT-HAIR-MASK", "Argan & Keratin Deep Conditioning Hair Mask", 35.00, 8.50),
        ("BEAUT-SCALP-SER", "Rosemary & Biotin Density Scalp Treatment", 42.00, 10.50),
        ("BEAUT-MIST-ROSE", "Organic Damascus Rosewater Hydrating Mist", 22.00, 5.00),
        ("BEAUT-HAND-CR-01", "Shea & Cocoa Butter Intensive Hand Salve", 16.00, 3.80)
    ],
    "Home & Kitchen": [
        ("HOME-LINEN-QUILT-01", "Washed French Linen Duvet - Queen Slate", 195.00, 68.00),
        ("HOME-LINEN-QUILT-02", "Washed French Linen Duvet - King Natural", 215.00, 75.00),
        ("HOME-SHEET-SET", "Percale Organic Cotton Sheet Set - Queen", 130.00, 44.00),
        ("HOME-DIFF-CER-02", "Ultrasonic Ceramic Aroma Diffuser 300ml", 55.00, 17.50),
        ("HOME-CANDLE-SOY-03", "Hand-Poured Amber & Sandalwood Soy Candle", 28.00, 7.50),
        ("HOME-CANDLE-SOY-04", "Hand-Poured Smoked Fig & Bergamot Candle", 28.00, 7.50),
        ("HOME-CHOP-BRD-01", "End-Grain Walnut Hardwood Cutting Board", 85.00, 28.00),
        ("HOME-KNIFE-CHEF", "Japanese VG-10 Damascus Steel Chef Knife 8in", 145.00, 49.00),
        ("HOME-CAST-IRON", "Pre-Seasoned Enamelled Dutch Oven 5.5 Qt", 120.00, 41.00),
        ("HOME-POUR-KETTLE", "Precision Gooseneck Electric Kettle Matte", 89.00, 29.00),
        ("HOME-CERAM-MUG", "Handmade Stoneware Coffee Mug Set of 2", 34.00, 9.00),
        ("HOME-GLASS-STRW", "Borosilicate Drinking Glasses 16oz Set of 4", 36.00, 10.00),
        ("HOME-AIR-PUR-01", "True HEPA Silent Room Air Purifier 250sqft", 139.00, 46.00),
        ("HOME-TOWEL-SET", "Turkish Zero-Twist Plush Bath Towel Set 4pc", 68.00, 21.00),
        ("HOME-THRW-BLNK", "Chunky Hand-Knit Weighted Throw Blanket", 125.00, 42.00)
    ]
}

def setup_clean_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

def generate_100_curated_skus():
    """Populates exactly 100 SKUs with structured inventory drift ground truth."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    sku_master_list = []
    for cat, items in CATEGORIES_SPEC.items():
        for sku, title, price, cost in items:
            barcode = f"UPC-{abs(hash(sku)) % 10000000000:010d}"
            cur.execute("""
                INSERT INTO ecom_products (sku, title, category, barcode, unit_price, cost_price, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (sku, title, cat, barcode, price, cost))
            sku_master_list.append({
                "sku": sku, "title": title, "category": cat,
                "price": price, "cost": cost, "barcode": barcode
            })
            
    print(f"[Setup] Inserted {len(sku_master_list)} distinct commercial SKUs across 6 categories.")
    
    # Partition 100 SKUs into deliberate ground-truth drift states:
    # 40 SKUs: State A (Perfect Match)
    # 25 SKUs: State B (Safe Hidden Stock: WMS > Shopify)
    # 25 SKUs: State C (Ghost Stock Danger: Shopify > WMS)
    # 10 SKUs: State D (Transit Noise: Drift <= 2% and in-transit)
    
    random.seed(42)
    shuffled_skus = list(sku_master_list)
    random.shuffle(shuffled_skus)
    
    state_a_skus = shuffled_skus[0:40]
    state_b_skus = shuffled_skus[40:65]
    state_c_skus = shuffled_skus[65:90]
    state_d_skus = shuffled_skus[90:100]
    
    inventory_records_storefront = []
    inventory_records_wms = []
    
    # State A (Perfect Match)
    for idx, item in enumerate(state_a_skus):
        base_qty = random.randint(30, 200)
        bin_loc = f"AISLE-A-B{(idx % 30) + 1:02d}"
        inventory_records_storefront.append((item["sku"], base_qty, "loc_primary_fba", 1))
        inventory_records_wms.append((item["sku"], base_qty, 0, bin_loc, 0))
        item["ground_truth"] = "STATE_A"
        item["shopify_qty"] = base_qty
        item["wms_qty"] = base_qty
        
    # State B (Safe Hidden Stock: WMS > Shopify)
    for idx, item in enumerate(state_b_skus):
        shop_qty = random.randint(10, 50)
        surplus = random.randint(15, 80)
        wms_qty = shop_qty + surplus
        bin_loc = f"AISLE-B-B{(idx % 30) + 1:02d}"
        inventory_records_storefront.append((item["sku"], shop_qty, "loc_primary_fba", 1))
        inventory_records_wms.append((item["sku"], wms_qty, 0, bin_loc, 0))
        item["ground_truth"] = "STATE_B"
        item["shopify_qty"] = shop_qty
        item["wms_qty"] = wms_qty
        item["surplus"] = surplus
        
    # State C (Ghost Stock Danger: Shopify > WMS)
    for idx, item in enumerate(state_c_skus):
        wms_qty = random.randint(0, 15)
        phantom_units = random.randint(20, 95)
        shop_qty = wms_qty + phantom_units
        bin_loc = f"AISLE-C-B{(idx % 30) + 1:02d}"
        inventory_records_storefront.append((item["sku"], shop_qty, "loc_primary_fba", 1))
        inventory_records_wms.append((item["sku"], wms_qty, 0, bin_loc, 0))
        item["ground_truth"] = "STATE_C"
        item["shopify_qty"] = shop_qty
        item["wms_qty"] = wms_qty
        item["phantom"] = phantom_units
        
    # State D (Transit Noise: Drift <= 2% and in-transit)
    for idx, item in enumerate(state_d_skus):
        base_stock = random.randint(400, 1000)
        transit_delta = max(1, int(base_stock * random.uniform(0.005, 0.018))) # <= 1.8%
        shop_qty = base_stock
        wms_qty = base_stock - transit_delta
        bin_loc = f"AISLE-D-B{(idx % 30) + 1:02d}"
        inventory_records_storefront.append((item["sku"], shop_qty, "loc_primary_fba", 1))
        inventory_records_wms.append((item["sku"], wms_qty, transit_delta, bin_loc, 1)) # Flagged in-transit
        item["ground_truth"] = "STATE_D"
        item["shopify_qty"] = shop_qty
        item["wms_qty"] = wms_qty
        item["in_transit"] = transit_delta
        
    cur.executemany("""
        INSERT INTO ecom_storefront_inventory (sku, shopify_quantity, location_id, tracked)
        VALUES (?, ?, ?, ?)
    """, inventory_records_storefront)
    
    cur.executemany("""
        INSERT INTO ecom_wms_inventory (sku, wms_quantity, in_transit_quantity, bin_location, is_in_transit)
        VALUES (?, ?, ?, ?, ?)
    """, inventory_records_wms)
    
    conn.commit()
    conn.close()
    
    print(f"[Inventory] Initialized ground-truth stock levels: "
          f"40 State A, 25 State B, 25 State C, 10 State D.")
    return sku_master_list

def generate_100k_orders(sku_list, total_orders=100000):
    """Generates exactly 100,000 realistic orders with Pareto distribution and returns."""
    start_time = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    cur = conn.cursor()
    
    now = datetime.now()
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Pareto sales distribution weights: top 20 SKUs receive ~65% of order traffic
    weights = []
    for i in range(len(sku_list)):
        if i < 20:
            weights.append(10.0) # High velocity
        elif i < 50:
            weights.append(3.0)  # Moderate
        elif i < 85:
            weights.append(1.0)  # Long tail
        else:
            weights.append(0.05) # Dead stock candidates
            
    order_batch = []
    items_batch = []
    returns_batch = []
    
    CHANNELS = ["shopify_online", "shopify_pos", "shopify_mobile_app", "instagram_shop"]
    CH_WEIGHTS = [0.65, 0.15, 0.15, 0.05]
    RETURN_REASONS = [
        "Customer Return: Size Mismatch",
        "Customer Return: Changed Mind",
        "Carrier Return: Undeliverable Address",
        "Quality Defect: Flawed Stitching / Finish",
        "Order Cancellation: Buyer Requested Before Dispatch"
    ]
    
    print(f"[Orders] Generating {total_orders:,} orders with realistic multi-item line carts...")
    
    order_counter = 100000
    for order_idx in range(1, total_orders + 1):
        order_counter += 1
        order_id = f"ORD-{order_counter}"
        
        # Date distribution: 85% in past 90 days, 10% yesterday, 5% today
        rand_date_factor = random.random()
        if rand_date_factor < 0.10:
            order_date = yesterday
        elif rand_date_factor < 0.15:
            order_date = now.strftime("%Y-%m-%d")
        else:
            days_ago = random.randint(2, 90)
            order_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            
        channel = random.choices(CHANNELS, weights=CH_WEIGHTS)[0]
        cust_email = f"user_{order_counter % 25000}@consumer.com"
        
        # Cart size: 70% 1 item, 22% 2 items, 8% 3 items
        cart_size = random.choices([1, 2, 3], weights=[0.70, 0.22, 0.08])[0]
        selected_items = random.choices(sku_list, weights=weights, k=cart_size)
        
        total_amount = 0.0
        for item in selected_items:
            qty = random.choices([1, 2, 3], weights=[0.88, 0.10, 0.02])[0]
            price = item["price"]
            total_amount += (qty * price)
            items_batch.append((order_id, item["sku"], qty, price))
            
            # 3.5% return rate on completed orders
            if random.random() < 0.035:
                returns_batch.append((
                    order_id,
                    item["sku"],
                    qty,
                    "return" if random.random() > 0.3 else "cancellation",
                    random.choice(RETURN_REASONS),
                    order_date
                ))
                
        order_batch.append((
            order_id,
            order_date,
            cust_email,
            round(total_amount, 2),
            channel
        ))
        
        # Flush in 20,000 chunks for lightning speed
        if len(order_batch) >= 20000:
            cur.executemany("""
                INSERT INTO ecom_orders (order_id, order_date, customer_email, total_amount, channel)
                VALUES (?, ?, ?, ?, ?)
            """, order_batch)
            cur.executemany("""
                INSERT INTO ecom_order_items (order_id, sku, quantity, unit_price)
                VALUES (?, ?, ?, ?)
            """, items_batch)
            if returns_batch:
                cur.executemany("""
                    INSERT INTO ecom_returns_cancellations (order_id, sku, quantity, event_type, reason, event_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, returns_batch)
            conn.commit()
            order_batch.clear()
            items_batch.clear()
            returns_batch.clear()
            sys.stdout.write(f"\r  -> Ingested {order_idx:,} / {total_orders:,} orders...")
            sys.stdout.flush()
            
    # Final flush
    if order_batch:
        cur.executemany("""
            INSERT INTO ecom_orders (order_id, order_date, customer_email, total_amount, channel)
            VALUES (?, ?, ?, ?, ?)
        """, order_batch)
        cur.executemany("""
            INSERT INTO ecom_order_items (order_id, sku, quantity, unit_price)
            VALUES (?, ?, ?, ?)
        """, items_batch)
        if returns_batch:
            cur.executemany("""
                INSERT INTO ecom_returns_cancellations (order_id, sku, quantity, event_type, reason, event_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, returns_batch)
        conn.commit()
        
    conn.close()
    elapsed = time.time() - start_time
    print(f"\n[Orders] Complete: {total_orders:,} orders successfully seeded in {elapsed:.2f} seconds ({total_orders/elapsed:,.0f} orders/sec).")

def generate_stock_reports():
    """Generates executive inventory valuation and audit reconciliation reports."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT p.sku, p.title, p.category, p.unit_price, p.cost_price,
               s.shopify_quantity, w.wms_quantity, w.in_transit_quantity, w.bin_location, w.is_in_transit
        FROM ecom_products p
        JOIN ecom_storefront_inventory s ON p.sku = s.sku
        JOIN ecom_wms_inventory w ON p.sku = w.sku
        ORDER BY p.sku ASC
    """)
    rows = cur.fetchall()
    
    total_retail_val = 0.0
    total_cost_val = 0.0
    total_hidden_rev = 0.0
    total_phantom_oversells = 0
    total_phantom_cost_risk = 0.0
    
    ledger_entries = []
    
    for r in rows:
        sku, title, cat, price, cost, s_qty, w_qty, in_transit, bin_loc, is_transit = r
        drift = s_qty - w_qty
        
        total_retail_val += (w_qty * price)
        total_cost_val += (w_qty * cost)
        
        state = "STATE_A_PERFECT_MATCH"
        if drift < 0:
            state = "STATE_B_SAFE_HIDDEN"
            total_hidden_rev += abs(drift) * price
        elif drift > 0:
            if is_transit and (abs(drift) / max(s_qty, w_qty, 1)) <= 0.02:
                state = "STATE_D_TRANSIT_NOISE"
            else:
                state = "STATE_C_GHOST_DANGER"
                total_phantom_oversells += drift
                total_phantom_cost_risk += (drift * price)
                
        ledger_entries.append({
            "sku": sku,
            "title": title,
            "category": cat,
            "unit_price": price,
            "cost_price": cost,
            "shopify_qty": s_qty,
            "wms_qty": w_qty,
            "drift_score": drift,
            "state": state,
            "bin_location": bin_loc
        })
        
    conn.close()
    
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "total_catalog_skus": len(rows),
        "total_physical_warehouse_units": sum(r[6] for r in rows),
        "total_storefront_advertised_units": sum(r[5] for r in rows),
        "warehouse_physical_retail_valuation": round(total_retail_val, 2),
        "warehouse_physical_cogs_valuation": round(total_cost_val, 2),
        "hidden_stock_revenue_locked": round(total_hidden_rev, 2),
        "phantom_ghost_stock_at_risk_units": total_phantom_oversells,
        "phantom_ghost_stock_at_risk_revenue": round(total_phantom_cost_risk, 2),
        "state_breakdown": {
            "state_a_perfect_match": sum(1 for e in ledger_entries if e["state"] == "STATE_A_PERFECT_MATCH"),
            "state_b_safe_hidden": sum(1 for e in ledger_entries if e["state"] == "STATE_B_SAFE_HIDDEN"),
            "state_c_ghost_danger": sum(1 for e in ledger_entries if e["state"] == "STATE_C_GHOST_DANGER"),
            "state_d_transit_noise": sum(1 for e in ledger_entries if e["state"] == "STATE_D_TRANSIT_NOISE")
        }
    }
    
    # Write JSON report
    json_path = os.path.join(REPORTS_DIR, "inventory_stock_valuation_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
        
    # Write Markdown report
    md_path = os.path.join(REPORTS_DIR, "inventory_stock_valuation_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(rf"""# Executive Inventory Stock Valuation & Drift Report
**Generated:** `{report_data['generated_at']}` | **Catalog Size:** `{report_data['total_catalog_skus']} SKUs`

## 📊 Inventory Financial Summary
| Valuation Metric | Amount | Description |
| :--- | :--- | :--- |
| **Physical Inventory Value (Retail)** | **${report_data['warehouse_physical_retail_valuation']:,.2f}** | Realizable gross revenue of physical shelf stock |
| **Physical Inventory Cost (COGS)** | **${report_data['warehouse_physical_cogs_valuation']:,.2f}** | Book asset value of physical stock |
| **Safe Hidden Revenue Locked** | **${report_data['hidden_stock_revenue_locked']:,.2f}** | Unlisted surplus stock ready for automated unlock |
| **Phantom Ghost Stock Exposure** | **${report_data['phantom_ghost_stock_at_risk_revenue']:,.2f}** | Exposure to oversell chargebacks & cancellations |
| **Phantom Oversell Risk Units** | **{report_data['phantom_ghost_stock_at_risk_units']:,} units** | Phantom items advertised without physical stock |

## 🎯 State Machine Classification Breakdown
| State Category | SKU Count | Share | Deterministic Action |
| :--- | :--- | :--- | :--- |
| **State A (Perfect Match)** | **{report_data['state_breakdown']['state_a_perfect_match']}** | {report_data['state_breakdown']['state_a_perfect_match']}% | Silent pass; 100% synchronized |
| **State B (Safe Hidden Stock)** | **{report_data['state_breakdown']['state_b_safe_hidden']}** | {report_data['state_breakdown']['state_b_safe_hidden']}% | Autonomous Shopify stock increase |
| **State C (Ghost Stock Danger)** | **{report_data['state_breakdown']['state_c_ghost_danger']}** | {report_data['state_breakdown']['state_c_ghost_danger']}% | Suspension protocol & HITL physical count |
| **State D (Transit Noise)** | **{report_data['state_breakdown']['state_d_transit_noise']}** | {report_data['state_breakdown']['state_d_transit_noise']}% | Covered by in-transit manifest ($\le 2\%$) |
""")

    # Write CSV Ledger
    csv_path = os.path.join(REPORTS_DIR, "daily_stock_drift_ledger.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("sku,title,category,unit_price,cost_price,shopify_qty,wms_qty,drift_score,state,bin_location\n")
        for e in ledger_entries:
            safe_title = e["title"].replace(",", " ")
            f.write(f"{e['sku']},{safe_title},{e['category']},{e['unit_price']},{e['cost_price']},{e['shopify_qty']},{e['wms_qty']},{e['drift_score']},{e['state']},{e['bin_location']}\n")
            
    print(f"[Reports] Reports generated in {REPORTS_DIR}:")
    print(f"  -> inventory_stock_valuation_report.json")
    print(f"  -> inventory_stock_valuation_report.md")
    print(f"  -> daily_stock_drift_ledger.csv")
    print(f"  -> Hidden Revenue Locked: ${report_data['hidden_stock_revenue_locked']:,.2f}")
    print(f"  -> Phantom Stock Oversell Risk: {report_data['phantom_ghost_stock_at_risk_units']} units (${report_data['phantom_ghost_stock_at_risk_revenue']:,.2f})")

if __name__ == "__main__":
    setup_clean_db()
    skus = generate_100_curated_skus()
    generate_100k_orders(skus, total_orders=100000)
    generate_stock_reports()

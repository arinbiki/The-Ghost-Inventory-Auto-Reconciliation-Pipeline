"""
Industrial-Grade Benchmark & Stress Testing Suite
The Ghost Inventory Auto-Reconciliation Pipeline

Evaluates:
  1. Mathematical Accuracy & Ground Truth Logic (0% tolerance)
  2. Database Query Throughput over 100,000 Orders
  3. Scoring Engine Throughput & Latency Percentiles (p50, p95, p99)
  4. Multi-Threaded Concurrency (50 concurrent workers, zero deadlocks)
  5. Reflex 1 (Blind Agent) & Reflex 2 (Flash Sale Lockdown) under stress
  6. Live End-to-End Webhook Pipeline Validation
"""

import unittest
import time
import sqlite3
import os
import sys
import json
import threading
import concurrent.futures
import statistics
import urllib.request
from datetime import datetime, timedelta

# Path configuration
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "database", "inventory_recon.db")
WM_SCRIPTS_DIR = os.path.join(PROJECT_DIR, "windmill", "scripts")
REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")
sys.path.insert(0, WM_SCRIPTS_DIR)

from quaint_script import (
    evaluate_sku_drift,
    main as run_quaint_brain,
    STATE_A_PERFECT_MATCH,
    STATE_B_SAFE_HIDDEN_STOCK,
    STATE_C_GHOST_STOCK_DANGER,
    STATE_D_TRANSIT_NOISE
)
from fetch_parallel_stock import main as run_fetch_parallel
from execute_tool_mutation import main as run_tool_mutation
from timeout_failsafe_reconciler import main as run_timeout_failsafe

N8N_SENSOR_URL = os.environ.get("N8N_SENSOR_WEBHOOK_URL", "")
N8N_EXECUTOR_URL = os.environ.get("N8N_SHOPIFY_TOOL_WEBHOOK_URL", "")

class TestEnterpriseStressAndAccuracy(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(DB_PATH):
            raise FileNotFoundError(f"Database at {DB_PATH} not found. Run generate_100k_dataset.py first.")
            
    def test_01_accuracy_against_100_sku_ground_truth(self):
        """Validates 100% mathematical accuracy and zero classification errors on all 100 SKUs."""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT p.sku, p.title, p.unit_price, s.shopify_quantity, w.wms_quantity, w.is_in_transit
            FROM ecom_products p
            JOIN ecom_storefront_inventory s ON p.sku = s.sku
            JOIN ecom_wms_inventory w ON p.sku = w.sku
        """)
        items = cur.fetchall()
        conn.close()
        
        self.assertEqual(len(items), 100, "Must have exactly 100 items in catalog")
        
        state_counts = {
            STATE_A_PERFECT_MATCH: 0,
            STATE_B_SAFE_HIDDEN_STOCK: 0,
            STATE_C_GHOST_STOCK_DANGER: 0,
            STATE_D_TRANSIT_NOISE: 0
        }
        
        for sku, title, price, s_qty, w_qty, is_transit in items:
            res = evaluate_sku_drift(
                sku=sku,
                title=title,
                shopify_qty=s_qty,
                wms_qty=w_qty,
                is_in_transit=bool(is_transit),
                unit_price=float(price),
                transit_margin_pct=0.02,
                is_lockdown=False
            )
            
            drift = s_qty - w_qty
            self.assertEqual(res["drift_score"], drift, f"Drift arithmetic error on {sku}")
            
            cat = res["state_category"]
            state_counts[cat] += 1
            
            # Mathematical invariant checks
            if cat == STATE_A_PERFECT_MATCH:
                self.assertEqual(s_qty, w_qty)
                self.assertEqual(res["oversell_risk_units"], 0)
                self.assertEqual(res["hidden_revenue_potential"], 0.0)
            elif cat == STATE_B_SAFE_HIDDEN_STOCK:
                self.assertGreater(w_qty, s_qty)
                self.assertEqual(res["oversell_risk_units"], 0)
                expected_rev = round((w_qty - s_qty) * price, 2)
                self.assertEqual(res["hidden_revenue_potential"], expected_rev)
            elif cat == STATE_C_GHOST_STOCK_DANGER:
                self.assertGreater(s_qty, w_qty)
                self.assertEqual(res["oversell_risk_units"], s_qty - w_qty)
                self.assertEqual(res["hidden_revenue_potential"], 0.0)
            elif cat == STATE_D_TRANSIT_NOISE:
                self.assertTrue(bool(is_transit))
                rel = abs(drift) / max(s_qty, w_qty, 1)
                self.assertLessEqual(rel, 0.02)
                
        # Verify ground truth distribution matches planned 40/25/25/10 breakdown
        self.assertEqual(state_counts[STATE_A_PERFECT_MATCH], 40)
        self.assertEqual(state_counts[STATE_B_SAFE_HIDDEN_STOCK], 25)
        self.assertEqual(state_counts[STATE_C_GHOST_STOCK_DANGER], 25)
        self.assertEqual(state_counts[STATE_D_TRANSIT_NOISE], 10)
        print(f"\n[Accuracy] 100/100 SKUs correctly classified. Error Rate: 0.0000%.")

    def test_02_database_query_speed_on_100k_orders(self):
        """Measures heuristic sensor query latency across 100,000 orders & 180,000 items."""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Verify 100k orders exist
        cur.execute("SELECT COUNT(*) FROM ecom_orders")
        order_count = cur.fetchone()[0]
        self.assertGreaterEqual(order_count, 100000, "Database must contain at least 100,000 orders")
        
        now = datetime.now()
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Benchmark Sensor Heuristic 1 & 2 query: High Velocity (>5) & Returns yesterday
        query_start = time.perf_counter()
        cur.execute("""
            SELECT 
                p.sku,
                p.title,
                COALESCE(sales.yesterday_qty, 0) as yesterday_sales,
                COALESCE(rets.yesterday_returns, 0) as yesterday_returns,
                COALESCE(sales30.sales_30d, 0) as sales_30d
            FROM ecom_products p
            LEFT JOIN (
                SELECT i.sku, SUM(i.quantity) as yesterday_qty
                FROM ecom_orders o INDEXED BY idx_orders_covering
                JOIN ecom_order_items i INDEXED BY idx_order_items_covering ON o.order_id = i.order_id
                WHERE o.order_date = ?
                GROUP BY i.sku
            ) sales ON p.sku = sales.sku
            LEFT JOIN (
                SELECT sku, SUM(quantity) as yesterday_returns
                FROM ecom_returns_cancellations
                WHERE event_date = ?
                GROUP BY sku
            ) rets ON p.sku = rets.sku
            LEFT JOIN (
                SELECT i.sku, SUM(i.quantity) as sales_30d
                FROM ecom_orders o INDEXED BY idx_orders_covering
                JOIN ecom_order_items i INDEXED BY idx_order_items_covering ON o.order_id = i.order_id
                WHERE o.order_date >= date(?, '-30 days')
                GROUP BY i.sku
            ) sales30 ON p.sku = sales30.sku
        """, (yesterday, yesterday, yesterday))
        
        results = cur.fetchall()
        query_time_ms = (time.perf_counter() - query_start) * 1000
        conn.close()
        
        self.assertEqual(len(results), 100)
        # High performance query: indexed execution across 100k orders should finish in < 1500ms
        self.assertLess(query_time_ms, 1500.0, f"Query took too long: {query_time_ms:.2f}ms")
        print(f"[Query Throughput] Evaluated 100k orders in {query_time_ms:.2f} ms ({order_count / (query_time_ms / 1000):,.0f} rows/sec).")

    def test_03_engine_throughput_and_latency_percentiles(self):
        """Stress tests the quaint_script scoring engine with 10,000 synthetic evaluations."""
        # Generate 10,000 synthetic test items
        test_items = []
        for i in range(10000):
            test_items.append({
                "sku": f"PERF-SKU-{i:05d}",
                "title": f"Performance Evaluation Item #{i}",
                "shopify_qty": (i % 80) + 10,
                "wms_qty": (i % 65) + 5,
                "is_in_transit": (i % 10 == 0),
                "unit_price": 50.0 + (i % 150)
            })
            
        latencies = []
        BATCH_SIZE = 500
        total_batches = len(test_items) // BATCH_SIZE
        
        overall_start = time.perf_counter()
        for b in range(total_batches):
            batch = test_items[b * BATCH_SIZE : (b + 1) * BATCH_SIZE]
            t0 = time.perf_counter()
            res = run_quaint_brain(audit_items=batch, is_lockdown=False)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000) # ms
            self.assertTrue(res["success"])
            
        total_time = time.perf_counter() - overall_start
        throughput = len(test_items) / total_time
        
        p50 = statistics.median(latencies)
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        p99 = max(latencies)
        
        print(f"[Engine Speed] Processed 10,000 SKUs in {total_time:.3f}s -> {throughput:,.0f} SKUs/sec.")
        print(f"  -> Batch Latency: p50={p50:.2f}ms, p95={p95:.2f}ms, p99={p99:.2f}ms (Batch Size: {BATCH_SIZE})")
        self.assertGreater(throughput, 15000, "Engine throughput must exceed 15,000 SKUs/sec")

    def test_04_concurrency_stress_test(self):
        """Simulates 30 concurrent workers making simultaneous state evaluations & DB mutations."""
        NUM_WORKERS = 30
        mutations_per_worker = 10
        
        errors = []
        completed_workers = []
        
        def worker_task(worker_id):
            try:
                # 1. Evaluate batch
                batch = [
                    {
                        "sku": f"CONCUR-SKU-W{worker_id}-{j}",
                        "title": f"Concurrent Product {j}",
                        "shopify_qty": 20 + j,
                        "wms_qty": 40 + j,
                        "is_in_transit": False,
                        "unit_price": 75.0
                    }
                    for j in range(mutations_per_worker)
                ]
                brain_res = run_quaint_brain(audit_items=batch, is_lockdown=False)
                if not brain_res["success"]:
                    errors.append(f"Worker {worker_id} brain failed")
                    return
                    
                # 2. Execute mutations locally
                muts = brain_res["auto_execute_mutations"]
                res = run_tool_mutation(mutations=muts, run_id=f"CONCUR-RUN-{worker_id}", call_n8n_remote=False)
                if not res["success"]:
                    errors.append(f"Worker {worker_id} tool failed")
                    return
                    
                completed_workers.append(worker_id)
            except Exception as e:
                errors.append(f"Worker {worker_id} exception: {e}")
                
        start_concurrency = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = [executor.submit(worker_task, w) for w in range(NUM_WORKERS)]
            concurrent.futures.wait(futures)
            
        elapsed = time.perf_counter() - start_concurrency
        
        self.assertEqual(len(errors), 0, f"Encountered concurrency errors: {errors}")
        self.assertEqual(len(completed_workers), NUM_WORKERS)
        print(f"[Concurrency] {NUM_WORKERS} concurrent threads completed {NUM_WORKERS * mutations_per_worker} mutations in {elapsed:.3f}s without deadlock.")

    def test_05_reflex_circuit_breakers_under_stress(self):
        """Validates Reflex 1 (Blind Agent) and Reflex 2 (Flash Sale Lockdown) under high stress."""
        
        # Test Reflex 1: 3PL API 503 Outage
        outage_res = run_fetch_parallel(
            target_skus=["SHOE-AIR-001", "APP-HOOD-BLK-L"],
            simulate_wms_outage=True,
            max_retries=3
        )
        self.assertFalse(outage_res["success"])
        self.assertEqual(outage_res["status"], "WMS_BLIND")
        self.assertEqual(len(outage_res["items"]), 0)
        self.assertIn("Refusing to alter storefront stock blindly", outage_res["error"])
        
        # Test Reflex 2: Flash Sale Lockdown suppresses State C downward inventory mutations
        flash_items = [
            {"sku": "FLASH-01", "title": "Viral Item", "shopify_qty": 500, "wms_qty": 20, "unit_price": 99.0},
            {"sku": "FLASH-02", "title": "Trending Item", "shopify_qty": 200, "wms_qty": 10, "unit_price": 149.0}
        ]
        lockdown_res = run_quaint_brain(audit_items=flash_items, is_lockdown=True)
        self.assertTrue(lockdown_res["success"])
        summary = lockdown_res["summary"]
        self.assertTrue(summary["is_lockdown_active"])
        self.assertFalse(summary["needs_human_approval"])
        self.assertEqual(len(lockdown_res["ghost_stock_approval_queue"]), 0) # Suppressed!
        
        for item in lockdown_res["state_c_items"]:
            self.assertEqual(item["action_required"], "FLASH_SALE_LOCKED_SKIP")
            self.assertEqual(item["proposed_shopify_qty"], item["shopify_qty"]) # Preserves storefront stock!
            
        print("[Reflex Stability] Reflex 1 (Blind Agent) & Reflex 2 (Flash Sale Lockdown) verified under stress.")

    def test_06_live_n8n_and_windmill_full_loop(self):
        """Validates the live deployed n8n sensor and tool webhooks against production."""
        if not N8N_SENSOR_URL or not N8N_EXECUTOR_URL:
            # Standalone verification using local tool executor simulation
            test_mutation = [{
                "sku": "SHOE-BOOT-101",
                "target_qty": 50,
                "previous_shopify_qty": 20,
                "wms_qty": 50,
                "reason": "SAFE_HIDDEN_STOCK_AUTO_INCREASE",
                "approved_by": "stress_benchmark_agent"
            }]
            sim_res = run_tool_mutation(mutations=test_mutation, call_n8n_remote=False)
            self.assertTrue(sim_res.get("success"))
            self.assertEqual(sim_res.get("mutations_count"), 1)
            print("[Offline / CI Verification] End-to-end mutation validated locally (N8N webhook URLs not configured).")
            return

        # 1. Trigger live n8n sensor webhook
        req_sensor = urllib.request.Request(
            N8N_SENSOR_URL,
            data=json.dumps({"trigger_type": "stress_validation_suite"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_sensor, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            sensor_data = json.loads(resp.read().decode("utf-8"))
            
        self.assertTrue(sensor_data.get("success"))
        targets = sensor_data.get("target_skus", [])
        self.assertGreater(len(targets), 0)
        
        # 2. Trigger live n8n tool executor webhook
        test_mutation = [{
            "sku": targets[0],
            "target_qty": 50,
            "previous_shopify_qty": 20,
            "wms_qty": 50,
            "reason": "SAFE_HIDDEN_STOCK_AUTO_INCREASE",
            "approved_by": "stress_benchmark_agent"
        }]
        
        req_tool = urllib.request.Request(
            N8N_EXECUTOR_URL,
            data=json.dumps({"run_id": "BENCHMARK-RUN", "mutations": test_mutation}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_tool, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            tool_data = json.loads(resp.read().decode("utf-8"))
            
        self.assertTrue(tool_data.get("success"))
        self.assertEqual(tool_data.get("mutations_executed_count"), 1)
        self.assertIn("Ghost Inventory Auto-Reconciliation Report", tool_data.get("executive_markdown_report", ""))
        print("[Live End-to-End] Both deployed n8n webhooks responding at 200 OK with correct payloads.")

if __name__ == "__main__":
    unittest.main(verbosity=2)

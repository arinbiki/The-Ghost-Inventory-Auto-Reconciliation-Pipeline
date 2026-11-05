"""
End-to-End Integration Test & Full Pipeline Simulation
Simulates the entire autonomous loop:
  Sensor (n8n) -> Deterministic Brain (Windmill) -> HITL Verification -> Tool Executor (n8n)
"""

import unittest
import urllib.request
import json
import os
import sys

# Add windmill and database scripts to path
SCRIPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "windmill", "scripts"
)
DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "database"
)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, DB_DIR)

from seed_data import init_db, seed_catalog, seed_inventory_and_telemetry
from quaint_script import main as run_quaint_brain
from fetch_parallel_stock import main as run_fetch_parallel
from execute_tool_mutation import main as run_execute_tool

N8N_SENSOR_URL = os.environ.get("N8N_SENSOR_WEBHOOK_URL", "")
N8N_EXECUTOR_URL = os.environ.get("N8N_SHOPIFY_TOOL_WEBHOOK_URL", "")

class TestEndToEndReconciliationPipeline(unittest.TestCase):
    
    def setUp(self):
        """Reseed fresh database before running end-to-end simulation."""
        init_db()
        skus = seed_catalog()
        seed_inventory_and_telemetry(skus)
    
    def test_live_sensor_to_brain_to_tool_execution(self):
        """Executes full live pipeline with deployed n8n webhooks and Windmill brain."""
        
        # 1. Trigger the Sensor Layer (n8n or local heuristic)
        if N8N_SENSOR_URL:
            req_sensor = urllib.request.Request(
                N8N_SENSOR_URL,
                data=json.dumps({"trigger_type": "e2e_integration_test", "is_lockdown": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req_sensor, timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                sensor_data = json.loads(resp.read().decode("utf-8"))
            target_skus = sensor_data.get("target_skus", [])
        else:
            # Standalone fallback for CI / local test
            import sqlite3
            conn = sqlite3.connect("database/inventory_recon.db")
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT sku FROM ecom_order_items WHERE quantity > 5
                UNION
                SELECT DISTINCT sku FROM ecom_returns_cancellations
            """)
            target_skus = [r[0] for r in cur.fetchall()]

        self.assertGreater(len(target_skus), 0)
        
        # 2. Parallel Fetch Phase (Windmill)
        fetch_result = run_fetch_parallel(target_skus=target_skus)
        self.assertTrue(fetch_result["success"])
        items = fetch_result["items"]
        
        # 3. Deterministic Brain Scoring Phase (quaint_script)
        brain_result = run_quaint_brain(audit_items=items, is_lockdown=False)
        self.assertTrue(brain_result["success"])
        summary = brain_result["summary"]
        
        self.assertGreater(summary["state_b_safe_hidden_stock_count"], 0)
        self.assertGreater(summary["state_c_ghost_stock_danger_count"], 0)
        
        # 4. Auto-Execute State B Mutations via n8n Tool (or local DB if offline)
        auto_mutations = brain_result["auto_execute_mutations"]
        call_remote = bool(N8N_EXECUTOR_URL)
        tool_res = run_execute_tool(mutations=auto_mutations, call_n8n_remote=call_remote)
        self.assertTrue(tool_res["success"])
        if call_remote:
            self.assertTrue(tool_res["remote_n8n_executed"])
            self.assertTrue(tool_res["n8n_response"]["success"])
        
        # 5. Simulate Human-in-the-Loop count verification for State C
        ghost_queue = brain_result["ghost_stock_approval_queue"]
        hitl_mutations = []
        for g in ghost_queue:
            # Warehouse manager walked aisle and verified physical stock equals wms_qty
            hitl_mutations.append({
                "sku": g["sku"],
                "target_qty": g["wms_qty"],
                "previous_shopify_qty": g["shopify_qty"],
                "wms_qty": g["wms_qty"],
                "drift_score": g["drift_score"],
                "reason": "HUMAN_VERIFIED_PHYSICAL_COUNT",
                "approved_by": "warehouse_manager@store.com"
            })
            
        hitl_tool_res = run_execute_tool(mutations=hitl_mutations, call_n8n_remote=call_remote)
        self.assertTrue(hitl_tool_res["success"])
        if call_remote:
            self.assertTrue(hitl_tool_res["remote_n8n_executed"])
            # Verify n8n operations report was generated
            report_text = hitl_tool_res["n8n_response"].get("executive_markdown_report", "")
            self.assertIn("Ghost Inventory Auto-Reconciliation Report", report_text)
            self.assertIn("Ghost Stock Prevented", report_text)

if __name__ == "__main__":
    unittest.main(verbosity=2)

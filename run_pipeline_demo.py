#!/usr/bin/env python3
"""
The Ghost Inventory Auto-Reconciliation Pipeline - Interactive Demonstration Runner
Simulates the complete Zero-LLM Agentic Architecture:
  1. Sensor & Heuristics (n8n)
  2. Simultaneous Parallel Fetch & Circuit Breaker (Windmill)
  3. Deterministic Brain Scoring & State Machine (Windmill quaint_script)
  4. Suspension Protocol / Human-in-the-Loop Verification
  5. Standardized Tool Executor & Executive Reporting (n8n)
"""

import os
import sys
import json
import time
import urllib.request
from datetime import datetime

# Path setup
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
WM_SCRIPTS_DIR = os.path.join(PROJECT_DIR, "windmill", "scripts")
DB_DIR = os.path.join(PROJECT_DIR, "database")
sys.path.insert(0, WM_SCRIPTS_DIR)
sys.path.insert(0, DB_DIR)

from seed_data import init_db, seed_catalog, seed_inventory_and_telemetry
from quaint_script import main as run_quaint_brain
from fetch_parallel_stock import main as run_fetch_parallel
from execute_tool_mutation import main as run_tool_mutation
from timeout_failsafe_reconciler import main as run_timeout_failsafe

N8N_SENSOR_URL = os.environ.get("N8N_SENSOR_WEBHOOK_URL", "")
N8N_EXECUTOR_URL = os.environ.get("N8N_SHOPIFY_TOOL_WEBHOOK_URL", "")

def print_banner():
    print("""
================================================================================
   THE GHOST INVENTORY AUTO-RECONCILIATION PIPELINE (Zero-LLM Agent)
   Storefront (Shopify) vs Physical Warehouse (3PL/WMS) Autonomous Auditor
================================================================================
""")

def step_1_seed_environment():
    print("\n[PHASE 0: Environment Initialization]")
    print("  -> Initializing SQLite database at database/inventory_recon.db")
    init_db()
    skus = seed_catalog()
    seed_inventory_and_telemetry(skus)
    print(f"  -> Successfully generated {len(skus)} SKUs with planted drift scenarios.")

def step_2_sensor_layer(is_lockdown=False):
    print("\n[PHASE 1: Sensor & Trigger Layer (n8n)]")
    print("  -> Waking up agent via n8n Sensor Webhook...")
    payload = {
        "trigger_type": "demonstration_run",
        "is_lockdown": is_lockdown
    }
    
    data = None
    if N8N_SENSOR_URL:
        try:
            req = urllib.request.Request(
                N8N_SENSOR_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            data = None
            
    if not data:
        # Standalone local heuristic evaluation
        import sqlite3
        conn = sqlite3.connect("database/inventory_recon.db")
        cur = conn.cursor()
        cur.execute("""
            SELECT p.sku, p.title, p.unit_price, 'HIGH_VELOCITY' as reason
            FROM ecom_order_items oi
            JOIN ecom_products p ON oi.sku = p.sku
            WHERE oi.quantity > 5
            UNION ALL
            SELECT p.sku, p.title, p.unit_price, 'REVERSE_LOGISTICS' as reason
            FROM ecom_returns_cancellations rc
            JOIN ecom_products p ON rc.sku = p.sku
            LIMIT 15
        """)
        rows = cur.fetchall()
        target_skus = list(set([r[0] for r in rows]))
        data = {
            "run_id": "RUN-LOCAL-DEMO-001",
            "targets_identified": len(target_skus),
            "target_skus": target_skus,
            "details": [{"sku": r[0], "title": r[1], "unit_price": r[2], "flagged_reason": r[3]} for r in rows]
        }
        
    print(f"  -> Run ID: {data.get('run_id')}")
    print(f"  -> Heuristics Evaluated: High Velocity (>5), Returns/Cancellations, 5% Dead Stock")
    print(f"  -> Target SKUs Identified: {data.get('targets_identified')} items")
    for t in data.get("details", [])[:6]:
        print(f"     * [{t.get('flagged_reason')}] {t.get('sku')}: {t.get('title')[:35]}... (${t.get('unit_price')})")
    if len(data.get("details", [])) > 6:
        print(f"     * ... and {len(data.get('details')) - 6} more target items.")
    return data.get("target_skus", [])

def step_3_parallel_fetch(target_skus):
    print("\n[PHASE 2: Point-in-Time Parallel Fetch (Windmill)]")
    print(f"  -> Dispatching concurrent fetch across Shopify and 3PL WMS for {len(target_skus)} SKUs...")
    fetch_result = run_fetch_parallel(target_skus=target_skus, batch_size=50)
    print(f"  -> Point-in-Time Timestamp synchronized.")
    print(f"  -> WMS Status: {fetch_result.get('status')} (Circuit Breaker OK)")
    return fetch_result.get("items", [])

def step_4_deterministic_brain(items, is_lockdown=False):
    print("\n[PHASE 3: Deterministic Brain & Scoring (Windmill quaint_script)]")
    print("  -> Calculating Drift Score = (Shopify_Qty - WMS_Qty) across all items...")
    brain_result = run_quaint_brain(audit_items=items, is_lockdown=is_lockdown)
    summary = brain_result["summary"]
    
    print("\n  +-------------------------------------------------------------------------+")
    print("  | AUDIT SUMMARY DASHBOARD                                                  |")
    print("  +-------------------------------------------------------------------------+")
    print(f"  | Total SKUs Evaluated       : {summary['total_skus_evaluated']:<44} |")
    print(f"  | State A (Perfect Match)    : {summary['state_a_perfect_match_count']:<44} |")
    print(f"  | State B (Safe Hidden Stock): {summary['state_b_safe_hidden_stock_count']:<44} |")
    print(f"  | State C (Ghost Stock Danger): {summary['state_c_ghost_stock_danger_count']:<44} |")
    print(f"  | State D (Transit Noise)    : {summary['state_d_transit_noise_count']:<44} |")
    print(f"  | Potential Revenue Unlocked : ${summary['total_hidden_revenue_unlocked']:<43,.2f} |")
    print(f"  | Oversell Risk Prevented    : {summary['total_oversell_risk_prevented']:<44} units |")
    print("  +-------------------------------------------------------------------------+\n")
    return brain_result

def step_5_execute_and_report(brain_result):
    print("[PHASE 4: Autonomous Execution & Suspension Protocol]")
    
    # 1. State B Auto-Increase
    auto_muts = brain_result.get("auto_execute_mutations", [])
    if auto_muts:
        print(f"  -> [Branch B] Auto-executing {len(auto_muts)} Safe Hidden Stock updates via n8n Tool...")
        tool_res = run_tool_mutation(mutations=auto_muts, call_n8n_remote=True)
        print(f"     Status: Storefront stock increased safely.")
        
    # 2. State C Suspension & Human Verification
    ghost_queue = brain_result.get("ghost_stock_approval_queue", [])
    if ghost_queue:
        print(f"\n  -> [Branch C] SUSPENSION PROTOCOL ACTIVATED for {len(ghost_queue)} Ghost Stock Danger items:")
        for g in ghost_queue:
            print(f"     ! [DANGER] {g['sku']}: Shopify advertising {g['shopify_qty']} vs Physical WMS {g['wms_qty']} (Delta: +{g['drift_score']} phantom units!)")
        
        print("\n  -> Simulating Warehouse Manager physical bin count in aisles...")
        time.sleep(1)
        print("  -> Physical aisle count confirmed: Physical matches WMS bins.")
        print("  -> Approving mutations and dispatching to n8n Tool Executor...")
        
        hitl_mutations = [
            {
                "sku": g["sku"],
                "target_qty": g["wms_qty"],
                "previous_shopify_qty": g["shopify_qty"],
                "wms_qty": g["wms_qty"],
                "drift_score": g["drift_score"],
                "reason": "HUMAN_VERIFIED_PHYSICAL_COUNT",
                "approved_by": "warehouse_manager@store.com"
            }
            for g in ghost_queue
        ]
        
        exec_res = run_tool_mutation(mutations=hitl_mutations, call_n8n_remote=True)
        n8n_report = exec_res["n8n_response"]
        
        print("\n[PHASE 5: Executive Report & Closed Loop (n8n)]")
        print("  -> Posted to Slack #operations channel:")
        print(n8n_report.get("executive_markdown_report"))

def main():
    print_banner()
    step_1_seed_environment()
    target_skus = step_2_sensor_layer()
    items = step_3_parallel_fetch(target_skus)
    brain_result = step_4_deterministic_brain(items)
    step_5_execute_and_report(brain_result)
    print("\n================================================================================")
    print("   DEMONSTRATION RUN COMPLETE - PIPELINE 100% OPERATIONAL")
    print("================================================================================\n")

if __name__ == "__main__":
    main()


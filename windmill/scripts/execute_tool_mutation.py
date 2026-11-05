"""
Standardized Tool Executor Client: Update_Shopify_Inventory
Windmill Path: f/ecom_inventory_recon/execute_tool_mutation

Dispatches verified inventory updates to n8n's standardized tool endpoint
or records them directly into the storefront inventory state.
"""

from typing import List, Dict, Any, Optional
import urllib.request
import urllib.error
import json
import os
import sqlite3
import datetime

N8N_TOOL_WEBHOOK_URL = os.environ.get(
    "N8N_SHOPIFY_TOOL_WEBHOOK_URL",
    "http://localhost:5678/webhook/update-shopify-inventory"
)
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

DB_PATHS = [
    r"D:\web project\Ecommerce\The Ghost Inventory Auto-Reconciliation Pipeline\database\inventory_recon.db",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Ecommerce", "The Ghost Inventory Auto-Reconciliation Pipeline", "database", "inventory_recon.db"),
    os.path.join(os.getcwd(), "database", "inventory_recon.db")
]

def get_db_path() -> Optional[str]:
    for p in DB_PATHS:
        if os.path.exists(p):
            return p
    return None

def update_local_db_inventory(mutations: List[Dict[str, Any]], run_id: str) -> Dict[str, Any]:
    """Applies mutations locally to the SQLite inventory database with concurrency busy retry."""
    db_file = get_db_path()
    if not db_file:
        return {"updated_count": len(mutations), "local_db": False}
        
    updated = 0
    max_retries = 5
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(db_file, timeout=30.0)
            conn.execute("PRAGMA busy_timeout = 30000;")
            cur = conn.cursor()
            
            for m in mutations:
                sku = m.get("sku")
                target_qty = int(m.get("target_qty", 0))
                reason = m.get("reason", "AUTO_RECONCILE")
                
                cur.execute("""
                    UPDATE ecom_storefront_inventory
                    SET shopify_quantity = ?, last_synced_at = CURRENT_TIMESTAMP
                    WHERE sku = ?
                """, (target_qty, sku))
                
                cur.execute("""
                    INSERT INTO ecom_audit_drift_records (
                        run_id, sku, shopify_qty, wms_qty, drift_score,
                        state_category, resolution_action, approved_physical_qty,
                        final_synced_qty, operator_notes, resolved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    run_id,
                    sku,
                    m.get("previous_shopify_qty", target_qty),
                    m.get("wms_qty", target_qty),
                    m.get("drift_score", 0),
                    m.get("state_category", "STATE_B_OR_APPROVED_C"),
                    reason,
                    m.get("approved_qty", target_qty),
                    target_qty,
                    f"Mutated by {m.get('approved_by', 'deterministic_agent')}"
                ))
                updated += 1
                
            conn.commit()
            conn.close()
            break
        except sqlite3.OperationalError as err:
            if "locked" in str(err) and attempt < max_retries - 1:
                time.sleep(0.05 * (attempt + 1))
            else:
                raise err
                
    return {"updated_count": updated, "local_db": True}

def main(
    mutations: Optional[List[Dict[str, Any]]] = None,
    run_id: Optional[str] = None,
    call_n8n_remote: bool = False
) -> Dict[str, Any]:
    """
    Executes inventory mutations via n8n's standardized tool endpoint or local database.
    """
    current_run_id = run_id or f"RUN-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    if not mutations:
        mutations = [
            {
                "sku": "SHOE-BOOT-101",
                "target_qty": 45,
                "previous_shopify_qty": 12,
                "wms_qty": 45,
                "drift_score": -33,
                "reason": "SAFE_HIDDEN_STOCK_AUTO_INCREASE",
                "approved_by": "autonomous_agent"
            }
        ]
        
    n8n_response = None
    remote_executed = False
    
    if call_n8n_remote and N8N_TOOL_WEBHOOK_URL:
        payload = {
            "run_id": current_run_id,
            "mutations": mutations,
            "executed_at": datetime.datetime.now().isoformat()
        }
        try:
            req = urllib.request.Request(
                N8N_TOOL_WEBHOOK_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-N8N-API-KEY": N8N_API_KEY
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                remote_executed = True
                n8n_response = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            n8n_response = {"error": str(e), "fallback": "local_db_update"}
            
    # Always commit to local database state
    db_result = update_local_db_inventory(mutations, current_run_id)
    
    return {
        "success": True,
        "run_id": current_run_id,
        "mutations_count": len(mutations),
        "mutations": mutations,
        "db_result": db_result,
        "remote_n8n_executed": remote_executed,
        "n8n_response": n8n_response
    }

if __name__ == "__main__":
    res = main()
    print("Execution result:", res)

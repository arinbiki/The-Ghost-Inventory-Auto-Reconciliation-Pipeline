"""
12-Hour Deterministic Timeout Failsafe Reconciler
Windmill Path: f/ecom_inventory_recon/timeout_failsafe_reconciler

Executes the fail-safe heuristic when a warehouse manager does not respond
within the 12-hour suspension window. Automatically forces Shopify stock to 0
for unverified ghost inventory to prevent customer chargebacks and overselling.
"""

from typing import List, Dict, Any, Optional
import os
import sqlite3
import datetime

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

def main(
    unresolved_ghost_items: Optional[List[Dict[str, Any]]] = None,
    run_id: Optional[str] = None,
    timeout_hours: int = 12
) -> Dict[str, Any]:
    """
    Applies the zero-out failsafe to unverified ghost items.
    """
    current_run_id = run_id or f"TIMEOUT-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    if not unresolved_ghost_items:
        unresolved_ghost_items = [
            {
                "sku": "SHOE-AIR-001",
                "title": "Air Trail Running Sneaker - Men US 10",
                "shopify_qty": 48,
                "wms_qty": 8,
                "drift_score": 40
            }
        ]
        
    zeroed_mutations = []
    total_prevented_oversells = 0
    
    for item in unresolved_ghost_items:
        sku = item.get("sku")
        prev_shopify_qty = int(item.get("shopify_qty", 0))
        oversell_prevented = prev_shopify_qty
        total_prevented_oversells += oversell_prevented
        
        mutation = {
            "sku": sku,
            "title": item.get("title", ""),
            "target_qty": 0, # Forced zero-out
            "previous_shopify_qty": prev_shopify_qty,
            "wms_qty": item.get("wms_qty", 0),
            "reason": f"TIMEOUT_FAILSAFE_ZERO_OUT_{timeout_hours}H_EXPIRED",
            "approved_by": "deterministic_timeout_watchdog",
            "oversell_prevented": oversell_prevented
        }
        zeroed_mutations.append(mutation)
        
    # Update database if available
    db_file = get_db_path()
    if db_file:
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        for m in zeroed_mutations:
            cur.execute("""
                UPDATE ecom_storefront_inventory
                SET shopify_quantity = 0, last_synced_at = CURRENT_TIMESTAMP
                WHERE sku = ?
            """, (m["sku"],))
            cur.execute("""
                INSERT INTO ecom_audit_drift_records (
                    run_id, sku, shopify_qty, wms_qty, drift_score,
                    state_category, resolution_action, approved_physical_qty,
                    final_synced_qty, operator_notes, resolved_at
                ) VALUES (?, ?, ?, ?, ?, 'STATE_C', 'TIMEOUT_ZERO_OUT', 0, 0, ?, CURRENT_TIMESTAMP)
            """, (
                current_run_id,
                m["sku"],
                m["previous_shopify_qty"],
                m["wms_qty"],
                m["previous_shopify_qty"] - m["wms_qty"],
                f"Warehouse count timed out after {timeout_hours} hours. Auto-zeroed storefront."
            ))
        conn.commit()
        conn.close()
        
    return {
        "success": True,
        "run_id": current_run_id,
        "timeout_policy": f"{timeout_hours}_hours_unresponsive",
        "zeroed_skus_count": len(zeroed_mutations),
        "total_oversell_risk_eliminated": total_prevented_oversells,
        "mutations": zeroed_mutations,
        "timestamp": datetime.datetime.now().isoformat()
    }

if __name__ == "__main__":
    res = main()
    print("Failsafe result:", res)

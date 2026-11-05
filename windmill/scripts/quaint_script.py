"""
The Ghost Inventory Auto-Reconciliation Pipeline - Deterministic Brain
Windmill Path: f/ecom_inventory_recon/quaint_script

Zero-LLM Deterministic State Machine for E-Commerce Inventory Reconciliation.
Replaces probabilistic AI with exact algorithmic scoring, drift categorization,
and automated routing between Storefront (Shopify) and Warehouse (3PL/WMS).
"""

from typing import List, Dict, Any, Optional
import time
import math
import uuid
import datetime

# --- State Machine Categorization Constants ---
STATE_A_PERFECT_MATCH = "STATE_A_PERFECT_MATCH"
STATE_B_SAFE_HIDDEN_STOCK = "STATE_B_SAFE_HIDDEN_STOCK"
STATE_C_GHOST_STOCK_DANGER = "STATE_C_GHOST_STOCK_DANGER"
STATE_D_TRANSIT_NOISE = "STATE_D_TRANSIT_NOISE"

def evaluate_sku_drift(
    sku: str,
    title: str,
    shopify_qty: int,
    wms_qty: int,
    is_in_transit: bool = False,
    unit_price: float = 0.0,
    transit_margin_pct: float = 0.02,
    is_lockdown: bool = False
) -> Dict[str, Any]:
    """
    Core Deterministic Scoring Algorithm:
    Drift Score = (Shopify_Qty - WMS_Qty)
    
    States:
      - State A: Drift == 0 (Perfect Match)
      - State B: WMS_Qty > Shopify_Qty (Safe Hidden Stock: Safe to increase storefront inventory)
      - State C: Shopify_Qty > WMS_Qty (Ghost Stock Danger: Website sells items warehouse doesn't have)
      - State D: Drift <= 2% margin and flagged in_transit in WMS (Transit Noise)
      
    Reflexes:
      - Flash Sale Lock (is_lockdown): Refuses to decrease storefront inventory during high-traffic sales.
    """
    drift_score = shopify_qty - wms_qty
    base_denom = max(abs(shopify_qty), abs(wms_qty), 1)
    relative_drift_pct = abs(drift_score) / base_denom
    
    # State A: Perfect Match
    if drift_score == 0:
        return {
            "sku": sku,
            "title": title,
            "shopify_qty": shopify_qty,
            "wms_qty": wms_qty,
            "drift_score": 0,
            "state_category": STATE_A_PERFECT_MATCH,
            "action_required": "NO_ACTION",
            "proposed_shopify_qty": shopify_qty,
            "hidden_revenue_potential": 0.0,
            "oversell_risk_units": 0,
            "notes": "Storefront and physical warehouse are perfectly synchronized."
        }
        
    # State D: Transit Noise Filter
    # Drift is within allowable tolerance (e.g. 2%) AND actively flagged as in-transit
    if is_in_transit and relative_drift_pct <= transit_margin_pct:
        return {
            "sku": sku,
            "title": title,
            "shopify_qty": shopify_qty,
            "wms_qty": wms_qty,
            "drift_score": drift_score,
            "state_category": STATE_D_TRANSIT_NOISE,
            "action_required": "TRANSIT_NOISE_DISMISSED",
            "proposed_shopify_qty": shopify_qty,
            "hidden_revenue_potential": 0.0,
            "oversell_risk_units": 0,
            "notes": f"Discrepancy ({drift_score:+d} units, {relative_drift_pct:.1%}) is accounted for by in-transit freight."
        }
        
    # State B: Safe Hidden Stock (WMS > Shopify)
    # Physical warehouse has more units than storefront shows. Safe to increase Shopify stock.
    if wms_qty > shopify_qty:
        delta = wms_qty - shopify_qty
        potential_revenue = round(delta * unit_price, 2)
        return {
            "sku": sku,
            "title": title,
            "shopify_qty": shopify_qty,
            "wms_qty": wms_qty,
            "drift_score": drift_score, # Negative drift
            "state_category": STATE_B_SAFE_HIDDEN_STOCK,
            "action_required": "AUTO_INCREASE_SHOPIFY",
            "proposed_shopify_qty": wms_qty,
            "hidden_revenue_potential": potential_revenue,
            "oversell_risk_units": 0,
            "notes": f"Physical warehouse has {delta} unlisted units. Auto-increase unlocks ${potential_revenue:,.2f} in sales."
        }
        
    # State C: Ghost Stock Danger (Shopify > WMS)
    # Digital storefront is selling phantom inventory not present in physical warehouse.
    oversell_units = shopify_qty - wms_qty
    
    # Check Reflex 2: Flash Sale Lock
    if is_lockdown:
        return {
            "sku": sku,
            "title": title,
            "shopify_qty": shopify_qty,
            "wms_qty": wms_qty,
            "drift_score": drift_score,
            "state_category": STATE_C_GHOST_STOCK_DANGER,
            "action_required": "FLASH_SALE_LOCKED_SKIP",
            "proposed_shopify_qty": shopify_qty,
            "hidden_revenue_potential": 0.0,
            "oversell_risk_units": oversell_units,
            "notes": "FLASH SALE LOCKDOWN ACTIVE: System refuses to lower inventory during high-traffic viral event."
        }
        
    return {
        "sku": sku,
        "title": title,
        "shopify_qty": shopify_qty,
        "wms_qty": wms_qty,
        "drift_score": drift_score,
        "state_category": STATE_C_GHOST_STOCK_DANGER,
        "action_required": "SUSPEND_FOR_HITL",
        "proposed_shopify_qty": wms_qty, # Proposed physical truth
        "hidden_revenue_potential": 0.0,
        "oversell_risk_units": oversell_units,
        "notes": f"DANGER: Website is advertising {oversell_units} non-existent units. Routing to warehouse physical count audit."
    }

def main(
    audit_items: Optional[List[Dict[str, Any]]] = None,
    is_lockdown: bool = False,
    transit_margin_pct: float = 0.02,
    run_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entry point for Windmill: f/ecom_inventory_recon/quaint_script
    
    Processes the target SKU list, executes deterministic classification,
    and returns branch routing for the orchestration pipeline.
    """
    current_run_id = run_id or f"RUN-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    
    # Fallback to realistic mock data if invoked without items for direct testing
    if not audit_items:
        audit_items = [
            {
                "sku": "SHOE-AIR-001",
                "title": "Air Trail Running Sneaker - Men US 10",
                "shopify_qty": 48,
                "wms_qty": 8,
                "is_in_transit": False,
                "unit_price": 129.99
            },
            {
                "sku": "APP-HOOD-BLK-L",
                "title": "Heavyweight Organic Hoodie - Black L",
                "shopify_qty": 35,
                "wms_qty": 2,
                "is_in_transit": False,
                "unit_price": 78.00
            },
            {
                "sku": "SHOE-BOOT-101",
                "title": "Weatherproof Hiking Boot - Unisex 9",
                "shopify_qty": 12,
                "wms_qty": 45,
                "is_in_transit": False,
                "unit_price": 189.50
            },
            {
                "sku": "HOME-LINEN-QUILT-01",
                "title": "Washed French Linen Duvet - Queen Slate",
                "shopify_qty": 500,
                "wms_qty": 495,
                "is_in_transit": True,
                "unit_price": 195.00
            },
            {
                "sku": "ELEC-MAG-CHRG-02",
                "title": "3-in-1 MagSafe Fast Charging Dock",
                "shopify_qty": 40,
                "wms_qty": 40,
                "is_in_transit": False,
                "unit_price": 89.95
            }
        ]
        
    state_a_items = []
    state_b_items = []
    state_c_items = []
    state_d_items = []
    
    total_oversell_risk_prevented = 0
    total_hidden_revenue_unlocked = 0.0
    
    for item in audit_items:
        res = evaluate_sku_drift(
            sku=item.get("sku", "UNKNOWN"),
            title=item.get("title", ""),
            shopify_qty=int(item.get("shopify_qty", 0)),
            wms_qty=int(item.get("wms_qty", 0)),
            is_in_transit=bool(item.get("is_in_transit", False)),
            unit_price=float(item.get("unit_price", 0.0)),
            transit_margin_pct=transit_margin_pct,
            is_lockdown=is_lockdown
        )
        
        cat = res["state_category"]
        if cat == STATE_A_PERFECT_MATCH:
            state_a_items.append(res)
        elif cat == STATE_B_SAFE_HIDDEN_STOCK:
            state_b_items.append(res)
            total_hidden_revenue_unlocked += res["hidden_revenue_potential"]
        elif cat == STATE_C_GHOST_STOCK_DANGER:
            state_c_items.append(res)
            total_oversell_risk_prevented += res["oversell_risk_units"]
        elif cat == STATE_D_TRANSIT_NOISE:
            state_d_items.append(res)
            
    needs_human_approval = len(state_c_items) > 0 and not is_lockdown
    auto_execute_mutations = [
        {
            "sku": item["sku"],
            "target_qty": item["proposed_shopify_qty"],
            "previous_shopify_qty": item["shopify_qty"],
            "wms_qty": item["wms_qty"],
            "drift_score": item["drift_score"],
            "reason": "SAFE_HIDDEN_STOCK_AUTO_INCREASE"
        }
        for item in state_b_items
    ]
    
    ghost_stock_approval_queue = []
    if not is_lockdown:
        ghost_stock_approval_queue = [
            {
                "sku": item["sku"],
                "title": item["title"],
                "shopify_qty": item["shopify_qty"],
                "wms_qty": item["wms_qty"],
                "drift_score": item["drift_score"],
                "oversell_units": item["oversell_risk_units"],
                "proposed_qty": item["proposed_shopify_qty"],
                "status": "AWAITING_PHYSICAL_COUNT"
            }
            for item in state_c_items
        ]
    
    summary = {
        "run_id": current_run_id,
        "total_skus_evaluated": len(audit_items),
        "state_a_perfect_match_count": len(state_a_items),
        "state_b_safe_hidden_stock_count": len(state_b_items),
        "state_c_ghost_stock_danger_count": len(state_c_items),
        "state_d_transit_noise_count": len(state_d_items),
        "total_oversell_risk_prevented": total_oversell_risk_prevented,
        "total_hidden_revenue_unlocked": round(total_hidden_revenue_unlocked, 2),
        "is_lockdown_active": is_lockdown,
        "needs_human_approval": needs_human_approval,
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    return {
        "success": True,
        "summary": summary,
        "state_a_items": state_a_items,
        "state_b_items": state_b_items,
        "state_c_items": state_c_items,
        "state_d_items": state_d_items,
        "auto_execute_mutations": auto_execute_mutations,
        "ghost_stock_approval_queue": ghost_stock_approval_queue
    }

if __name__ == "__main__":
    result = main()
    print(f"Evaluated {result['summary']['total_skus_evaluated']} items.")
    print(f"State A: {result['summary']['state_a_perfect_match_count']}")
    print(f"State B (Hidden Stock): {result['summary']['state_b_safe_hidden_stock_count']}, Unlocked: ${result['summary']['total_hidden_revenue_unlocked']:,.2f}")
    print(f"State C (Ghost Stock): {result['summary']['state_c_ghost_stock_danger_count']}, Oversells Stopped: {result['summary']['total_oversell_risk_prevented']}")
    print(f"State D (Transit Noise): {result['summary']['state_d_transit_noise_count']}")


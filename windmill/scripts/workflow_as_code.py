"""
The Ghost Inventory Auto-Reconciliation Pipeline - Workflow as Code
Windmill Path: f/ecom_inventory_recon/workflow_as_code

Directed Acyclic Graph (DAG) for deterministic e-commerce inventory audit.
Orchestrates:
  1. Parallel simultaneous stock fetch (Shopify vs WMS)
  2. Deterministic brain evaluation (Drift State Machine)
  3. Suspension Protocol (Human-in-the-Loop physical count audit)
  4. 12-hour deterministic timeout fallback (auto-zero out)
  5. Standardized tool execution via n8n
"""

from typing import List, Dict, Any, Optional
import datetime
import uuid

# Official Windmill Workflow-as-Code SDK imports
from wmill import (
    workflow,
    task,
    task_script,
    step,
    sleep,
    wait_for_approval,
    get_approval_urls,
    parallel
)

fetch_parallel_script = task_script("f/ecom_inventory_recon/fetch_parallel_stock")
brain_evaluator_script = task_script("f/ecom_inventory_recon/quaint_script")
mutation_executor_script = task_script("f/ecom_inventory_recon/execute_tool_mutation")
failsafe_timeout_script = task_script("f/ecom_inventory_recon/timeout_failsafe_reconciler")

@task()
async def prepare_approval_payload(
    ghost_queue: List[Dict[str, Any]],
    urls: Dict[str, str],
    run_id: str
) -> Dict[str, Any]:
    """Prepares structured notification and form data for the warehouse manager."""
    return {
        "run_id": run_id,
        "notification_channel": "#warehouse-operations",
        "magic_approval_url": urls.get("resume", ""),
        "cancellation_url": urls.get("cancel", ""),
        "items_requiring_physical_audit": ghost_queue,
        "instructions": "Walk the designated warehouse bins, verify physical count, and submit approved quantities."
    }

@workflow
async def main(
    target_skus: Optional[List[str]] = None,
    is_lockdown: bool = False,
    transit_margin_pct: float = 0.02,
    timeout_seconds: int = 43200 # 12 hours
) -> Dict[str, Any]:
    
    run_id = await step("init_run_id", lambda: f"WAC-RUN-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}")
    
    # Step 1: Parallel Simultaneous Stock Fetch
    fetch_result = await fetch_parallel_script(
        target_skus=target_skus,
        simulate_wms_outage=False,
        max_retries=3
    )
    
    # Reflex 1 Check: Blind Agent (3PL outage)
    if not fetch_result.get("success", False) or fetch_result.get("status") == "WMS_BLIND":
        return {
            "status": "ABORTED_WMS_BLIND",
            "run_id": run_id,
            "error": fetch_result.get("error", "WMS Unavailable"),
            "action_taken": "Refusing to alter storefront stock without confirmed physical truth."
        }
        
    fetched_items = fetch_result.get("items", [])
    
    # Step 2: Deterministic Brain Evaluation (State Machine)
    brain_result = await brain_evaluator_script(
        audit_items=fetched_items,
        is_lockdown=is_lockdown,
        transit_margin_pct=transit_margin_pct,
        run_id=run_id
    )
    
    summary = brain_result.get("summary", {})
    auto_mutations = brain_result.get("auto_execute_mutations", [])
    ghost_queue = brain_result.get("ghost_stock_approval_queue", [])
    
    # Branch B: Auto-execute mutations for Safe Hidden Stock (WMS > Shopify)
    hidden_stock_exec_result = None
    if auto_mutations:
        hidden_stock_exec_result = await mutation_executor_script(
            mutations=auto_mutations,
            run_id=run_id,
            call_n8n_remote=True
        )
        
    # Branch C: Suspension Protocol for Ghost Stock Danger
    hitl_decision = None
    if ghost_queue and not is_lockdown:
        # Mint bound approval URLs for the human auditor
        approval_urls = await step("approval_urls", lambda: get_approval_urls("warehouse_manager_audit"))
        
        # Prepare dispatch payload for Slack / Email notification
        audit_packet = await prepare_approval_payload(ghost_queue, approval_urls, run_id)
        
        try:
            # Suspend DAG for Human Truth (Costs drop to $0)
            approval = await wait_for_approval(key="warehouse_manager_audit", timeout=timeout_seconds)
            
            # Human responded within grace period
            verified_counts = approval.get("physical_counts", {})
            approved_mutations = []
            
            for item in ghost_queue:
                sku = item["sku"]
                physical_verified_qty = int(verified_counts.get(sku, item["wms_qty"]))
                approved_mutations.append({
                    "sku": sku,
                    "target_qty": physical_verified_qty,
                    "previous_shopify_qty": item["shopify_qty"],
                    "wms_qty": item["wms_qty"],
                    "reason": "HUMAN_VERIFIED_PHYSICAL_COUNT",
                    "approved_by": approval.get("approver_email", "warehouse_manager@store.com")
                })
                
            hitl_decision = await mutation_executor_script(
                mutations=approved_mutations,
                run_id=run_id,
                call_n8n_remote=True
            )
            
        except Exception:
            # Deterministic Timeout Reflex: 12-hour grace period expired without human response!
            # Automatically force Shopify stock to 0 to prevent overselling chargebacks.
            hitl_decision = await failsafe_timeout_script(
                unresolved_ghost_items=ghost_queue,
                run_id=run_id,
                timeout_hours=12
            )
            
    return {
        "success": True,
        "run_id": run_id,
        "summary": summary,
        "hidden_stock_execution": hidden_stock_exec_result,
        "hitl_execution": hitl_decision,
        "status": "COMPLETED"
    }

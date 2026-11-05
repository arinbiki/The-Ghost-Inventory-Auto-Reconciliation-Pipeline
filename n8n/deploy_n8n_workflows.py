"""
Deploy and Activate n8n Workflows for The Ghost Inventory Auto-Reconciliation Pipeline.
Configurable via environment variables (N8N_BASE_URL, N8N_API_KEY).
"""

import urllib.request
import urllib.error
import json
import os
import sys

N8N_BASE_URL = os.environ.get("N8N_BASE_URL", "http://localhost:5678/api/v1/workflows")
API_KEY = os.environ.get("N8N_API_KEY", "")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_existing_workflow_id(wf_name: str) -> str:
    """Checks if a workflow with the given name already exists."""
    if not API_KEY:
        return ""
    req = urllib.request.Request(
        f"{N8N_BASE_URL}?limit=250",
        headers={"X-N8N-API-KEY": API_KEY}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("data", []):
                if item.get("name") == wf_name:
                    return item.get("id")
    except Exception as e:
        print(f"Could not check existing workflows: {e}")
    return ""

def deploy_workflow(filename: str):
    if not API_KEY:
        print("ERROR: N8N_API_KEY environment variable is required. Please configure it in .env.")
        return None

    file_path = os.path.join(CURRENT_DIR, filename)
    with open(file_path, "r", encoding="utf-8") as f:
        wf_data = json.load(f)
        
    wf_name = wf_data.get("name")
    existing_id = get_existing_workflow_id(wf_name)
    
    payload = {
        "name": wf_name,
        "nodes": wf_data.get("nodes"),
        "connections": wf_data.get("connections"),
        "settings": wf_data.get("settings", {"executionOrder": "v1"})
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-N8N-API-KEY": API_KEY
    }
    
    if existing_id:
        print(f"Workflow '{wf_name}' already exists (ID: {existing_id}). Updating...")
        req = urllib.request.Request(
            f"{N8N_BASE_URL}/{existing_id}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="PUT"
        )
        wf_id = existing_id
    else:
        print(f"Creating new workflow '{wf_name}'...")
        req = urllib.request.Request(
            N8N_BASE_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        wf_id = None
        
    try:
        with urllib.request.urlopen(req) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            wf_id = wf_id or res_data.get("id")
            print(f"Deploy success for '{wf_name}'! Workflow ID: {wf_id}")
            
            # Activate workflow
            act_url = f"{N8N_BASE_URL}/{wf_id}/activate"
            act_req = urllib.request.Request(
                act_url,
                data=b"{}",
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(act_req) as act_resp:
                print(f"Workflow '{wf_name}' ({wf_id}) ACTIVATED successfully (HTTP {act_resp.status})!")
                return wf_id
    except urllib.error.HTTPError as err:
        print(f"Deployment HTTP Error: {err.code} - {err.read().decode('utf-8')}")
    except Exception as err:
        print(f"Deployment failed for {filename}: {err}")
    return None

if __name__ == "__main__":
    print("--- Deploying Ghost Inventory Auto-Reconciliation Workflows to n8n ---")
    if not API_KEY:
        print("Notice: N8N_API_KEY is not set. Set N8N_API_KEY and N8N_BASE_URL before deploying.")
        sys.exit(1)
    id1 = deploy_workflow("workflow_1_inventory_sensor_and_trigger.json")
    id2 = deploy_workflow("workflow_2_shopify_inventory_executor.json")
    print(f"Deployment complete. Sensor ID: {id1}, Executor ID: {id2}")

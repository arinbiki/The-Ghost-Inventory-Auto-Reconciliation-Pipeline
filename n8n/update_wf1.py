import json
import os

wf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow_1_inventory_sensor_and_trigger.json")
with open(wf_path, "r", encoding="utf-8") as f:
    wf = json.load(f)

# Connect heuristic sensor to both respond and router
wf["connections"]["Heuristic Sensor Code Node"] = {
    "main": [
        [
            {"node": "Respond Trigger Status", "type": "main", "index": 0},
            {"node": "Router (Empty vs Has Targets)", "type": "main", "index": 0}
        ]
    ]
}

# Update respond trigger status node response expression
for n in wf["nodes"]:
    if n["name"] == "Respond Trigger Status":
        n["parameters"]["responseBody"] = "={{ JSON.stringify({\n  success: true,\n  run_id: $json.run_id,\n  targets_identified: $json.target_audit_count,\n  target_skus: $json.target_skus,\n  details: $json.target_audit_details,\n  is_lockdown: $json.is_lockdown,\n  status: $json.has_targets ? 'TARGETS_DISPATCHED_TO_WINDMILL' : 'TERMINATED_NO_TARGETS',\n  timestamp: $json.audit_timestamp\n}) }}"
    if n["name"] == "Dispatch to Windmill Brain":
        n["continueOnFail"] = True

with open(wf_path, "w", encoding="utf-8") as f:
    json.dump(wf, f, indent=2)

print("Successfully updated workflow_1_inventory_sensor_and_trigger.json structure!")

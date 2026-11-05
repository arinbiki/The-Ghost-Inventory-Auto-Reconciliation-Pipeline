"""
Unit Test Suite: 12-Hour Deterministic Timeout Failsafe
Validates that unverified ghost inventory is zeroed out to eliminate chargeback liability.
"""

import unittest
import sys
import os

SCRIPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "windmill", "scripts"
)
sys.path.insert(0, SCRIPT_DIR)

from timeout_failsafe_reconciler import main as run_timeout_failsafe

class TestTimeoutFailsafe(unittest.TestCase):
    
    def test_timeout_zero_out_mechanism(self):
        """Unverified ghost inventory must be forced to 0 after timeout expires."""
        unresolved_ghost_items = [
            {
                "sku": "SHOE-AIR-001",
                "title": "Air Trail Running Sneaker - Men US 10",
                "shopify_qty": 48,
                "wms_qty": 8,
                "drift_score": 40
            },
            {
                "sku": "APP-HOOD-BLK-L",
                "title": "Heavyweight Organic Hoodie - Black L",
                "shopify_qty": 35,
                "wms_qty": 2,
                "drift_score": 33
            }
        ]
        
        result = run_timeout_failsafe(
            unresolved_ghost_items=unresolved_ghost_items,
            run_id="TEST-TIMEOUT-RUN-01",
            timeout_hours=12
        )
        
        self.assertTrue(result["success"])
        self.assertEqual(result["zeroed_skus_count"], 2)
        self.assertEqual(result["total_oversell_risk_eliminated"], 83) # 48 + 35
        
        for m in result["mutations"]:
            self.assertEqual(m["target_qty"], 0)
            self.assertIn("TIMEOUT_FAILSAFE_ZERO_OUT", m["reason"])

if __name__ == "__main__":
    unittest.main(verbosity=2)


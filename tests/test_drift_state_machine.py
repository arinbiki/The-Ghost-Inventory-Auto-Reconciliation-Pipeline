"""
Unit Test Suite: Deterministic Drift State Machine
Validates States A, B, C, D, Flash Sale Lockdown, and Margin Tolerance.
"""

import unittest
import sys
import os

# Add windmill scripts to path
SCRIPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "windmill", "scripts"
)
sys.path.insert(0, SCRIPT_DIR)

from quaint_script import (
    evaluate_sku_drift,
    STATE_A_PERFECT_MATCH,
    STATE_B_SAFE_HIDDEN_STOCK,
    STATE_C_GHOST_STOCK_DANGER,
    STATE_D_TRANSIT_NOISE
)

class TestDeterministicStateMachine(unittest.TestCase):
    
    def test_state_a_perfect_match(self):
        """State A: Drift == 0. No mutations required."""
        res = evaluate_sku_drift(
            sku="SKU-MATCH-01",
            title="Matched Product",
            shopify_qty=50,
            wms_qty=50,
            unit_price=100.0
        )
        self.assertEqual(res["state_category"], STATE_A_PERFECT_MATCH)
        self.assertEqual(res["drift_score"], 0)
        self.assertEqual(res["action_required"], "NO_ACTION")
        self.assertEqual(res["proposed_shopify_qty"], 50)
        self.assertEqual(res["hidden_revenue_potential"], 0.0)
        self.assertEqual(res["oversell_risk_units"], 0)

    def test_state_b_safe_hidden_stock(self):
        """State B: WMS > Shopify. Safe to increase storefront inventory."""
        res = evaluate_sku_drift(
            sku="SKU-HIDDEN-02",
            title="Hidden Stock Product",
            shopify_qty=10,
            wms_qty=40,
            unit_price=50.0
        )
        self.assertEqual(res["state_category"], STATE_B_SAFE_HIDDEN_STOCK)
        self.assertEqual(res["drift_score"], -30) # WMS has 30 more
        self.assertEqual(res["action_required"], "AUTO_INCREASE_SHOPIFY")
        self.assertEqual(res["proposed_shopify_qty"], 40)
        self.assertEqual(res["hidden_revenue_potential"], 1500.0) # 30 * $50
        self.assertEqual(res["oversell_risk_units"], 0)

    def test_state_c_ghost_stock_danger(self):
        """State C: Shopify > WMS. Dangerous phantom inventory. Route to HITL."""
        res = evaluate_sku_drift(
            sku="SKU-GHOST-03",
            title="Ghost Sneaker",
            shopify_qty=48,
            wms_qty=8,
            unit_price=120.0,
            is_lockdown=False
        )
        self.assertEqual(res["state_category"], STATE_C_GHOST_STOCK_DANGER)
        self.assertEqual(res["drift_score"], 40) # 40 phantom units advertised!
        self.assertEqual(res["action_required"], "SUSPEND_FOR_HITL")
        self.assertEqual(res["oversell_risk_units"], 40)
        self.assertEqual(res["proposed_shopify_qty"], 8)

    def test_state_d_transit_noise_within_tolerance(self):
        """State D: Discrepancy <= 2% margin and flagged in-transit."""
        res = evaluate_sku_drift(
            sku="SKU-TRANSIT-04",
            title="In-Transit Linen",
            shopify_qty=500,
            wms_qty=495,
            is_in_transit=True,
            transit_margin_pct=0.02
        )
        self.assertEqual(res["state_category"], STATE_D_TRANSIT_NOISE)
        self.assertEqual(res["drift_score"], 5)
        self.assertEqual(res["action_required"], "TRANSIT_NOISE_DISMISSED")
        self.assertEqual(res["oversell_risk_units"], 0)

    def test_transit_noise_exceeding_tolerance_becomes_ghost(self):
        """If in-transit discrepancy exceeds 2% margin, it must NOT be dismissed as noise."""
        res = evaluate_sku_drift(
            sku="SKU-TRANSIT-05",
            title="Linen Large Discrepancy",
            shopify_qty=500,
            wms_qty=450, # 50 units delta = 10% drift > 2% margin!
            is_in_transit=True,
            transit_margin_pct=0.02
        )
        # Exceeds 2% margin -> classified as Ghost Stock Danger despite in_transit flag
        self.assertEqual(res["state_category"], STATE_C_GHOST_STOCK_DANGER)
        self.assertEqual(res["action_required"], "SUSPEND_FOR_HITL")

    def test_reflex_2_flash_sale_lockdown(self):
        """Reflex 2: If is_lockdown is True, downward inventory mutations must be frozen."""
        res = evaluate_sku_drift(
            sku="SKU-VIRAL-TIKTOK-06",
            title="Viral Lip Gloss",
            shopify_qty=100,
            wms_qty=20,
            is_lockdown=True # Flash sale active!
        )
        self.assertEqual(res["state_category"], STATE_C_GHOST_STOCK_DANGER)
        self.assertEqual(res["action_required"], "FLASH_SALE_LOCKED_SKIP")
        self.assertEqual(res["proposed_shopify_qty"], 100) # Preserves current storefront stock!

if __name__ == "__main__":
    unittest.main(verbosity=2)


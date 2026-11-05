"""
Unit Test Suite: Heuristic Sensor & Target Selection
Validates:
  1. High velocity SKUs (>5 sales yesterday) are flagged
  2. Reverse logistics SKUs (returns or cancellations yesterday) are flagged
  3. 5% random dead stock sample is audited
  4. Non-qualifying stable SKUs are filtered out to respect rate limits
"""

import unittest
import random

def evaluate_heuristic_sensor(catalog_items, random_seed=42):
    """Deterministic implementation matching the n8n Heuristic Sensor Code Node."""
    random.seed(random_seed)
    target_audit_list = []
    
    for item in catalog_items:
        reasons = []
        # Heuristic 1: High velocity (>5 sales yesterday)
        if item.get("yesterday_sales", 0) > 5:
            reasons.append("HIGH_VELOCITY_SALES")
            
        # Heuristic 2: Return or cancellation yesterday
        if item.get("yesterday_returns", 0) > 0:
            reasons.append("REVERSE_LOGISTICS_EVENT")
            
        # Heuristic 3: Dead stock (<1 sale in 30 days) with 5% sampling
        if item.get("sales_30d", 0) == 0:
            if random.random() <= 0.05 or item.get("force_sample", False):
                reasons.append("DEAD_STOCK_RANDOM_SAMPLE")
                
        if reasons:
            target_audit_list.append({
                "sku": item["sku"],
                "flagged_reasons": reasons
            })
            
    return target_audit_list

class TestHeuristicSensor(unittest.TestCase):
    
    def setUp(self):
        self.catalog = [
            {"sku": "SKU-VELOCITY-01", "yesterday_sales": 14, "yesterday_returns": 0, "sales_30d": 80},
            {"sku": "SKU-VELOCITY-02", "yesterday_sales": 6, "yesterday_returns": 0, "sales_30d": 40},
            {"sku": "SKU-LOW-SALES-03", "yesterday_sales": 2, "yesterday_returns": 0, "sales_30d": 35},
            {"sku": "SKU-RETURN-04", "yesterday_sales": 0, "yesterday_returns": 1, "sales_30d": 12},
            {"sku": "SKU-CANCEL-05", "yesterday_sales": 1, "yesterday_returns": 2, "sales_30d": 5},
            {"sku": "SKU-DEAD-FORCED-06", "yesterday_sales": 0, "yesterday_returns": 0, "sales_30d": 0, "force_sample": True},
            {"sku": "SKU-STABLE-UNTOUCHED", "yesterday_sales": 3, "yesterday_returns": 0, "sales_30d": 25}
        ]

    def test_high_velocity_selection(self):
        """SKUs with >5 sales yesterday must be targeted."""
        targets = evaluate_heuristic_sensor(self.catalog)
        target_skus = [t["sku"] for t in targets]
        self.assertIn("SKU-VELOCITY-01", target_skus)
        self.assertIn("SKU-VELOCITY-02", target_skus)

    def test_low_velocity_not_selected_without_other_flags(self):
        """SKUs with <=5 sales and no returns/dead stock must be excluded to save API budget."""
        targets = evaluate_heuristic_sensor(self.catalog)
        target_skus = [t["sku"] for t in targets]
        self.assertNotIn("SKU-LOW-SALES-03", target_skus)
        self.assertNotIn("SKU-STABLE-UNTOUCHED", target_skus)

    def test_reverse_logistics_selection(self):
        """SKUs with returns or cancellations must be targeted for potential inventory drift."""
        targets = evaluate_heuristic_sensor(self.catalog)
        target_skus = [t["sku"] for t in targets]
        self.assertIn("SKU-RETURN-04", target_skus)
        self.assertIn("SKU-CANCEL-05", target_skus)

    def test_dead_stock_sample_selection(self):
        """Dead stock sample must be captured."""
        targets = evaluate_heuristic_sensor(self.catalog)
        target_skus = [t["sku"] for t in targets]
        self.assertIn("SKU-DEAD-FORCED-06", target_skus)

    def test_empty_catalog_returns_empty_list(self):
        """If no SKUs qualify, returns empty list so n8n router can terminate execution."""
        clean_catalog = [
            {"sku": "SKU-CLEAN-1", "yesterday_sales": 1, "yesterday_returns": 0, "sales_30d": 50},
            {"sku": "SKU-CLEAN-2", "yesterday_sales": 2, "yesterday_returns": 0, "sales_30d": 30}
        ]
        targets = evaluate_heuristic_sensor(clean_catalog)
        self.assertEqual(len(targets), 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)


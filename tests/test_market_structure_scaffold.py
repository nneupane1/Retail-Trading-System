import copy
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from market_structure import (
    DEFAULT_SCAFFOLD_CONFIG,
    build_display_only_context,
    build_scaffold_inventory_payload,
    detect_equal_highs_lows,
    detect_liquidity_placeholders,
    detect_pivot_levels,
    load_scaffold_config,
    write_scaffold_inventory,
)
import market_structure.liquidity_zones as liquidity_zones
import market_structure.market_structure_context as market_structure_context
import market_structure.scaffold_inventory as scaffold_inventory
import market_structure.support_resistance as support_resistance


class MarketStructureScaffoldTests(unittest.TestCase):
    def test_default_scaffold_flags_are_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "market_structure_scaffold.json").write_text(
                json.dumps(DEFAULT_SCAFFOLD_CONFIG, indent=2),
                encoding="utf-8",
            )

            payload = load_scaffold_config(root)

            self.assertFalse(payload["market_structure_refactor"]["enabled"])
            self.assertFalse(payload["market_structure_refactor"]["support_resistance"]["enabled"])
            self.assertTrue(payload["market_structure_refactor"]["support_resistance"]["display_only"])
            self.assertFalse(payload["market_structure_refactor"]["behavior_change_allowed"])
            self.assertFalse(payload["market_structure_refactor"]["strategy_authority_allowed"])

    def test_scaffold_inventory_is_parseable_and_dormant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "market_structure_scaffold.json").write_text(
                json.dumps(DEFAULT_SCAFFOLD_CONFIG, indent=2),
                encoding="utf-8",
            )

            path = write_scaffold_inventory(root)
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertTrue(path.exists())
            self.assertEqual("market_structure_support_resistance_liquidity", payload["scaffold"])
            self.assertFalse(payload["enabled"])
            self.assertFalse(payload["behavior_change_allowed"])
            self.assertFalse(payload["real_money_allowed"])
            self.assertTrue(payload["display_only"])
            self.assertTrue(payload["future_research_only"])
            self.assertFalse(payload["entry_behavior_changed"])
            self.assertFalse(payload["allocator_behavior_changed"])

    def test_support_resistance_helper_is_pure_and_respects_cutoff(self):
        candles = [
            {"timestamp": "2026-01-01T00:00:00Z", "open": 99, "high": 100, "low": 94, "close": 95},
            {"timestamp": "2026-01-01T00:01:00Z", "open": 95, "high": 101, "low": 93, "close": 100},
            {"timestamp": "2026-01-01T00:02:00Z", "open": 100, "high": 106, "low": 95, "close": 104},
            {"timestamp": "2026-01-01T00:03:00Z", "open": 104, "high": 102, "low": 92, "close": 94},
            {"timestamp": "2026-01-01T00:04:00Z", "open": 94, "high": 101, "low": 91, "close": 96},
            {"timestamp": "2026-01-01T00:05:00Z", "open": 96, "high": 109, "low": 97, "close": 108},
            {"timestamp": "2026-01-01T00:06:00Z", "open": 108, "high": 103, "low": 96, "close": 98},
        ]
        before = copy.deepcopy(candles)

        levels = detect_pivot_levels(
            candles,
            left_bars=1,
            right_bars=1,
            cutoff_timestamp="2026-01-01T00:04:00Z",
            timeframe_source="15m",
        )

        self.assertEqual(before, candles)
        self.assertTrue(levels)
        self.assertTrue(all(level.display_only for level in levels))
        self.assertTrue(all(level.timeframe_source == "15m" for level in levels))
        self.assertTrue(all(level.anchor_timestamp <= "2026-01-01T00:04:00+00:00" for level in levels))
        prices = [level.price for level in levels]
        self.assertIn(106.0, prices)
        self.assertNotIn(109.0, prices)

    def test_liquidity_helpers_are_pure_and_respect_cutoff(self):
        candles = [
            {"timestamp": "2026-01-01T00:00:00Z", "open": 99, "high": 100, "low": 94, "close": 95},
            {"timestamp": "2026-01-01T00:01:00Z", "open": 95, "high": 106, "low": 93, "close": 100},
            {"timestamp": "2026-01-01T00:02:00Z", "open": 100, "high": 101, "low": 95, "close": 99},
            {"timestamp": "2026-01-01T00:03:00Z", "open": 99, "high": 106.05, "low": 94, "close": 100},
            {"timestamp": "2026-01-01T00:04:00Z", "open": 100, "high": 102, "low": 95, "close": 98},
            {"timestamp": "2026-01-01T00:05:00Z", "open": 98, "high": 112, "low": 96, "close": 111},
            {"timestamp": "2026-01-01T00:06:00Z", "open": 111, "high": 103, "low": 95, "close": 97},
        ]
        before = copy.deepcopy(candles)

        zones = detect_equal_highs_lows(
            candles,
            cutoff_timestamp="2026-01-01T00:04:00Z",
            timeframe_source="1h",
            tolerance_pct=0.001,
        )
        placeholders = detect_liquidity_placeholders(
            candles,
            cutoff_timestamp="2026-01-01T00:04:00Z",
            timeframe_source="1h",
        )

        self.assertEqual(before, candles)
        self.assertEqual([], placeholders)
        self.assertEqual(1, len(zones))
        self.assertEqual("equal_highs", zones[0].kind)
        self.assertTrue(zones[0].display_only)
        self.assertLess(zones[0].price, 110.0)

    def test_context_is_display_only(self):
        context = build_display_only_context(
            nearest_support=98.0,
            nearest_resistance=105.0,
            current_price=100.0,
            source_timeframe="12h",
        )

        self.assertTrue(context.display_only)
        self.assertTrue(context.inside_range)
        self.assertEqual("12h", context.source_timeframe)

    def test_scaffold_modules_do_not_import_strategy_or_allocator_code(self):
        forbidden_terms = [
            "from entry",
            "import entry",
            "from exit",
            "import exit",
            "from position",
            "import position",
            "from simulation",
            "import simulation",
            "from live_sim",
            "import live_sim",
        ]
        for module in (support_resistance, liquidity_zones, market_structure_context, scaffold_inventory):
            source = inspect.getsource(module)
            for term in forbidden_terms:
                self.assertNotIn(term, source)

    def test_inventory_payload_marks_non_authoritative_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "market_structure_scaffold.json").write_text(
                json.dumps(DEFAULT_SCAFFOLD_CONFIG, indent=2),
                encoding="utf-8",
            )

            payload = build_scaffold_inventory_payload(root)

            self.assertFalse(payload["enabled"])
            self.assertFalse(payload["behavior_change_allowed"])
            self.assertTrue(payload["display_only"])
            self.assertFalse(payload["real_money_allowed"])
            self.assertEqual(
                "market_structure_scaffold_only_no_trading_behavior_change",
                payload["warning"],
            )


if __name__ == "__main__":
    unittest.main()

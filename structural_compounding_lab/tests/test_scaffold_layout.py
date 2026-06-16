import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StructuralCompoundingLabScaffoldTests(unittest.TestCase):
    def test_core_scaffold_files_exist(self):
        expected = [
            ROOT / "README.md",
            ROOT / "pyproject.toml",
            ROOT / "project_manifest.json",
            ROOT / "config" / "structural_compounding_settings.json",
            ROOT / "config" / "structural_compounding_settings.yaml",
            ROOT / "config" / "structural_compounding_smoke.yaml",
            ROOT / "config" / "symbols.json",
            ROOT / "frontend" / "README.md",
            ROOT / "frontend" / "routes.json",
            ROOT / "frontend" / "panel_layout.yaml",
            ROOT / "docs" / "architecture.md",
            ROOT / "output" / "README.md",
        ]
        for path in expected:
            self.assertTrue(path.exists(), f"missing scaffold file: {path}")

    def test_settings_json_is_parseable(self):
        payload = json.loads((ROOT / "config" / "structural_compounding_settings.json").read_text(encoding="utf-8"))
        self.assertTrue(payload["research_only"])
        self.assertEqual(payload["execution_timeframe"], "1h")
        self.assertEqual(payload["base_capital"], 20000.0)
        self.assertIn("risk", payload)
        self.assertIn("ema", payload)

    def test_symbols_json_includes_btcusdt(self):
        payload = json.loads((ROOT / "config" / "symbols.json").read_text(encoding="utf-8"))
        self.assertIn("BTCUSDT", payload["symbols"])


if __name__ == "__main__":
    unittest.main()

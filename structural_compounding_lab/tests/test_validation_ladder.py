import json
import unittest
from pathlib import Path


class StructuralValidationLadderTests(unittest.TestCase):
    def test_btc_first_before_multi_symbol_expansion(self):
        path = Path(__file__).resolve().parents[1] / "config" / "validation_ladder.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        stages = payload["stages"]
        self.assertEqual(stages[1]["symbol_scope"], ["BTCUSDT"])
        self.assertEqual(stages[-1]["symbol_scope"], ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "BNBUSDT"])
        self.assertTrue(payload["promotion_policy"]["multi_symbol_requires_btc_success"])
        stage_map = {stage["stage"]: stage for stage in stages}
        self.assertFalse(stage_map["full_history_confirmation"]["auto_run"])
        self.assertFalse(stage_map["monte_carlo"]["auto_run"])
        self.assertFalse(stage_map["paper_candidate_later"]["auto_run"])


if __name__ == "__main__":
    unittest.main()

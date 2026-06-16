import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from structural_compounding_lab.config import StructuralLabConfig
from structural_compounding_lab.data import StructuralDataAdapter


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "btcusdt_structural_fixture_1m.csv"


class StructuralDataAdapterTests(unittest.TestCase):
    def test_adapter_enforces_analysis_window_after_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "windowed_settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "data": {
                            "analysis_start_date": "2026-01-01T01:00:00+00:00",
                            "analysis_end_date": "2026-01-01T02:00:00+00:00",
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = StructuralLabConfig.load(config_path)
            adapter = StructuralDataAdapter(config)
            frame = adapter.load_base_1m("BTCUSDT", source_csv=FIXTURE)

            self.assertFalse(frame.empty)
            self.assertGreaterEqual(pd.Timestamp(frame.index.min()), pd.Timestamp("2026-01-01T01:00:00+00:00"))
            self.assertLessEqual(pd.Timestamp(frame.index.max()), pd.Timestamp("2026-01-01T02:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()

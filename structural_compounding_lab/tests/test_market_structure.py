import unittest

import pandas as pd

from structural_compounding_lab.market_structure import detect_liquidity_events, detect_structural_levels


def _sample_frame() -> pd.DataFrame:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=16, freq="1h")
    rows = [
        (100.0, 101.5, 99.4, 101.0, 120),
        (101.0, 102.3, 100.6, 102.0, 118),
        (102.0, 103.1, 101.3, 102.4, 121),
        (102.4, 102.8, 100.8, 101.1, 126),
        (101.1, 101.7, 99.9, 100.5, 128),
        (100.5, 101.0, 99.1, 99.6, 131),
        (99.6, 100.4, 98.7, 99.2, 133),
        (99.2, 100.9, 98.8, 100.6, 145),
        (100.6, 101.2, 99.4, 100.1, 140),
        (100.1, 102.4, 99.9, 101.9, 150),
        (101.9, 102.5, 100.8, 101.2, 144),
        (101.2, 101.4, 99.3, 99.7, 152),
        (99.7, 100.2, 98.9, 99.1, 158),
        (99.1, 101.8, 98.8, 101.4, 163),
        (101.4, 102.6, 100.9, 102.1, 166),
        (102.1, 102.9, 101.2, 101.5, 170),
    ]
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=index)
    return frame


class StructuralMarketStructureTests(unittest.TestCase):
    def test_levels_respect_cutoff_and_no_future_data(self):
        frame = _sample_frame()
        cutoff = frame.index[9]
        levels = detect_structural_levels(frame, cutoff_timestamp=cutoff, timeframe_source="1h")

        self.assertTrue(levels)
        self.assertTrue(all(level.no_future_data for level in levels))
        self.assertTrue(all(pd.Timestamp(level.last_touched) <= cutoff for level in levels))

    def test_liquidity_events_respect_cutoff(self):
        frame = _sample_frame()
        cutoff = frame.index[12]
        events = detect_liquidity_events(frame, cutoff_timestamp=cutoff, timeframe_source="1h", sweep_lookback_bars=4)

        self.assertTrue(events)
        self.assertTrue(all(event.no_future_data for event in events))
        self.assertTrue(all(pd.Timestamp(event.timestamp) <= cutoff for event in events))


if __name__ == "__main__":
    unittest.main()

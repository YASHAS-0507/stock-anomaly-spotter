"""
test_merge.py
-------------
Pure unit tests for the merge_bars function in daily_extract.py.
No network calls, no Angel login.

Run with:
    pytest test_merge.py -v
or:
    python -m unittest test_merge.py
"""

import sys
import unittest

# Import the pure merge function only — no side-effects at import time
from daily_extract import merge_bars, SESSION_SLOTS, DISAGREE_THRESHOLD


def _bar(o=100.0, h=101.0, l=99.0, c=100.5, v=1000) -> dict:
    return {"o": o, "h": h, "l": l, "c": c, "v": v}


SLOT = "09:15"
SLOT2 = "09:20"


class TestMergeBars(unittest.TestCase):

    def _run(self, angel: dict, yfin: dict, slots=None):
        return merge_bars(angel, yfin, slots=slots or [SLOT])

    # ------------------------------------------------------------------
    # Angel-only slot: use Angel bar, src="angel"
    # ------------------------------------------------------------------
    def test_angel_only(self):
        candles, missing, zvol, disagree = self._run({SLOT: _bar()}, {})
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0]["src"], "angel")
        self.assertNotIn(SLOT, missing)
        self.assertEqual(disagree, [])

    # ------------------------------------------------------------------
    # yfinance-only slot: use yfinance bar, src="yfinance"
    # ------------------------------------------------------------------
    def test_yfinance_only(self):
        candles, missing, zvol, disagree = self._run({}, {SLOT: _bar()})
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0]["src"], "yfinance")
        self.assertNotIn(SLOT, missing)
        self.assertEqual(disagree, [])

    # ------------------------------------------------------------------
    # Both sources agree (within threshold): Angel kept, no disagreement
    # ------------------------------------------------------------------
    def test_both_agree(self):
        b = _bar(o=100.0, h=101.0, l=99.0, c=100.5, v=500)
        # 0.01% difference — well below 0.05%
        b2 = _bar(o=100.01, h=101.0, l=99.0, c=100.5, v=490)
        candles, missing, zvol, disagree = self._run({SLOT: b}, {SLOT: b2})
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0]["src"], "angel")
        self.assertEqual(disagree, [])

    # ------------------------------------------------------------------
    # Both sources disagree (> threshold): Angel bar kept, disagreement logged
    # ------------------------------------------------------------------
    def test_both_disagree_angel_kept(self):
        a = _bar(o=100.0)
        # 1% open difference
        y = _bar(o=101.0)
        candles, missing, zvol, disagree = self._run({SLOT: a}, {SLOT: y})
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0]["src"], "angel")
        self.assertEqual(candles[0]["o"], 100.0)
        self.assertTrue(any(d["field"] == "o" for d in disagree))

    # ------------------------------------------------------------------
    # Slot missing from both: recorded in missing_slots, not in candles
    # ------------------------------------------------------------------
    def test_missing_from_both(self):
        candles, missing, zvol, disagree = self._run({}, {})
        self.assertEqual(candles, [])
        self.assertIn(SLOT, missing)

    # ------------------------------------------------------------------
    # Zero-volume bar: flagged with zero_volume=True, still in candles
    # ------------------------------------------------------------------
    def test_zero_volume_flagged(self):
        b = _bar(v=0)
        candles, missing, zvol, disagree = self._run({SLOT: b}, {})
        self.assertEqual(len(candles), 1)
        self.assertTrue(candles[0].get("zero_volume"))
        self.assertIn(SLOT, zvol)

    # ------------------------------------------------------------------
    # Multi-slot: correct counts across several slots
    # ------------------------------------------------------------------
    def test_multi_slot(self):
        slots = [SLOT, SLOT2, "09:25"]
        angel = {SLOT: _bar(), SLOT2: _bar(v=0)}
        yfin  = {"09:25": _bar()}
        candles, missing, zvol, disagree = merge_bars(angel, yfin, slots=slots)
        self.assertEqual(len(candles), 3)
        srcs = {b["slot"]: b["src"] for b in candles}
        self.assertEqual(srcs[SLOT], "angel")
        self.assertEqual(srcs[SLOT2], "angel")
        self.assertEqual(srcs["09:25"], "yfinance")
        self.assertEqual(missing, [])
        self.assertIn(SLOT2, zvol)

    # ------------------------------------------------------------------
    # Disagreement threshold boundary: exactly at threshold is NOT logged
    # ------------------------------------------------------------------
    def test_disagree_at_threshold_not_logged(self):
        # pct_diff for 100.0 vs 100.05 ≈ 0.04999% < 0.05%
        a = _bar(o=100.0)
        y = _bar(o=100.05)
        _, _, _, disagree = self._run({SLOT: a}, {SLOT: y})
        self.assertEqual(disagree, [])

    def test_disagree_just_over_threshold_logged(self):
        # pct_diff for 100.0 vs 100.06 ≈ 0.0600% > 0.05%
        a = _bar(o=100.0)
        y = _bar(o=100.06)
        _, _, _, disagree = self._run({SLOT: a}, {SLOT: y})
        self.assertTrue(len(disagree) >= 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

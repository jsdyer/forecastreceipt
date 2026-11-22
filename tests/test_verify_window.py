"""Ensure incomplete and stale archives cannot send a successful heartbeat."""
import copy
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect import DATA, GFS, OWM, parse, load
from verify_window import verify


class Monitoring(unittest.TestCase):
    def setUp(self):
        self.slot = parse("2026-11-22T06:00:00Z")
        self.index = load(DATA / "index.json")

    def read(self, path):
        return self.index if path == "index.json" else load(DATA / path)

    def test_existing_receipts_satisfy_repeat_run(self):
        verify(self.slot, [GFS], self.read)

    def test_partial_commit_rejected(self):
        self.index["receipts"] = [r for r in self.index["receipts"] if r["station"] == "langley"]
        with self.assertRaisesRegex(ValueError, "halifax"):
            verify(self.slot, [GFS], self.read)

    def test_other_feeds_must_be_present_if_enabled(self):
        self.index["receipts"] = [r for r in self.index["receipts"] if r["provider"] != OWM]
        with self.assertRaisesRegex(ValueError, "openweather"):
            verify(self.slot, [GFS, OWM], self.read)

    def test_old_capture_rejected_even_with_current_filename(self):
        def stale(path):
            data = copy.deepcopy(self.read(path))
            if path != "index.json":
                data["capture_utc"] = "2026-11-22T01:00:00Z"
            return data
        with self.assertRaisesRegex(ValueError, "Wrong capture window"):
            verify(self.slot, [GFS], stale)

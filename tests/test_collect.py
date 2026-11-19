from pathlib import Path
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect import DATA, STATIONS, LABELS, OWM, forecast, observation_range, parse, load, future_points, SourceError
from score import scores


class Archive(unittest.TestCase):
    def test_archive_identity_future_only_and_exact_forecast_sampling(self):
        idx = load(DATA / "index.json")
        for slug, station in STATIONS.items():
            obs = load(DATA / "observed" / (slug + ".json"))
            self.assertTrue(any(isinstance(x[0], (int,float)) and not x[1] for x in obs.values()))
            self.assertTrue(any(row["station"] == slug for row in idx["receipts"]))
            for provider in LABELS:
                self.assertIsInstance(load(DATA / "scores" / f"{slug}-{provider}.json"), list)
            for row in [r for r in idx["receipts"] if r["station"] == slug]:
                doc = load(DATA / row["path"])
                self.assertEqual(doc["provider"], row["provider"])
                self.assertEqual(doc["station_id"], station["climate_id"])
                captured = parse(doc["capture_utc"])
                self.assertEqual([list(p) for p in future_points([(parse(t),v) for t,v in doc["points"]],captured)],doc["points"])
                self.assertLessEqual(len(doc["points"]),40)
                if doc["model_initialization_utc"]:
                    self.assertLessEqual(parse(doc["model_initialization_utc"]),captured)

    def test_openweather_schema_leaves_issue_unknown_and_stores_only_valid_temps(self):
        now = datetime.now(timezone.utc)
        next_hour = now.replace(hour=(now.hour // 3) * 3, minute=0, second=0, microsecond=0) + timedelta(hours=3)
        raw = {"list": [{"dt": int((next_hour+timedelta(hours=3*i)).timestamp()), "main": {"temp": 0}}
                        for i in range(40)]}
        with patch("collect.get", return_value=raw) as get:
            saved = forecast(OWM, STATIONS["langley"], now, None)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(len(saved["points"]), 40)
        self.assertIsNone(saved["provider_issue_utc"])
        self.assertIsNone(saved["model_initialization_utc"])
        self.assertEqual(saved["content_license"], "https://creativecommons.org/licenses/by-sa/4.0/")
        self.assertNotIn("appid", saved)
        self.assertNotIn("list", saved)

    def test_observation_query_pads_local_dates_then_clips_by_exact_utc(self):
        station = STATIONS["langley"]
        start, end = parse("2026-11-15T00:00:00Z"), parse("2026-11-15T01:00:00Z")
        times = ["2026-11-14T23:00:00", "2026-11-15T00:00:00", "2026-11-15T01:00:00", "2026-11-15T02:00:00"]
        rows = [{"properties":{"CLIMATE_IDENTIFIER":station["climate_id"],"UTC_DATE":t,"TEMP":0}} for t in times]
        with patch("collect.get", return_value={"features":rows,"numberMatched":4}) as request:
            received = observation_range(station, start, end)
        self.assertEqual(list(received), [times[1]+"Z", times[2]+"Z"])
        self.assertEqual(request.call_args.args[1]["datetime"], "2026-11-14T00:00:00Z/2026-11-16T01:00:00Z")

    def test_incomplete_forecast_rejected(self):
        when = parse("2026-11-15T00:00:00Z")
        with self.assertRaises(SourceError):
            future_points([(when,0), (when+timedelta(hours=3), 4)],when)

    def test_revision_precedes_target_and_scores_exclude_flags_and_missing(self):
        valid = "2026-11-19T06:00:00Z"
        other = "2026-11-19T09:00:00Z"
        attached = [({"path":"a"},{"capture_utc":"2026-11-17T05:00:00Z","points":[[valid,2],[other,4]]}),
                    ({"path":"b"},{"capture_utc":"2026-11-18T05:00:00Z","points":[[valid,-1],[other,6]]})]
        obs = {valid:[0,None],other:[2,"E"]}
        cells = scores(attached,obs,"America/Vancouver",parse("2026-11-20T00:00:00Z"))
        self.assertEqual(sum(x["matched"] for x in cells),2)
        self.assertEqual(sum(x["eligible"] for x in cells),4)
        self.assertEqual(sum(x["sum_error"] for x in cells),1)
        self.assertEqual(sum(x["sum_absolute"] for x in cells),3)
        cell = next(x for x in cells if x["day"]==2 and x["period"]=="Evening")
        self.assertEqual(cell["largest_revision"]["change"],-3)
        self.assertEqual(cell["largest_revision"]["before"]["path"],"a")

if __name__ == "__main__":
    unittest.main()

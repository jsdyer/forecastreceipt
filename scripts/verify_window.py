"""Check that the pushed revision contains a complete receipt for every expected feed."""
import argparse
import json
import subprocess
from datetime import timedelta

from collect import GFS, OWM, STATIONS, future_points, parse


def verify(slot, providers, read):
    index = read("index.json")
    by_path = {row["path"]: row for row in index["receipts"]}
    for slug, station in STATIONS.items():
        for provider in providers:
            path = f"receipts/{slot:%Y-%m}/{slot:%Y%m%dT%H}-{slug}-{provider}.json"
            row = by_path.get(path)
            if not row or row["station"] != slug or row["provider"] != provider:
                raise ValueError(f"Missing or mismatched {path} in the committed index")
            doc = read(path)
            captured = parse(doc["capture_utc"])
            if not (slot <= captured < slot + timedelta(hours=6)):
                raise ValueError(f"Wrong capture window for {path}")
            if (doc["station_id"] != station["climate_id"] or doc["provider"] != provider
                    or row["capture"] != doc["capture_utc"] or row["count"] != len(doc["points"])):
                raise ValueError(f"Archive metadata mismatch for {path}")
            valid = future_points([(parse(t), v) for t, v in doc["points"]], captured)
            if [list(point) for point in valid] != doc["points"]:
                raise ValueError(f"Invalid forecast values in {path}")
            print(f"Verified {slug} / {provider}: {len(valid)} forecast points")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slot")
    parser.add_argument("revision")
    parser.add_argument("--openweather", action="store_true")
    args = parser.parse_args()
    def read_committed(path):
        return json.loads(subprocess.check_output(["git", "show", f"{args.revision}:web/data/{path}"]))
    verify(parse(args.slot), [GFS, OWM] if args.openweather else [GFS], read_committed)

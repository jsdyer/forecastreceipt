"""Build small station/provider score tables from immutable receipts and station observations."""
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass
class Bin:
    month: str
    day: int
    period: str
    eligible: int = 0
    matched: int = 0
    sum_error: float = 0
    sum_absolute: float = 0
    largest_revision: dict | None = None


def scores(receipts, observations, zone, asof):
    bins, previous = {}, {}
    tz = ZoneInfo(zone)
    for entry, receipt in sorted(receipts, key=lambda pair: pair[1]["capture_utc"]):
        capture = datetime.fromisoformat(receipt["capture_utc"].replace("Z", "+00:00"))
        for valid, forecast in receipt["points"]:
            when = datetime.fromisoformat(valid.replace("Z", "+00:00"))
            if when <= capture:
                continue
            local = when.astimezone(tz)
            day = ((when - capture).total_seconds() - 1) // 86400 + 1
            period = ("Overnight", "Morning", "Afternoon", "Evening")[local.hour // 6]
            key = (local.strftime("%Y-%m"), int(day), period)
            cell = bins.setdefault(key, Bin(*key))
            if when <= asof:
                cell.eligible += 1
                obs = observations.get(valid)
                if obs is not None and obs[0] is not None and not obs[1]:
                    error = forecast - obs[0]
                    cell.matched += 1
                    cell.sum_error += error
                    cell.sum_absolute += abs(error)
            older = previous.get(valid)
            if older and (cell.largest_revision is None or abs(forecast - older["forecast"]) > abs(cell.largest_revision["change"])):
                cell.largest_revision = dict(valid=valid, change=round(forecast - older["forecast"], 2),
                    before=older, after=dict(capture=receipt["capture_utc"], forecast=forecast, path=entry["path"]))
            previous[valid] = dict(capture=receipt["capture_utc"], forecast=forecast, path=entry["path"])
    rows = []
    for _, cell in sorted(bins.items()):
        row = asdict(cell)
        row["sum_error"] = round(row["sum_error"], 5)
        row["sum_absolute"] = round(row["sum_absolute"], 5)
        rows.append(row)
    return rows

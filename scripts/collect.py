"""Capture forecasts while their valid times are still in the future, then reconcile ECCC hours."""
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from score import scores

DATA = Path(__file__).resolve().parents[1] / "web/data"
UTC = timezone.utc
STATIONS = {
    "langley": dict(name="Langley Regional", climate_id="1104570", lat=49.100833, lon=-122.630833, zone="America/Vancouver"),
    "halifax": dict(name="Halifax Stanfield", climate_id="8202251", lat=44.881111, lon=-63.508611, zone="America/Halifax"),
}
GFS = "noaa-gfs"
OWM = "openweather"
LABELS = {GFS: "NOAA GFS via Open-Meteo", OWM: "OpenWeather"}
LICENSES = {GFS: "https://creativecommons.org/licenses/by/4.0/", OWM: "https://opendatacommons.org/licenses/odbl/1-0/"}


def stamp(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse(value):
    # The GeoMet UTC_DATE field and Open-Meteo GMT hourly fields can omit a suffix.
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def save(path, value, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w") as output:
        json.dump(value, output, indent=1, ensure_ascii=False, allow_nan=False)
        output.write("\n")


class SourceError(Exception):
    """Include only a public source name and status, never a credential-bearing URL."""


def get(endpoint, parameters):
    url = endpoint + "?" + urlencode(parameters)
    request = Request(url, headers={"User-Agent": "CoolCode-ForecastReceipt/1.0"})
    for attempt in range(2):
        try:
            with urlopen(request, timeout=24) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code < 500 or attempt:
                raise SourceError(f"HTTP {exc.code}") from None
        except (URLError, OSError, ValueError):
            if attempt:
                raise SourceError("unavailable or invalid response") from None
        time.sleep(1)


def temperature(value):
    return type(value) in (int, float) and math.isfinite(value) and -100 <= value <= 65


def future_points(points, captured):
    found = {}
    for valid, value in points:
        if temperature(value) and captured < valid <= captured + timedelta(days=5) and valid.hour % 3 == 0 and valid.minute == valid.second == 0:
            key = stamp(valid)
            if key in found:
                raise SourceError("duplicate valid hour")
            found[key] = round(value, 2)
    if len(found) < 38:
        raise SourceError("incomplete five-day forecast")
    return sorted(found.items())


def forecast(provider, station, now, key):
    point = dict(latitude=station["lat"], longitude=station["lon"])
    run = None
    if provider == OWM:
        raw = get("https://api.openweathermap.org/data/2.5/forecast", {
            "lat": point["latitude"], "lon": point["longitude"], "units": "metric", "appid": key,
        })
        points = [(datetime.fromtimestamp(x["dt"], UTC), x["main"]["temp"]) for x in raw["list"]]
    else:
        base = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
        # Request a fixed model initialisation. Current run can be absent or partially available.
        for lag in (0, 6, 12, 18):
            run = base - timedelta(hours=lag)
            try:
                raw = get("https://single-runs-api.open-meteo.com/v1/forecast", {
                    **point, "models": "gfs_global", "run": run.strftime("%Y-%m-%dT%H:%M"),
                    "hourly": "temperature_2m", "forecast_days": 7, "timezone": "GMT",
                })
                if raw.get("utc_offset_seconds") != 0 or raw["hourly_units"]["temperature_2m"] != "°C":
                    raise SourceError("unexpected time or temperature units")
                hourly = raw["hourly"]
                points = [(parse(t), v) for t, v in zip(hourly["time"], hourly["temperature_2m"], strict=True)]
                future_points(points, datetime.now(UTC))
                break
            except SourceError:
                if lag == 18:
                    raise
    captured = datetime.now(UTC)
    return {"provider": provider, "station_id": station["climate_id"], "coordinates": point,
            "capture_utc": stamp(captured), "model_initialization_utc": stamp(run) if run else None,
            "provider_issue_utc": None, "units": "°C", "attribution": LABELS[provider], "data_license": LICENSES[provider],
            "content_license": "https://creativecommons.org/licenses/by-sa/4.0/" if provider == OWM else LICENSES[GFS],
            "columns": ["valid_utc", "forecast_c"], "points": future_points(points, captured)}


def observation_range(station, start, end):
    # GeoMet's temporal query indexes local station dates. Pad each UTC chunk
    # and select the precise UTC interval from returned UTC_DATE observations.
    buffer = timedelta(days=1)
    raw = get("https://api.weather.gc.ca/collections/climate-hourly/items", {
        "f": "json", "CLIMATE_IDENTIFIER": station["climate_id"], "limit": 1000,
        "datetime": f"{stamp(start-buffer)}/{stamp(end+buffer)}",
    })
    if raw.get("numberMatched", 0) > len(raw["features"]):
        raise SourceError("truncated station query")
    result = {}
    for item in raw["features"]:
        row = item["properties"]
        if row["CLIMATE_IDENTIFIER"] != station["climate_id"]:
            raise SourceError("mismatched station")
        valid = parse(row["UTC_DATE"])
        if start <= valid <= end and (temperature(row["TEMP"]) or row["TEMP"] is None):
            result[stamp(valid)] = [row["TEMP"], row.get("TEMP_FLAG")]
    return result


def update_observations(data, slug, station, now, first_capture):
    # Refresh the latest fortnight for revisions and advance through any missed period in bounded chunks.
    path = data / "observed" / (slug + ".json")
    obs = load(path, {})
    recent = now - timedelta(days=14)
    resume = parse(max(obs)) if obs else first_capture - timedelta(days=2)
    start = min(recent, resume).replace(minute=0, second=0, microsecond=0)
    while start <= now:
        end = min(now, start + timedelta(days=28) - timedelta(seconds=1))
        obs.update(observation_range(station, start, end))
        start = end + timedelta(seconds=1)
    if not obs:
        raise SourceError("station returned no observed hours")
    save(path, dict(sorted(obs.items())))
    return obs


def manifest(data, statuses, checked):
    receipts = []
    for path in sorted((data / "receipts").rglob("*.json")):
        doc = load(path)
        slug = next(s for s, st in STATIONS.items() if st["climate_id"] == doc["station_id"])
        receipts.append(dict(station=slug, provider=doc["provider"], capture=doc["capture_utc"],
                             count=len(doc["points"]), path=str(path.relative_to(data))))
    catalog = dict(checked=stamp(checked), stations=STATIONS, providers=LABELS, status=statuses, receipts=receipts)
    catalog["first_capture"] = min((r["capture"] for r in receipts), default=None)
    catalog["last_capture"] = max((r["capture"] for r in receipts), default=None)
    catalog["forecast_points"] = sum(r["count"] for r in receipts)
    for slug, station in STATIONS.items():
        obs = load(data / "observed" / (slug + ".json"), {})
        for provider in LABELS:
            selected = [(r, load(data / r["path"])) for r in receipts if r["station"] == slug and r["provider"] == provider]
            cells = scores(selected, obs, station["zone"], checked)
            save(data / "scores" / f"{slug}-{provider}.json", cells)
    save(data / "index.json", catalog)
    return catalog


def main():
    now = datetime.now(UTC)
    slot = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
    if output_path := os.environ.get("GITHUB_OUTPUT"):
        with open(output_path, "a") as output:
            print(f"slot={stamp(slot)}", file=output)
            print(f"openweather={str(bool(os.environ.get('COOLCODE_OPENWEATHER_API_KEY'))).lower()}", file=output)
    statuses, fresh = {}, 0
    key = os.environ.get("COOLCODE_OPENWEATHER_API_KEY")
    for slug, station in STATIONS.items():
        statuses[slug] = {}
        for provider in (GFS, OWM):
            path = DATA / "receipts" / slot.strftime("%Y-%m") / f"{slot:%Y%m%dT%H}-{slug}-{provider}.json"
            if provider == OWM and not key:
                statuses[slug][provider] = "Awaiting a configured OpenWeather feed."
                continue
            try:
                if not path.exists():
                    save(path, forecast(provider, station, now, key), exclusive=True)
                statuses[slug][provider] = "Captured for this six-hour window."
                fresh += 1
            except (SourceError, KeyError, IndexError, TypeError, ValueError, OverflowError):
                statuses[slug][provider] = "Latest fetch unavailable. Previous receipts are retained."
        saved = sorted((DATA / "receipts").glob(f"*/*-{slug}-*.json"))
        first = parse(load(saved[0])["capture_utc"]) if saved else now
        try:
            update_observations(DATA, slug, station, now, first)
            statuses[slug]["observed"] = "Retrieved"
        except (SourceError, ValueError, KeyError):
            statuses[slug]["observed"] = "ECCC refresh unavailable. Showing the last saved readings."
    if not fresh:
        raise SystemExit("No forecast capture available for this window; preserving last deployment.")
    index = manifest(DATA, statuses, datetime.now(UTC))
    print(index["checked"], len(index["receipts"]), "archived station/provider receipts", statuses)


if __name__ == "__main__":
    main()

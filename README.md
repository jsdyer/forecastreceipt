# Forecast Receipt

[Open Forecast Receipt](https://coolcode.ca/forecastreceipt/) to audit temperature forecasts at Langley Regional, BC (ECCC climate ID 1104570) and Halifax Stanfield, NS (8202251). Select a station and provider, filter scores by lead, valid month and local time of day, then inspect the original timestamped receipt. [Weather Archive](https://coolcode.ca/weatherarchive/) explores daily records and station normals.

<!-- coolcode:guide -->
Choose a receipt and a station-local hour. The hour history links every available prediction for that hour, its lead time and its error when ECCC has an unflagged reading. The first Langley GFS receipt predicted 3.8 °C for 06:00 UTC on November 19, 2026.
<!-- /coolcode:guide -->

## Reading a receipt

Each UTC six-hour window can add one immutable five-day receipt per station and provider. A new receipt saves up to 40 future temperatures at three-hour intervals. The slot name identifies the scheduled window, while the JSON records actual wall-clock capture time. It also records the exact GFS model initialization if supplied. The OpenWeather endpoint reports UTC valid times but omits a provider issue timestamp. All lead times therefore use capture to valid time, across both providers.

The pilot began on 19 November 2026. Earlier measured readings give station context. A receipt can earn its first score only after a valid hour passes and ECCC publishes that hour. Occasional outages and source delays can leave gaps. The archive never fills a missed capture with a later download. When assessing two providers, select each separately and compare their dates and counts.

- Signed bias is mean forecast minus observation. Positive bias indicates warm forecasts.
- Mean absolute error is the mean of the absolute differences, in degrees Celsius. Each eligible saved forecast counts separately, even when several receipts cover the same valid hour.
- A matched pair needs an exact UTC timestamp, a numerical ECCC temperature and an empty temperature flag. Flagged station values are displayed but excluded from scoring. Missing hours remain blank.
- Day 1 covers positive lead through 24 hours and each following bin covers the next 24 hours. Valid month and overnight (00–06), morning (06–12), afternoon (12–18) and evening (18–24) use the station’s local civil time.
- A revision compares two adjacent available receipts for the same station, forecast provider and valid UTC time. Filters apply to the newer receipt. The largest absolute change links to both original records; a tie uses one of the tied records.

## Data and reuse

| Source | Role and terms |
| --- | --- |
| [OpenWeather 5 day / 3 hour forecast](https://openweathermap.org/api/forecast5) | Weather data © OpenWeather. OpenWeather-derived content uses [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), under [section G of the provider terms](https://openweathermap.org/payload/api/files/file/OpenWeather_T%26C_of_sale.pdf). The OpenWeather forecast and derived verification database (when present) is offered under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Download the individual receipts, scores and station inputs from `web/data/` or clone this repository for the database. [Provider licensing](https://openweathermap.org/full-price#licenses). |
| [NOAA GFS via Open-Meteo Single Runs](https://open-meteo.com/en/docs/single-runs-api) | Independent model series offered under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Fixed model run, station-point extraction, rounded temperature and three-hour subsampling. This noncommercial pilot uses the [free API](https://open-meteo.com/en/terms). |
| [Environment and Climate Change Canada hourly station observations](https://api.weather.gc.ca/collections/climate-hourly) | Fields UTC_DATE, TEMP and TEMP_FLAG, with ECCC climate identifier verification. Contains information licensed under the [ECCC Data Services End-use Licence](https://eccc-msc.github.io/open-data/licence/readme_en/). Station measurements and a gridded forecast can represent different local conditions. |

## Update and operation

The main Pages workflow builds from saved files on push. On schedule (00:17, 06:17, 12:17, 18:17 UTC) or a manual main-branch dispatch, it also collects forecasts and observations, validates the site, commits data and deploys in the same run. A failed build leaves the previous deployment in place. Successful captures survive later source outages. Recent measurements are checked for revisions over a fourteen-day window, with a catch-up cursor after longer gaps. Source timestamps, source-specific availability and latest measured hour are visible in the app.

OpenWeather collection is opt-in. To enable it, add a fresh key as the GitHub Actions repository secret `COOLCODE_OPENWEATHER_API_KEY`. The next scheduled capture picks it up. No key is needed for the NOAA/ECCC series. The collector reads credentials server-side, never logs a query URL and publishes no credentials. Visitors request static files from the site. They provide no location and make no weather API requests.

Run with Python 3.12+ and Node 24+. From the repository root:

```sh
python3 scripts/collect.py
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -v
python3 scripts/build.py
python3 -m http.server 8000 --directory dist
```

The build and application tests also work offline with the committed archive. For the optional browser check, install `tests/browser-requirements.txt`, install Playwright Chromium, then run `python3 tests/browser_smoke.py`.

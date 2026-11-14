# weather-pipeline

[![CI](https://github.com/initysl/weather-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/initysl/weather-pipeline/actions/workflows/ci.yml)

A daily batch pipeline that keeps a clean, de-duplicated table of weather for the Nigerian cities an agritech startup serves, so analysts can answer questions like *"how many rainy days did Kano get this month?"* or *"is Osogbo hotter than usual this week?"*

## The scenario

The company sends planting and irrigation advice to farmers. That advice depends on recent weather, so the analysts need one table they can trust:

- **fresh**: updated every morning with yesterday's weather
- **correct**: values are validated before they land
- **free of duplicates**: re-running a job, or running two that overlap, never creates a second row for the same city and day

## Architecture

```mermaid
flowchart LR
    A[Open-Meteo<br/>archive API] -->|backfill| E
    B[Open-Meteo<br/>forecast API<br/>past_days=7] -->|daily| E
    E[extract.py<br/>retries, raw JSON copy] --> T[transform.py<br/>pandas + validation]
    T --> L[load.py<br/>upsert, one transaction per city]
    L --> P[(PostgreSQL<br/>dim_city<br/>fact_daily_weather)]
    P --> V[summary views<br/>monthly, rolling 7-day,<br/>hotter than usual]
    C[cron 07:00] -.->|python -m src.pipeline --mode daily| E
```

| Step | File | What it does |
|---|---|---|
| Extract | [src/extract.py](src/extract.py) | Calls Open-Meteo per city, retries failures with backoff, saves the raw JSON to `data/raw/` |
| Transform | [src/transform.py](src/transform.py) | Turns the API's parallel arrays into a DataFrame, renames columns, validates |
| Load | [src/load.py](src/load.py) | Upserts rows into `fact_daily_weather` |
| Orchestrate | [src/pipeline.py](src/pipeline.py) | Command-line entry point, runs every active city independently, exits non-zero on failure |
| Cities | [src/cities.py](src/cities.py) | Finds Nigerian towns with Open-Meteo's geocoder and manages `dim_city` |
| Config | [src/config.py](src/config.py) | Endpoints, validation bounds, DB connection from `.env` |

## Schema

```mermaid
erDiagram
    dim_city ||--o{ fact_daily_weather : has
    dim_city {
        serial city_id PK
        text name UK
        text state UK
        numeric latitude
        numeric longitude
        boolean active
    }
    fact_daily_weather {
        int city_id PK,FK
        date weather_date PK
        numeric temp_max_c
        numeric temp_min_c
        numeric precipitation_mm
        numeric wind_speed_max_kmh
        timestamptz loaded_at
    }
```

Definitions: [sql/schema.sql](sql/schema.sql). `(name, state)` is unique because town names repeat across states (there are at least eight places called Ibadan). The primary key `(city_id, weather_date)` is what makes the whole pipeline safe to re-run.

**Analyst views** ([sql/summaries.sql](sql/summaries.sql)):

| View | Answers |
|---|---|
| `v_monthly_city_summary` | Average max/min temperature, total rain, rainy days (> 1 mm) per city per month |
| `v_temp_7day_rolling` | 7-day rolling average of max temperature per city |
| `v_hotter_than_usual` | Each day's max temperature vs that city's average for the same month in previous years (`anomaly_c`, `hotter_than_usual` = more than 2 °C above) |

```sql
-- How many rainy days did Kano get this month?
SELECT rainy_days FROM v_monthly_city_summary
WHERE city = 'Kano' AND month = date_trunc('month', CURRENT_DATE);

-- Is Osogbo hotter than usual this week?
SELECT ROUND(AVG(anomaly_c), 1) AS avg_anomaly_c FROM v_hotter_than_usual
WHERE city = 'Osogbo' AND weather_date >= CURRENT_DATE - 7;
```

## Running it

### Setup

```bash
cp .env.example .env                      # set a real POSTGRES_PASSWORD
python -m venv .venv && .venv/bin/pip install -r requirements.txt
source .venv/bin/activate
docker compose up -d                      # Postgres 16; on first start runs schema.sql, seed_cities.sql (5 cities), summaries.sql
```

The SQL files only run automatically when the database volume is empty. To apply changes to an existing database:

```bash
docker exec -i weather-db psql -U weather -d weather < sql/migrations/001_city_state_active.sql  # only for databases created before cities moved out of config
docker exec -i weather-db psql -U weather -d weather < sql/summaries.sql
```

### Choosing cities

Any town or city in Nigeria can be tracked. The pipeline loads every *active* row in `dim_city`:

```bash
python -m src.cities search Ilorin                          # look it up, add nothing
python -m src.cities add Ilorin --backfill-from 2024-01-01  # track it and load its history
python -m src.cities add Ibadan --state Ogun --pick 2       # choose among same-named places
python -m src.cities list                                   # what's tracked (--all includes inactive)
python -m src.cities deactivate "Ilorin"                    # stop fetching, keep history
python -m src.cities activate "Ilorin, Kwara"
```

`add` looks the name up with Open-Meteo's geocoding API, keeps only Nigerian towns and cities, and prints exactly what it matched. When a name is shared, it picks the one that is a capital or local government seat (so `Ibadan` means the Oyo State capital, not one of the villages). If that still leaves several, it lists them and asks for `--state` or `--pick`.

### Backfill and daily modes

Run from the project root with `-m` (modules import each other as `src.…`):

```bash
# History, from the archive API
python -m src.pipeline --mode backfill --start 2024-01-01 --end 2026-11-08

# Daily: re-fetches the last 7 complete days from the forecast API
python -m src.pipeline --mode daily

# Any mode can be limited to some cities ("Name" or "Name, State"); --no-raw skips the JSON copy
python -m src.pipeline --mode daily --cities Kano "Ibadan, Oyo" --no-raw
```

The exit code is 1 if any city failed, so a scheduler can flag the run.

### Scheduling (cron)

Run daily mode at 07:00 (the cron times use the machine's time zone, here Africa/Lagos):

```cron
0 7 * * * cd /path/to/weather-pipeline && mkdir -p logs && .venv/bin/python -m src.pipeline --mode daily --no-raw >> logs/run.log 2>&1
```

Add it with `crontab -e`. Postgres restarts with Docker (`restart: unless-stopped`), so the job works after a reboot. Because daily mode re-fetches 7 days, a missed run (machine off, API down) is repaired by the next successful one.

### Deployment (GitHub Actions + hosted Postgres)

The production pipeline runs on GitHub's servers and writes to a hosted Postgres (e.g. Neon or Supabase), so it doesn't depend on a laptop being on.

| Workflow | When | What |
|---|---|---|
| [ci.yml](.github/workflows/ci.yml) | every push | tests against a throwaway Postgres |
| [daily.yml](.github/workflows/daily.yml) | 07:00 Lagos daily, or by hand | `--mode daily`; run by hand with `mode: backfill` to load history. Raw JSON is kept as a run artifact for 30 days |
| [setup-db.yml](.github/workflows/setup-db.yml) | by hand | applies `schema.sql`, `seed_cities.sql`, `summaries.sql` (all safe to re-run) |

One-time setup:
1. Create a Postgres database with a hosted provider and copy its connection string.
2. Add it to the repo as a secret named `DATABASE_URL` (Settings → Secrets and variables → Actions).
3. Actions → **Set up database** → Run workflow.
4. Actions → **Daily weather load** → Run workflow with `mode: backfill`, a start date and yesterday as the end date.

After that the schedule takes over. To manage cities in the hosted database, run the same commands locally with `DATABASE_URL` set; it takes priority over the `POSTGRES_*` settings.

Things GitHub does with scheduled workflows: runs can start some minutes late when GitHub is busy; failed runs trigger an email; and in a repository with no activity for 60 days, scheduled workflows are switched off until re-enabled.

### Tests

```bash
pytest
```

- `test_transform.py`: uses a real sample response ([tests/fixtures/sample_response.json](tests/fixtures/sample_response.json)) and checks column names, data types and every validation rule
- `test_load.py`: loads the same data twice and asserts the row count doesn't change; also checks that values update and NaN becomes NULL. It runs against the Docker database inside a transaction that is rolled back, and is skipped if the database is down.
- `test_extract.py`: checks the endpoint and parameters each mode sends, using a fake HTTP session (no network)
- `test_cities.py`: geocoder filtering and how one place is chosen among several, matching `--cities` names, and adding cities (in a rolled-back transaction)
- `test_pipeline.py`: command-line validation

## Design decisions

**Upsert, not insert.** Every load is `INSERT ... ON CONFLICT (city_id, weather_date) DO UPDATE`. Any run, for any range, any number of times, leaves exactly one row per city per day holding the latest values. This is what lets every other part of the pipeline be relaxed about overlap: retries, re-runs and overlapping windows cost nothing. `df.to_sql()` can't do this, so the load uses SQLAlchemy `text()` with named parameters.

**Why `past_days=7` in daily mode.** Fetching only yesterday would make every failure permanent: if the job misses a day, nothing ever goes back for it. Re-fetching a rolling week means any run repairs the previous six days, and because loads are upserts, the overlap is free. `forecast_days=0` stops it from loading today (not finished yet) or forecasts.

**Why the archive delay matters.** The archive API is built from reanalysis data, which is published a few days behind real time. Its newest days can be missing or provisional. So the pipeline uses two sources: the archive for backfills, the forecast API for the last week. The two come from different weather models and can differ slightly (on 2026-11-13 Kano's max was 32.1 °C in the archive and 32.3 °C in the forecast API). Recent rows therefore hold forecast-API values. Re-running a backfill over older months replaces them with archive values; because of the upsert, that's safe to do whenever needed.

**Validate in transform, and be explicit about what happens.**
- Problems with dates (missing, duplicated, gaps) **stop the run** for that city, since the date is part of the key and the batch can't be trusted.
- Implausible values (temperature outside −10 to 55 °C, negative rain or wind, max below min) are **logged with the full row and dropped**, never silently.
- Missing measurements are **kept as NULL** and counted in the log, because Open-Meteo sometimes leaves the newest day blank and dropping it would lose the whole day.
- NaN is converted to NULL before loading: Postgres `NUMERIC` accepts `'NaN'` as a value, which would make `AVG()` return NaN.

**One transaction per city.** Each city's rows commit together or not at all, and one city failing (bad data, API error) doesn't block the others. The run still exits with code 1 so the failure is noticed.

**Retries with backoff.** Network calls fail. Connection errors and 429/5xx responses are retried 4 times with exponential backoff (`urllib3.Retry`). 4xx errors aren't retried; Open-Meteo's explanation is logged instead.

**Raw JSON copies.** Each API response is saved to `data/raw/` (ignored by git), so a transform bug can be fixed and the data reprocessed without calling the API again.

**Star schema, with cities as data, not code.** City details live once in `dim_city`; the fact table stores only `city_id`. The list of cities lives in the database rather than in a config file, so analysts can start tracking a new town with one command instead of a code change and a deploy. Cities are switched off with `active = false` instead of being deleted, because their weather history is still worth keeping (and the foreign key wouldn't allow deleting them anyway).

**Geocoding has to be checked, not trusted.** Open-Meteo's geocoder treats `country_code=NG` as a hint (asking for "Kano" also returns towns in Japan and Tanzania) and includes airports and districts, so results are filtered to Nigerian populated places. Names are ambiguous, so `add` always prints what it matched. Coordinates of an existing city are never overwritten by a new lookup, because its history was fetched with the original ones.

**Views, not tables, for summaries.** The data is small (a few thousand rows), so views are fast enough and are always up to date with no refresh step. The rolling average uses `RANGE BETWEEN INTERVAL '6 days' PRECEDING` instead of `ROWS BETWEEN 6 PRECEDING`, so a missing day can't stretch the window past 7 days; `days_in_window` shows when it covers fewer.

## Limits worth knowing

- **Licensing:** Open-Meteo's free API is for non-commercial use. A real company would need its paid plan.
- **API quota:** the free tier allows roughly 10,000 calls a day. Daily mode is one call per city, so hundreds of cities fit. Multi-year backfills count as more than one call, so large backfills should be spread out.
- **Grid resolution:** the weather models work on a grid of roughly 10–25 km. Towns close together can get identical values.
- **Same name, same state:** two villages can share both a name and a state (the geocoder lists two Ibadans in Odeda, Ogun State). Only one of them can be tracked under that `(name, state)`.

## Project layout

```
src/            config, cities, extract, transform, load, pipeline
sql/            schema.sql, seed_cities.sql, summaries.sql, migrations/
tests/          pytest tests and a sample API response
data/raw/       raw API responses (git-ignored)
logs/           cron output (git-ignored)
```

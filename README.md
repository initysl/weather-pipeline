# weather-pipeline

Daily weather for the cities we operate in, kept fresh, correct and free of duplicates for the analytics team.

```
Open-Meteo API → Extract (Python) → Transform (pandas) → Load (PostgreSQL) → Summary tables → Scheduled daily
```

## Layout

```
src/config.py      cities, API URLs, DB connection (reads .env)
src/extract.py     fetch from Open-Meteo
src/transform.py   clean/shape with pandas
src/load.py        upsert into Postgres
src/pipeline.py    runs the steps, takes CLI args
sql/schema.sql     table definitions (auto-applied on first DB start)
sql/summaries.sql  summary tables/views for analysts
tests/             pytest tests
```

## Setup

```bash
cp .env.example .env            # then set a real POSTGRES_PASSWORD
uv venv .venv && uv pip install -r requirements.txt   # or: python -m venv .venv && .venv/bin/pip install -r requirements.txt
source .venv/bin/activate
docker compose up -d            # Postgres 16 on localhost:5432
```

`sql/schema.sql` only runs when the data volume is empty. After changing it, either apply it by hand:

```bash
docker exec -i weather-db psql -U weather -d weather < sql/schema.sql
```

or reset the database (deletes all data): `docker compose down -v && docker compose up -d`.

## Useful commands

```bash
docker exec -it weather-db psql -U weather -d weather   # open a psql shell
pytest                                                   # run tests
```

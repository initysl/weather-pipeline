-- Active: 1790843856008@@127.0.0.1@5432
-- One row per city per day. The primary key on (city, date) is what keeps
-- the table free of duplicates: loads should upsert (INSERT ... ON CONFLICT).
CREATE TABLE IF NOT EXISTS daily_weather (
    city                TEXT          NOT NULL,
    date                DATE          NOT NULL,
    temp_max_c          NUMERIC(5,2),
    temp_min_c          NUMERIC(5,2),
    precipitation_mm    NUMERIC(6,2),
    rain_mm             NUMERIC(6,2),
    windspeed_max_kmh   NUMERIC(6,2),
    loaded_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (city, date)
);

-- Dimension: one row per city we operate in.
CREATE TABLE IF NOT EXISTS dim_city (
    city_id     SERIAL PRIMARY KEY,
    name        TEXT          NOT NULL UNIQUE,
    latitude    NUMERIC(8,5)  NOT NULL,
    longitude   NUMERIC(8,5)  NOT NULL
);

-- Fact: one row per city per day.
-- The primary key (city_id, weather_date) makes reruns safe: the same city
-- and date can't exist twice, so loads upsert with INSERT ... ON CONFLICT.
CREATE TABLE IF NOT EXISTS fact_daily_weather (
    city_id             INT           NOT NULL REFERENCES dim_city(city_id),
    weather_date        DATE          NOT NULL,
    temp_max_c          NUMERIC(5,2),
    temp_min_c          NUMERIC(5,2),
    precipitation_mm    NUMERIC(6,2),
    wind_speed_max_kmh  NUMERIC(6,2),
    loaded_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (city_id, weather_date)
);

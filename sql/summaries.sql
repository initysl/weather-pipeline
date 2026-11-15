-- Analyst-facing views over fact_daily_weather.
-- Views always reflect the latest load, so there's nothing to refresh.
-- Safe to re-run: each view is dropped and recreated.

DROP VIEW IF EXISTS v_monthly_city_summary, v_temp_7day_rolling, v_hotter_than_usual;

-- 1. Monthly summary per city
--    "How many rainy days did Kano get this month?"
CREATE VIEW v_monthly_city_summary AS
SELECT
    c.name                                              AS city,
    c.state,
    date_trunc('month', f.weather_date)::date           AS month,
    COUNT(*)                                            AS days_recorded,
    ROUND(AVG(f.temp_max_c), 1)                         AS avg_temp_max_c,
    ROUND(AVG(f.temp_min_c), 1)                         AS avg_temp_min_c,
    ROUND(SUM(f.precipitation_mm), 1)                   AS total_rain_mm,
    COUNT(*) FILTER (WHERE f.precipitation_mm > 1)      AS rainy_days  -- > 1 mm ignores drizzle
FROM fact_daily_weather f
JOIN dim_city c USING (city_id)
GROUP BY c.city_id, c.name, c.state, date_trunc('month', f.weather_date);


-- 2. 7-day rolling average of max temperature
--    RANGE over dates (not ROWS) so a missing day can't stretch the window past 7 days.
CREATE VIEW v_temp_7day_rolling AS
SELECT
    c.name                                              AS city,
    c.state,
    f.weather_date,
    f.temp_max_c,
    ROUND(AVG(f.temp_max_c) OVER w, 1)                  AS temp_max_7day_avg_c,
    COUNT(f.temp_max_c) OVER w                          AS days_in_window  -- < 7 at the start of the data
FROM fact_daily_weather f
JOIN dim_city c USING (city_id)
WINDOW w AS (
    PARTITION BY f.city_id
    ORDER BY f.weather_date
    RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
);


-- 3. Hotter than usual
--    Each day vs that city's average max temperature for the same calendar month
--    in all *previous* years. "Is Lagos hotter than usual this week?"
CREATE VIEW v_hotter_than_usual AS
WITH city_month_year AS (
    SELECT
        city_id,
        EXTRACT(YEAR  FROM weather_date)::int AS yr,
        EXTRACT(MONTH FROM weather_date)::int AS mon,
        SUM(temp_max_c)   AS sum_temp,
        COUNT(temp_max_c) AS n_days
    FROM fact_daily_weather
    GROUP BY 1, 2, 3
),
baseline AS (
    -- For each (city, year, month): pool all days of that month from earlier years
    SELECT
        cur.city_id, cur.yr, cur.mon,
        SUM(prev.sum_temp) / NULLIF(SUM(prev.n_days), 0) AS usual_temp_max_c,
        COUNT(prev.yr)                                   AS years_of_history
    FROM city_month_year cur
    JOIN city_month_year prev
      ON prev.city_id = cur.city_id
     AND prev.mon = cur.mon
     AND prev.yr < cur.yr
    GROUP BY cur.city_id, cur.yr, cur.mon
)
SELECT
    c.name                                               AS city,
    c.state,
    f.weather_date,
    f.temp_max_c,
    ROUND(b.usual_temp_max_c, 1)                         AS usual_temp_max_c,
    ROUND(f.temp_max_c - b.usual_temp_max_c, 1)          AS anomaly_c,
    f.temp_max_c - b.usual_temp_max_c > 2                AS hotter_than_usual,  -- > 2 °C above normal
    b.years_of_history
FROM fact_daily_weather f
JOIN dim_city c USING (city_id)
JOIN baseline b
  ON b.city_id = f.city_id
 AND b.yr  = EXTRACT(YEAR  FROM f.weather_date)::int
 AND b.mon = EXTRACT(MONTH FROM f.weather_date)::int;
-- Inner join: days with no earlier year of the same month have no baseline and are left out.

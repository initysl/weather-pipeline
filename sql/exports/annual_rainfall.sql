-- Chart: total rainfall and rainy days per city in the last complete calendar year.
-- Cities without a full year of data are left out, so a partial year never looks dry.
WITH last_year AS (
    SELECT EXTRACT(YEAR FROM CURRENT_DATE)::int - 1 AS yr
)
SELECT
    c.name                                              AS "City",
    c.state                                             AS "State",
    ly.yr                                               AS "Year",
    ROUND(SUM(f.precipitation_mm))::int                 AS "Rainfall (mm)",
    COUNT(*) FILTER (WHERE f.precipitation_mm > 1)      AS "Rainy days"
FROM fact_daily_weather f
JOIN dim_city c USING (city_id)
CROSS JOIN last_year ly
WHERE c.active
  AND f.weather_date >= make_date(ly.yr, 1, 1)
  AND f.weather_date <  make_date(ly.yr + 1, 1, 1)
GROUP BY c.name, c.state, ly.yr
HAVING COUNT(*) >= 365
ORDER BY "Rainfall (mm)" DESC;

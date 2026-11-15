-- Chart (heat map table): rainy days (> 1 mm) per city per month, last complete year.
-- Cities are ordered north to south, so the rainy season visibly moves down the table.
WITH last_year AS (
    SELECT EXTRACT(YEAR FROM CURRENT_DATE)::int - 1 AS yr
),
days AS (
    SELECT c.name, c.state, c.latitude,
           EXTRACT(MONTH FROM f.weather_date)::int AS mon,
           f.precipitation_mm > 1                  AS rainy
    FROM fact_daily_weather f
    JOIN dim_city c USING (city_id)
    CROSS JOIN last_year ly
    WHERE c.active
      AND f.weather_date >= make_date(ly.yr, 1, 1)
      AND f.weather_date <  make_date(ly.yr + 1, 1, 1)
)
SELECT
    name                                        AS "City",
    state                                       AS "State",
    COUNT(*) FILTER (WHERE rainy AND mon = 1)   AS "Jan",
    COUNT(*) FILTER (WHERE rainy AND mon = 2)   AS "Feb",
    COUNT(*) FILTER (WHERE rainy AND mon = 3)   AS "Mar",
    COUNT(*) FILTER (WHERE rainy AND mon = 4)   AS "Apr",
    COUNT(*) FILTER (WHERE rainy AND mon = 5)   AS "May",
    COUNT(*) FILTER (WHERE rainy AND mon = 6)   AS "Jun",
    COUNT(*) FILTER (WHERE rainy AND mon = 7)   AS "Jul",
    COUNT(*) FILTER (WHERE rainy AND mon = 8)   AS "Aug",
    COUNT(*) FILTER (WHERE rainy AND mon = 9)   AS "Sep",
    COUNT(*) FILTER (WHERE rainy AND mon = 10)  AS "Oct",
    COUNT(*) FILTER (WHERE rainy AND mon = 11)  AS "Nov",
    COUNT(*) FILTER (WHERE rainy AND mon = 12)  AS "Dec"
FROM days
GROUP BY name, state, latitude
HAVING COUNT(*) >= 365
ORDER BY latitude DESC;

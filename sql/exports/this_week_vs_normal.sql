-- Chart: each city's average max temperature over the latest 7 days of data,
-- against its normal for those dates (same month in previous years).
-- Positive = hotter than usual. Changes every day.
SELECT
    h.city                                  AS "City",
    h.state                                 AS "State",
    ROUND(AVG(h.temp_max_c), 1)             AS "This week (°C)",
    ROUND(AVG(h.usual_temp_max_c), 1)       AS "Usual (°C)",
    ROUND(AVG(h.anomaly_c), 1)              AS "Difference (°C)",
    -- A category for chart colours, so the colouring follows the data every day
    CASE
        WHEN ROUND(AVG(h.anomaly_c), 1) > 0 THEN 'Hotter than usual'
        WHEN ROUND(AVG(h.anomaly_c), 1) < 0 THEN 'Cooler than usual'
        ELSE 'As usual'
    END                                     AS "Compared with usual",
    MAX(h.weather_date)                     AS "Week ending"
FROM v_hotter_than_usual h
-- A scalar subquery runs once. (As a joined CTE, Postgres re-ran MAX() for every row: 30+ s.)
WHERE h.weather_date > (SELECT MAX(weather_date) FROM fact_daily_weather) - 7
GROUP BY h.city, h.state
ORDER BY "Difference (°C)" DESC;

-- Starting set of cities for a fresh database. Safe to re-run.
-- State names match what Open-Meteo's geocoder returns, so `src.cities add`
-- recognises these as already tracked.
INSERT INTO dim_city (name, state, latitude, longitude) VALUES
    ('Kano',   'Kano State',   12.00220, 8.59200),
    ('Osogbo', 'Osun State',    7.78270, 4.54180),
    ('Ibadan', 'Oyo State',     7.37750, 3.94700),
    ('Kaduna', 'Kaduna State', 10.51050, 7.41650),
    ('Lagos',  'Lagos',         6.52440, 3.37920)
ON CONFLICT (name, state) DO NOTHING;

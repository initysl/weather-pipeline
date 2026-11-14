-- Upgrade a database created before cities moved out of config.py.
-- Adds state + active to dim_city and makes (name, state) unique instead of name.
-- Not needed for fresh databases: schema.sql already has this shape.
-- Safe to re-run.
BEGIN;

ALTER TABLE dim_city ADD COLUMN IF NOT EXISTS state  TEXT;
ALTER TABLE dim_city ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;

UPDATE dim_city SET state = CASE name
        WHEN 'Kano'   THEN 'Kano State'
        WHEN 'Osogbo' THEN 'Osun State'
        WHEN 'Ibadan' THEN 'Oyo State'
        WHEN 'Kaduna' THEN 'Kaduna State'
        WHEN 'Lagos'  THEN 'Lagos'
    END
WHERE state IS NULL;

-- Fails (and rolls back everything) if any other city is still missing a state
ALTER TABLE dim_city ALTER COLUMN state SET NOT NULL;

ALTER TABLE dim_city DROP CONSTRAINT IF EXISTS dim_city_name_key;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dim_city_name_state_key') THEN
        ALTER TABLE dim_city ADD CONSTRAINT dim_city_name_state_key UNIQUE (name, state);
    END IF;
END $$;

COMMIT;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE video_uploads
ADD COLUMN IF NOT EXISTS description TEXT;

ALTER TABLE vehicle_events
ADD COLUMN IF NOT EXISTS sequence_no INTEGER;

ALTER TABLE vehicle_events
ADD COLUMN IF NOT EXISTS detected_label VARCHAR(100);

ALTER TABLE vehicle_events
ADD COLUMN IF NOT EXISTS vehicle_type_code VARCHAR(100);

ALTER TABLE vehicle_events
ADD COLUMN IF NOT EXISTS vehicle_type_label VARCHAR(255);

ALTER TABLE vehicle_events
ADD COLUMN IF NOT EXISTS golongan_code VARCHAR(50);

ALTER TABLE vehicle_events
ADD COLUMN IF NOT EXISTS golongan_label VARCHAR(100);

WITH ranked_events AS (
    SELECT
        id,
        ROW_NUMBER() OVER (PARTITION BY video_upload_id ORDER BY crossed_at_seconds ASC, id ASC) AS sequence_no
    FROM vehicle_events
)
UPDATE vehicle_events AS ve
SET sequence_no = ranked_events.sequence_no
FROM ranked_events
WHERE ve.id = ranked_events.id
  AND ve.sequence_no IS NULL;

UPDATE vehicle_events
SET detected_label = CASE vehicle_class
    WHEN 'motorcycle' THEN 'motorcycle'
    WHEN 'bus' THEN 'bus'
    WHEN 'truck' THEN 'truck'
    ELSE 'car'
END
WHERE detected_label IS NULL;

UPDATE vehicle_events
SET vehicle_type_code = CASE vehicle_class
    WHEN 'motorcycle' THEN 'motorcycle_three_wheeler'
    WHEN 'bus' THEN 'small_bus'
    WHEN 'truck' THEN 'light_truck_2_axle'
    ELSE 'passenger_car'
END
WHERE vehicle_type_code IS NULL;

UPDATE vehicle_events
SET vehicle_type_label = CASE vehicle_type_code
    WHEN 'motorcycle_three_wheeler' THEN 'motorcycle'
    WHEN 'small_bus' THEN 'small bus'
    WHEN 'light_truck_2_axle' THEN 'light 2-axle truck'
    ELSE 'car (sedan, jeep, station wagon)'
END
WHERE vehicle_type_label IS NULL;

UPDATE vehicle_events
SET golongan_code = CASE vehicle_type_code
    WHEN 'motorcycle_three_wheeler' THEN '1'
    WHEN 'small_bus' THEN '5a'
    WHEN 'light_truck_2_axle' THEN '6a'
    ELSE '2'
END
WHERE golongan_code IS NULL;

UPDATE vehicle_events
SET golongan_label = CASE golongan_code
    WHEN '1' THEN 'Motorcycle / 3-wheel vehicle'
    WHEN '2' THEN 'Sedan / jeep / station wagon'
    WHEN '5a' THEN 'Small bus'
    WHEN '6a' THEN 'Light 2-axle truck'
    ELSE 'Sedan / jeep / station wagon'
END
WHERE golongan_label IS NULL;

ALTER TABLE vehicle_events
ALTER COLUMN sequence_no SET NOT NULL;

ALTER TABLE vehicle_events
ALTER COLUMN golongan_code SET NOT NULL;

ALTER TABLE vehicle_events
ALTER COLUMN golongan_label SET NOT NULL;

CREATE TABLE IF NOT EXISTS analysis_golongan_totals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_upload_id UUID NOT NULL REFERENCES video_uploads(id) ON DELETE CASCADE,
    analysis_job_id UUID NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    golongan_code VARCHAR(50) NOT NULL,
    golongan_label VARCHAR(100) NOT NULL,
    vehicle_count INTEGER NOT NULL DEFAULT 0 CHECK (vehicle_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_analysis_golongan_total_job UNIQUE (analysis_job_id, golongan_code)
);

CREATE INDEX IF NOT EXISTS idx_vehicle_events_video_sequence ON vehicle_events(video_upload_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_analysis_golongan_totals_video_code ON analysis_golongan_totals(video_upload_id, golongan_code);

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_analysis_golongan_totals_updated_at ON analysis_golongan_totals;
CREATE TRIGGER trg_analysis_golongan_totals_updated_at
BEFORE UPDATE ON analysis_golongan_totals
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS car_min_confidence DOUBLE PRECISION;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS bus_min_confidence DOUBLE PRECISION;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS truck_min_confidence DOUBLE PRECISION;

UPDATE detection_settings
SET car_min_confidence = COALESCE(car_min_confidence, vehicle_min_confidence, 0.30);

UPDATE detection_settings
SET bus_min_confidence = COALESCE(bus_min_confidence, GREATEST(COALESCE(vehicle_min_confidence, 0.30) + 0.04, 0.34));

UPDATE detection_settings
SET truck_min_confidence = COALESCE(truck_min_confidence, GREATEST(COALESCE(vehicle_min_confidence, 0.30) + 0.08, 0.38));

ALTER TABLE detection_settings
ALTER COLUMN car_min_confidence SET DEFAULT 0.30;

ALTER TABLE detection_settings
ALTER COLUMN bus_min_confidence SET DEFAULT 0.34;

ALTER TABLE detection_settings
ALTER COLUMN truck_min_confidence SET DEFAULT 0.38;

ALTER TABLE detection_settings
ALTER COLUMN vehicle_min_confidence SET DEFAULT 0.30;

UPDATE detection_settings
SET car_min_confidence = 0.30
WHERE car_min_confidence IS NULL;

UPDATE detection_settings
SET bus_min_confidence = 0.34
WHERE bus_min_confidence IS NULL;

UPDATE detection_settings
SET truck_min_confidence = 0.38
WHERE truck_min_confidence IS NULL;

ALTER TABLE detection_settings
ALTER COLUMN car_min_confidence SET NOT NULL;

ALTER TABLE detection_settings
ALTER COLUMN bus_min_confidence SET NOT NULL;

ALTER TABLE detection_settings
ALTER COLUMN truck_min_confidence SET NOT NULL;

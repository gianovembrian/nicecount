CREATE TABLE IF NOT EXISTS detection_settings (
    id INTEGER PRIMARY KEY,
    global_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.12,
    motorcycle_min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.12,
    car_min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.30,
    bus_min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.34,
    truck_min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.38,
    vehicle_min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.30,
    iou_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.45,
    frame_stride INTEGER NOT NULL DEFAULT 1,
    target_analysis_fps DOUBLE PRECISION NOT NULL DEFAULT 15.0,
    preview_fps DOUBLE PRECISION NOT NULL DEFAULT 6.0,
    working_max_width INTEGER NOT NULL DEFAULT 1600,
    preview_max_width INTEGER NOT NULL DEFAULT 960,
    preview_jpeg_quality INTEGER NOT NULL DEFAULT 70,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS car_min_confidence DOUBLE PRECISION;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS bus_min_confidence DOUBLE PRECISION;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS truck_min_confidence DOUBLE PRECISION;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS iou_threshold DOUBLE PRECISION;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS frame_stride INTEGER;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS target_analysis_fps DOUBLE PRECISION;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS preview_fps DOUBLE PRECISION;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS working_max_width INTEGER;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS preview_max_width INTEGER;

ALTER TABLE detection_settings
ADD COLUMN IF NOT EXISTS preview_jpeg_quality INTEGER;

INSERT INTO detection_settings (
    id,
    global_confidence,
    motorcycle_min_confidence,
    car_min_confidence,
    bus_min_confidence,
    truck_min_confidence,
    vehicle_min_confidence,
    iou_threshold,
    frame_stride,
    target_analysis_fps,
    preview_fps,
    working_max_width,
    preview_max_width,
    preview_jpeg_quality
)
VALUES (1, 0.12, 0.12, 0.30, 0.34, 0.38, 0.30, 0.45, 1, 15.0, 6.0, 1600, 960, 70)
ON CONFLICT (id) DO NOTHING;

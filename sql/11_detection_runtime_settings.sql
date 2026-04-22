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

UPDATE detection_settings
SET
    iou_threshold = COALESCE(iou_threshold, 0.45),
    frame_stride = COALESCE(frame_stride, 1),
    target_analysis_fps = COALESCE(target_analysis_fps, 15.0),
    preview_fps = COALESCE(preview_fps, 6.0),
    working_max_width = COALESCE(working_max_width, 1600),
    preview_max_width = COALESCE(preview_max_width, 960),
    preview_jpeg_quality = COALESCE(preview_jpeg_quality, 70);

ALTER TABLE detection_settings
ALTER COLUMN iou_threshold SET DEFAULT 0.45;

ALTER TABLE detection_settings
ALTER COLUMN frame_stride SET DEFAULT 1;

ALTER TABLE detection_settings
ALTER COLUMN target_analysis_fps SET DEFAULT 15.0;

ALTER TABLE detection_settings
ALTER COLUMN preview_fps SET DEFAULT 6.0;

ALTER TABLE detection_settings
ALTER COLUMN working_max_width SET DEFAULT 1600;

ALTER TABLE detection_settings
ALTER COLUMN preview_max_width SET DEFAULT 960;

ALTER TABLE detection_settings
ALTER COLUMN preview_jpeg_quality SET DEFAULT 70;

ALTER TABLE detection_settings
ALTER COLUMN iou_threshold SET NOT NULL;

ALTER TABLE detection_settings
ALTER COLUMN frame_stride SET NOT NULL;

ALTER TABLE detection_settings
ALTER COLUMN target_analysis_fps SET NOT NULL;

ALTER TABLE detection_settings
ALTER COLUMN preview_fps SET NOT NULL;

ALTER TABLE detection_settings
ALTER COLUMN working_max_width SET NOT NULL;

ALTER TABLE detection_settings
ALTER COLUMN preview_max_width SET NOT NULL;

ALTER TABLE detection_settings
ALTER COLUMN preview_jpeg_quality SET NOT NULL;

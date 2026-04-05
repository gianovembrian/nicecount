ALTER TABLE vehicle_events
ADD COLUMN IF NOT EXISTS count_line_order INTEGER;

ALTER TABLE vehicle_events
ADD COLUMN IF NOT EXISTS count_line_name VARCHAR(255);

UPDATE vehicle_events
SET count_line_order = 1
WHERE count_line_order IS NULL;

UPDATE vehicle_events
SET count_line_name = 'Line 1'
WHERE count_line_name IS NULL;

CREATE INDEX IF NOT EXISTS idx_vehicle_events_video_line
ON vehicle_events(video_upload_id, count_line_order, sequence_no);

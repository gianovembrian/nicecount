ALTER TABLE video_uploads
DROP CONSTRAINT IF EXISTS video_uploads_status_check;

ALTER TABLE video_uploads
ADD CONSTRAINT video_uploads_status_check
CHECK (status IN ('uploaded', 'converting', 'processing', 'processed', 'failed'));

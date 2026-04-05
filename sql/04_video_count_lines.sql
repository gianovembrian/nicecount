CREATE TABLE IF NOT EXISTS video_count_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_upload_id UUID NOT NULL REFERENCES video_uploads(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    line_order INTEGER NOT NULL CHECK (line_order BETWEEN 1 AND 2),
    start_x DOUBLE PRECISION NOT NULL CHECK (start_x >= 0 AND start_x <= 1),
    start_y DOUBLE PRECISION NOT NULL CHECK (start_y >= 0 AND start_y <= 1),
    end_x DOUBLE PRECISION NOT NULL CHECK (end_x >= 0 AND end_x <= 1),
    end_y DOUBLE PRECISION NOT NULL CHECK (end_y >= 0 AND end_y <= 1),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_video_count_line_order UNIQUE (video_upload_id, line_order)
);

CREATE INDEX IF NOT EXISTS idx_video_count_lines_video_active
ON video_count_lines(video_upload_id, is_active, line_order);

DROP TRIGGER IF EXISTS trg_video_count_lines_updated_at ON video_count_lines;
CREATE TRIGGER trg_video_count_lines_updated_at
BEFORE UPDATE ON video_count_lines
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

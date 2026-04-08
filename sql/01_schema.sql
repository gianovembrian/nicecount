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

CREATE TABLE IF NOT EXISTS detection_settings (
    id INTEGER PRIMARY KEY,
    global_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.12,
    motorcycle_min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.12,
    vehicle_min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.35,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS master_classes (
    code VARCHAR(50) PRIMARY KEY,
    label VARCHAR(100) NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL UNIQUE CHECK (sort_order >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    location_description TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    direction_normal_label VARCHAR(255) NOT NULL DEFAULT 'Normal',
    direction_opposite_label VARCHAR(255) NOT NULL DEFAULT 'Opposite',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS count_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    line_order INTEGER NOT NULL DEFAULT 1,
    start_x DOUBLE PRECISION NOT NULL CHECK (start_x >= 0 AND start_x <= 1),
    start_y DOUBLE PRECISION NOT NULL CHECK (start_y >= 0 AND start_y <= 1),
    end_x DOUBLE PRECISION NOT NULL CHECK (end_x >= 0 AND end_x <= 1),
    end_y DOUBLE PRECISION NOT NULL CHECK (end_y >= 0 AND end_y <= 1),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS video_uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE RESTRICT,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL UNIQUE,
    relative_path TEXT NOT NULL,
    description TEXT,
    mime_type VARCHAR(255),
    file_size_bytes BIGINT,
    recorded_at TIMESTAMPTZ,
    uploaded_by VARCHAR(255),
    status VARCHAR(50) NOT NULL CHECK (status IN ('uploaded', 'converting', 'processing', 'processed', 'failed')),
    video_fps DOUBLE PRECISION,
    frame_width INTEGER,
    frame_height INTEGER,
    frame_count BIGINT,
    duration_seconds DOUBLE PRECISION,
    processing_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_upload_id UUID NOT NULL UNIQUE REFERENCES video_uploads(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL CHECK (status IN ('pending', 'queued', 'processing', 'completed', 'failed')),
    model_name VARCHAR(255),
    config_json JSONB,
    summary_json JSONB,
    annotated_relative_path TEXT,
    report_relative_path TEXT,
    total_frames BIGINT,
    processed_frames BIGINT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vehicle_events (
    id BIGSERIAL PRIMARY KEY,
    video_upload_id UUID NOT NULL REFERENCES video_uploads(id) ON DELETE CASCADE,
    analysis_job_id UUID NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE RESTRICT,
    sequence_no INTEGER NOT NULL,
    track_id BIGINT,
    vehicle_class VARCHAR(50) NOT NULL CHECK (vehicle_class IN ('bicycle', 'motorcycle', 'car', 'bus', 'truck')),
    detected_label VARCHAR(100),
    vehicle_type_code VARCHAR(100),
    vehicle_type_label VARCHAR(255),
    golongan_code VARCHAR(50) NOT NULL REFERENCES master_classes(code) ON DELETE RESTRICT,
    golongan_label VARCHAR(100) NOT NULL,
    source_label VARCHAR(100),
    count_line_order INTEGER,
    count_line_name VARCHAR(255),
    direction VARCHAR(50) NOT NULL CHECK (direction IN ('normal', 'opposite')),
    crossed_at_seconds DOUBLE PRECISION NOT NULL,
    crossed_at_frame INTEGER NOT NULL,
    confidence DOUBLE PRECISION,
    speed_kph DOUBLE PRECISION,
    bbox_x1 DOUBLE PRECISION,
    bbox_y1 DOUBLE PRECISION,
    bbox_x2 DOUBLE PRECISION,
    bbox_y2 DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analysis_golongan_totals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_upload_id UUID NOT NULL REFERENCES video_uploads(id) ON DELETE CASCADE,
    analysis_job_id UUID NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    golongan_code VARCHAR(50) NOT NULL REFERENCES master_classes(code) ON DELETE RESTRICT,
    golongan_label VARCHAR(100) NOT NULL,
    vehicle_count INTEGER NOT NULL DEFAULT 0 CHECK (vehicle_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_analysis_golongan_total_job UNIQUE (analysis_job_id, golongan_code)
);

CREATE TABLE IF NOT EXISTS video_count_aggregates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_upload_id UUID NOT NULL REFERENCES video_uploads(id) ON DELETE CASCADE,
    analysis_job_id UUID NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE RESTRICT,
    bucket_type VARCHAR(50) NOT NULL CHECK (bucket_type IN ('minute', 'five_minute', 'hour', 'day', 'total')),
    bucket_index INTEGER NOT NULL,
    bucket_start_seconds DOUBLE PRECISION NOT NULL,
    bucket_end_seconds DOUBLE PRECISION NOT NULL,
    bucket_started_at TIMESTAMPTZ,
    bucket_ended_at TIMESTAMPTZ,
    direction VARCHAR(50) NOT NULL CHECK (direction IN ('normal', 'opposite')),
    vehicle_class VARCHAR(50) NOT NULL CHECK (vehicle_class IN ('bicycle', 'motorcycle', 'car', 'bus', 'truck')),
    vehicle_count INTEGER NOT NULL CHECK (vehicle_count >= 0),
    avg_speed_kph DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_video_count_aggregate_bucket UNIQUE (
        video_upload_id,
        bucket_type,
        bucket_index,
        direction,
        vehicle_class
    )
);

CREATE INDEX IF NOT EXISTS idx_count_lines_site_active ON count_lines(site_id, is_active, line_order);
CREATE INDEX IF NOT EXISTS idx_master_classes_sort_order ON master_classes(sort_order);
CREATE UNIQUE INDEX IF NOT EXISTS uq_count_lines_one_active_per_site ON count_lines(site_id) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_video_uploads_site_status ON video_uploads(site_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_video_count_lines_video_active ON video_count_lines(video_upload_id, is_active, line_order);
CREATE INDEX IF NOT EXISTS idx_vehicle_events_video_sequence ON vehicle_events(video_upload_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_vehicle_events_video_time ON vehicle_events(video_upload_id, crossed_at_seconds);
CREATE INDEX IF NOT EXISTS idx_vehicle_events_video_line ON vehicle_events(video_upload_id, count_line_order, sequence_no);
CREATE INDEX IF NOT EXISTS idx_vehicle_events_video_type ON vehicle_events(video_upload_id, vehicle_type_code);
CREATE INDEX IF NOT EXISTS idx_analysis_golongan_totals_video_code ON analysis_golongan_totals(video_upload_id, golongan_code);
CREATE INDEX IF NOT EXISTS idx_video_count_aggregates_video_bucket ON video_count_aggregates(video_upload_id, bucket_type, bucket_index);

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_sites_updated_at ON sites;
CREATE TRIGGER trg_sites_updated_at
BEFORE UPDATE ON sites
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_master_classes_updated_at ON master_classes;
CREATE TRIGGER trg_master_classes_updated_at
BEFORE UPDATE ON master_classes
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_count_lines_updated_at ON count_lines;
CREATE TRIGGER trg_count_lines_updated_at
BEFORE UPDATE ON count_lines
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_video_uploads_updated_at ON video_uploads;
CREATE TRIGGER trg_video_uploads_updated_at
BEFORE UPDATE ON video_uploads
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_video_count_lines_updated_at ON video_count_lines;
CREATE TRIGGER trg_video_count_lines_updated_at
BEFORE UPDATE ON video_count_lines
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_analysis_jobs_updated_at ON analysis_jobs;
CREATE TRIGGER trg_analysis_jobs_updated_at
BEFORE UPDATE ON analysis_jobs
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_analysis_golongan_totals_updated_at ON analysis_golongan_totals;
CREATE TRIGGER trg_analysis_golongan_totals_updated_at
BEFORE UPDATE ON analysis_golongan_totals
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

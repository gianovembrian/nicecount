CREATE TABLE IF NOT EXISTS detection_settings (
    id INTEGER PRIMARY KEY,
    global_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.12,
    motorcycle_min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.12,
    vehicle_min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.35,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO detection_settings (
    id,
    global_confidence,
    motorcycle_min_confidence,
    vehicle_min_confidence
)
VALUES (1, 0.12, 0.12, 0.35)
ON CONFLICT (id) DO NOTHING;

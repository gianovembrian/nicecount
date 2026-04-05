CREATE TABLE IF NOT EXISTS master_classes (
    code VARCHAR(50) PRIMARY KEY CHECK (code IN ('golongan_1', 'golongan_2', 'golongan_3', 'golongan_4', 'golongan_5')),
    label VARCHAR(100) NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL UNIQUE CHECK (sort_order BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_master_classes_sort_order ON master_classes(sort_order);

DROP TRIGGER IF EXISTS trg_master_classes_updated_at ON master_classes;
CREATE TRIGGER trg_master_classes_updated_at
BEFORE UPDATE ON master_classes
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

INSERT INTO master_classes (code, label, description, sort_order)
VALUES
    ('golongan_1', 'Class I', 'Sedan, jeep / SUV, small pickup, small bus, light truck, and motorcycle.', 1),
    ('golongan_2', 'Class II', 'Large 2-axle trucks bigger than Class I vehicles.', 2),
    ('golongan_3', 'Class III', 'Trucks with a 3-axle configuration.', 3),
    ('golongan_4', 'Class IV', 'Trucks with a 4-axle configuration.', 4),
    ('golongan_5', 'Class V', 'Trucks with 5 axles or more.', 5)
ON CONFLICT (code) DO NOTHING;

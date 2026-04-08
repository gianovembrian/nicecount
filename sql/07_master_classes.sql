CREATE TABLE IF NOT EXISTS master_classes (
    code VARCHAR(50) PRIMARY KEY,
    label VARCHAR(100) NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL UNIQUE CHECK (sort_order >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO master_classes (code, label, description, sort_order)
VALUES
    ('1', 'Motorcycle / 3-wheel vehicle', 'Motorcycles and 3-wheel motor vehicles.', 1),
    ('2', 'Sedan / jeep / station wagon', 'Sedans, jeeps, and station wagons.', 2),
    ('3', 'Medium passenger vehicle', 'Medium passenger transport vehicles.', 3),
    ('4', 'Pickup / micro truck / delivery', 'Pickups, micro trucks, and delivery vehicles.', 4),
    ('5a', 'Small bus', 'Small buses.', 5),
    ('5b', 'Large bus', 'Large buses.', 6),
    ('6a', 'Light 2-axle truck', 'Light 2-axle trucks.', 7),
    ('6b', 'Medium 2-axle truck', 'Medium 2-axle trucks.', 8),
    ('7a', '3-axle truck', '3-axle trucks.', 9),
    ('7b', 'Articulated truck', 'Articulated trucks.', 10),
    ('7c', 'Semi-trailer truck', 'Semi-trailer trucks.', 11),
    ('8', 'Non-motorized vehicle', 'Non-motorized vehicles.', 12)
ON CONFLICT (code) DO UPDATE
SET
    label = EXCLUDED.label,
    description = EXCLUDED.description,
    sort_order = EXCLUDED.sort_order;

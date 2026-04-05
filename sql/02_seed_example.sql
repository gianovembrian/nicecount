INSERT INTO sites (
    code,
    name,
    location_description,
    direction_normal_label,
    direction_opposite_label
) VALUES (
    '17034',
    'Bts. Kota Bandar Lampung - Gedong Tataan',
    'Lampung',
    'Arah Bandar Lampung',
    'Arah Gedong Tataan'
) ON CONFLICT (code) DO NOTHING;

INSERT INTO count_lines (
    site_id,
    name,
    line_order,
    start_x,
    start_y,
    end_x,
    end_y,
    is_active
)
SELECT
    id,
    'Main Line',
    1,
    0.10,
    0.55,
    0.90,
    0.55,
    TRUE
FROM sites
WHERE code = '17034'
AND NOT EXISTS (
    SELECT 1
    FROM count_lines
    WHERE count_lines.site_id = sites.id
      AND count_lines.name = 'Main Line'
);

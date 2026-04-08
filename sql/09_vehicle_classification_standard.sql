ALTER TABLE master_classes
    DROP CONSTRAINT IF EXISTS master_classes_code_check;

ALTER TABLE master_classes
    DROP CONSTRAINT IF EXISTS master_classes_sort_order_check;

ALTER TABLE vehicle_events
    ADD COLUMN IF NOT EXISTS vehicle_type_code VARCHAR(100);

ALTER TABLE vehicle_events
    ADD COLUMN IF NOT EXISTS vehicle_type_label VARCHAR(255);

ALTER TABLE vehicle_events
    DROP CONSTRAINT IF EXISTS vehicle_events_vehicle_class_check;

ALTER TABLE vehicle_events
    DROP CONSTRAINT IF EXISTS vehicle_events_golongan_code_check;

ALTER TABLE vehicle_events
    DROP CONSTRAINT IF EXISTS vehicle_events_golongan_code_fkey;

ALTER TABLE analysis_golongan_totals
    DROP CONSTRAINT IF EXISTS analysis_golongan_totals_golongan_code_check;

ALTER TABLE analysis_golongan_totals
    DROP CONSTRAINT IF EXISTS analysis_golongan_totals_golongan_code_fkey;

ALTER TABLE video_count_aggregates
    DROP CONSTRAINT IF EXISTS video_count_aggregates_vehicle_class_check;

UPDATE vehicle_events
SET
    detected_label = CASE
        WHEN vehicle_class = 'bicycle' THEN 'bicycle'
        WHEN vehicle_class = 'motorcycle' THEN 'motorcycle'
        WHEN vehicle_class = 'bus' THEN 'bus'
        WHEN vehicle_class = 'truck' THEN 'truck'
        ELSE 'car'
    END,
    vehicle_type_code = CASE
        WHEN vehicle_type_code IN (
            'motorcycle_three_wheeler',
            'passenger_car',
            'medium_passenger',
            'pickup_micro_delivery',
            'small_bus',
            'large_bus',
            'light_truck_2_axle',
            'medium_truck_2_axle',
            'truck_3_axle',
            'articulated_truck',
            'semi_trailer_truck',
            'non_motorized'
        ) THEN vehicle_type_code
        WHEN vehicle_class = 'bicycle' THEN 'non_motorized'
        WHEN vehicle_class = 'motorcycle' THEN 'motorcycle_three_wheeler'
        WHEN vehicle_class = 'bus' THEN
            CASE
                WHEN golongan_code IN ('5b', '7a', '7b', '7c', 'golongan_5')
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%large%'
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%besar%'
                THEN 'large_bus'
                ELSE 'small_bus'
            END
        WHEN vehicle_class = 'truck' THEN
            CASE
                WHEN golongan_code IN ('7c', 'golongan_5')
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%semi%'
                THEN 'semi_trailer_truck'
                WHEN golongan_code IN ('7b', 'golongan_4')
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%gandengan%'
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%articulated%'
                THEN 'articulated_truck'
                WHEN golongan_code IN ('7a', 'golongan_3')
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%3-axle%'
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%3 axle%'
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%3 sumbu%'
                THEN 'truck_3_axle'
                WHEN golongan_code IN ('6b', 'golongan_2')
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%medium 2-axle%'
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%2-axle%'
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%2 axle%'
                    OR LOWER(COALESCE(golongan_label, '')) LIKE '%2 sumbu%'
                THEN 'medium_truck_2_axle'
                ELSE 'light_truck_2_axle'
            END
        ELSE
            CASE
                WHEN LOWER(COALESCE(detected_label, '')) LIKE '%pick up%'
                    OR LOWER(COALESCE(detected_label, '')) LIKE '%pickup%'
                    OR LOWER(COALESCE(detected_label, '')) LIKE '%delivery%'
                    OR LOWER(COALESCE(detected_label, '')) LIKE '%micro truck%'
                    OR LOWER(COALESCE(detected_label, '')) LIKE '%hantaran%'
                    OR golongan_code = '4'
                THEN 'pickup_micro_delivery'
                WHEN LOWER(COALESCE(detected_label, '')) LIKE '%passenger%'
                    OR LOWER(COALESCE(detected_label, '')) LIKE '%angkutan%'
                    OR LOWER(COALESCE(detected_label, '')) LIKE '%minibus%'
                    OR LOWER(COALESCE(detected_label, '')) LIKE '%van%'
                    OR golongan_code = '3'
                THEN 'medium_passenger'
                ELSE 'passenger_car'
            END
    END;

UPDATE vehicle_events
SET
    vehicle_type_label = CASE vehicle_type_code
        WHEN 'motorcycle_three_wheeler' THEN 'motorcycle'
        WHEN 'passenger_car' THEN 'car (sedan, jeep, station wagon)'
        WHEN 'medium_passenger' THEN 'medium passenger transport'
        WHEN 'pickup_micro_delivery' THEN 'pickup / micro truck / delivery vehicle'
        WHEN 'small_bus' THEN 'small bus'
        WHEN 'large_bus' THEN 'large bus'
        WHEN 'light_truck_2_axle' THEN 'light 2-axle truck'
        WHEN 'medium_truck_2_axle' THEN 'medium 2-axle truck'
        WHEN 'truck_3_axle' THEN '3-axle truck'
        WHEN 'articulated_truck' THEN 'articulated truck'
        WHEN 'semi_trailer_truck' THEN 'semi-trailer truck'
        WHEN 'non_motorized' THEN 'non-motorized vehicle'
        ELSE vehicle_type_label
    END,
    golongan_code = CASE vehicle_type_code
        WHEN 'motorcycle_three_wheeler' THEN '1'
        WHEN 'passenger_car' THEN '2'
        WHEN 'medium_passenger' THEN '3'
        WHEN 'pickup_micro_delivery' THEN '4'
        WHEN 'small_bus' THEN '5a'
        WHEN 'large_bus' THEN '5b'
        WHEN 'light_truck_2_axle' THEN '6a'
        WHEN 'medium_truck_2_axle' THEN '6b'
        WHEN 'truck_3_axle' THEN '7a'
        WHEN 'articulated_truck' THEN '7b'
        WHEN 'semi_trailer_truck' THEN '7c'
        WHEN 'non_motorized' THEN '8'
        ELSE golongan_code
    END;

DELETE FROM master_classes;

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
    ('8', 'Non-motorized vehicle', 'Non-motorized vehicles.', 12);

UPDATE vehicle_events AS ve
SET golongan_label = mc.label
FROM master_classes AS mc
WHERE mc.code = ve.golongan_code;

DELETE FROM analysis_golongan_totals;

INSERT INTO analysis_golongan_totals (
    id,
    video_upload_id,
    analysis_job_id,
    golongan_code,
    golongan_label,
    vehicle_count,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    ve.video_upload_id,
    ve.analysis_job_id,
    ve.golongan_code,
    mc.label,
    COUNT(*)::INTEGER,
    NOW(),
    NOW()
FROM vehicle_events AS ve
JOIN master_classes AS mc
    ON mc.code = ve.golongan_code
GROUP BY
    ve.video_upload_id,
    ve.analysis_job_id,
    ve.golongan_code,
    mc.label;

ALTER TABLE master_classes
    ADD CONSTRAINT master_classes_sort_order_check
    CHECK (sort_order >= 1);

ALTER TABLE vehicle_events
    ADD CONSTRAINT vehicle_events_vehicle_class_check
    CHECK (vehicle_class IN ('bicycle', 'motorcycle', 'car', 'bus', 'truck'));

ALTER TABLE vehicle_events
    ADD CONSTRAINT vehicle_events_golongan_code_fkey
    FOREIGN KEY (golongan_code) REFERENCES master_classes(code) ON DELETE RESTRICT;

ALTER TABLE analysis_golongan_totals
    ADD CONSTRAINT analysis_golongan_totals_golongan_code_fkey
    FOREIGN KEY (golongan_code) REFERENCES master_classes(code) ON DELETE RESTRICT;

ALTER TABLE video_count_aggregates
    ADD CONSTRAINT video_count_aggregates_vehicle_class_check
    CHECK (vehicle_class IN ('bicycle', 'motorcycle', 'car', 'bus', 'truck'));

CREATE INDEX IF NOT EXISTS idx_vehicle_events_video_type
    ON vehicle_events(video_upload_id, vehicle_type_code);

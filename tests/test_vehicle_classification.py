from __future__ import annotations

import unittest

from app.constants import DEFAULT_MASTER_CLASSES, MASTER_CLASS_CODES
from app.services.analysis import _build_report_events_from_overlay_frames, _stabilize_track_detection
from app.services.vehicle_classification import (
    VEHICLE_TYPE_ARTICULATED_TRUCK,
    VEHICLE_TYPE_LARGE_BUS,
    VEHICLE_TYPE_LIGHT_TRUCK_2_AXLE,
    VEHICLE_TYPE_MEDIUM_PASSENGER,
    VEHICLE_TYPE_MEDIUM_TRUCK_2_AXLE,
    VEHICLE_TYPE_MOTORCYCLE,
    VEHICLE_TYPE_NON_MOTORIZED,
    VEHICLE_TYPE_PASSENGER_CAR,
    VEHICLE_TYPE_PICKUP_MICRO_DELIVERY,
    VEHICLE_TYPE_SEMITRAILER_TRUCK,
    VEHICLE_TYPE_SMALL_BUS,
    VEHICLE_TYPE_TRUCK_3_AXLE,
    classify_vehicle,
)


class VehicleClassificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.master_lookup = {code: payload for code, payload in DEFAULT_MASTER_CLASSES.items()}
        self.frame_width = 1920
        self.frame_height = 1080

    def classify(self, vehicle_class: str, bbox: tuple[int, int, int, int]):
        return classify_vehicle(
            vehicle_class=vehicle_class,
            source_label=vehicle_class,
            bbox=bbox,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            master_class_lookup=self.master_lookup,
        )

    def test_master_class_codes_follow_official_standard(self) -> None:
        self.assertEqual(
            MASTER_CLASS_CODES,
            ("1", "2", "3", "4", "5a", "5b", "6a", "6b", "7a", "7b", "7c", "8"),
        )
        self.assertEqual(DEFAULT_MASTER_CLASSES["1"]["label"], "Motorcycle / 3-wheel vehicle")
        self.assertEqual(DEFAULT_MASTER_CLASSES["5a"]["label"], "Small bus")
        self.assertEqual(DEFAULT_MASTER_CLASSES["7c"]["label"], "Semi-trailer truck")

    def test_motorcycle_maps_to_class_1(self) -> None:
        result = self.classify("motorcycle", (800, 700, 930, 980))
        self.assertEqual(result.vehicle_type_code, VEHICLE_TYPE_MOTORCYCLE)
        self.assertEqual(result.golongan_code, "1")

    def test_bicycle_maps_to_class_8(self) -> None:
        result = self.classify("bicycle", (500, 620, 610, 930))
        self.assertEqual(result.vehicle_type_code, VEHICLE_TYPE_NON_MOTORIZED)
        self.assertEqual(result.golongan_code, "8")

    def test_car_family_splits_into_class_2_3_and_4(self) -> None:
        passenger_car = self.classify("car", (900, 640, 1160, 880))
        medium_passenger = self.classify("car", (900, 560, 1180, 900))
        pickup_delivery = self.classify("car", (880, 620, 1260, 860))

        self.assertEqual(passenger_car.vehicle_type_code, VEHICLE_TYPE_PASSENGER_CAR)
        self.assertEqual(passenger_car.golongan_code, "2")
        self.assertEqual(medium_passenger.vehicle_type_code, VEHICLE_TYPE_MEDIUM_PASSENGER)
        self.assertEqual(medium_passenger.golongan_code, "3")
        self.assertEqual(pickup_delivery.vehicle_type_code, VEHICLE_TYPE_PICKUP_MICRO_DELIVERY)
        self.assertEqual(pickup_delivery.golongan_code, "4")

    def test_bus_family_splits_into_5a_and_5b(self) -> None:
        small_bus = self.classify("bus", (860, 560, 1220, 900))
        large_bus = self.classify("bus", (760, 480, 1350, 950))

        self.assertEqual(small_bus.vehicle_type_code, VEHICLE_TYPE_SMALL_BUS)
        self.assertEqual(small_bus.golongan_code, "5a")
        self.assertEqual(large_bus.vehicle_type_code, VEHICLE_TYPE_LARGE_BUS)
        self.assertEqual(large_bus.golongan_code, "5b")

    def test_truck_family_splits_into_6a_6b_7a_7b_and_7c(self) -> None:
        light_truck = self.classify("truck", (900, 600, 1240, 900))
        medium_truck = self.classify("truck", (860, 520, 1280, 930))
        truck_3_axle = self.classify("truck", (820, 460, 1350, 960))
        articulated = self.classify("truck", (680, 500, 1490, 930))
        semi_trailer = self.classify("truck", (520, 470, 1650, 950))

        self.assertEqual(light_truck.vehicle_type_code, VEHICLE_TYPE_LIGHT_TRUCK_2_AXLE)
        self.assertEqual(light_truck.golongan_code, "6a")
        self.assertEqual(medium_truck.vehicle_type_code, VEHICLE_TYPE_MEDIUM_TRUCK_2_AXLE)
        self.assertEqual(medium_truck.golongan_code, "6b")
        self.assertEqual(truck_3_axle.vehicle_type_code, VEHICLE_TYPE_TRUCK_3_AXLE)
        self.assertEqual(truck_3_axle.golongan_code, "7a")
        self.assertEqual(articulated.vehicle_type_code, VEHICLE_TYPE_ARTICULATED_TRUCK)
        self.assertEqual(articulated.golongan_code, "7b")
        self.assertEqual(semi_trailer.vehicle_type_code, VEHICLE_TYPE_SEMITRAILER_TRUCK)
        self.assertEqual(semi_trailer.golongan_code, "7c")

    def test_small_false_truck_can_be_recovered_to_car_family(self) -> None:
        result = self.classify("truck", (980, 690, 1170, 900))
        self.assertIn(result.vehicle_type_code, {VEHICLE_TYPE_PASSENGER_CAR, VEHICLE_TYPE_PICKUP_MICRO_DELIVERY})
        self.assertIn(result.golongan_code, {"2", "4"})

    def test_track_reference_class_preserves_large_bus_when_later_frames_flip_to_truck(self) -> None:
        track_states = {}
        first = _stabilize_track_detection(
            track_states=track_states,
            track_id=2992,
            frame_number=900,
            vehicle_class="bus",
            source_label="bus",
            confidence=0.64,
            bbox=(40, 288, 322, 655),
        )
        second = _stabilize_track_detection(
            track_states=track_states,
            track_id=2992,
            frame_number=910,
            vehicle_class="truck",
            source_label="truck",
            confidence=0.82,
            bbox=(410, 163, 566, 267),
        )

        self.assertEqual(first["reference_vehicle_class"], "bus")
        self.assertEqual(second["reference_vehicle_class"], "bus")
        self.assertEqual(second["reference_source_label"], "bus")

        result = classify_vehicle(
            vehicle_class=second["reference_vehicle_class"],
            source_label=second["reference_source_label"],
            bbox=second["reference_bbox"],
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            master_class_lookup=self.master_lookup,
        )
        self.assertEqual(result.vehicle_type_code, VEHICLE_TYPE_LARGE_BUS)
        self.assertEqual(result.golongan_code, "5b")

    def test_overlay_event_builder_recovers_large_bus_when_crossing_frames_flip_to_truck(self) -> None:
        class Line:
            def __init__(self, line_order: int, name: str, start_y: float, end_y: float) -> None:
                self.line_order = line_order
                self.name = name
                self.start_x = 0.1
                self.start_y = start_y
                self.end_x = 0.9
                self.end_y = end_y

        lines = [
            Line(1, "Line 1", 0.60, 0.60),
            Line(2, "Line 2", 0.45, 0.45),
        ]
        overlay_frames = [
            {
                "source_frame": 10,
                "time_seconds": 1.0,
                "detections": [
                    {
                        "track_id": 2992,
                        "vehicle_class": "bus",
                        "source_label": "bus",
                        "detected_label": "bus",
                        "confidence": 0.64,
                        "x1": 0.20,
                        "y1": 0.25,
                        "x2": 0.42,
                        "y2": 0.72,
                    }
                ],
            },
            {
                "source_frame": 11,
                "time_seconds": 1.2,
                "detections": [
                    {
                        "track_id": 2992,
                        "vehicle_class": "truck",
                        "source_label": "truck",
                        "detected_label": "truck",
                        "confidence": 0.81,
                        "x1": 0.24,
                        "y1": 0.31,
                        "x2": 0.39,
                        "y2": 0.55,
                    }
                ],
            },
            {
                "source_frame": 12,
                "time_seconds": 1.4,
                "detections": [
                    {
                        "track_id": 2992,
                        "vehicle_class": "truck",
                        "source_label": "truck",
                        "detected_label": "truck",
                        "confidence": 0.78,
                        "x1": 0.28,
                        "y1": 0.34,
                        "x2": 0.40,
                        "y2": 0.40,
                    }
                ],
            },
        ]

        events = _build_report_events_from_overlay_frames(
            overlay_frames,
            lines=lines,
            source_width=self.frame_width,
            source_height=self.frame_height,
            master_class_lookup=self.master_lookup,
        )

        self.assertEqual(len(events), 2)
        self.assertEqual([event["count_line_order"] for event in events], [1, 2])
        self.assertTrue(all(event["vehicle_class"] == "bus" for event in events))
        self.assertTrue(all(event["vehicle_type_code"] == VEHICLE_TYPE_LARGE_BUS for event in events))
        self.assertTrue(all(event["golongan_code"] == "5b" for event in events))


if __name__ == "__main__":
    unittest.main()

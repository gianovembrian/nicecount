from __future__ import annotations

from collections import OrderedDict


VIDEO_STATUS_UPLOADED = "uploaded"
VIDEO_STATUS_CONVERTING = "converting"
VIDEO_STATUS_PROCESSING = "processing"
VIDEO_STATUS_PROCESSED = "processed"
VIDEO_STATUS_FAILED = "failed"

JOB_STATUS_PENDING = "pending"
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_PROCESSING = "processing"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_STOPPED = "stopped"
JOB_STATUS_FAILED = "failed"

DIRECTION_NORMAL = "normal"
DIRECTION_OPPOSITE = "opposite"

VEHICLE_CLASS_MOTORCYCLE = "motorcycle"
VEHICLE_CLASS_CAR = "car"
VEHICLE_CLASS_BUS = "bus"
VEHICLE_CLASS_TRUCK = "truck"

TRACKABLE_CLASS_IDS = (2, 3, 5, 7)

COCO_CLASS_TO_VEHICLE_CLASS = {
    2: VEHICLE_CLASS_CAR,
    3: VEHICLE_CLASS_MOTORCYCLE,
    5: VEHICLE_CLASS_BUS,
    7: VEHICLE_CLASS_TRUCK,
}

GOLONGAN_I = "golongan_1"
GOLONGAN_II = "golongan_2"
GOLONGAN_III = "golongan_3"
GOLONGAN_IV = "golongan_4"
GOLONGAN_V = "golongan_5"

GOLONGAN_LABELS = OrderedDict(
    [
        (GOLONGAN_I, "Class I"),
        (GOLONGAN_II, "Class II"),
        (GOLONGAN_III, "Class III"),
        (GOLONGAN_IV, "Class IV"),
        (GOLONGAN_V, "Class V"),
    ]
)

VEHICLE_CLASS_LABELS = OrderedDict(
    [
        (VEHICLE_CLASS_MOTORCYCLE, "Motorcycle"),
        (VEHICLE_CLASS_CAR, "Car / SUV / Small Pickup"),
        (VEHICLE_CLASS_BUS, "Bus"),
        (VEHICLE_CLASS_TRUCK, "Truck"),
    ]
)

DEFAULT_MASTER_CLASSES = OrderedDict(
    [
        (
            GOLONGAN_I,
            {
                "label": "Class I",
                "description": "Sedan, jeep / SUV, small pickup, small bus, light truck, and motorcycle.",
                "sort_order": 1,
            },
        ),
        (
            GOLONGAN_II,
            {
                "label": "Class II",
                "description": "Large 2-axle trucks bigger than Class I vehicles.",
                "sort_order": 2,
            },
        ),
        (
            GOLONGAN_III,
            {
                "label": "Class III",
                "description": "Trucks with a 3-axle configuration.",
                "sort_order": 3,
            },
        ),
        (
            GOLONGAN_IV,
            {
                "label": "Class IV",
                "description": "Trucks with a 4-axle configuration.",
                "sort_order": 4,
            },
        ),
        (
            GOLONGAN_V,
            {
                "label": "Class V",
                "description": "Trucks with 5 axles or more.",
                "sort_order": 5,
            },
        ),
    ]
)

GOLONGAN_DESCRIPTIONS = {code: item["description"] for code, item in DEFAULT_MASTER_CLASSES.items()}

DETECTED_TYPE_LABELS = {
    VEHICLE_CLASS_MOTORCYCLE: "motorcycle",
    VEHICLE_CLASS_CAR: "car (sedan, jeep, suv, pick up kecil)",
    VEHICLE_CLASS_BUS: "bus",
    VEHICLE_CLASS_TRUCK: "truck",
}

DEFAULT_GLOBAL_CONFIDENCE = 0.12
DEFAULT_MOTORCYCLE_MIN_CONFIDENCE = 0.12
DEFAULT_VEHICLE_MIN_CONFIDENCE = 0.35

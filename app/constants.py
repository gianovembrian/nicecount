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

VEHICLE_CLASS_BICYCLE = "bicycle"
VEHICLE_CLASS_MOTORCYCLE = "motorcycle"
VEHICLE_CLASS_CAR = "car"
VEHICLE_CLASS_BUS = "bus"
VEHICLE_CLASS_TRUCK = "truck"

TRACKABLE_CLASS_IDS = (1, 2, 3, 5, 7)

COCO_CLASS_TO_VEHICLE_CLASS = {
    1: VEHICLE_CLASS_BICYCLE,
    2: VEHICLE_CLASS_CAR,
    3: VEHICLE_CLASS_MOTORCYCLE,
    5: VEHICLE_CLASS_BUS,
    7: VEHICLE_CLASS_TRUCK,
}

RAW_DETECTION_LABELS = OrderedDict(
    [
        (VEHICLE_CLASS_BICYCLE, "bicycle"),
        (VEHICLE_CLASS_MOTORCYCLE, "motorcycle"),
        (VEHICLE_CLASS_CAR, "car"),
        (VEHICLE_CLASS_BUS, "bus"),
        (VEHICLE_CLASS_TRUCK, "truck"),
    ]
)

VEHICLE_CLASS_LABELS = OrderedDict(
    [
        (VEHICLE_CLASS_BICYCLE, "Bicycle / non-motorized"),
        (VEHICLE_CLASS_MOTORCYCLE, "Motorcycle"),
        (VEHICLE_CLASS_CAR, "Car"),
        (VEHICLE_CLASS_BUS, "Bus"),
        (VEHICLE_CLASS_TRUCK, "Truck"),
    ]
)

GOLONGAN_1 = "1"
GOLONGAN_2 = "2"
GOLONGAN_3 = "3"
GOLONGAN_4 = "4"
GOLONGAN_5A = "5a"
GOLONGAN_5B = "5b"
GOLONGAN_6A = "6a"
GOLONGAN_6B = "6b"
GOLONGAN_7A = "7a"
GOLONGAN_7B = "7b"
GOLONGAN_7C = "7c"
GOLONGAN_8 = "8"

GOLONGAN_LABELS = OrderedDict(
    [
        (GOLONGAN_1, "Motorcycle / 3-wheel vehicle"),
        (GOLONGAN_2, "Sedan / jeep / station wagon"),
        (GOLONGAN_3, "Medium passenger vehicle"),
        (GOLONGAN_4, "Pickup / micro truck / delivery"),
        (GOLONGAN_5A, "Small bus"),
        (GOLONGAN_5B, "Large bus"),
        (GOLONGAN_6A, "Light 2-axle truck"),
        (GOLONGAN_6B, "Medium 2-axle truck"),
        (GOLONGAN_7A, "3-axle truck"),
        (GOLONGAN_7B, "Articulated truck"),
        (GOLONGAN_7C, "Semi-trailer truck"),
        (GOLONGAN_8, "Non-motorized vehicle"),
    ]
)

DEFAULT_MASTER_CLASSES = OrderedDict(
    [
        (
            GOLONGAN_1,
            {
                "label": "Motorcycle / 3-wheel vehicle",
                "description": "Motorcycles and 3-wheel motor vehicles.",
                "sort_order": 1,
            },
        ),
        (
            GOLONGAN_2,
            {
                "label": "Sedan / jeep / station wagon",
                "description": "Sedans, jeeps, and station wagons.",
                "sort_order": 2,
            },
        ),
        (
            GOLONGAN_3,
            {
                "label": "Medium passenger vehicle",
                "description": "Medium passenger transport vehicles.",
                "sort_order": 3,
            },
        ),
        (
            GOLONGAN_4,
            {
                "label": "Pickup / micro truck / delivery",
                "description": "Pickups, micro trucks, and delivery vehicles.",
                "sort_order": 4,
            },
        ),
        (
            GOLONGAN_5A,
            {
                "label": "Small bus",
                "description": "Small buses.",
                "sort_order": 5,
            },
        ),
        (
            GOLONGAN_5B,
            {
                "label": "Large bus",
                "description": "Large buses.",
                "sort_order": 6,
            },
        ),
        (
            GOLONGAN_6A,
            {
                "label": "Light 2-axle truck",
                "description": "Light 2-axle trucks.",
                "sort_order": 7,
            },
        ),
        (
            GOLONGAN_6B,
            {
                "label": "Medium 2-axle truck",
                "description": "Medium 2-axle trucks.",
                "sort_order": 8,
            },
        ),
        (
            GOLONGAN_7A,
            {
                "label": "3-axle truck",
                "description": "3-axle trucks.",
                "sort_order": 9,
            },
        ),
        (
            GOLONGAN_7B,
            {
                "label": "Articulated truck",
                "description": "Articulated trucks.",
                "sort_order": 10,
            },
        ),
        (
            GOLONGAN_7C,
            {
                "label": "Semi-trailer truck",
                "description": "Semi-trailer trucks.",
                "sort_order": 11,
            },
        ),
        (
            GOLONGAN_8,
            {
                "label": "Non-motorized vehicle",
                "description": "Non-motorized vehicles.",
                "sort_order": 12,
            },
        ),
    ]
)

MASTER_CLASS_CODES = tuple(DEFAULT_MASTER_CLASSES.keys())
GOLONGAN_DESCRIPTIONS = {code: item["description"] for code, item in DEFAULT_MASTER_CLASSES.items()}

DEFAULT_GLOBAL_CONFIDENCE = 0.12
DEFAULT_MOTORCYCLE_MIN_CONFIDENCE = 0.12
DEFAULT_CAR_MIN_CONFIDENCE = 0.22
DEFAULT_BUS_MIN_CONFIDENCE = 0.25
DEFAULT_TRUCK_MIN_CONFIDENCE = 0.28
DEFAULT_VEHICLE_MIN_CONFIDENCE = DEFAULT_CAR_MIN_CONFIDENCE
DEFAULT_IOU_THRESHOLD = 0.45
DEFAULT_FRAME_STRIDE = 1
DEFAULT_TARGET_ANALYSIS_FPS = 15.0
DEFAULT_PREVIEW_FPS = 6.0
DEFAULT_WORKING_MAX_WIDTH = 1600
DEFAULT_PREVIEW_MAX_WIDTH = 960
DEFAULT_PREVIEW_JPEG_QUALITY = 70

from __future__ import annotations

from dataclasses import dataclass

from app.constants import (
    GOLONGAN_1,
    GOLONGAN_2,
    GOLONGAN_3,
    GOLONGAN_4,
    GOLONGAN_5A,
    GOLONGAN_5B,
    GOLONGAN_6A,
    GOLONGAN_6B,
    GOLONGAN_7A,
    GOLONGAN_7B,
    GOLONGAN_7C,
    GOLONGAN_8,
    RAW_DETECTION_LABELS,
    VEHICLE_CLASS_BICYCLE,
    VEHICLE_CLASS_BUS,
    VEHICLE_CLASS_CAR,
    VEHICLE_CLASS_MOTORCYCLE,
    VEHICLE_CLASS_TRUCK,
)

VEHICLE_TYPE_MOTORCYCLE = "motorcycle_three_wheeler"
VEHICLE_TYPE_PASSENGER_CAR = "passenger_car"
VEHICLE_TYPE_MEDIUM_PASSENGER = "medium_passenger"
VEHICLE_TYPE_PICKUP_MICRO_DELIVERY = "pickup_micro_delivery"
VEHICLE_TYPE_SMALL_BUS = "small_bus"
VEHICLE_TYPE_LARGE_BUS = "large_bus"
VEHICLE_TYPE_LIGHT_TRUCK_2_AXLE = "light_truck_2_axle"
VEHICLE_TYPE_MEDIUM_TRUCK_2_AXLE = "medium_truck_2_axle"
VEHICLE_TYPE_TRUCK_3_AXLE = "truck_3_axle"
VEHICLE_TYPE_ARTICULATED_TRUCK = "articulated_truck"
VEHICLE_TYPE_SEMITRAILER_TRUCK = "semi_trailer_truck"
VEHICLE_TYPE_NON_MOTORIZED = "non_motorized"

VEHICLE_TYPE_TO_GOLONGAN = {
    VEHICLE_TYPE_MOTORCYCLE: GOLONGAN_1,
    VEHICLE_TYPE_PASSENGER_CAR: GOLONGAN_2,
    VEHICLE_TYPE_MEDIUM_PASSENGER: GOLONGAN_3,
    VEHICLE_TYPE_PICKUP_MICRO_DELIVERY: GOLONGAN_4,
    VEHICLE_TYPE_SMALL_BUS: GOLONGAN_5A,
    VEHICLE_TYPE_LARGE_BUS: GOLONGAN_5B,
    VEHICLE_TYPE_LIGHT_TRUCK_2_AXLE: GOLONGAN_6A,
    VEHICLE_TYPE_MEDIUM_TRUCK_2_AXLE: GOLONGAN_6B,
    VEHICLE_TYPE_TRUCK_3_AXLE: GOLONGAN_7A,
    VEHICLE_TYPE_ARTICULATED_TRUCK: GOLONGAN_7B,
    VEHICLE_TYPE_SEMITRAILER_TRUCK: GOLONGAN_7C,
    VEHICLE_TYPE_NON_MOTORIZED: GOLONGAN_8,
}

VEHICLE_TYPE_LABELS = {
    VEHICLE_TYPE_MOTORCYCLE: "motorcycle",
    VEHICLE_TYPE_PASSENGER_CAR: "car (sedan, jeep, station wagon)",
    VEHICLE_TYPE_MEDIUM_PASSENGER: "medium passenger transport",
    VEHICLE_TYPE_PICKUP_MICRO_DELIVERY: "pickup / micro truck / delivery vehicle",
    VEHICLE_TYPE_SMALL_BUS: "small bus",
    VEHICLE_TYPE_LARGE_BUS: "large bus",
    VEHICLE_TYPE_LIGHT_TRUCK_2_AXLE: "light 2-axle truck",
    VEHICLE_TYPE_MEDIUM_TRUCK_2_AXLE: "medium 2-axle truck",
    VEHICLE_TYPE_TRUCK_3_AXLE: "3-axle truck",
    VEHICLE_TYPE_ARTICULATED_TRUCK: "articulated truck",
    VEHICLE_TYPE_SEMITRAILER_TRUCK: "semi-trailer truck",
    VEHICLE_TYPE_NON_MOTORIZED: "non-motorized vehicle",
}


@dataclass(frozen=True)
class VehicleGeometry:
    width: float
    height: float
    area: float
    aspect_ratio: float
    width_ratio: float
    height_ratio: float
    area_ratio: float
    bottom_ratio: float
    perspective_scale: float
    normalized_width: float
    normalized_height: float
    normalized_area: float


@dataclass(frozen=True)
class VehicleClassificationResult:
    raw_detected_label: str
    vehicle_type_code: str
    vehicle_type_label: str
    golongan_code: str
    golongan_label: str


def normalize_raw_detected_label(vehicle_class: str, source_label: str | None = None) -> str:
    normalized_source = str(source_label or "").strip().lower()
    if normalized_source:
        return normalized_source
    return RAW_DETECTION_LABELS.get(str(vehicle_class or "").strip().lower(), str(vehicle_class or "").strip().lower() or "-")


def classify_vehicle(
    *,
    vehicle_class: str,
    source_label: str | None,
    bbox: tuple[float, float, float, float],
    frame_width: int,
    frame_height: int,
    master_class_lookup: dict[str, dict],
) -> VehicleClassificationResult:
    raw_detected_label = normalize_raw_detected_label(vehicle_class, source_label)
    geometry = _build_geometry(
        bbox=bbox,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    vehicle_type_code = _classify_vehicle_type(vehicle_class=vehicle_class, geometry=geometry)
    golongan_code = VEHICLE_TYPE_TO_GOLONGAN[vehicle_type_code]
    golongan_payload = master_class_lookup.get(golongan_code) or {}
    return VehicleClassificationResult(
        raw_detected_label=raw_detected_label,
        vehicle_type_code=vehicle_type_code,
        vehicle_type_label=VEHICLE_TYPE_LABELS[vehicle_type_code],
        golongan_code=golongan_code,
        golongan_label=str(golongan_payload.get("label") or golongan_code),
    )


def _build_geometry(
    *,
    bbox: tuple[float, float, float, float],
    frame_width: int,
    frame_height: int,
) -> VehicleGeometry:
    x1, y1, x2, y2 = bbox
    width = max(float(x2) - float(x1), 1.0)
    height = max(float(y2) - float(y1), 1.0)
    area = width * height
    safe_frame_width = max(float(frame_width), 1.0)
    safe_frame_height = max(float(frame_height), 1.0)
    width_ratio = width / safe_frame_width
    height_ratio = height / safe_frame_height
    area_ratio = area / max(safe_frame_width * safe_frame_height, 1.0)
    bottom_ratio = min(max(float(y2) / safe_frame_height, 0.0), 1.0)
    aspect_ratio = width / max(height, 1.0)

    # Compensate partially for perspective so far-away vehicles are not always pushed to tiny classes.
    perspective_scale = max(0.35, 0.35 + (bottom_ratio * 0.65))
    normalized_width = width_ratio / perspective_scale
    normalized_height = height_ratio / perspective_scale
    normalized_area = area_ratio / max(perspective_scale * perspective_scale, 1e-6)

    return VehicleGeometry(
        width=width,
        height=height,
        area=area,
        aspect_ratio=aspect_ratio,
        width_ratio=width_ratio,
        height_ratio=height_ratio,
        area_ratio=area_ratio,
        bottom_ratio=bottom_ratio,
        perspective_scale=perspective_scale,
        normalized_width=normalized_width,
        normalized_height=normalized_height,
        normalized_area=normalized_area,
    )


def _classify_vehicle_type(*, vehicle_class: str, geometry: VehicleGeometry) -> str:
    normalized_class = str(vehicle_class or "").strip().lower()

    if normalized_class == VEHICLE_CLASS_BICYCLE:
        return VEHICLE_TYPE_NON_MOTORIZED

    if normalized_class == VEHICLE_CLASS_MOTORCYCLE:
        return VEHICLE_TYPE_MOTORCYCLE

    if normalized_class == VEHICLE_CLASS_CAR:
        return _classify_car_like(geometry)

    if normalized_class == VEHICLE_CLASS_BUS:
        return _classify_bus_like(geometry)

    if normalized_class == VEHICLE_CLASS_TRUCK:
        return _classify_truck_like(geometry)

    return VEHICLE_TYPE_PASSENGER_CAR


def _classify_car_like(geometry: VehicleGeometry) -> str:
    if geometry.normalized_width >= 0.21 or geometry.aspect_ratio >= 1.45:
        return VEHICLE_TYPE_PICKUP_MICRO_DELIVERY

    if geometry.normalized_height >= 0.32 or geometry.aspect_ratio <= 0.95:
        return VEHICLE_TYPE_MEDIUM_PASSENGER

    return VEHICLE_TYPE_PASSENGER_CAR


def _classify_bus_like(geometry: VehicleGeometry) -> str:
    if geometry.normalized_height < 0.14 and geometry.normalized_area < 0.010:
        return VEHICLE_TYPE_MEDIUM_PASSENGER

    if (
        geometry.normalized_height >= 0.43
        or geometry.normalized_width >= 0.30
        or geometry.normalized_area >= 0.12
    ):
        return VEHICLE_TYPE_LARGE_BUS

    return VEHICLE_TYPE_SMALL_BUS


def _classify_truck_like(geometry: VehicleGeometry) -> str:
    # Recover common false-positive SUVs / MPVs that the detector tagged as trucks.
    if (
        geometry.normalized_height < 0.28
        and geometry.normalized_width < 0.18
        and geometry.normalized_area < 0.045
        and geometry.aspect_ratio < 1.9
    ):
        if geometry.aspect_ratio >= 1.45 or geometry.normalized_width >= 0.15:
            return VEHICLE_TYPE_PICKUP_MICRO_DELIVERY
        return VEHICLE_TYPE_PASSENGER_CAR

    if geometry.aspect_ratio >= 2.2 or geometry.normalized_width >= 0.55 or geometry.normalized_area >= 0.27:
        return VEHICLE_TYPE_SEMITRAILER_TRUCK

    if geometry.aspect_ratio >= 1.55 or geometry.normalized_width >= 0.40 or geometry.normalized_area >= 0.18:
        return VEHICLE_TYPE_ARTICULATED_TRUCK

    if geometry.normalized_height >= 0.47 or geometry.normalized_width >= 0.28 or geometry.normalized_area >= 0.13:
        return VEHICLE_TYPE_TRUCK_3_AXLE

    if geometry.normalized_height >= 0.38 or geometry.normalized_width >= 0.23 or geometry.normalized_area >= 0.09:
        return VEHICLE_TYPE_MEDIUM_TRUCK_2_AXLE

    return VEHICLE_TYPE_LIGHT_TRUCK_2_AXLE

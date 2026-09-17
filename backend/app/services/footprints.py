"""
Building footprint service (OpenStreetMap via Overpass).

Fetches the real building outline at a location so we can clip the SAM
roof mask to the actual building boundary — stopping segmentation from
bleeding onto a neighbour, road, or courtyard.

Free, keyless. Coverage varies: well-mapped areas return good polygons;
unmapped buildings return nothing, in which case clipping is skipped and
the raw mask is used unchanged (this feature can only ever help).
"""

import math
from dataclasses import dataclass

import cv2
import httpx
import numpy as np

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Same Web Mercator constant used in geometry.py.
EQUATOR_METERS_PER_PIXEL_AT_ZOOM_0 = 156543.03392


@dataclass
class Footprint:
    # Polygon as (lat, lng) vertices of the building containing/nearest the point.
    latlng: list[tuple[float, float]]


def _point_in_polygon(lat: float, lng: float, poly: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test (poly = list of (lat, lng))."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if ((xi > lng) != (xj > lng)) and (
            lat < (yj - yi) * (lng - xi) / (xj - xi + 1e-12) + yi
        ):
            inside = not inside
        j = i
    return inside


def fetch_building_footprint(
    lat: float, lng: float, radius_m: int = 60
) -> Footprint | None:
    """
    Return the building footprint at (lat, lng): the polygon that CONTAINS
    the point if one exists, else the nearest building within radius_m.
    Returns None if nothing is found or the query fails (safe fallback).
    """
    query = (
        "[out:json][timeout:25];"
        f'(way["building"](around:{radius_m},{lat},{lng}););'
        "out geom;"
    )
    try:
        r = httpx.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": "PV-Yield/0.1 (rooftop solar tool)"},
            timeout=40.0,
        )
    except httpx.RequestError:
        return None
    if r.status_code != 200:
        return None

    elements = r.json().get("elements", [])
    polygons: list[list[tuple[float, float]]] = []
    for e in elements:
        geom = e.get("geometry")
        if not geom or len(geom) < 3:
            continue
        polygons.append([(p["lat"], p["lon"]) for p in geom])

    if not polygons:
        return None

    # Prefer the polygon that actually contains the geocoded point.
    for poly in polygons:
        if _point_in_polygon(lat, lng, poly):
            return Footprint(latlng=poly)

    # Otherwise, nearest by centroid distance.
    def centroid_dist(poly: list[tuple[float, float]]) -> float:
        clat = sum(p[0] for p in poly) / len(poly)
        clng = sum(p[1] for p in poly) / len(poly)
        return (clat - lat) ** 2 + (clng - lng) ** 2

    polygons.sort(key=centroid_dist)
    return Footprint(latlng=polygons[0])


def footprint_to_pixels(
    footprint: Footprint,
    center_lat: float,
    center_lng: float,
    zoom: int,
    scale: int,
    image_size_px: int,
) -> list[tuple[int, int]]:
    """
    Convert a lat/lng footprint into image PIXEL coordinates.

    The satellite image is centered on (center_lat, center_lng) at a known
    zoom/scale. We use the Web Mercator projection to turn each geo vertex
    into a pixel offset from the image center.
    """
    m_per_px = (
        EQUATOR_METERS_PER_PIXEL_AT_ZOOM_0
        * math.cos(math.radians(center_lat))
        / (2 ** zoom * scale)
    )
    # Meters per degree at this latitude.
    m_per_deg_lat = 111_320.0
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(center_lat))
    cx = cy = image_size_px / 2.0

    pts: list[tuple[int, int]] = []
    for plat, plng in footprint.latlng:
        # meters east/north of center
        east_m = (plng - center_lng) * m_per_deg_lng
        north_m = (plat - center_lat) * m_per_deg_lat
        # pixels: +east = +x, +north = -y (image y grows downward)
        px = cx + east_m / m_per_px
        py = cy - north_m / m_per_px
        pts.append((int(round(px)), int(round(py))))
    return pts


def estimate_azimuth_from_footprint(footprint_px: list[tuple[int, int]]) -> float:
    """
    Estimate the panel azimuth (degrees, 180 = due south) from the
    building's footprint orientation.

    Panels on a roof are laid out aligned to the roof edges. We find the
    footprint's minimum-area bounding rectangle, take its orientation, and
    return whichever roof-aligned facing is CLOSEST TO SOUTH (best for the
    northern hemisphere). This is a genuine, data-driven azimuth estimate
    from 2D geometry (unlike tilt, which needs 3D data we don't have).

    In image space: +x = east, +y = south (y grows downward). A rectangle
    edge at angle `theta` from the x-axis has two outward normals; we pick
    the one nearest due south.
    """
    pts = np.array(footprint_px, dtype=np.float32)
    if len(pts) < 3:
        return 180.0

    # minAreaRect returns ((cx, cy), (w, h), angle_degrees).
    (_, _), (rw, rh), angle = cv2.minAreaRect(pts)

    # The rectangle's two edge directions are `angle` and `angle + 90`.
    # Panels face perpendicular to the longer edge (across the roof slope),
    # but for a flat-roof frame layout, either facing is possible — so we
    # consider all four normal directions and choose the one closest to
    # south (compass 180).
    #
    # Convert an image-space direction angle to a compass azimuth where
    # 0 = north, 90 = east, 180 = south, 270 = west.
    def image_angle_to_compass(deg: float) -> float:
        # image +x is east (compass 90), +y is south (compass 180).
        # a vector at image angle `deg` (from +x, clockwise since y is down)
        # points to compass = 90 + deg.
        return (90.0 + deg) % 360.0

    candidates = [
        image_angle_to_compass(angle),
        image_angle_to_compass(angle + 90),
        image_angle_to_compass(angle + 180),
        image_angle_to_compass(angle + 270),
    ]

    # Pick the candidate whose angular distance to south (180) is smallest.
    def dist_to_south(a: float) -> float:
        d = abs(a - 180.0) % 360.0
        return min(d, 360.0 - d)

    best = min(candidates, key=dist_to_south)
    return round(best, 1)

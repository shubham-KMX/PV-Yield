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

import httpx

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

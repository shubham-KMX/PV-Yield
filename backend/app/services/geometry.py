"""
Web Mercator ground-geometry helpers.

Google's satellite tiles use the Web Mercator projection. At a given
zoom level, one pixel maps to a KNOWN real-world distance on the ground.
That's what lets us later turn a roof's pixel count into actual square
meters — deterministic geometry, no guessing.

Everything here is pure math (no I/O, no network), so it's trivial to
unit-test and reason about.
"""

import math

# Ground distance covered by one pixel at the equator, zoom 0, scale 1.
# This is the standard Web Mercator constant: the Earth's circumference
# (~40,075 km) divided by the 256-pixel base tile.
EQUATOR_METERS_PER_PIXEL_AT_ZOOM_0 = 156543.03392


def meters_per_pixel(lat: float, zoom: int, scale: int = 1) -> float:
    """
    Real-world meters represented by one image pixel.

    Formula:
        156543.03392 * cos(latitude) / (2^zoom * scale)

    - Each zoom level halves the ground distance per pixel (2^zoom).
    - `scale=2` doubles pixel density, so it halves m/pixel again.
    - cos(latitude) corrects for Mercator stretching distances as you
      move away from the equator (at the poles, cos -> 0).

    Example: at lat 37.42, zoom 21, scale 2 -> ~0.0074 m/pixel
    (about 7.4 mm on the ground per pixel).
    """
    return (
        EQUATOR_METERS_PER_PIXEL_AT_ZOOM_0
        * math.cos(math.radians(lat))
        / (2 ** zoom * scale)
    )


def pixels_to_area(pixel_count: int, lat: float, zoom: int, scale: int = 1) -> dict:
    """
    Convert a pixel count (e.g. a roof mask's area) into ground area.

    Returns both square meters and square feet. Area scales with the
    SQUARE of meters-per-pixel, because each pixel is a little square of
    side `m_per_px`.
    """
    m_per_px = meters_per_pixel(lat, zoom, scale)
    area_m2 = pixel_count * (m_per_px ** 2)
    area_sqft = area_m2 * 10.7639  # 1 m^2 = 10.7639 ft^2
    return {
        "area_m2": area_m2,
        "area_sqft": area_sqft,
        "m_per_pixel": m_per_px,
    }

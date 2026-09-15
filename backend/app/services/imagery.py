"""
Satellite imagery service.

Given coordinates, return the overhead satellite image plus the geometry
(meters-per-pixel) needed to measure things in it later.

Like the geocoding service, this is UI-agnostic and has a mock path:
  - live:  call Google Static Maps for real image bytes
  - mock:  load a real saved sample image from sample_data/images/

Both paths return the same SatelliteImage dataclass, so nothing
downstream can tell which mode produced it.
"""

from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import get_settings
from app.services.geometry import meters_per_pixel

# Folder holding the saved sample images (used in mock mode).
# __file__ is .../app/services/imagery.py, so parents[2] is the backend/ root.
SAMPLE_IMAGE_DIR = Path(__file__).resolve().parents[2] / "sample_data" / "images"


@dataclass
class SatelliteImage:
    """The result of fetching imagery: the bytes plus everything we need
    to interpret them geometrically."""
    image_bytes: bytes
    lat: float
    lng: float
    zoom: int
    scale: int
    m_per_pixel: float
    source: str  # "google" or "mock" — handy for debugging/UI


class ImageryError(Exception):
    """Raised when imagery cannot be fetched (network, denied, missing sample)."""

    def __init__(self, message: str, code: str = "imagery_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def _nearest_sample_image(lat: float, lng: float) -> Path | None:
    """
    Pick the saved sample image whose baked-in coordinates are closest to
    the requested lat/lng.

    Sample filenames end in "..._<lat>_<lng>.png". We parse those two
    trailing numbers and return whichever file is nearest. This way mock
    imagery still "follows" the location instead of always returning the
    same picture.
    """
    if not SAMPLE_IMAGE_DIR.exists():
        return None

    best_path: Path | None = None
    best_dist = float("inf")
    for path in SAMPLE_IMAGE_DIR.glob("*.png"):
        parts = path.stem.split("_")
        try:
            # last two underscore-separated tokens are lat and lng
            file_lat = float(parts[-2])
            file_lng = float(parts[-1])
        except (ValueError, IndexError):
            continue
        dist = (file_lat - lat) ** 2 + (file_lng - lng) ** 2
        if dist < best_dist:
            best_dist = dist
            best_path = path
    return best_path


def fetch_satellite_image(
    lat: float,
    lng: float,
    zoom: int | None = None,
    scale: int | None = None,
) -> SatelliteImage:
    """
    Fetch the satellite image for a location.

    In mock mode, returns the nearest saved sample image. In live mode,
    calls the Google Static Maps API. Either way, the returned object
    carries the correct meters-per-pixel for the coordinates so area
    measurement downstream is accurate.
    """
    settings = get_settings()
    zoom = zoom if zoom is not None else settings.default_zoom
    scale = scale if scale is not None else settings.default_scale

    m_per_px = meters_per_pixel(lat, zoom, scale)

    # --- mock path: load a real saved image -----------------------------
    if settings.use_mock_imagery:
        sample = _nearest_sample_image(lat, lng)
        if sample is None:
            raise ImageryError(
                "No sample images available for mock imagery.",
                code="no_sample",
            )
        return SatelliteImage(
            image_bytes=sample.read_bytes(),
            lat=lat,
            lng=lng,
            zoom=zoom,
            scale=scale,
            m_per_pixel=m_per_px,
            source="mock",
        )

    # --- live path: call Google Static Maps -----------------------------
    size = settings.default_image_size
    params = {
        "center": f"{lat},{lng}",
        "zoom": zoom,
        "size": f"{size}x{size}",
        "scale": scale,
        "maptype": "satellite",
        "key": settings.google_maps_api_key,
    }
    try:
        response = httpx.get(settings.staticmap_base_url, params=params, timeout=15.0)
    except httpx.RequestError as exc:
        raise ImageryError(
            f"Could not reach the imagery service: {exc}",
            code="network_error",
        ) from exc

    if response.status_code != 200:
        # Google returns a small error image or text on failure; surface it.
        raise ImageryError(
            f"Imagery service returned HTTP {response.status_code}: "
            f"{response.text[:200]}",
            code="http_error",
        )

    # A valid satellite PNG has the PNG magic bytes; guard against Google
    # handing back an HTML/text error with a 200 status.
    content = response.content
    if not content.startswith(b"\x89PNG"):
        raise ImageryError(
            "Imagery service did not return a PNG image.",
            code="bad_image",
        )

    return SatelliteImage(
        image_bytes=content,
        lat=lat,
        lng=lng,
        zoom=zoom,
        scale=scale,
        m_per_pixel=m_per_px,
        source="google",
    )

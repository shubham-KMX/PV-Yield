"""
Geocoding service — turns a human address into coordinates.

This talks to the Google Geocoding API. It is deliberately UI-agnostic:
it knows nothing about FastAPI or HTTP responses. It just takes an
address string and returns a result (or raises a clear error). The
endpoint layer decides how to present that over HTTP.

Design pattern used here (reused for every external service):
  - A dataclass for the successful result (typed, predictable).
  - A custom exception (GeocodingError) for the many ways Google can fail.
  - One public function: geocode_address(address).
"""

from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.services.mock_data import mock_lookup


@dataclass
class GeocodeResult:
    """The clean, typed result we hand back on success."""
    lat: float
    lng: float
    formatted_address: str


class GeocodingError(Exception):
    """
    Raised when geocoding fails for any reason.

    Carrying a human-readable `message` (and an optional machine `code`)
    lets the endpoint translate this into a helpful HTTP response.
    """

    def __init__(self, message: str, code: str = "geocoding_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def geocode_address(address: str) -> GeocodeResult:
    """
    Convert an address into coordinates using the Google Geocoding API.

    Raises GeocodingError on any failure (empty input, network problem,
    denied key, quota exceeded, or address not found). Returns a
    GeocodeResult on success.
    """
    # Guard against empty/whitespace input before wasting an API call.
    address = (address or "").strip()
    if not address:
        raise GeocodingError("Address must not be empty.", code="empty_address")

    settings = get_settings()

    # --- mock mode: skip Google entirely (used before billing is Active).
    # Same return type as the live path, so nothing downstream can tell
    # the difference. Flip settings.use_mock_geocoding to False for live.
    if settings.use_mock_geocoding:
        data = mock_lookup(address)
        return GeocodeResult(
            lat=data["lat"],
            lng=data["lng"],
            formatted_address=data["formatted_address"],
        )

    # Query parameters Google expects. httpx URL-encodes these for us,
    # so spaces and special characters in the address are handled safely.
    params = {"address": address, "key": settings.google_maps_api_key}

    # --- make the HTTP call, translating network failures ---------------
    try:
        # timeout prevents the request from hanging forever if Google
        # is slow or unreachable.
        response = httpx.get(settings.geocoding_base_url, params=params, timeout=10.0)
    except httpx.RequestError as exc:
        # Covers DNS failures, connection refused, timeouts, etc.
        raise GeocodingError(
            f"Could not reach the geocoding service: {exc}",
            code="network_error",
        ) from exc

    # A non-2xx HTTP status (e.g. 500 from Google) is also a failure.
    if response.status_code != 200:
        raise GeocodingError(
            f"Geocoding service returned HTTP {response.status_code}.",
            code="http_error",
        )

    payload = response.json()
    status = payload.get("status")

    # --- interpret Google's own status field ----------------------------
    # Google returns HTTP 200 even for logical failures; the real outcome
    # is in payload["status"]. We translate each case into a clear message.
    if status == "ZERO_RESULTS":
        raise GeocodingError(
            f"No location found for address: {address!r}.",
            code="not_found",
        )
    if status == "OVER_QUERY_LIMIT":
        raise GeocodingError(
            "Geocoding quota exceeded. Try again later.",
            code="quota_exceeded",
        )
    if status == "REQUEST_DENIED":
        # Usually a bad/restricted API key or the API not enabled.
        raise GeocodingError(
            "Geocoding request denied. Check the API key and that the "
            "Geocoding API is enabled.",
            code="request_denied",
        )
    if status != "OK":
        # Any other status (INVALID_REQUEST, UNKNOWN_ERROR, ...).
        raise GeocodingError(
            f"Geocoding failed with status: {status}.",
            code="unknown_status",
        )

    # --- success: pull the first (best) result --------------------------
    results = payload.get("results", [])
    if not results:
        raise GeocodingError(
            f"No results returned for address: {address!r}.",
            code="not_found",
        )

    best = results[0]
    location = best["geometry"]["location"]
    return GeocodeResult(
        lat=float(location["lat"]),
        lng=float(location["lng"]),
        formatted_address=best.get("formatted_address", address),
    )

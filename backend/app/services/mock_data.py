"""
Mock data for offline / pre-billing development.

While the Google billing account isn't Active, services fall back to
these realistic canned values so we can build and test the full
pipeline without live API calls. Coordinates here are real, so anything
downstream (weather, sun position, etc.) still behaves sensibly.

When live billing is ready, set USE_MOCK_GEOCODING=false and these are
never touched.
"""

# A few known addresses -> real coordinates. Keys are lowercased so we
# can match case-insensitively. If an address isn't in this table, the
# mock geocoder falls back to DEFAULT_LOCATION.
MOCK_GEOCODE_TABLE: dict[str, dict] = {
    "mountain view": {
        "lat": 37.4220095,
        "lng": -122.0847514,
        "formatted_address": "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
    },
    "cupertino": {
        "lat": 37.3287379,
        "lng": -122.0078912,
        "formatted_address": "1 Apple Park Way, Cupertino, CA 95014, USA",
    },
    "sarita vihar": {
        "lat": 28.5323,
        "lng": 77.2884,
        "formatted_address": "Sarita Vihar, New Delhi, Delhi 110076, India",
    },
    "delhi": {
        "lat": 28.6139,
        "lng": 77.2090,
        "formatted_address": "New Delhi, Delhi, India",
    },
    "mumbai": {
        "lat": 19.0760,
        "lng": 72.8777,
        "formatted_address": "Mumbai, Maharashtra, India",
    },
}

# Used when an address doesn't match anything in the table above.
DEFAULT_LOCATION: dict = {
    "lat": 28.5323,
    "lng": 77.2884,
    "formatted_address": "Sarita Vihar, New Delhi, Delhi 110076, India (mock default)",
}


def mock_lookup(address: str) -> dict:
    """
    Return canned coordinates for an address.

    Matches if any table key appears as a substring of the (lowercased)
    address, so "E-87, Sarita Vihar, Delhi" matches the "sarita vihar"
    entry. Falls back to DEFAULT_LOCATION when nothing matches.
    """
    key = (address or "").lower()
    for name, data in MOCK_GEOCODE_TABLE.items():
        if name in key:
            return data
    return DEFAULT_LOCATION

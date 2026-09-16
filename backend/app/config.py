"""
Application configuration.

We use pydantic-settings, which reads values from environment variables
and from a local `.env` file, then validates them into a typed object.

Why this instead of os.getenv() scattered around the code?
  - One single source of truth for all config.
  - Type validation: the key is guaranteed to be a string when present.
  - Fails loudly and early if something required is missing.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All app configuration lives here as typed fields.

    Each field name maps to an environment variable of the SAME name.
    So `google_maps_api_key` is populated from GOOGLE_MAPS_API_KEY
    (pydantic-settings is case-insensitive about this).
    """

    # The one secret we need so far. It has no default, so if it's missing
    # from both the environment and .env, pydantic raises a clear error.
    google_maps_api_key: str

    # Base URLs for the Google APIs. Kept here (not hardcoded in the
    # service) so they're easy to find and change in one place.
    geocoding_base_url: str = "https://maps.googleapis.com/maps/api/geocode/json"
    staticmap_base_url: str = "https://maps.googleapis.com/maps/api/staticmap"

    # --- satellite imagery defaults ------------------------------------
    # zoom 21 is the practical sweet spot for rooftops; scale 2 doubles
    # pixel density (1280x1280) for a sharper mask later.
    default_zoom: int = 21
    default_scale: int = 2
    default_image_size: int = 640  # per-side pixels before scale multiplier

    # --- NASA POWER weather --------------------------------------------
    # Free hourly solar/weather reanalysis, no API key required.
    nasa_power_base_url: str = "https://power.larc.nasa.gov/api/temporal/hourly/point"
    # Which year of weather to pull. A recent complete year, not a true TMY.
    default_weather_year: int = 2023

    # --- development toggles -------------------------------------------
    # When True, services return realistic canned data instead of calling
    # the external APIs. Lets us build/test the whole pipeline offline.
    # Flip to False (or set USE_MOCK_*=false in .env) for live data.
    # NASA POWER is free (no key), so mock weather defaults OFF.
    use_mock_geocoding: bool = True
    use_mock_imagery: bool = True
    use_mock_weather: bool = False

    # --- CORS ----------------------------------------------------------
    # Comma-separated list of allowed frontend origins. Defaults to local
    # dev; in production set CORS_ORIGINS to your Vercel URL, e.g.
    #   CORS_ORIGINS=https://pv-yield.vercel.app
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Tells pydantic-settings to load from a .env file in the current
    # working directory (we run the server from the backend/ folder).
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore any unrelated env vars instead of erroring
    )


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    @lru_cache means Settings() is constructed only once, then the same
    object is reused for every call. So we read/parse the .env a single
    time, not on every request. FastAPI endpoints will depend on this.
    """
    return Settings()

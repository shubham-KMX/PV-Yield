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

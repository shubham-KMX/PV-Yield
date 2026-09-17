"""
Weather service — hourly solar irradiance + temperature from NASA POWER.

To simulate a year of solar generation we need, for every hour:
  - GHI  global horizontal irradiance  (total sun on a flat surface, W/m^2)
  - DNI  direct normal irradiance      (the direct beam from the sun)
  - DHI  diffuse horizontal irradiance (scattered sky light)
  - temp_air (deg C) and wind_speed (m/s) — panels lose efficiency when hot,
    wind cools them.

NASA POWER provides all of this globally, for free, with NO API key. The
data is ~55 km resolution reanalysis — coarse, but fine for pre-feasibility.

Design mirrors the other services: a clean return (a pandas DataFrame),
a custom exception, one public function, plus disk caching and a mock path.
"""

import hashlib
import json
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from app.config import get_settings

# NASA POWER parameter codes -> our friendly column names.
NASA_PARAMS = {
    "ALLSKY_SFC_SW_DWN": "ghi",
    "ALLSKY_SFC_SW_DNI": "dni",
    "ALLSKY_SFC_SW_DIFF": "dhi",
    "T2M": "temp_air",
    "WS10M": "wind_speed",
}

# NASA uses this sentinel for missing values.
NASA_FILL_VALUE = -999.0

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "weather"


class WeatherError(Exception):
    """Raised when weather data can't be fetched or parsed."""

    def __init__(self, message: str, code: str = "weather_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def _cache_path(lat: float, lng: float, year: int) -> Path:
    """A stable cache filename for a rounded location + year."""
    key = f"{round(lat, 3)}_{round(lng, 3)}_{year}"
    digest = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"nasa_{year}_{digest}.json"


def _parse_payload(payload: dict) -> pd.DataFrame:
    """
    Turn NASA POWER's JSON into a tidy, tz-aware hourly DataFrame.

    NASA nests the data under properties.parameter.<CODE>.<timestamp>,
    where timestamp is "YYYYMMDDHH". We pivot that into columns.
    """
    try:
        params = payload["properties"]["parameter"]
    except (KeyError, TypeError) as exc:
        raise WeatherError("Unexpected NASA POWER response shape.", code="bad_response") from exc

    # Build one Series per parameter, keyed by the timestamp strings.
    series = {}
    for code, name in NASA_PARAMS.items():
        if code not in params:
            raise WeatherError(f"NASA POWER response missing '{code}'.", code="missing_param")
        series[name] = pd.Series(params[code])

    df = pd.DataFrame(series)

    # Index is "YYYYMMDDHH" strings -> parse to UTC-aware timestamps.
    df.index = pd.to_datetime(df.index, format="%Y%m%d%H", utc=True)
    df.sort_index(inplace=True)

    # Replace NASA's -999 fill with NaN, then drop rows we can't use.
    df.replace(NASA_FILL_VALUE, np.nan, inplace=True)
    df.dropna(subset=["ghi", "temp_air"], inplace=True)

    # Irradiance can't be negative; clip tiny negatives from the model.
    for col in ("ghi", "dni", "dhi"):
        df[col] = df[col].clip(lower=0)

    return df


def fetch_hourly_weather(
    lat: float,
    lng: float,
    year: int | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Return a year of hourly weather for a location as a pandas DataFrame
    with columns [ghi, dni, dhi, temp_air, wind_speed], indexed by
    tz-aware UTC timestamps (~8760 rows).

    Cached to disk per (lat, lng, year). In mock mode, returns a
    synthetic-but-realistic year so the pipeline runs offline.
    """
    settings = get_settings()
    year = year if year is not None else settings.default_weather_year

    if settings.use_mock_weather:
        return _mock_weather(lat, lng, year)

    # PVGIS TMY is the default source — free, keyless, and more accurate
    # for India than NASA POWER's single year.
    if settings.weather_source == "pvgis":
        return _fetch_pvgis_tmy(lat, lng)

    # --- disk cache ------------------------------------------------------
    cache_file = _cache_path(lat, lng, year)
    if use_cache and cache_file.exists():
        payload = json.loads(cache_file.read_text())
        return _parse_payload(payload)

    # --- live NASA POWER call -------------------------------------------
    params = {
        "parameters": ",".join(NASA_PARAMS.keys()),
        "community": "RE",  # Renewable Energy community
        "longitude": lng,
        "latitude": lat,
        "start": f"{year}0101",
        "end": f"{year}1231",
        "format": "JSON",
        # Force UTC timestamps so they align with pvlib's sun-position
        # calc. Without this NASA returns Local Solar Time, which puts
        # "noon" hours in the wrong place and tanks the simulated yield.
        "time-standard": "UTC",
    }
    try:
        response = httpx.get(settings.nasa_power_base_url, params=params, timeout=60.0)
    except httpx.RequestError as exc:
        raise WeatherError(f"Could not reach NASA POWER: {exc}", code="network_error") from exc

    if response.status_code != 200:
        raise WeatherError(
            f"NASA POWER returned HTTP {response.status_code}.", code="http_error"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise WeatherError("NASA POWER returned invalid JSON.", code="bad_response") from exc

    df = _parse_payload(payload)

    # Cache the raw payload for next time.
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload))

    return df


def _fetch_pvgis_tmy(lat: float, lng: float) -> pd.DataFrame:
    """
    Fetch a Typical Meteorological Year (TMY) from EU JRC PVGIS via pvlib.

    TMY = one representative year assembled from ~15 years (2005-2020) of
    data, so it's more stable than a single calendar year and, for India,
    reads noticeably closer to reality than NASA POWER.

    pvlib does the HTTP call, parsing, and column naming for us
    (map_variables=True -> ghi/dni/dhi/temp_air/wind_speed). We just
    normalize the index to tz-aware UTC to match the rest of the pipeline.
    """
    from pvlib.iotools import get_pvgis_tmy

    try:
        df, _months, _inputs, _meta = get_pvgis_tmy(
            latitude=lat, longitude=lng, map_variables=True, timeout=60
        )
    except Exception as exc:  # pvlib wraps network/HTTP errors variously
        raise WeatherError(f"Could not reach PVGIS: {exc}", code="network_error") from exc

    # Keep only the columns our simulation uses.
    keep = ["ghi", "dni", "dhi", "temp_air", "wind_speed"]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise WeatherError(f"PVGIS response missing {missing}.", code="missing_param")
    df = df[keep].copy()

    # TMY timestamps come from mixed source years; normalize to a single
    # non-leap year and make them tz-aware UTC so sun-position aligns.
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    df.index = idx

    for col in ("ghi", "dni", "dhi"):
        df[col] = df[col].clip(lower=0)

    return df


def _mock_weather(lat: float, lng: float, year: int) -> pd.DataFrame:
    """
    Generate a synthetic but plausible year of hourly weather for offline
    development. A simple daily sine for irradiance (zero at night, peak at
    solar noon) and a mild seasonal/daily temperature swing.
    """
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h", tz="UTC")
    hours = idx.hour.to_numpy()
    doy = idx.dayofyear.to_numpy()

    # Daytime bell curve peaking at ~13:00 local-ish, zero at night.
    daylight = np.clip(np.sin((hours - 6) / 12 * np.pi), 0, None)
    seasonal = 0.75 + 0.25 * np.cos((doy - 172) / 365 * 2 * np.pi)  # summer peak
    ghi = 950 * daylight * seasonal
    dni = 0.85 * ghi
    dhi = 0.15 * ghi
    temp = 25 + 8 * np.cos((doy - 200) / 365 * 2 * np.pi) + 5 * (daylight - 0.5)
    wind = np.full(len(idx), 2.0)

    return pd.DataFrame(
        {"ghi": ghi, "dni": dni, "dhi": dhi, "temp_air": temp, "wind_speed": wind},
        index=idx,
    )

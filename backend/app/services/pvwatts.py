"""
PVWatts v5 solar generation simulation.

Turns a year of hourly weather + a system size into annual/monthly
electricity generation (kWh), following NREL's PVWatts methodology via
the pvlib library.

Per-hour chain (what pvlib does for us):
    sun position  ->  transpose GHI/DNI/DHI onto the tilted panel (POA)
    ->  cell temperature (panels lose efficiency when hot)
    ->  DC power (scaled by system size, temperature-derated)
    ->  apply the named loss stack (soiling, wiring, mismatch, ...)
    ->  DC -> AC through the inverter
    ->  sum over 8760 hours = annual kWh

This is the "solar engineering" heart of the project.
"""

from dataclasses import dataclass

import pandas as pd
from pvlib import inverter, irradiance, pvsystem, solarposition, temperature

# Temperature coefficient of power: silicon loses ~0.4% per deg C above STC.
DEFAULT_GAMMA_PDC = -0.004

# PVWatts v5 default named losses (percent). pvlib combines these
# MULTIPLICATIVELY (not summed) into one system derate (~14%).
DEFAULT_LOSSES_PCT = {
    "soiling": 2.0,
    "shading": 3.0,
    "snow": 0.0,
    "mismatch": 2.0,
    "wiring": 2.0,
    "connections": 0.5,
    "lid": 1.5,            # light-induced degradation
    "nameplate_rating": 1.0,
    "age": 0.0,
    "availability": 3.0,
}

# Sandia cell-temperature coefficients for an open-rack glass/glass module
# (typical rooftop mount with airflow beneath).
SAPM_TEMP_COEFFS = temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"][
    "open_rack_glass_glass"
]


@dataclass
class GenerationResult:
    annual_kwh: float
    monthly_kwh: dict           # {"Jan": .., ... "Dec": ..}
    peak_ac_kw: float
    capacity_factor_pct: float  # annual_kwh / (size_kw * 8760) * 100
    specific_yield: float       # annual_kwh / size_kw  (kWh/kWp/year)
    system_size_kw: float
    tilt: float
    azimuth: float
    total_loss_pct: float


def _default_tilt_for_latitude(lat: float) -> float:
    """Tilt = |latitude|, clipped to a practical 10-35 deg for rooftops."""
    return min(35.0, max(10.0, abs(lat)))


def simulate_annual_generation(
    weather: pd.DataFrame,
    latitude: float,
    longitude: float,
    system_size_kw: float,
    tilt: float | None = None,
    azimuth: float = 180.0,           # due south (northern hemisphere)
    losses_pct: dict | None = None,
    gamma_pdc: float = DEFAULT_GAMMA_PDC,
    inverter_efficiency: float = 0.96,
) -> GenerationResult:
    """
    Run an 8760-hour PVWatts simulation.

    `weather` must have columns [ghi, dni, dhi, temp_air, wind_speed],
    indexed by tz-aware UTC timestamps (exactly what the weather service
    returns).
    """
    if tilt is None:
        tilt = _default_tilt_for_latitude(latitude)
    if losses_pct is None:
        losses_pct = DEFAULT_LOSSES_PCT.copy()

    # 1. Sun position for every hour.
    solpos = solarposition.get_solarposition(
        time=weather.index,
        latitude=latitude,
        longitude=longitude,
        temperature=weather["temp_air"],
    )

    # 2. Transpose horizontal irradiance onto the tilted panel plane (POA).
    poa = irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=weather["dni"],
        ghi=weather["ghi"],
        dhi=weather["dhi"],
    )
    poa_global = poa["poa_global"].clip(lower=0).fillna(0)

    # 3. Cell temperature (Sandia model, open-rack).
    cell_temp = temperature.sapm_cell(
        poa_global=poa_global,
        temp_air=weather["temp_air"],
        wind_speed=weather["wind_speed"],
        **SAPM_TEMP_COEFFS,
    )

    # 4. DC power (nameplate watts) with temperature derating.
    pdc0_w = system_size_kw * 1000.0
    dc_power_w = pvsystem.pvwatts_dc(
        g_poa_effective=poa_global,
        temp_cell=cell_temp,
        pdc0=pdc0_w,
        gamma_pdc=gamma_pdc,
    )

    # 5. Combined loss stack (multiplicative), applied to DC.
    total_loss_pct = pvsystem.pvwatts_losses(**losses_pct)
    dc_after_losses_w = dc_power_w * (1 - total_loss_pct / 100.0)

    # 6. DC -> AC via the PVWatts inverter model.
    ac_power_w = inverter.pvwatts(
        pdc=dc_after_losses_w,
        pdc0=pdc0_w,
        eta_inv_nom=inverter_efficiency,
    ).clip(lower=0)

    # --- aggregate ------------------------------------------------------
    hourly_ac_kw = ac_power_w / 1000.0
    annual_kwh = float(hourly_ac_kw.sum())

    # Monthly totals (group by calendar month of the UTC index).
    monthly = hourly_ac_kw.groupby(hourly_ac_kw.index.month).sum()
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_kwh = {month_names[m - 1]: round(float(v), 1) for m, v in monthly.items()}

    peak_ac_kw = float(hourly_ac_kw.max())
    capacity_factor = annual_kwh / (system_size_kw * 8760) * 100
    specific_yield = annual_kwh / system_size_kw

    return GenerationResult(
        annual_kwh=round(annual_kwh, 1),
        monthly_kwh=monthly_kwh,
        peak_ac_kw=round(peak_ac_kw, 2),
        capacity_factor_pct=round(capacity_factor, 2),
        specific_yield=round(specific_yield, 1),
        system_size_kw=system_size_kw,
        tilt=round(tilt, 1),
        azimuth=azimuth,
        total_loss_pct=round(total_loss_pct, 2),
    )

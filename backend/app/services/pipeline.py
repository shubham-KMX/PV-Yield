"""
End-to-end analysis pipeline.

One function, run_full_analysis(), runs the whole chain:

    address (or lat/lng)
      -> geocode            coordinates
      -> satellite image    pixels + meters-per-pixel
      -> segment roof       roof mask + area
      -> shading            usable mask (obstacles + shade removed)
      -> panel layout       panel count + system kW
      -> weather (NASA)     8760 hourly irradiance/temperature
      -> PVWatts            annual + monthly kWh
      -> financials         subsidy, savings, payback, EMI
      -> one bundled result dict

This module contains NO new domain logic — it only coordinates the
services we already built and tested, plus a small adapter that feeds the
generation number into the financial model.
"""

import io

import numpy as np
from PIL import Image

from app.services.finance.financial_model import (
    emi,
    loan_rate_for_amount,
    monthly_net_metering_savings,
    payback_and_lifetime_savings,
    total_subsidy,
)
from app.services.geocoding import geocode_address
from app.services.imagery import fetch_satellite_image
from app.services.panel_layout import optimize_panel_layout
from app.services.pvwatts import simulate_annual_generation
from app.services.segmentation import auto_pick_prompt_point, segment_from_polygon, segment_roof
from app.services.shading import analyze_shading
from app.services.weather import fetch_hourly_weather
from app.services.footprints import (
    fetch_building_footprint,
    footprint_to_pixels,
    estimate_azimuth_from_footprint,
)
import cv2

# Simple install-cost assumption (₹ per watt). A real quote varies; this is
# an illustrative national average for residential rooftop.
DEFAULT_COST_PER_WATT = 45.0


def _compute_financials(
    system_kw: float,
    annual_kwh: float,
    state: str,
    discom_key: str,
    monthly_consumption_kwh: float,
    cost_per_watt: float = DEFAULT_COST_PER_WATT,
) -> dict:
    """
    Adapter: turn the pipeline's physical outputs (system kW, annual kWh)
    into a financial summary using the finance service.
    """
    system_cost = system_kw * 1000.0 * cost_per_watt
    subsidy = total_subsidy(system_kw, state)

    monthly_gen = annual_kwh / 12.0
    savings = monthly_net_metering_savings(
        monthly_generation_kwh=monthly_gen,
        monthly_consumption_kwh=monthly_consumption_kwh,
        state=state,
        discom_key=discom_key,
    )
    annual_savings = savings["monthly_savings"] * 12.0

    payback = payback_and_lifetime_savings(
        system_cost=system_cost,
        subsidy=subsidy["total_subsidy"],
        annual_savings_year1=annual_savings,
    )

    net_cost = payback["net_cost_after_subsidy"]
    loan_rate = loan_rate_for_amount("SBI Surya Ghar Loan", net_cost)

    return {
        "system_cost": round(system_cost, 0),
        "subsidy": subsidy,
        "net_cost_after_subsidy": round(net_cost, 0),
        "monthly_savings": savings["monthly_savings"],
        "annual_savings": round(annual_savings, 0),
        "payback_years": payback["payback_years"],
        "lifetime_savings": payback["lifetime_savings"],
        "loan_emi_monthly": emi(net_cost, loan_rate, 5),
        "loan_rate_pct": loan_rate,
        "cost_per_watt": cost_per_watt,
    }


def run_full_analysis(
    address: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    points: list[tuple[int, int]] | None = None,
    polygon: list[tuple[int, int]] | None = None,
    auto_expand: bool = False,
    apply_shading: bool = True,
    clip_to_footprint: bool = True,
    tilt: float | None = None,       # None = latitude-based default
    azimuth: float | None = None,    # None = estimate from footprint, else 180
    state: str = "Delhi",
    discom_key: str = "Delhi (BSES/Tata Power, illustrative)",
    monthly_consumption_kwh: float = 300.0,
) -> dict:
    """
    Run the whole analysis end to end and return one bundled result.

    Either `address` OR (`lat`, `lng`) must be provided. Roof selection
    mode: polygon > points > auto-pick (same priority as /segment).
    """
    # 1. Coordinates.
    if lat is not None and lng is not None:
        site_lat, site_lng = lat, lng
        formatted = f"{lat:.5f}, {lng:.5f}"
    elif address:
        geo = geocode_address(address)
        site_lat, site_lng, formatted = geo.lat, geo.lng, geo.formatted_address
    else:
        raise ValueError("Provide either 'address' or both 'lat' and 'lng'.")

    # 2. Satellite image (carries zoom/scale/m-per-pixel).
    image = fetch_satellite_image(site_lat, site_lng)

    # 3. Segment the roof.
    if polygon:
        w, h = Image.open(io.BytesIO(image.image_bytes)).size
        seg = segment_from_polygon(polygon, (h, w), image.lat, image.zoom, image.scale)
    else:
        pts = points or [auto_pick_prompt_point(image.image_bytes)]
        seg = segment_roof(
            image.image_bytes, image.lat, image.zoom, image.scale,
            prompt_points=pts, auto_expand=auto_expand,
        )

    # 3.5. Clip the SAM mask to the real building footprint (OSM), so it
    # can't spill onto a neighbour. Only for the SAM path (a user-drawn
    # polygon is already precise). Safe: if no footprint is found, skip.
    footprint_clipped = False
    estimated_azimuth: float | None = None
    if clip_to_footprint and not polygon:
        fp = fetch_building_footprint(site_lat, site_lng)
        if fp is not None:
            h, w = seg.mask.shape
            fp_px = footprint_to_pixels(
                fp, image.lat, image.lng, image.zoom, image.scale, image_size_px=w
            )
            # Estimate the roof azimuth from the footprint's orientation.
            estimated_azimuth = estimate_azimuth_from_footprint(fp_px)
            fp_mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(fp_mask, [np.array(fp_px, dtype=np.int32)], 1)
            fp_bool = fp_mask.astype(bool)
            clipped = seg.mask & fp_bool
            # Apply the clip whenever it leaves a plausible building-sized
            # region. This is the whole point: if SAM over-grew across
            # several buildings, clipping SHOULD remove most of it. We only
            # skip when the result is essentially empty (a misaligned
            # footprint), to avoid erasing a good mask entirely.
            clipped_frac = clipped.sum() / max(fp_bool.sum(), 1)
            if clipped.sum() > 0 and clipped_frac > 0.05:
                seg.mask = clipped
                seg.pixel_count = int(clipped.sum())
                seg.area_m2 = round(seg.pixel_count * (seg.m_per_pixel ** 2), 2)
                seg.area_sqft = round(seg.area_m2 * 10.7639, 1)
                footprint_clipped = True

    # 4. Shading -> usable mask (optional refinement).
    usable_mask = seg.mask
    shading_summary = None
    if apply_shading:
        rgb = np.array(Image.open(io.BytesIO(image.image_bytes)).convert("RGB"))
        shade = analyze_shading(rgb, seg.mask, image.lat, image.lng, seg.m_per_pixel)
        usable_mask = shade.usable_mask
        shading_summary = {
            "obstacle_pixels": shade.obstacle_pixel_count,
            "usable_pixels": shade.usable_pixel_count,
        }

    # 5. Panel layout -> system size.
    layout = optimize_panel_layout(
        usable_mask, seg.m_per_pixel, image.lat, image.zoom, image.scale
    )

    # If no panels fit, stop here with a partial (but honest) result.
    if layout.panel_count == 0:
        return {
            "success": True,
            "coordinates": {"lat": site_lat, "lng": site_lng},
            "formatted_address": formatted,
            "roof_area_m2": seg.area_m2,
            "panel_count": 0,
            "message": "No panels fit on the usable roof area.",
        }

    # 6. Weather + PVWatts generation.
    weather = fetch_hourly_weather(site_lat, site_lng)

    # Resolve azimuth: user override > footprint estimate > south (180).
    if azimuth is not None:
        eff_azimuth, azimuth_source = azimuth, "user"
    elif estimated_azimuth is not None:
        eff_azimuth, azimuth_source = estimated_azimuth, "footprint"
    else:
        eff_azimuth, azimuth_source = 180.0, "default"

    gen = simulate_annual_generation(
        weather, site_lat, site_lng, layout.system_size_kw,
        tilt=tilt, azimuth=eff_azimuth,
    )

    # 7. Financials.
    financials = _compute_financials(
        system_kw=layout.system_size_kw,
        annual_kwh=gen.annual_kwh,
        state=state,
        discom_key=discom_key,
        monthly_consumption_kwh=monthly_consumption_kwh,
    )

    # 8. Bundle everything.
    return {
        "success": True,
        "coordinates": {"lat": site_lat, "lng": site_lng},
        "formatted_address": formatted,
        "roof_area_m2": seg.area_m2,
        "usable_area_m2": layout.usable_area_m2,
        "footprint_clipped": footprint_clipped,
        "shading": shading_summary,
        "panel_count": layout.panel_count,
        "system_size_kw": layout.system_size_kw,
        "orientation": layout.orientation,
        "annual_kwh": gen.annual_kwh,
        "monthly_kwh": gen.monthly_kwh,
        "specific_yield": gen.specific_yield,
        "tilt": gen.tilt,
        "azimuth": gen.azimuth,
        "azimuth_source": azimuth_source,
        "financials": financials,
        "image_source": image.source,
    }

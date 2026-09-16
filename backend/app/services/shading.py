"""
Shading analysis — refine a roof mask into the truly USABLE area.

Not all roof is good for panels:
  - obstacles (water tanks, AC units, stairwells, parapets) block placement
    AND cast shadows on nearby roof,
  - heavily shaded spots aren't worth a panel (industry rule: >~10% annual
    shade badly hurts output).

This module detects on-roof obstacles, ray-casts their shadows across a
year of sun positions, accumulates per-pixel shade, and returns a
`usable_mask` = roof that is neither obstacle nor heavily shaded. That
mask is what panel_layout should pack (instead of the raw roof mask).

Uses pvlib for sun positions (already a dependency). Pure computation.
"""

from dataclasses import dataclass

import cv2
import numpy as np
import pandas as pd
from pvlib import solarposition


@dataclass
class ShadingResult:
    usable_mask: np.ndarray       # roof, minus obstacles and heavy shade
    obstacle_mask: np.ndarray     # detected on-roof obstacles
    shade_fraction: np.ndarray    # per-pixel fraction of daylight hours shaded
    usable_pixel_count: int
    obstacle_pixel_count: int
    shade_threshold: float


def _detect_obstacles(
    image: np.ndarray,
    roof_mask: np.ndarray,
    m_per_pixel: float,
    dark_percentile: float = 15.0,
    min_obstacle_m2: float = 0.5,
) -> np.ndarray:
    """
    Flag REAL obstacle clusters on the roof (tanks, AC units, stairwells).

    Obstacles read darker than clean roof, but so do harmless things like
    edge staining and slight discoloration. To avoid over-flagging (which
    fragments the panel layout), we:
      1. threshold on the darkest `dark_percentile` of roof pixels,
      2. clean speckle with a morphological open,
      3. KEEP ONLY connected components bigger than `min_obstacle_m2` — a
         real obstacle is a chunk of pixels; scattered dark specks are not.
    """
    if not roof_mask.any():
        return np.zeros_like(roof_mask)

    v = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)[..., 2]
    roof_vals = v[roof_mask]
    threshold = np.percentile(roof_vals, dark_percentile)

    dark = (roof_mask & (v <= threshold)).astype(np.uint8)

    # Clean speckle first.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel)

    # Keep only components that are physically large enough to be a real
    # obstacle — this is the key fix against scattered-speckle over-flagging.
    min_px = int(min_obstacle_m2 / (m_per_pixel ** 2))
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    obstacles = np.zeros_like(dark, dtype=bool)
    for i in range(1, n_labels):  # skip background
        if int(stats[i, cv2.CC_STAT_AREA]) >= min_px:
            obstacles |= labels == i

    return obstacles


def _daylight_sun_positions(lat: float, lng: float, year: int) -> pd.DataFrame:
    """
    Hourly sun positions over the year, keeping only daylight hours
    (elevation > 5 deg). Returns azimuth + elevation.
    """
    times = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h", tz="UTC")
    solpos = solarposition.get_solarposition(times, lat, lng)
    daylight = solpos[solpos["apparent_elevation"] > 5.0]
    return daylight[["azimuth", "apparent_elevation"]]


def analyze_shading(
    image: np.ndarray,
    roof_mask: np.ndarray,
    lat: float,
    lng: float,
    m_per_pixel: float,
    year: int = 2023,
    obstacle_height_m: float = 1.5,
    shade_threshold: float = 0.10,
    n_azimuth_bins: int = 24,
) -> ShadingResult:
    """
    Compute per-pixel annual shade and the usable mask.

    For speed, we bin the ~4000 daylight sun positions into `n_azimuth_bins`
    azimuth buckets (weighted by how many hours fall in each), then cast
    each obstacle's shadow once per bucket. Shadow length = obstacle_height
    / tan(elevation); direction = opposite the sun's azimuth.
    """
    h, w = roof_mask.shape
    obstacle_mask = _detect_obstacles(image, roof_mask, m_per_pixel)

    shade_hours = np.zeros((h, w), dtype=np.float32)

    if obstacle_mask.any():
        solpos = _daylight_sun_positions(lat, lng, year)
        total_hours = len(solpos)

        # Bin daylight hours by azimuth; use the mean elevation per bin.
        bins = np.linspace(0, 360, n_azimuth_bins + 1)
        solpos = solpos.copy()
        solpos["bin"] = np.digitize(solpos["azimuth"], bins) - 1

        obst_u8 = obstacle_mask.astype(np.uint8)
        for b in range(n_azimuth_bins):
            group = solpos[solpos["bin"] == b]
            if group.empty:
                continue
            hours_in_bin = len(group)
            mean_az = float(group["azimuth"].mean())
            mean_el = float(group["apparent_elevation"].mean())

            # Shadow length in pixels; direction = away from the sun.
            shadow_len_m = obstacle_height_m / np.tan(np.radians(mean_el))
            shadow_len_px = int(round(shadow_len_m / m_per_pixel))
            if shadow_len_px <= 0:
                continue
            # Sun azimuth measured from north, clockwise; shadow points opposite.
            shadow_az = np.radians((mean_az + 180.0) % 360.0)
            dx = int(round(np.sin(shadow_az) * shadow_len_px))
            dy = int(round(-np.cos(shadow_az) * shadow_len_px))

            # Shift the obstacle mask along the shadow direction.
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            shadow = cv2.warpAffine(obst_u8, M, (w, h))
            shade_hours += shadow.astype(np.float32) * hours_in_bin

        shade_fraction = shade_hours / max(total_hours, 1)
    else:
        shade_fraction = np.zeros((h, w), dtype=np.float32)

    # Usable = roof, not an obstacle, shaded less than the threshold.
    usable_mask = roof_mask & ~obstacle_mask & (shade_fraction < shade_threshold)

    return ShadingResult(
        usable_mask=usable_mask,
        obstacle_mask=obstacle_mask,
        shade_fraction=shade_fraction,
        usable_pixel_count=int(usable_mask.sum()),
        obstacle_pixel_count=int(obstacle_mask.sum()),
        shade_threshold=shade_threshold,
    )

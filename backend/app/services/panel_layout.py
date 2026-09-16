"""
Panel layout optimiser.

Given a usable roof mask + meters-per-pixel, work out how many real solar
panels physically fit, and therefore the system size in kW. That kW number
is the bridge into the PVWatts simulation.

This is a 2D bin-packing problem with real-world constraints:
  - panel size (~1.65 m x 1.0 m standard residential module)
  - setback from the roof edge (fire/maintenance code)
  - a small aisle gap between panels
  - both portrait and landscape orientations tried; best wins

Pure geometry — no ML, no network — so it's fast and easy to test.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from app.services.geometry import pixels_to_area


@dataclass
class PanelLayoutResult:
    panel_count: int
    system_size_kw: float
    panels: list[tuple[int, int, int, int]]  # (x, y, w, h) rects in pixels
    orientation: str                          # "portrait" | "landscape"
    usable_area_m2: float
    panel_wattage: int
    packing_efficiency_pct: float             # panel area / usable area


def _erode_for_setback(mask: np.ndarray, setback_px: int) -> np.ndarray:
    """Shrink the mask inward by the edge setback (fire code clearance)."""
    if setback_px <= 0:
        return mask
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * setback_px + 1, 2 * setback_px + 1)
    )
    return cv2.erode(mask.astype(np.uint8), kernel, iterations=1).astype(bool)


def _pack_grid(usable: np.ndarray, pw: int, ph: int, aisle: int) -> list[tuple[int, int, int, int]]:
    """
    Greedily grid-pack panel rectangles (pw x ph pixels) into the usable
    mask. A slot is kept only if EVERY pixel under the panel is usable.

    Tries a few grid origin offsets and keeps the densest packing.
    """
    h, w = usable.shape
    step_x, step_y = pw + aisle, ph + aisle
    best: list[tuple[int, int, int, int]] = []

    # A few starting offsets so the grid isn't locked to (0,0).
    for oy in range(0, step_y, max(1, step_y // 3)):
        for ox in range(0, step_x, max(1, step_x // 3)):
            placed: list[tuple[int, int, int, int]] = []
            y = oy
            while y + ph <= h:
                x = ox
                while x + pw <= w:
                    # Panel fits only if the whole rectangle is usable.
                    if usable[y : y + ph, x : x + pw].all():
                        placed.append((x, y, pw, ph))
                    x += step_x
                y += step_y
            if len(placed) > len(best):
                best = placed
    return best


def optimize_panel_layout(
    usable_mask: np.ndarray,
    m_per_pixel: float,
    lat: float,
    zoom: int,
    scale: int,
    panel_height_m: float = 1.65,
    panel_width_m: float = 1.00,
    panel_wattage: int = 400,
    setback_m: float = 0.4,
    aisle_m: float = 0.10,
) -> PanelLayoutResult:
    """
    Compute how many panels fit and the resulting system size.

    Tries both portrait and landscape; keeps whichever packs more panels.
    """
    # meters -> pixels
    ph = max(1, int(round(panel_height_m / m_per_pixel)))
    pw = max(1, int(round(panel_width_m / m_per_pixel)))
    setback_px = int(round(setback_m / m_per_pixel))
    aisle_px = max(0, int(round(aisle_m / m_per_pixel)))

    usable = _erode_for_setback(usable_mask, setback_px)
    usable_px = int(usable.sum())
    usable_area_m2 = usable_px * (m_per_pixel ** 2)

    # Try both orientations.
    portrait = _pack_grid(usable, pw, ph, aisle_px)      # tall panels
    landscape = _pack_grid(usable, ph, pw, aisle_px)     # rotated 90 deg

    if len(landscape) > len(portrait):
        panels, orientation = landscape, "landscape"
    else:
        panels, orientation = portrait, "portrait"

    panel_count = len(panels)
    system_size_kw = panel_count * panel_wattage / 1000.0

    # Packing efficiency: how much of the usable area the panels cover.
    panel_area_px = panel_count * pw * ph
    packing_eff = (panel_area_px / usable_px * 100) if usable_px > 0 else 0.0

    return PanelLayoutResult(
        panel_count=panel_count,
        system_size_kw=round(system_size_kw, 2),
        panels=panels,
        orientation=orientation,
        usable_area_m2=round(usable_area_m2, 2),
        panel_wattage=panel_wattage,
        packing_efficiency_pct=round(packing_eff, 1),
    )

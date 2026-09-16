"""
Roof segmentation service.

Turns a satellite image + a prompt point into a measured roof area:

    image bytes + (x, y)  ->  SAM mask  ->  pixel count  ->  square meters

This is where the project's core claim lives: the roof area is a real
measurement (pixel count x meters-per-pixel^2), not a guess.

Sub-step 3 keeps it simple: one point prompt, pick SAM's highest-
confidence mask. Later sub-steps add smarter mask selection, shadow
removal, and automatic prompt picking.
"""

import io
import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from app.services.geometry import pixels_to_area
from app.services.sam_model import get_predictor

# --- plausible roof-size bounds (fraction of the whole frame) ---------------
# A residential rooftop at zoom 21 typically fills 2-40% of the frame.
# Below MIN it's probably a fragment (pavement sliver, chimney); above MAX
# it's probably "everything merged into one blob" (roads + neighbors).
MIN_MASK_FRAC = 0.02
MAX_MASK_FRAC = 0.60


def auto_pick_prompt_point(
    image_bytes: bytes,
    bright_percentile: float = 60.0,
    min_size_frac: float = 0.005,
    morph_kernel: int = 15,
) -> tuple[int, int]:
    """
    Pick a sensible default prompt point automatically.

    The satellite image is centered on the geocoded property, and rooftops
    are usually noticeably brighter than the ground around them (concrete,
    beige paint, white tile). So we:
      1. Threshold on HSV brightness to find bright regions.
      2. Clean noise with morphological open/close.
      3. Find connected components and score each by
         size / (1 + distance_to_center) — big AND central wins.
      4. Return the centroid of the best component.

    Falls back to the image center if nothing plausible is found. This
    gives the user a first result with zero clicks; they can refine later.
    """
    pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    rgb = np.array(pil)
    h, w = rgb.shape[:2]
    cx, cy = w // 2, h // 2

    v = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 2]
    threshold = float(np.percentile(v, bright_percentile))
    bright = (v >= threshold).astype(np.uint8)

    # Clean speckle: open removes tiny bright specks, close fills small holes.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (morph_kernel, morph_kernel))
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, kernel)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel)

    n_labels, _, stats, centroids = cv2.connectedComponentsWithStats(bright, connectivity=8)
    min_size_px = int(min_size_frac * h * w)

    best_score = -1.0
    best_xy: tuple[int, int] | None = None
    for i in range(1, n_labels):  # skip background label 0
        size = int(stats[i, cv2.CC_STAT_AREA])
        if size < min_size_px:
            continue
        comp_cx, comp_cy = float(centroids[i][0]), float(centroids[i][1])
        dist = math.hypot(comp_cx - cx, comp_cy - cy)
        score = size / (1.0 + dist / 100.0)  # big + central scores highest
        if score > best_score:
            best_score = score
            best_xy = (int(round(comp_cx)), int(round(comp_cy)))

    return best_xy if best_xy is not None else (cx, cy)


@dataclass
class SegmentationResult:
    """Result of segmenting a roof (possibly from multiple prompt points)."""
    mask: np.ndarray            # boolean HxW array: True where roof
    pixel_count: int            # number of True pixels
    area_m2: float
    area_sqft: float
    m_per_pixel: float
    score: float                # mean SAM confidence across chosen masks
    image_shape: tuple[int, int]  # (height, width)
    prompt_points: list[tuple[int, int]]  # every point used
    num_points: int             # how many prompt points contributed
    selection_reason: str       # why each mask was chosen (for debugging)


def _pick_best_mask(
    masks: np.ndarray,
    scores: np.ndarray,
    prompt_point: tuple[int, int],
    image_shape: tuple[int, int],
) -> tuple[np.ndarray, float, str]:
    """
    Choose the most plausible roof mask from SAM's 3 candidates.

    Heuristics (in priority order):
      1. The mask MUST contain the prompt point (it's what the user aimed at).
      2. Prefer masks whose size falls in the plausible roof range.
      3. Among plausible masks, prefer the highest SAM confidence.
      4. If none are plausible, fall back to the smallest candidate that
         contains the point (avoids the "whole neighborhood" blob), or
         SAM's top score if nothing contains the point at all.

    Returns (mask, score, reason).
    """
    h, w = image_shape
    px, py = prompt_point
    total = h * w

    containing = []
    for i, (mask, score) in enumerate(zip(masks, scores)):
        # Guard: prompt point could be out of bounds after scaling.
        if not (0 <= py < h and 0 <= px < w):
            continue
        if not mask[py, px]:
            continue
        frac = float(mask.sum()) / total
        in_range = MIN_MASK_FRAC <= frac <= MAX_MASK_FRAC
        containing.append((i, mask, float(score), frac, in_range))

    if not containing:
        # Nothing contains the point — fall back to SAM's top score.
        i = int(np.argmax(scores))
        return masks[i].astype(bool), float(scores[i]), "fallback: top SAM score (no mask contained the point)"

    # Prefer plausibly-sized masks; among those, highest confidence.
    plausible = [c for c in containing if c[4]]
    if plausible:
        plausible.sort(key=lambda c: c[2], reverse=True)
        _, mask, score, frac, _ = plausible[0]
        return mask.astype(bool), score, f"plausible size ({frac*100:.1f}% of frame), highest confidence"

    # No plausible-size mask: take the smallest that contains the point,
    # which avoids grabbing a giant merged blob.
    containing.sort(key=lambda c: c[3])
    _, mask, score, frac, _ = containing[0]
    return mask.astype(bool), score, f"no in-range mask; smallest containing ({frac*100:.1f}% of frame)"


def _segment_single_point(
    predictor,
    point: tuple[int, int],
    image_shape: tuple[int, int],
) -> tuple[np.ndarray, float, str]:
    """
    Run SAM for ONE foreground point and return the best mask.

    Assumes predictor.set_image() has already been called (the expensive
    embedding is computed once and reused for every point).
    """
    px, py = point
    point_coords = np.array([[px, py]], dtype=np.float32)
    point_labels = np.array([1], dtype=np.int32)  # 1 = foreground

    masks, scores, _ = predictor.predict(
        point_coords=point_coords,
        point_labels=point_labels,
        multimask_output=True,  # SAM returns 3 candidates + scores
    )
    return _pick_best_mask(masks, scores, point, image_shape)


def _auto_expand_sections(
    predictor,
    image: np.ndarray,
    primary_mask: np.ndarray,
    anchor: tuple[int, int],
    max_distance_frac: float = 0.15,
    brightness_tol: float = 0.08,
    ring_gap_px: int = 10,
    n_ring_points: int = 24,
    max_growth_multiple: float = 2.5,
) -> tuple[np.ndarray, list[str]]:
    """
    Conservatively grow `primary_mask` into ADJACENT, roof-like sections
    of the SAME building, without swallowing neighbours.

    Anti-neighbour design (all tested against the FROZEN primary roof, so
    the mask can't snowball):
      (a) brightness similarity to the primary roof (tight tolerance),
      (b) connectivity to the PRIMARY roof (not the growing mask) — a
          neighbour separated by a wall/alley/setback fails this,
      (c) within a small distance cap from the geocoded anchor,
      (d) each candidate must be SMALLER than the primary roof (a bigger
          blob is probably a neighbour or courtyard, not a sub-section),
      (e) a hard cap on TOTAL growth: the final mask may not exceed
          `max_growth_multiple` x the primary area. A single house does not
          have hidden sections that triple its footprint.

    Returns (expanded_mask, notes).
    """
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    v = hsv[..., 2].astype(np.float32) / 255.0  # brightness 0..1

    primary_area = int(primary_mask.sum())
    if primary_area == 0:
        return primary_mask, ["auto-expand: empty primary mask"]

    roof_v = float(np.median(v[primary_mask]))
    ax, ay = anchor
    max_dist = max_distance_frac * min(h, w)
    max_total_area = int(primary_area * max_growth_multiple)

    # Freeze the anchor: connectivity is always tested against the ORIGINAL
    # primary roof (dilated once), never the growing result.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ring_gap_px, ring_gap_px))
    primary_u8 = primary_mask.astype(np.uint8)
    primary_dilated = cv2.dilate(primary_u8, kernel, iterations=1).astype(bool)

    # Candidate seeds: a rim just outside the primary roof boundary.
    rim = primary_dilated & ~primary_mask
    rim_ys, rim_xs = np.where(rim)
    if len(rim_xs) == 0:
        return primary_mask, ["auto-expand: no rim pixels to probe"]

    idxs = np.linspace(0, len(rim_xs) - 1, num=min(n_ring_points, len(rim_xs))).astype(int)

    current = primary_mask.copy()
    notes: list[str] = []
    merged_count = 0

    for i in idxs:
        cx, cy = int(rim_xs[i]), int(rim_ys[i])

        # (c) distance cap from the frozen anchor.
        if np.hypot(cx - ax, cy - ay) > max_dist:
            continue
        # (a) brightness similarity to the primary roof (tight).
        if abs(float(v[cy, cx]) - roof_v) > brightness_tol:
            continue

        cand_mask, _score, _reason = _segment_single_point(predictor, (cx, cy), (h, w))
        cand_area = int(cand_mask.sum())
        if cand_area == 0:
            continue

        # (d) candidate must be smaller than the primary roof.
        if cand_area >= primary_area:
            continue
        # size sanity (frame-fraction bounds).
        frac = cand_area / (h * w)
        if not (MIN_MASK_FRAC <= frac <= MAX_MASK_FRAC):
            continue
        # (b) connectivity to the FROZEN primary roof (not the growing mask).
        if not (primary_dilated & cand_mask).any():
            continue

        # (e) hard total-growth cap.
        candidate_result = current | cand_mask
        if int(candidate_result.sum()) > max_total_area:
            notes.append(f"skipped ({cx},{cy}): would exceed {max_growth_multiple}x growth cap")
            continue

        before = int(current.sum())
        current = candidate_result
        gained = int(current.sum()) - before
        if gained > 0:
            merged_count += 1
            notes.append(f"merged section at ({cx},{cy}) +{gained} px")

    if merged_count == 0:
        notes.append("auto-expand: no adjacent same-building sections found")
    return current, notes


def _remove_shadow(
    image: np.ndarray,
    mask: np.ndarray,
    reference_point: tuple[int, int],
    brightness_ratio: float = 0.65,
    sample_radius: int = 25,
    open_kernel: int = 7,
) -> np.ndarray:
    """
    Strip cast-shadow pixels out of a SAM mask.

    Why: SAM often treats a building and its cast shadow as one object,
    because the shadow is dark, attached, and looks like nearby shaded
    ground. That inflates the roof area with pixels that aren't roof.

    Method:
      1. Sample the roof's true brightness in a patch around a point we
         KNOW is on the roof (the prompt point).
      2. Drop masked pixels darker than `brightness_ratio` x that reference.
      3. Morphological opening to break thin shadow "tails".
      4. Keep only the connected component containing the reference point,
         so we don't leave floating fragments.
    """
    h, w = image.shape[:2]
    px, py = reference_point
    px = min(max(px, 0), w - 1)
    py = min(max(py, 0), h - 1)

    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    v = hsv[..., 2]

    # 1. reference brightness = median of a patch around the roof point.
    y0, y1 = max(0, py - sample_radius), min(h, py + sample_radius)
    x0, x1 = max(0, px - sample_radius), min(w, px + sample_radius)
    ref_v = float(np.median(v[y0:y1, x0:x1]))

    # 2. keep only mask pixels bright enough relative to the roof.
    bright_enough = v >= (ref_v * brightness_ratio)
    refined = (mask & bright_enough).astype(np.uint8)

    # 3. opening removes thin shadow tails while keeping the roof body.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_kernel, open_kernel))
    refined = cv2.morphologyEx(refined, cv2.MORPH_OPEN, kernel)

    # 4. keep only the component containing the reference point.
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(refined, connectivity=8)
    if n_labels > 1:
        ref_label = int(labels[py, px])
        if ref_label > 0:
            refined = (labels == ref_label).astype(np.uint8)
        else:
            # reference fell on a hole — keep the largest non-background blob.
            largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            refined = (labels == largest).astype(np.uint8)

    return refined.astype(bool)


def segment_roof(
    image_bytes: bytes,
    lat: float,
    zoom: int,
    scale: int,
    prompt_points: list[tuple[int, int]] | tuple[int, int] | None = None,
    auto_expand: bool = False,
    remove_shadows: bool = True,
) -> SegmentationResult:
    """
    Segment the rooftop and measure its ground area.

    `prompt_points` may be:
      - None: default to the image center (map is usually centered on the
        building).
      - a single (x, y) tuple: segment one point (backward compatible).
      - a list of (x, y) tuples: segment each point and MERGE the masks
        into one roof. This is how the frontend's "click each roof
        section" feature captures multi-section / multi-level roofs.

    `auto_expand` (default False, opt-in from the frontend): after
    segmenting, conservatively grow the mask into ADJACENT, roof-like
    sections anchored at the image center (the geocoded property). It only
    merges connected, similar regions within a distance cap, so a
    neighbour's separate house is excluded. It can never shrink the mask.

    All points share one image embedding (computed once), so adding points
    is cheap.
    """
    # Decode the PNG bytes into an RGB numpy array (H, W, 3) for SAM.
    pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = np.array(pil_img)
    h, w = image.shape[:2]

    # Normalize prompt_points into a list of (int, int).
    if prompt_points is None:
        points = [(w // 2, h // 2)]
    elif isinstance(prompt_points, tuple):
        points = [prompt_points]
    else:
        points = list(prompt_points)
        if not points:
            points = [(w // 2, h // 2)]
    points = [(int(x), int(y)) for (x, y) in points]

    # Compute the image embedding ONCE, then reuse for every point.
    predictor = get_predictor()
    predictor.set_image(image)

    # Segment each point and union the masks together.
    merged_mask = np.zeros((h, w), dtype=bool)
    scores: list[float] = []
    reasons: list[str] = []
    for point in points:
        mask, score, reason = _segment_single_point(predictor, point, (h, w))
        # Strip cast shadows using this point as the roof brightness
        # reference (we know the point is on the roof).
        if remove_shadows and mask.any():
            before = int(mask.sum())
            mask = _remove_shadow(image, mask, point)
            dropped = before - int(mask.sum())
            if dropped > 0:
                reason += f"; shadow -{dropped}px"
        merged_mask |= mask  # logical OR = union of roof regions
        scores.append(score)
        reasons.append(f"{point}: {reason}")

    # Optional, opt-in: grow into adjacent roof-like sections. Anchored at
    # the image center (the geocoded property) so neighbours are excluded.
    if auto_expand and merged_mask.any():
        anchor = (w // 2, h // 2)
        merged_mask, expand_notes = _auto_expand_sections(
            predictor, image, merged_mask, anchor
        )
        reasons.extend(expand_notes)

    pixel_count = int(merged_mask.sum())
    area = pixels_to_area(pixel_count, lat, zoom, scale)
    mean_score = float(np.mean(scores)) if scores else 0.0

    return SegmentationResult(
        mask=merged_mask,
        pixel_count=pixel_count,
        area_m2=round(area["area_m2"], 2),
        area_sqft=round(area["area_sqft"], 1),
        m_per_pixel=round(area["m_per_pixel"], 6),
        score=round(mean_score, 3),
        image_shape=(h, w),
        prompt_points=points,
        num_points=len(points),
        selection_reason=" | ".join(reasons),
    )


def segment_from_polygon(
    polygon: list[tuple[int, int]],
    image_shape: tuple[int, int],
    lat: float,
    zoom: int,
    scale: int,
) -> SegmentationResult:
    """
    Build a roof mask from a user-drawn polygon (fully manual selection).

    No ML involved: the polygon vertices the user clicked ARE the roof
    outline. We rasterize them into a filled mask, then measure area with
    the same geometry used everywhere else. This is the most reliable
    selection method — the human traces the exact boundary, so neighbours
    and courtyards are never included by accident. It also works on roofs
    where SAM struggles (attached row-houses, low-contrast edges).

    Parameters
    ----------
    polygon : ordered list of (x, y) pixel vertices tracing the roof.
              Needs at least 3 points to enclose an area.
    image_shape : (height, width) of the satellite image the polygon was
                  drawn on — the mask is sized to match.
    lat, zoom, scale : geometry for the pixel -> area conversion.

    Returns the same SegmentationResult type as the SAM path, so it's a
    drop-in alternative for everything downstream.
    """
    if len(polygon) < 3:
        raise ValueError("A polygon needs at least 3 points to enclose an area.")

    h, w = image_shape

    # Rasterize: start with an empty mask, fill the polygon interior.
    # cv2.fillPoly expects int32 vertices shaped (n_points, 2).
    mask_u8 = np.zeros((h, w), dtype=np.uint8)
    pts = np.array([[int(x), int(y)] for (x, y) in polygon], dtype=np.int32)
    cv2.fillPoly(mask_u8, [pts], color=1)
    mask = mask_u8.astype(bool)

    pixel_count = int(mask.sum())
    area = pixels_to_area(pixel_count, lat, zoom, scale)

    return SegmentationResult(
        mask=mask,
        pixel_count=pixel_count,
        area_m2=round(area["area_m2"], 2),
        area_sqft=round(area["area_sqft"], 1),
        m_per_pixel=round(area["m_per_pixel"], 6),
        score=1.0,  # user-drawn: full confidence by definition
        image_shape=(h, w),
        prompt_points=[(int(x), int(y)) for (x, y) in polygon],
        num_points=len(polygon),
        selection_reason="manual polygon (user-drawn outline)",
    )

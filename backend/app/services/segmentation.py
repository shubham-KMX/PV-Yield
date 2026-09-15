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
from dataclasses import dataclass

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


def segment_roof(
    image_bytes: bytes,
    lat: float,
    zoom: int,
    scale: int,
    prompt_points: list[tuple[int, int]] | tuple[int, int] | None = None,
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
        merged_mask |= mask  # logical OR = union of roof regions
        scores.append(score)
        reasons.append(f"{point}: {reason}")

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

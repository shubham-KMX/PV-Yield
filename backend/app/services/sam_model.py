"""
MobileSAM model loader.

Loading a neural network is expensive (read weights from disk, build the
graph, move to device). We only ever want to do it ONCE per process,
then reuse the same predictor for every segmentation request. So this
module lazily builds a single cached SamPredictor.

The weights file (~40 MB) is downloaded on first use and cached under
backend/.cache/models/, which is git-ignored.
"""

import os
import urllib.request
from pathlib import Path

# Windows OpenMP workaround: torch + other libs can each load their own
# copy of the OpenMP runtime, which crashes. Setting this before torch is
# imported/used tells the runtime to tolerate it. Harmless elsewhere.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Where to store the downloaded model weights.
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "models"
WEIGHTS_PATH = CACHE_DIR / "mobile_sam.pt"

# Official MobileSAM weights (the vit_t / TinyViT variant).
WEIGHTS_URL = (
    "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt"
)
MODEL_TYPE = "vit_t"

# Module-level cache. Populated on first call, reused thereafter.
_predictor = None


def _ensure_weights() -> Path:
    """Download the model weights on first use; return the local path."""
    if WEIGHTS_PATH.exists():
        return WEIGHTS_PATH
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[sam_model] downloading MobileSAM weights -> {WEIGHTS_PATH} ...")
    urllib.request.urlretrieve(WEIGHTS_URL, WEIGHTS_PATH)
    print("[sam_model] download complete.")
    return WEIGHTS_PATH


def get_predictor():
    """
    Return the cached SamPredictor, building it on first call.

    Import torch/mobile_sam lazily (inside the function) so that simply
    importing this module doesn't drag in the heavy ML stack until we
    actually need to segment something.
    """
    global _predictor
    if _predictor is not None:
        return _predictor

    import torch
    from mobile_sam import SamPredictor, sam_model_registry

    weights = _ensure_weights()

    # CPU is fine for MobileSAM; use CUDA if a GPU happens to be present.
    device = "cuda" if torch.cuda.is_available() else "cpu"

    sam = sam_model_registry[MODEL_TYPE](checkpoint=str(weights))
    sam.to(device=device)
    sam.eval()  # inference mode (disables dropout/batchnorm updates)

    _predictor = SamPredictor(sam)
    return _predictor

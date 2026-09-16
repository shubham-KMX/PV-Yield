# PV-Yield backend — FastAPI + PyTorch (CPU) + MobileSAM.
# Heavy image (torch + CV libs), so we use a slim Python base and the
# CPU-only torch wheels to keep it as small as practical.

FROM python:3.11-slim

# System libs OpenCV needs at runtime (headless still needs libgl/glib).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching — deps change less often
# than app code).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY app ./app
COPY sample_data ./sample_data

# The model weights (~40 MB) download to .cache on first segmentation.
# Hosts with an ephemeral filesystem will re-download on cold start.
ENV KMP_DUPLICATE_LIB_OK=TRUE

# Most container hosts inject $PORT. Default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Use shell form so $PORT is expanded at runtime.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}

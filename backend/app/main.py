"""
PV-Yield backend — FastAPI application entry point.

This file creates the FastAPI app and defines our first endpoints.
Run it locally with:

    uvicorn app.main:app --reload

`app.main:app` means: in the package `app`, file `main.py`, use the
variable named `app`. `--reload` restarts the server automatically
whenever you save a code change (great for development).
"""

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel

from app.services.geocoding import GeocodingError, geocode_address
from app.services.imagery import ImageryError, fetch_satellite_image
from app.services.segmentation import (
    auto_pick_prompt_point,
    segment_from_polygon,
    segment_roof,
)
from app.services.pipeline import run_full_analysis

# The FastAPI() instance IS your application. Every endpoint gets
# attached to it. The title/version show up in the auto-generated
# API docs at /docs.
app = FastAPI(
    title="PV-Yield API",
    version="0.1.0",
    description="Address-to-kWh rooftop solar potential analysis.",
)


# A Pydantic response model describes the SHAPE of what /geocode returns.
# FastAPI uses it to validate the output, serialize it to JSON, and
# document it automatically at /docs. This is the typed contract the
# frontend will rely on.
class GeocodeResponse(BaseModel):
    lat: float
    lng: float
    formatted_address: str


# --- /segment models --------------------------------------------------------
class SegmentRequest(BaseModel):
    """
    Request body for /segment. Provide a location (address OR lat/lng) and
    optionally how to select the roof.

    Selection modes (in priority order):
      - polygon: user-drawn outline (most reliable, no ML)
      - points:  one or more click points for SAM
      - neither: auto-pick a starting point automatically
    """
    address: str | None = None
    lat: float | None = None
    lng: float | None = None

    points: list[tuple[int, int]] | None = None      # SAM click points
    polygon: list[tuple[int, int]] | None = None      # manual outline
    auto_expand: bool = False                          # opt-in section growth
    remove_shadows: bool = True                        # SAM path only


class SegmentResponse(BaseModel):
    area_m2: float
    area_sqft: float
    m_per_pixel: float
    pixel_count: int
    num_points: int
    prompt_points: list[tuple[int, int]]
    selection_reason: str
    coordinates: dict
    image_source: str


@app.get("/")
def read_root():
    """
    A health-check endpoint.

    @app.get("/") registers this function to handle HTTP GET requests
    to the root URL ("/"). Whatever we return, FastAPI automatically
    converts to JSON and sends back to the caller.
    """
    return {"status": "ok", "service": "PV-Yield API", "version": "0.1.0"}


@app.get("/ping")
def ping():
    """A trivial second endpoint, just to show routing with a different path."""
    return {"message": "pong"}


@app.get("/geocode", response_model=GeocodeResponse)
def geocode(address: str = Query(..., description="Street address to geocode")):
    """
    Turn an address into coordinates.

    `address: str = Query(...)` declares a required query-string
    parameter, so you call this as /geocode?address=Mumbai. FastAPI
    validates it's present and documents it at /docs.

    `response_model=GeocodeResponse` tells FastAPI to shape the output
    to that model.

    We call the service and translate its GeocodingError into a proper
    HTTP error. This is the key separation: the service raises a plain
    Python exception (it knows nothing about HTTP); the endpoint decides
    the status code and response body.
    """
    try:
        result = geocode_address(address)
    except GeocodingError as exc:
        # 404 when the address genuinely wasn't found; 502 (bad gateway)
        # when the upstream service failed on us. Everything else -> 400.
        if exc.code == "not_found":
            status_code = 404
        elif exc.code in {"network_error", "http_error", "quota_exceeded"}:
            status_code = 502
        else:
            status_code = 400
        raise HTTPException(status_code=status_code, detail=exc.message) from exc

    return GeocodeResponse(
        lat=result.lat,
        lng=result.lng,
        formatted_address=result.formatted_address,
    )


@app.get(
    "/satellite",
    responses={200: {"content": {"image/png": {}}}},
    response_class=Response,
)
def satellite(
    address: str | None = Query(None, description="Address to fetch imagery for"),
    lat: float | None = Query(None, description="Latitude (use with lng)"),
    lng: float | None = Query(None, description="Longitude (use with lat)"),
):
    """
    Return the satellite image for a location as a PNG.

    Provide EITHER `address` OR both `lat` and `lng`. If an address is
    given, we geocode it first, then fetch imagery for the resulting
    coordinates.

    This endpoint returns raw image bytes (not JSON), so opening it in a
    browser shows the actual satellite photo. The meters-per-pixel value
    is returned in a response header for callers that need the geometry.
    """
    # Resolve coordinates: prefer explicit lat/lng, else geocode address.
    if lat is not None and lng is not None:
        site_lat, site_lng = lat, lng
    elif address:
        try:
            geo = geocode_address(address)
        except GeocodingError as exc:
            status_code = 404 if exc.code == "not_found" else 400
            raise HTTPException(status_code=status_code, detail=exc.message) from exc
        site_lat, site_lng = geo.lat, geo.lng
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'address' or both 'lat' and 'lng'.",
        )

    # Fetch the image.
    try:
        image = fetch_satellite_image(site_lat, site_lng)
    except ImageryError as exc:
        status_code = 502 if exc.code in {"network_error", "http_error"} else 400
        raise HTTPException(status_code=status_code, detail=exc.message) from exc

    # Return raw PNG bytes. Custom headers expose the geometry + source so
    # a caller (or curious human) can see meters-per-pixel without a
    # separate request.
    return Response(
        content=image.image_bytes,
        media_type="image/png",
        headers={
            "X-Meters-Per-Pixel": f"{image.m_per_pixel:.6f}",
            "X-Image-Source": image.source,
            "X-Coordinates": f"{image.lat},{image.lng}",
        },
    )


@app.post("/segment", response_model=SegmentResponse)
def segment(req: SegmentRequest):
    """
    Measure a rooftop's area from a satellite image.

    Chains the whole front of the pipeline: resolve coordinates ->
    fetch imagery -> segment the roof -> return the measured area.

    POST (not GET) because points/polygon are lists that belong in a JSON
    body, not a URL query string. Selection mode is chosen from the body:
    polygon > points > auto-pick.
    """
    # 1. Resolve coordinates (explicit lat/lng, else geocode the address).
    if req.lat is not None and req.lng is not None:
        site_lat, site_lng = req.lat, req.lng
    elif req.address:
        try:
            geo = geocode_address(req.address)
        except GeocodingError as exc:
            code = 404 if exc.code == "not_found" else 400
            raise HTTPException(status_code=code, detail=exc.message) from exc
        site_lat, site_lng = geo.lat, geo.lng
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'address' or both 'lat' and 'lng'.",
        )

    # 2. Fetch the satellite image (carries zoom/scale/m-per-pixel).
    try:
        image = fetch_satellite_image(site_lat, site_lng)
    except ImageryError as exc:
        code = 502 if exc.code in {"network_error", "http_error"} else 400
        raise HTTPException(status_code=code, detail=exc.message) from exc

    # 3. Segment, choosing the mode from what the caller supplied.
    try:
        if req.polygon:
            # Manual outline: needs the image dimensions to size the mask.
            from PIL import Image
            import io
            w, h = Image.open(io.BytesIO(image.image_bytes)).size
            result = segment_from_polygon(
                polygon=req.polygon,
                image_shape=(h, w),
                lat=image.lat,
                zoom=image.zoom,
                scale=image.scale,
            )
        else:
            # SAM path: use supplied points, or auto-pick one if none given.
            points = req.points or [auto_pick_prompt_point(image.image_bytes)]
            result = segment_roof(
                image_bytes=image.image_bytes,
                lat=image.lat,
                zoom=image.zoom,
                scale=image.scale,
                prompt_points=points,
                auto_expand=req.auto_expand,
                remove_shadows=req.remove_shadows,
            )
    except ValueError as exc:
        # e.g. a polygon with fewer than 3 points.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SegmentResponse(
        area_m2=result.area_m2,
        area_sqft=result.area_sqft,
        m_per_pixel=result.m_per_pixel,
        pixel_count=result.pixel_count,
        num_points=result.num_points,
        prompt_points=result.prompt_points,
        selection_reason=result.selection_reason,
        coordinates={"lat": image.lat, "lng": image.lng},
        image_source=image.source,
    )


# --- /analyze: the full end-to-end pipeline --------------------------------
class AnalyzeRequest(BaseModel):
    """Request body for /analyze — the whole address-to-rupees pipeline."""
    address: str | None = None
    lat: float | None = None
    lng: float | None = None

    # Roof selection (polygon > points > auto-pick).
    points: list[tuple[int, int]] | None = None
    polygon: list[tuple[int, int]] | None = None
    auto_expand: bool = False
    apply_shading: bool = True

    # Financial context.
    state: str = "Delhi"
    discom_key: str = "Delhi (BSES/Tata Power, illustrative)"
    monthly_consumption_kwh: float = 300.0


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """
    Run the complete analysis: address -> roof -> panels -> generation ->
    financials, returned as one bundled result.

    This is the capstone endpoint the frontend calls to produce a full
    homeowner report from a single request.
    """
    try:
        result = run_full_analysis(
            address=req.address,
            lat=req.lat,
            lng=req.lng,
            points=req.points,
            polygon=req.polygon,
            auto_expand=req.auto_expand,
            apply_shading=req.apply_shading,
            state=req.state,
            discom_key=req.discom_key,
            monthly_consumption_kwh=req.monthly_consumption_kwh,
        )
    except GeocodingError as exc:
        code = 404 if exc.code == "not_found" else 400
        raise HTTPException(status_code=code, detail=exc.message) from exc
    except ImageryError as exc:
        code = 502 if exc.code in {"network_error", "http_error"} else 400
        raise HTTPException(status_code=code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result

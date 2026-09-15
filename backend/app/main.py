"""
PV-Yield backend — FastAPI application entry point.

This file creates the FastAPI app and defines our first endpoints.
Run it locally with:

    uvicorn app.main:app --reload

`app.main:app` means: in the package `app`, file `main.py`, use the
variable named `app`. `--reload` restarts the server automatically
whenever you save a code change (great for development).
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app.services.geocoding import GeocodingError, geocode_address

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

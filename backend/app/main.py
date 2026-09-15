"""
PV-Yield backend — FastAPI application entry point.

This file creates the FastAPI app and defines our first endpoints.
Run it locally with:

    uvicorn app.main:app --reload

`app.main:app` means: in the package `app`, file `main.py`, use the
variable named `app`. `--reload` restarts the server automatically
whenever you save a code change (great for development).
"""

from fastapi import FastAPI

# The FastAPI() instance IS your application. Every endpoint gets
# attached to it. The title/version show up in the auto-generated
# API docs at /docs.
app = FastAPI(
    title="PV-Yield API",
    version="0.1.0",
    description="Address-to-kWh rooftop solar potential analysis.",
)


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

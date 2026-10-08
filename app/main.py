"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.files import router as files_router
from app.api.routes.health import router as health_router

STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Geospatial File Measurement API",
    version="1.0.0",
    description="Upload a KML or Shapefile ZIP and receive feature measurements in metres.",
)
app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
app.include_router(health_router)
app.include_router(files_router)


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    """Serve the small browser interface."""
    return FileResponse(STATIC_DIRECTORY / "index.html")

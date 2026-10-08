"""Service-status endpoint."""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["service"])


@router.get("/health", summary="Check that the API is available")
async def health_check() -> dict[str, str]:
    """Return a small response that confirms the service is running."""
    return {"message": "Geospatial File Measurement API is running."}

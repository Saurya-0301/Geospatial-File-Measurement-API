"""Pydantic models returned by the file API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class FeatureDetails(BaseModel):
    """A source feature and any measurement that can be calculated for it."""

    feature_id: str
    geometry_type: str
    geometry: dict[str, Any] | None
    crs: str | None
    properties: dict[str, Any]
    area_square_meters: float | None = None
    length_meters: float | None = None
    measurement_crs: str | None = None
    measurement_note: str | None = None


class FileRecord(BaseModel):
    """Metadata and processing output for one uploaded geospatial file."""

    id: str = Field(description="Unique identifier assigned to the upload.")
    filename: str = Field(description="Original name of the uploaded file.")
    format: Literal["KML", "SHAPEFILE_ZIP"]
    size_bytes: int = Field(ge=0)
    status: Literal["UPLOADED", "PROCESSING", "COMPLETED", "FAILED"]
    created_at: datetime
    feature_count: int = Field(default=0, ge=0)
    crs: str | None = None
    measurement_crs: str | None = None
    features: list[FeatureDetails] = Field(default_factory=list)
    error: str | None = None

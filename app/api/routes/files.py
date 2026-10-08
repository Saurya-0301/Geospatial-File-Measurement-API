"""Endpoints for uploading, processing, and inspecting geospatial files."""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.schemas.files import FileRecord
from app.services.file_store import (
    UnsupportedFileTypeError,
    UploadTooLargeError,
    get_record,
    save_upload,
    update_record,
)
from app.services.geospatial_processor import FileProcessingError, process_geospatial_file

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/", response_model=FileRecord, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: Annotated[UploadFile, File(description="A .kml file or a .zip archive containing a Shapefile")],
) -> FileRecord:
    """Upload, read, and measure every supported feature in one geospatial file."""
    try:
        stored_upload = await save_upload(file)
    except UnsupportedFileTypeError as error:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)) from error
    except UploadTooLargeError as error:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(error)) from error

    processing_record = update_record(stored_upload.record.model_copy(update={"status": "PROCESSING"}))
    try:
        processed = process_geospatial_file(stored_upload.path, processing_record.format)
        return update_record(
            processing_record.model_copy(
                update={
                    "status": "COMPLETED",
                    "feature_count": len(processed.features),
                    "crs": processed.crs,
                    "measurement_crs": processed.measurement_crs,
                    "features": processed.features,
                }
            )
        )
    except FileProcessingError as error:
        return update_record(processing_record.model_copy(update={"status": "FAILED", "error": str(error)}))


@router.get("/{file_id}", response_model=FileRecord)
async def get_file(file_id: str) -> FileRecord:
    """Return the complete processing result for an uploaded file."""
    record = get_record(file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File record not found.")
    return record

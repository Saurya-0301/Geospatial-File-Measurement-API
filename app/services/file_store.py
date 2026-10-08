"""Safe local storage for uploaded geospatial files."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

from fastapi import UploadFile

from app.schemas.files import FileRecord

PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
UPLOAD_DIRECTORY = PROJECT_DIRECTORY / "uploads"
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
CHUNK_SIZE_BYTES = 1024 * 1024

_records: dict[str, FileRecord] = {}
_records_lock = RLock()


@dataclass(frozen=True)
class StoredUpload:
    """The record returned to clients and its private on-disk location."""

    record: FileRecord
    path: Path


class UnsupportedFileTypeError(ValueError):
    """Raised when an upload is not a supported geospatial file type."""


class UploadTooLargeError(ValueError):
    """Raised when an upload exceeds the configured size limit."""


def validate_upload_filename(filename: str | None) -> tuple[str, str]:
    """Return a safe filename and its normalized supported extension."""
    if not filename:
        raise UnsupportedFileTypeError("The upload must include a filename.")
    safe_filename = Path(filename).name
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in {".kml", ".zip"}:
        raise UnsupportedFileTypeError("Only .kml files and .zip Shapefile archives are supported.")
    return safe_filename, suffix


async def save_upload(upload: UploadFile) -> StoredUpload:
    """Stream an upload to private local storage and create its initial record."""
    original_filename, suffix = validate_upload_filename(upload.filename)
    upload_id = str(uuid4())
    destination = UPLOAD_DIRECTORY / f"{upload_id}{suffix}"
    total_size = 0
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as destination_file:
            while chunk := await upload.read(CHUNK_SIZE_BYTES):
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE_BYTES:
                    raise UploadTooLargeError("The file exceeds the 50 MB upload limit.")
                destination_file.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    record = FileRecord(
        id=upload_id,
        filename=original_filename,
        format="KML" if suffix == ".kml" else "SHAPEFILE_ZIP",
        size_bytes=total_size,
        status="UPLOADED",
        created_at=datetime.now(UTC),
    )
    with _records_lock:
        _records[record.id] = record
    return StoredUpload(record=record, path=destination)


def get_record(file_id: str) -> FileRecord | None:
    """Find a file record created during the current application process."""
    with _records_lock:
        return _records.get(file_id)


def update_record(record: FileRecord) -> FileRecord:
    """Replace a processing record."""
    with _records_lock:
        _records[record.id] = record
    return record

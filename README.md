# Geospatial File Measurement API

A **FastAPI** backend that accepts a KML file or a ZIP archive containing a Shapefile, extracts its features, and returns safe area and length measurements.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Setup & Run](#setup--run)
- [API Endpoints](#api-endpoints)
- [Usage Examples (curl)](#usage-examples-curl)
- [Example Response](#example-response)
- [Shapefile ZIP Requirements](#shapefile-zip-requirements)
- [Running Tests](#running-tests)

---

## Features

- Upload **KML** files and **ZIP archives** containing a Shapefile.
- Extract each feature's ID, geometry type, geometry, source CRS, and attributes.
- Calculate **polygon area** in square metres and **line length** in metres.
- Leave **points** unmeasured and report unsupported geometries safely.
- **Never** calculate measurements directly in latitude/longitude degrees — WGS 84 data (`EPSG:4326`) is automatically projected to the appropriate local **UTM zone** before measurement.
- Reject invalid file types and unsafe or incomplete Shapefile archives.
- Enforces upload limits: **50 MB** per file, **200 MB** max archive expansion.
- In-memory result store allows retrieving past results by UUID during the same server session.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) >= 0.115 |
| ASGI server | [Uvicorn](https://www.uvicorn.org/) |
| Geospatial processing | Custom Python services (UTM projection, KML/SHP parsing) |
| Testing | [pytest](https://pytest.org/) + [httpx](https://www.python-httpx.org/) |

---

## Project Structure

```
geospatial-file-measurement-api/
├── app/
│   ├── main.py                       # FastAPI app entry point
│   ├── api/
│   │   └── routes/
│   │       ├── files.py              # POST /api/files/ and GET /api/files/{id}
│   │       └── health.py             # GET /api/health
│   ├── schemas/
│   │   └── file_schema.py            # Pydantic request/response models
│   ├── services/
│   │   ├── file_store.py             # In-memory result store
│   │   └── geospatial_processor.py   # KML/SHP parsing + UTM measurement
│   └── static/
│       └── index.html                # (Optional) minimal browser interface
├── tests/
│   ├── test_root.py                  # Health check tests
│   └── test_files.py                 # File upload and processing tests
├── uploads/                          # Runtime upload storage (git-ignored)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Requirements

- **Python 3.11 or later**
- No external database required — results are stored in memory.

---

## Setup & Run

### 1. Clone the repository

```bash
git clone https://github.com/Saurya-0301/Geospatial-File-Measurement-API.git
cd Geospatial-File-Measurement-API
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

> **Note for Windows users:** If `python` opens the Microsoft Store, use the full path to your Python executable:
>
> ```powershell
> & "C:\Users\<YourUsername>\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
> ```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the development server

```bash
uvicorn app.main:app --reload
```

The API will be available at: **`http://127.0.0.1:8000`**

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Confirm the API is running. |
| `POST` | `/api/files/` | Upload and process a `.kml` or Shapefile `.zip`. |
| `GET` | `/api/files/{id}` | Retrieve an earlier processing result by UUID. |

### Interactive API Documentation

FastAPI generates interactive documentation automatically after you start the server:

- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

You can use Swagger UI to explore all endpoints and test file uploads directly from the browser — no extra tool needed.

---

## Usage Examples (curl)

> On Windows, use `curl.exe` instead of `curl` if your shell aliases `curl` to PowerShell's `Invoke-WebRequest`.

### Health check

```bash
curl http://127.0.0.1:8000/api/health
```

### Upload a KML file

```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -H "accept: application/json" \
  -F "file=@survey.kml"
```

**Windows PowerShell equivalent:**

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/files/" `
  -H "accept: application/json" `
  -F "file=@survey.kml"
```

### Upload a Shapefile ZIP archive

```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -H "accept: application/json" \
  -F "file=@survey.zip"
```

### Retrieve a previously processed result

```bash
curl "http://127.0.0.1:8000/api/files/<result-id>"
```

Replace `<result-id>` with the `id` field returned from the upload response.

---

## Example Response

```json
{
  "id": "b79e1eb5-1f06-4da5-9ec0-284f8a9a7ed4",
  "filename": "survey.kml",
  "format": "KML",
  "status": "COMPLETED",
  "feature_count": 1,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32618",
  "features": [
    {
      "feature_id": "1",
      "geometry_type": "Polygon",
      "area_square_meters": 937184.71,
      "length_meters": null
    }
  ]
}
```

**Field descriptions:**

| Field | Description |
|---|---|
| `id` | UUID of this processing result (use with `GET /api/files/{id}`) |
| `filename` | Original uploaded filename |
| `format` | Detected format: `KML` or `Shapefile` |
| `status` | `COMPLETED` or `FAILED` |
| `feature_count` | Number of features found |
| `crs` | Source coordinate reference system |
| `measurement_crs` | Projected CRS used for measurement (e.g., UTM zone) |
| `features[].area_square_meters` | Area for Polygon geometries; `null` for others |
| `features[].length_meters` | Length for LineString geometries; `null` for others |

---

## Shapefile ZIP Requirements

The ZIP archive must contain **exactly one matching set** of these core files:

```
dataset.shp    <- geometry
dataset.dbf    <- attributes
dataset.shx    <- shape index
```

Include `dataset.prj` whenever possible — it lets the backend determine the CRS and calculate measurements safely. Without it, the service will attempt to proceed but measurement accuracy cannot be guaranteed.

---

## Running Tests

```bash
pytest
```

The test suite covers:

- API health endpoint
- File-type validation (reject non-KML/ZIP)
- KML file processing and feature extraction
- UTM-based polygon area measurement
- Result retrieval by ID

---

## Notes

- Uploaded files are stored temporarily in the `uploads/` directory (git-ignored).
- Results are held **in memory** — they are lost when the server restarts.
- There is no authentication layer; this is a development/assignment backend.

## Features

- Upload KML files and ZIP archives containing a Shapefile.
- Extract each feature's ID, geometry type, geometry, source CRS, and attributes.
- Calculate polygon area in square metres and line length in metres.
- Leave points unmeasured and report unsupported geometries safely.
- Never calculate measurements directly in latitude/longitude degrees. WGS 84 data (`EPSG:4326`) is projected to an appropriate local UTM zone before measurement.
- Reject invalid file types and unsafe or incomplete Shapefile archives.
- Limit uploads to 50 MB and archive expansion to 200 MB.

## Requirements

- Python 3.11 or later

## Setup and run

From the project directory, create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the backend:

```powershell
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

If Windows routes `python` to the Microsoft Store, use your installed Python executable instead:

```powershell
& "C:\Users\saury\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
```

## API documentation

FastAPI generates interactive documentation automatically:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Confirm the API is running. |
| `POST` | `/api/files/` | Upload and process a `.kml` or Shapefile `.zip`. |
| `GET` | `/api/files/{id}` | Retrieve an earlier processing result while the server is running. |

### Upload a file

Use `curl` (on Windows, use `curl.exe`):

```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -H "accept: application/json" \
  -F "file=@survey.kml"
```

For a Shapefile archive:

```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -H "accept: application/json" \
  -F "file=@survey.zip"
```

Example response:

```json
{
  "id": "b79e1eb5-1f06-4da5-9ec0-284f8a9a7ed4",
  "filename": "survey.kml",
  "format": "KML",
  "status": "COMPLETED",
  "feature_count": 1,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32618",
  "features": [
    {
      "feature_id": "1",
      "geometry_type": "Polygon",
      "area_square_meters": 937184.71,
      "length_meters": null
    }
  ]
}
```

### Retrieve a result

```bash
curl "http://127.0.0.1:8000/api/files/b79e1eb5-1f06-4da5-9ec0-284f8a9a7ed4"
```

Records are kept in memory while the API process runs. Uploaded source files are stored in `uploads/`, which is excluded from version control.

## Shapefile ZIP requirements

The ZIP must contain exactly one matching set of these core files:

```text
dataset.shp
dataset.shx
dataset.dbf
```

Include `dataset.prj` whenever possible. It lets the backend determine the data's CRS and calculate measurements safely.

## Tests

Run the automated test suite:

```powershell
pytest
```

The tests cover service health, file-type validation, KML processing, UTM-based polygon measurement, and result lookup.

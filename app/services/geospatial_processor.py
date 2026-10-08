"""Read supported files and calculate metre-based geospatial measurements."""

from __future__ import annotations

import math
import re
import struct
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from zipfile import BadZipFile, ZipFile

from app.schemas.files import FeatureDetails

MAX_UNCOMPRESSED_ARCHIVE_BYTES = 200 * 1024 * 1024
WGS84_SEMI_MAJOR_AXIS = 6_378_137.0
WGS84_ECCENTRICITY_SQUARED = 0.00669437999014


class FileProcessingError(ValueError):
    """Raised when a supported upload does not contain readable geospatial data."""


@dataclass(frozen=True)
class ProcessedFile:
    crs: str | None
    measurement_crs: str | None
    features: list[FeatureDetails]


def process_geospatial_file(path: Path, file_format: str) -> ProcessedFile:
    """Read one stored KML or Shapefile ZIP and measure every readable feature."""
    if file_format == "KML":
        raw_features, crs, coordinate_mode = _read_kml(path)
    elif file_format == "SHAPEFILE_ZIP":
        raw_features, crs, coordinate_mode = _read_shapefile_zip(path)
    else:
        raise FileProcessingError("The uploaded file format is not supported.")
    features: list[FeatureDetails] = []
    measurement_crs_values: set[str] = set()
    for feature_id, geometry, properties in raw_features:
        feature = _build_feature(feature_id, geometry, properties, crs, coordinate_mode)
        features.append(feature)
        if feature.measurement_crs:
            measurement_crs_values.add(feature.measurement_crs)
    if not features:
        raise FileProcessingError("No readable features were found in the uploaded file.")
    measurement_crs = next(iter(measurement_crs_values)) if len(measurement_crs_values) == 1 else "Feature-specific local UTM zones" if measurement_crs_values else None
    return ProcessedFile(crs=crs, measurement_crs=measurement_crs, features=features)


def _read_kml(path: Path) -> tuple[list[tuple[str, dict[str, Any], dict[str, Any]]], str, str]:
    try:
        root = element_tree.parse(path).getroot()
    except (element_tree.ParseError, OSError) as error:
        raise FileProcessingError("The KML file could not be read.") from error
    features = []
    for index, placemark in enumerate((element for element in root.iter() if _local_name(element.tag) == "Placemark"), start=1):
        geometry = _kml_geometry(placemark)
        if geometry is not None:
            features.append((str(index), geometry, _kml_properties(placemark)))
    return features, "EPSG:4326", "wgs84_geographic"


def _kml_properties(placemark: element_tree.Element) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for element in placemark.iter():
        name = _local_name(element.tag)
        if name == "name" and element.text and "name" not in properties:
            properties["name"] = element.text.strip()
        elif name == "Data" and element.attrib.get("name"):
            value = next((child.text for child in element.iter() if _local_name(child.tag) == "value"), None)
            properties[element.attrib["name"]] = value.strip() if value else None
        elif name == "SimpleData" and element.attrib.get("name"):
            properties[element.attrib["name"]] = element.text.strip() if element.text else None
    return properties


def _kml_geometry(container: element_tree.Element) -> dict[str, Any] | None:
    tags = {"Point", "LineString", "Polygon", "MultiGeometry"}
    element = next((item for item in container.iter() if _local_name(item.tag) in tags), None)
    return _parse_kml_geometry(element) if element is not None else None


def _parse_kml_geometry(element: element_tree.Element) -> dict[str, Any] | None:
    geometry_type = _local_name(element.tag)
    if geometry_type == "Point":
        coordinates = _coordinates_from_element(element)
        return {"type": "Point", "coordinates": coordinates[0]} if coordinates else None
    if geometry_type == "LineString":
        return {"type": "LineString", "coordinates": _coordinates_from_element(element)}
    if geometry_type == "Polygon":
        outer = next((item for item in element.iter() if _local_name(item.tag) == "outerBoundaryIs"), None)
        if outer is None:
            return None
        rings = [_coordinates_from_element(outer)]
        rings.extend(_coordinates_from_element(item) for item in element.iter() if _local_name(item.tag) == "innerBoundaryIs")
        return {"type": "Polygon", "coordinates": rings}
    if geometry_type == "MultiGeometry":
        geometries = []
        for child in element.iter():
            if child is not element and _local_name(child.tag) in {"Point", "LineString", "Polygon"}:
                parsed = _parse_kml_geometry(child)
                if parsed is not None:
                    geometries.append(parsed)
        return {"type": "GeometryCollection", "geometries": geometries}
    return None


def _coordinates_from_element(element: element_tree.Element) -> list[list[float]]:
    node = next((item for item in element.iter() if _local_name(item.tag) == "coordinates"), None)
    if node is None or not node.text:
        return []
    result = []
    for item in node.text.replace("\n", " ").split():
        values = item.split(",")
        if len(values) >= 2:
            result.append([float(values[0]), float(values[1])])
    return result


def _read_shapefile_zip(path: Path) -> tuple[list[tuple[str, dict[str, Any], dict[str, Any]]], str | None, str]:
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if sum(member.file_size for member in members) > MAX_UNCOMPRESSED_ARCHIVE_BYTES:
                raise FileProcessingError("The archive expands beyond the 200 MB safety limit.")
            if any(Path(member.filename).is_absolute() or ".." in Path(member.filename).parts for member in members):
                raise FileProcessingError("The archive contains an unsafe path.")
            shp_files = [member.filename for member in members if member.filename.lower().endswith(".shp")]
            if len(shp_files) != 1:
                raise FileProcessingError("The ZIP archive must contain exactly one .shp file.")
            shp_name = shp_files[0]
            stem = shp_name.rsplit(".", 1)[0]
            names = {member.filename.lower(): member.filename for member in members}
            missing = [extension for extension in (".shx", ".dbf") if f"{stem}{extension}".lower() not in names]
            if missing:
                raise FileProcessingError("The Shapefile ZIP must include matching .shp, .shx, and .dbf files.")
            shp_data = archive.read(shp_name)
            dbf_data = archive.read(names[f"{stem}.dbf".lower()])
            prj_name = names.get(f"{stem}.prj".lower())
            prj = archive.read(prj_name).decode("utf-8", errors="replace") if prj_name else None
    except (BadZipFile, OSError) as error:
        raise FileProcessingError("The uploaded ZIP is not a readable Shapefile archive.") from error
    geometries = _parse_shp(shp_data)
    attributes = _parse_dbf(dbf_data)
    crs, coordinate_mode = _classify_prj(prj)
    features = [(str(index), geometry, attributes[index - 1] if index <= len(attributes) else {}) for index, geometry in enumerate(geometries, start=1)]
    return features, crs, coordinate_mode


def _parse_shp(data: bytes) -> list[dict[str, Any]]:
    if len(data) < 100 or struct.unpack_from(">i", data, 0)[0] != 9994:
        raise FileProcessingError("The .shp component is not a valid Shapefile.")
    geometries, position = [], 100
    while position + 8 <= len(data):
        _, content_words = struct.unpack_from(">2i", data, position)
        position += 8
        content = data[position : position + content_words * 2]
        position += content_words * 2
        if len(content) < 4:
            raise FileProcessingError("A Shapefile record is incomplete.")
        shape_type = struct.unpack_from("<i", content, 0)[0]
        if shape_type == 0:
            geometries.append({"type": "Null", "coordinates": None})
        elif shape_type == 1 and len(content) >= 20:
            geometries.append({"type": "Point", "coordinates": list(struct.unpack_from("<2d", content, 4))})
        elif shape_type in {3, 5}:
            geometries.append(_parse_multipart_shape(content, "LineString" if shape_type == 3 else "Polygon"))
        elif shape_type == 8:
            count = struct.unpack_from("<i", content, 36)[0]
            geometries.append({"type": "MultiPoint", "coordinates": _read_points(content, 40, count)})
        else:
            geometries.append({"type": f"Unsupported ({shape_type})", "coordinates": None})
    return geometries


def _parse_multipart_shape(content: bytes, geometry_type: str) -> dict[str, Any]:
    if len(content) < 44:
        raise FileProcessingError("A multipart Shapefile record is incomplete.")
    part_count, point_count = struct.unpack_from("<2i", content, 36)
    parts = list(struct.unpack_from(f"<{part_count}i", content, 44))
    points = _read_points(content, 44 + part_count * 4, point_count)
    sequences = [points[start : parts[index + 1] if index + 1 < part_count else point_count] for index, start in enumerate(parts)]
    if geometry_type == "LineString":
        return {"type": "LineString" if len(sequences) == 1 else "MultiLineString", "coordinates": sequences[0] if len(sequences) == 1 else sequences}
    return {"type": "Polygon", "coordinates": sequences}


def _read_points(data: bytes, offset: int, count: int) -> list[list[float]]:
    if offset + count * 16 > len(data):
        raise FileProcessingError("A Shapefile point array is incomplete.")
    return [list(struct.unpack_from("<2d", data, offset + index * 16)) for index in range(count)]


def _parse_dbf(data: bytes) -> list[dict[str, Any]]:
    if len(data) < 33:
        raise FileProcessingError("The .dbf component is not valid.")
    record_count, header_length, record_length = struct.unpack_from("<IHH", data, 4)
    fields, position = [], 32
    while position < header_length - 1:
        descriptor = data[position : position + 32]
        if len(descriptor) < 32:
            break
        fields.append((descriptor[:11].split(b"\x00", 1)[0].decode("latin-1").strip(), chr(descriptor[11]), descriptor[16]))
        position += 32
    records, position = [], header_length
    for _ in range(record_count):
        row, position = data[position : position + record_length], position + record_length
        if len(row) < record_length or row[:1] == b"*":
            records.append({})
            continue
        values, cursor = {}, 1
        for name, field_type, length in fields:
            raw = row[cursor : cursor + length].decode("latin-1").strip()
            cursor += length
            values[name] = _parse_dbf_value(raw, field_type)
        records.append(values)
    return records


def _parse_dbf_value(value: str, field_type: str) -> Any:
    if not value:
        return None
    if field_type in {"N", "F"}:
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            return value
    if field_type == "L":
        return value.upper() in {"Y", "T"}
    return value


def _classify_prj(prj: str | None) -> tuple[str | None, str]:
    if not prj:
        return None, "unknown"
    upper, match = prj.upper(), re.search(r'AUTHORITY\["EPSG","(\d+)"\]', prj, flags=re.IGNORECASE)
    epsg = f"EPSG:{match.group(1)}" if match else None
    if "GEOGCS" in upper or "GEODCRS" in upper:
        return ("EPSG:4326", "wgs84_geographic") if "WGS 84" in upper or "WGS_1984" in upper or "4326" in upper else (epsg or "Geographic CRS", "unknown_geographic")
    if "PROJCS" in upper or "PROJCRS" in upper:
        return (epsg or "Projected CRS (metres)", "projected_meters") if "METRE" in upper or "METER" in upper else (epsg or "Projected CRS", "unknown")
    return None, "unknown"


def _build_feature(feature_id: str, geometry: dict[str, Any], properties: dict[str, Any], crs: str | None, coordinate_mode: str) -> FeatureDetails:
    feature = FeatureDetails(feature_id=feature_id, geometry_type=geometry.get("type", "Unknown"), geometry=geometry, crs=crs, properties=properties)
    if geometry.get("type") in {"Point", "MultiPoint"}:
        return feature.model_copy(update={"measurement_note": "Points do not require a measurement."})
    if geometry.get("coordinates") is None:
        return feature.model_copy(update={"measurement_note": "This geometry type is not supported for measurement."})
    try:
        if coordinate_mode == "wgs84_geographic":
            measured_geometry, measurement_crs = _project_geometry_to_utm(geometry)
        elif coordinate_mode == "projected_meters":
            measured_geometry, measurement_crs = geometry, crs or "Projected CRS (metres)"
        elif coordinate_mode == "unknown_geographic":
            return feature.model_copy(update={"measurement_note": "This geographic CRS is not WGS 84, so it cannot be safely transformed."})
        else:
            return feature.model_copy(update={"measurement_note": "The file has no usable CRS, so measurements cannot be calculated safely."})
        area, length = _measure_geometry(measured_geometry)
        return feature.model_copy(update={"area_square_meters": area, "length_meters": length, "measurement_crs": measurement_crs, "measurement_note": None if area is not None or length is not None else "This geometry type is not supported for measurement."})
    except (TypeError, ValueError, ZeroDivisionError) as error:
        return feature.model_copy(update={"measurement_note": f"Measurement could not be calculated: {error}"})


def _project_geometry_to_utm(geometry: dict[str, Any]) -> tuple[dict[str, Any], str]:
    positions = list(_positions(geometry))
    if not positions:
        raise ValueError("The geometry does not contain coordinate positions.")
    longitude = sum(point[0] for point in positions) / len(positions)
    latitude = sum(point[1] for point in positions) / len(positions)
    zone, northern = max(1, min(60, int((longitude + 180) / 6) + 1)), latitude >= 0
    epsg = 32600 + zone if northern else 32700 + zone
    return _map_positions(geometry, lambda point: list(_utm_forward(point[0], point[1], zone, northern))), f"EPSG:{epsg}"


def _positions(geometry: dict[str, Any]) -> Iterable[list[float]]:
    geometry_type = geometry.get("type")
    if geometry_type == "Point":
        yield geometry["coordinates"]
    elif geometry_type in {"LineString", "MultiPoint"}:
        yield from geometry["coordinates"]
    elif geometry_type in {"Polygon", "MultiLineString"}:
        for sequence in geometry["coordinates"]:
            yield from sequence
    elif geometry_type == "GeometryCollection":
        for item in geometry["geometries"]:
            yield from _positions(item)


def _map_positions(geometry: dict[str, Any], transform: Any) -> dict[str, Any]:
    geometry_type = geometry["type"]
    if geometry_type == "Point":
        return {"type": geometry_type, "coordinates": transform(geometry["coordinates"])}
    if geometry_type in {"LineString", "MultiPoint"}:
        return {"type": geometry_type, "coordinates": [transform(point) for point in geometry["coordinates"]]}
    if geometry_type in {"Polygon", "MultiLineString"}:
        return {"type": geometry_type, "coordinates": [[transform(point) for point in sequence] for sequence in geometry["coordinates"]]}
    if geometry_type == "GeometryCollection":
        return {"type": geometry_type, "geometries": [_map_positions(item, transform) for item in geometry["geometries"]]}
    return geometry


def _utm_forward(longitude: float, latitude: float, zone: int, northern: bool) -> tuple[float, float]:
    latitude_radians, longitude_radians = math.radians(latitude), math.radians(longitude)
    origin = math.radians((zone - 1) * 6 - 177)
    eccentricity_prime = WGS84_ECCENTRICITY_SQUARED / (1 - WGS84_ECCENTRICITY_SQUARED)
    sine, cosine, tangent = math.sin(latitude_radians), math.cos(latitude_radians), math.tan(latitude_radians)
    n = WGS84_SEMI_MAJOR_AXIS / math.sqrt(1 - WGS84_ECCENTRICITY_SQUARED * sine**2)
    t, c, a = tangent**2, eccentricity_prime * cosine**2, cosine * (longitude_radians - origin)
    m = WGS84_SEMI_MAJOR_AXIS * ((1 - WGS84_ECCENTRICITY_SQUARED / 4 - 3 * WGS84_ECCENTRICITY_SQUARED**2 / 64 - 5 * WGS84_ECCENTRICITY_SQUARED**3 / 256) * latitude_radians - (3 * WGS84_ECCENTRICITY_SQUARED / 8 + 3 * WGS84_ECCENTRICITY_SQUARED**2 / 32 + 45 * WGS84_ECCENTRICITY_SQUARED**3 / 1024) * math.sin(2 * latitude_radians) + (15 * WGS84_ECCENTRICITY_SQUARED**2 / 256 + 45 * WGS84_ECCENTRICITY_SQUARED**3 / 1024) * math.sin(4 * latitude_radians) - 35 * WGS84_ECCENTRICITY_SQUARED**3 / 3072 * math.sin(6 * latitude_radians))
    scale = 0.9996
    easting = scale * n * (a + (1 - t + c) * a**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * eccentricity_prime) * a**5 / 120) + 500000
    northing = scale * (m + n * tangent * (a**2 / 2 + (5 - t + 9 * c + 4 * c**2) * a**4 / 24 + (61 - 58 * t + t**2 + 600 * c - 330 * eccentricity_prime) * a**6 / 720))
    return easting, northing if northern else northing + 10_000_000


def _measure_geometry(geometry: dict[str, Any]) -> tuple[float | None, float | None]:
    geometry_type = geometry.get("type")
    if geometry_type == "LineString":
        return None, _line_length(geometry["coordinates"])
    if geometry_type == "MultiLineString":
        return None, sum(_line_length(line) for line in geometry["coordinates"])
    if geometry_type == "Polygon":
        return _polygon_area(geometry["coordinates"]), None
    if geometry_type == "GeometryCollection":
        values = [_measure_geometry(item) for item in geometry["geometries"]]
        areas, lengths = [area for area, _ in values if area is not None], [length for _, length in values if length is not None]
        return sum(areas) if areas else None, sum(lengths) if lengths else None
    return None, None


def _line_length(points: list[list[float]]) -> float:
    return sum(math.dist(start, end) for start, end in zip(points, points[1:]))


def _polygon_area(rings: list[list[list[float]]]) -> float:
    areas = [abs(_signed_ring_area(ring)) for ring in rings if len(ring) >= 3]
    return max(0.0, areas[0] - sum(areas[1:])) if areas else 0.0


def _signed_ring_area(ring: list[list[float]]) -> float:
    return 0.5 * sum(start[0] * end[1] - end[0] * start[1] for start, end in zip(ring, ring[1:] + ring[:1]))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

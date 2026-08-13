from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import requests
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.merge import merge
import rasterio
import shapely
from shapely.geometry import box, mapping, shape

USER_AGENT = "caspar-water-solar-siting/0.1"


class AcquisitionError(RuntimeError):
    pass


def _request(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    *,
    post: bool = False,
) -> requests.Response:
    for attempt in range(4):
        try:
            if post:
                response = session.post(url, data=params, timeout=(20, 180))
            else:
                response = session.get(url, params=params, timeout=(20, 180))
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            if attempt == 3:
                raise AcquisitionError(f"request failed for {url}: {error}") from error
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def fetch_arcgis_vector(
    session: requests.Session,
    source: dict[str, Any],
    bbox: list[float],
    destination: Path,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    page_size = 1000
    query_url = source["url"].rstrip("/") + "/query"
    clip_geometry = box(*bbox)
    spatial_params = {
        "where": source.get("where", "1=1"),
        "geometry": ",".join(str(value) for value in bbox),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }
    id_payload = _request(
        session,
        query_url,
        {
            **spatial_params,
            "f": "json",
            "returnIdsOnly": "true",
            "returnGeometry": "false",
        },
    ).json()
    if "error" in id_payload:
        raise AcquisitionError(f"{source['url']}: {id_payload['error']}")
    object_ids = sorted(id_payload.get("objectIds") or [])
    print(f"  {len(object_ids)} matching features", flush=True)

    for start in range(0, len(object_ids), page_size):
        batch = object_ids[start : start + page_size]
        params = {
            "f": "geojson",
            "objectIds": ",".join(str(object_id) for object_id in batch),
            "outFields": ",".join(source["fields"]),
            "returnGeometry": "true",
            "outSR": "4326",
        }
        payload = _request(session, query_url, params, post=True).json()
        if "error" in payload:
            raise AcquisitionError(f"{source['url']}: {payload['error']}")
        for feature in payload.get("features", []):
            geometry = feature.get("geometry")
            if geometry is not None:
                clipped = shapely.intersection(
                    shapely.make_valid(shape(geometry)),
                    clip_geometry,
                    grid_size=1e-8,
                )
                if clipped.is_empty:
                    continue
                feature["geometry"] = mapping(clipped)
            features.append(feature)
        print(
            f"  downloaded {min(start + len(batch), len(object_ids))}/{len(object_ids)}",
            flush=True,
        )

    unique_features: dict[Any, dict[str, Any]] = {}
    anonymous_features = []
    for feature in features:
        feature_id = feature.get("id")
        if feature_id is None:
            anonymous_features.append(feature)
        else:
            unique_features.setdefault(feature_id, feature)
    features = list(unique_features.values()) + anonymous_features
    collection = {
        "type": "FeatureCollection",
        "features": features,
    }
    destination.write_text(json.dumps(collection, separators=(",", ":")))
    return {"feature_count": len(features)}


def fetch_arcgis_raster(
    session: requests.Session,
    source: dict[str, Any],
    bbox: list[float],
    destination: Path,
) -> dict[str, Any]:
    output_crs = source.get("output_crs", "EPSG:3857")
    output_wkid = output_crs.rsplit(":", 1)[-1]
    transformer = Transformer.from_crs("EPSG:4326", output_crs, always_xy=True)
    xmin, ymin = transformer.transform(bbox[0], bbox[1])
    xmax, ymax = transformer.transform(bbox[2], bbox[3])
    pixel_size = float(source["pixel_size_m"])
    width = math.ceil((xmax - xmin) / pixel_size)
    height = math.ceil((ymax - ymin) / pixel_size)
    if width > 8000 or height > 8000:
        raise AcquisitionError(
            f"requested raster is {width}x{height}; increase pixel_size_m or add tiling"
        )

    tile_size = 2000
    memories: list[MemoryFile] = []
    datasets = []
    tile_count = math.ceil(width / tile_size) * math.ceil(height / tile_size)
    completed = 0
    try:
        for row in range(0, height, tile_size):
            tile_height = min(tile_size, height - row)
            tile_ymin = ymin + row * pixel_size
            tile_ymax = tile_ymin + tile_height * pixel_size
            for column in range(0, width, tile_size):
                tile_width = min(tile_size, width - column)
                tile_xmin = xmin + column * pixel_size
                tile_xmax = tile_xmin + tile_width * pixel_size
                params = {
                    "f": "image",
                    "bbox": f"{tile_xmin},{tile_ymin},{tile_xmax},{tile_ymax}",
                    "bboxSR": output_wkid,
                    "imageSR": output_wkid,
                    "size": f"{tile_width},{tile_height}",
                    "format": "tiff",
                    "pixelType": "F32",
                    "interpolation": "RSP_BilinearInterpolation",
                }
                response = _request(
                    session, source["url"].rstrip("/") + "/exportImage", params
                )
                content_type = response.headers.get("content-type", "")
                if (
                    "image" not in content_type
                    and "tiff" not in content_type
                    and "octet-stream" not in content_type
                ):
                    raise AcquisitionError(
                        f"{source['url']} returned {content_type}: "
                        f"{response.text[:500]}"
                    )
                memory = MemoryFile(response.content)
                memories.append(memory)
                datasets.append(memory.open())
                completed += 1
                print(f"  downloaded raster tile {completed}/{tile_count}", flush=True)

        mosaic, transform = merge(datasets)
        profile = datasets[0].profile.copy()
        profile.update(
            width=mosaic.shape[2],
            height=mosaic.shape[1],
            transform=transform,
            compress="deflate",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        with rasterio.open(destination, "w", **profile) as output:
            output.write(mosaic)
    finally:
        for dataset in datasets:
            dataset.close()
        for memory in memories:
            memory.close()
    return {
        "width": width,
        "height": height,
        "pixel_size_m": pixel_size,
        "output_crs": output_crs,
    }


def fetch_ogc_raster(
    session: requests.Session,
    source: dict[str, Any],
    bbox: list[float],
    destination: Path,
) -> dict[str, Any]:
    output_crs = source["output_crs"]
    transformer = Transformer.from_crs("EPSG:4326", output_crs, always_xy=True)
    xmin, ymin = transformer.transform(bbox[0], bbox[1])
    xmax, ymax = transformer.transform(bbox[2], bbox[3])
    pixel_size = float(source["pixel_size_m"])
    width = math.ceil((xmax - xmin) / pixel_size)
    height = math.ceil((ymax - ymin) / pixel_size)
    tile_size = 2000
    memories: list[MemoryFile] = []
    datasets = []
    tile_count = math.ceil(width / tile_size) * math.ceil(height / tile_size)
    completed = 0
    try:
        for row in range(0, height, tile_size):
            tile_height = min(tile_size, height - row)
            tile_ymin = ymin + row * pixel_size
            tile_ymax = tile_ymin + tile_height * pixel_size
            for column in range(0, width, tile_size):
                tile_width = min(tile_size, width - column)
                tile_xmin = xmin + column * pixel_size
                tile_xmax = tile_xmin + tile_width * pixel_size
                if source["kind"] == "wcs-raster":
                    params = {
                        "service": "WCS",
                        "version": "1.0.0",
                        "request": "GetCoverage",
                        "coverage": source["layer"],
                        "crs": output_crs,
                        "response_crs": output_crs,
                        "bbox": f"{tile_xmin},{tile_ymin},{tile_xmax},{tile_ymax}",
                        "width": tile_width,
                        "height": tile_height,
                        "format": "GeoTIFF",
                    }
                else:
                    params = {
                        "service": "WMS",
                        "version": "1.1.1",
                        "request": "GetMap",
                        "layers": source["layer"],
                        "styles": "",
                        "srs": output_crs,
                        "bbox": f"{tile_xmin},{tile_ymin},{tile_xmax},{tile_ymax}",
                        "width": tile_width,
                        "height": tile_height,
                        "format": "image/geotiff",
                    }
                response = _request(session, source["url"], params)
                if "tiff" not in response.headers.get("content-type", ""):
                    raise AcquisitionError(
                        f"{source['url']} returned "
                        f"{response.headers.get('content-type')}: {response.text[:500]}"
                    )
                memory = MemoryFile(response.content)
                memories.append(memory)
                datasets.append(memory.open())
                completed += 1
                print(f"  downloaded raster tile {completed}/{tile_count}", flush=True)

        mosaic, transform = merge(datasets)
        profile = datasets[0].profile.copy()
        profile.update(
            width=mosaic.shape[2],
            height=mosaic.shape[1],
            transform=transform,
            compress="deflate",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        with rasterio.open(destination, "w", **profile) as output:
            output.write(mosaic)
    finally:
        for dataset in datasets:
            dataset.close()
        for memory in memories:
            memory.close()
    return {
        "width": width,
        "height": height,
        "pixel_size_m": pixel_size,
        "output_crs": output_crs,
        "layer": source["layer"],
    }


def fetch_nasa_power(
    session: requests.Session,
    source: dict[str, Any],
    bbox: list[float],
    destination: Path,
) -> dict[str, Any]:
    center_lon = (bbox[0] + bbox[2]) / 2
    center_lat = (bbox[1] + bbox[3]) / 2
    # The regional endpoint requires at least two degrees on each axis.
    params = {
        "latitude-min": center_lat - 1.1,
        "latitude-max": center_lat + 1.1,
        "longitude-min": center_lon - 1.1,
        "longitude-max": center_lon + 1.1,
        "parameters": source["parameter"],
        "community": "RE",
        "format": "JSON",
    }
    response = _request(session, source["url"], params)
    payload = response.json()
    if "features" not in payload:
        raise AcquisitionError(f"NASA POWER returned no features: {payload}")
    destination.write_text(json.dumps(payload, separators=(",", ":")))
    return {"point_count": len(payload["features"]), "parameter": source["parameter"]}


def fetch_arcgis_related_table(
    session: requests.Session,
    source: dict[str, Any],
    data_dir: Path,
    destination: Path,
) -> dict[str, Any]:
    id_payload = json.loads((data_dir / source["ids_from"]).read_text())
    source_field = source["source_id_field"]
    ids = sorted(
        {
            str(feature["properties"][source_field]).lstrip("0")
            for feature in id_payload["features"]
            if feature["properties"].get(source_field) not in (None, "")
        }
    )
    if not ids:
        raise AcquisitionError(f"{source['ids_from']} contains no {source_field} values")

    table_field = source["table_id_field"]
    where = f"{table_field} IN ({','.join(ids)})"
    query_url = source["url"].rstrip("/") + "/query"
    oid_payload = _request(
        session,
        query_url,
        {
            "f": "json",
            "where": where,
            "returnIdsOnly": "true",
            "returnGeometry": "false",
        },
        post=True,
    ).json()
    if "error" in oid_payload:
        raise AcquisitionError(f"{source['url']}: {oid_payload['error']}")
    object_ids = sorted(oid_payload.get("objectIds") or [])
    print(f"  {len(object_ids)} matching rows", flush=True)

    rows = []
    page_size = 2000
    for start in range(0, len(object_ids), page_size):
        batch = object_ids[start : start + page_size]
        payload = _request(
            session,
            query_url,
            {
                "f": "json",
                "objectIds": ",".join(str(object_id) for object_id in batch),
                "outFields": ",".join(source["fields"]),
                "returnGeometry": "false",
            },
            post=True,
        ).json()
        if "error" in payload:
            raise AcquisitionError(f"{source['url']}: {payload['error']}")
        rows.extend(feature["attributes"] for feature in payload.get("features", []))
        print(
            f"  downloaded {min(start + len(batch), len(object_ids))}/{len(object_ids)}",
            flush=True,
        )

    destination.write_text(json.dumps({"records": rows}, separators=(",", ":")))
    return {"row_count": len(rows), "related_id_count": len(ids)}


def fetch_all(config: dict[str, Any], data_dir: Path, refresh: bool = False) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    bbox = config["area"]["bbox"]
    provenance_path = data_dir / "provenance.json"
    if provenance_path.exists():
        provenance = json.loads(provenance_path.read_text())
        provenance["area"] = config["area"]["name"]
    else:
        provenance = {"area": config["area"]["name"], "sources": {}}

    for name, source in config["sources"].items():
        destination = data_dir / source["filename"]
        cache_fields = set(source.get("cache_fields", []))
        cached_payload = (
            json.loads(destination.read_text())
            if destination.exists() and cache_fields and not refresh
            else {}
        )
        cached_features = cached_payload.get("features", [])
        cache_has_fields = not cache_fields or (
            cached_features
            and cache_fields.issubset(cached_features[0].get("properties", {}))
        )
        if destination.exists() and not refresh and cache_has_fields:
            details = dict(provenance.get("sources", {}).get(name, {}))
            details["cached"] = True
            if source["kind"] == "arcgis-vector" and "feature_count" not in details:
                details["feature_count"] = len(
                    json.loads(destination.read_text()).get("features", [])
                )
            elif source["kind"] == "nasa-power" and "point_count" not in details:
                details["point_count"] = len(
                    json.loads(destination.read_text()).get("features", [])
                )
            elif source["kind"] == "arcgis-related-table" and "row_count" not in details:
                details["row_count"] = len(
                    json.loads(destination.read_text()).get("records", [])
                )
            print(f"{name}: cached", flush=True)
        else:
            if destination.exists() and not refresh and not cache_has_fields:
                print(f"{name}: cache missing requested fields", flush=True)
            print(f"{name}: downloading", flush=True)
            kind = source["kind"]
            if kind == "arcgis-vector":
                details = fetch_arcgis_vector(session, source, bbox, destination)
            elif kind == "arcgis-raster":
                details = fetch_arcgis_raster(session, source, bbox, destination)
            elif kind in {"wms-raster", "wcs-raster"}:
                details = fetch_ogc_raster(session, source, bbox, destination)
            elif kind == "nasa-power":
                details = fetch_nasa_power(session, source, bbox, destination)
            elif kind == "arcgis-related-table":
                details = fetch_arcgis_related_table(
                    session, source, data_dir, destination
                )
            else:
                raise AcquisitionError(f"unsupported source kind {kind!r}")
            details["cached"] = False
            print(f"{name}: complete", flush=True)

        details.update(
            {
                "url": source["url"],
                "filename": source["filename"],
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "retrieved_unix": int(destination.stat().st_mtime),
            }
        )
        provenance["sources"][name] = details

    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")

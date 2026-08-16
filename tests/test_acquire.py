from pathlib import Path

import pytest

from solar_siting.acquire import fetch_all, fetch_nasa_power


class Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class Session:
    def __init__(self):
        self.params = None

    def get(self, url, params, timeout):
        self.params = params
        return Response({"features": [{"type": "Feature"}]})


def test_nasa_power_expands_small_region(tmp_path: Path):
    session = Session()
    destination = tmp_path / "solar.json"
    source = {
        "url": "https://example.test/power",
        "parameter": "ALLSKY_SFC_SW_DWN",
    }

    details = fetch_nasa_power(
        session,
        source,
        [-124.15, 38.74, -123.20, 40.05],
        destination,
    )

    assert (
        session.params["latitude-max"] - session.params["latitude-min"]
        == pytest.approx(2.2)
    )
    assert (
        session.params["longitude-max"] - session.params["longitude-min"]
        == pytest.approx(2.2)
    )
    assert details["point_count"] == 1
    assert destination.exists()


def test_fetch_all_refreshes_vector_missing_cache_fields(tmp_path, monkeypatch):
    destination = tmp_path / "parcels.geojson"
    destination.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature",'
        '"properties":{"APNFULL":"1"},"geometry":null}]}'
    )
    calls = []

    def fetch(session, source, bbox, path):
        calls.append(path)
        path.write_text(
            '{"type":"FeatureCollection","features":[{"type":"Feature",'
            '"properties":{"APNFULL":"1","SITUS_ADD":"1 Main St"},'
            '"geometry":null}]}'
        )
        return {"feature_count": 1}

    monkeypatch.setattr("solar_siting.acquire.fetch_arcgis_vector", fetch)
    config = {
        "area": {"name": "Test", "bbox": [0, 0, 1, 1]},
        "sources": {
            "parcels": {
                "kind": "arcgis-vector",
                "url": "https://example.test/parcels",
                "filename": "parcels.geojson",
                "cache_fields": ["SITUS_ADD"],
            }
        },
    }

    fetch_all(config, tmp_path)

    assert calls == [destination]


def test_fetch_all_uses_source_specific_bbox(tmp_path, monkeypatch):
    seen_bbox = None

    def fetch(session, source, bbox, path):
        nonlocal seen_bbox
        seen_bbox = bbox
        path.write_text('{"type":"FeatureCollection","features":[]}')
        return {"feature_count": 0}

    monkeypatch.setattr("solar_siting.acquire.fetch_arcgis_vector", fetch)
    config = {
        "area": {"name": "Test", "bbox": [0, 0, 1, 1]},
        "sources": {
            "transmission": {
                "kind": "arcgis-vector",
                "url": "https://example.test/transmission",
                "filename": "transmission.geojson",
                "bbox": [-1, -2, 3, 4],
            }
        },
    }

    fetch_all(config, tmp_path)

    assert seen_bbox == [-1, -2, 3, 4]

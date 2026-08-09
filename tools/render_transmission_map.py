#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


WIDTH = 860
HEIGHT = 850
LEFT = 32
TOP = 28
MAP_WIDTH = 650
MAP_HEIGHT = 782
LON_MIN = -124.12
LON_MAX = -122.72
LAT_MIN = 38.68
LAT_MAX = 40.08

COUNTY_URL = (
    "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
    "California_County_Boundaries/FeatureServer/0/query"
)
TRANSMISSION_URL = (
    "https://services3.arcgis.com/bWPjFyq029ChCGur/arcgis/rest/services/"
    "Transmission_Line/FeatureServer/2/query"
)
ROADS_URL = (
    "https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHhighway/"
    "SHN_Lines/FeatureServer/0/query"
)


def fetch(url: str, parameters: dict[str, str]) -> dict:
    with urlopen(f"{url}?{urlencode(parameters)}") as response:
        result = json.load(response)
    if "features" not in result:
        raise RuntimeError(result)
    return result


def load_or_fetch(path: Path | None, url: str, parameters: dict[str, str]) -> dict:
    if path:
        return json.loads(path.read_text())
    return fetch(url, parameters)


def project(coordinate: list[float]) -> tuple[float, float]:
    longitude, latitude = coordinate[:2]
    x = LEFT + (longitude - LON_MIN) / (LON_MAX - LON_MIN) * MAP_WIDTH
    y = TOP + (LAT_MAX - latitude) / (LAT_MAX - LAT_MIN) * MAP_HEIGHT
    return x, y


def point_segment_distance(
    point: list[float], start: list[float], end: list[float]
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    ratio = (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    ) / (dx * dx + dy * dy)
    ratio = max(0.0, min(1.0, ratio))
    return math.hypot(
        point[0] - (start[0] + ratio * dx),
        point[1] - (start[1] + ratio * dy),
    )


def simplify(coordinates: list[list[float]], tolerance: float) -> list[list[float]]:
    if len(coordinates) <= 2:
        return coordinates
    start = coordinates[0]
    end = coordinates[-1]
    index, distance = max(
        (
            (index, point_segment_distance(point, start, end))
            for index, point in enumerate(coordinates[1:-1], 1)
        ),
        key=lambda item: item[1],
    )
    if distance <= tolerance:
        return [start, end]
    return simplify(coordinates[: index + 1], tolerance)[:-1] + simplify(
        coordinates[index:], tolerance
    )


def line_path(coordinates: list[list[float]], tolerance: float) -> str:
    points = [project(point) for point in simplify(coordinates, tolerance)]
    return "M" + " ".join(
        f"{x:.1f},{y:.1f}" if index == 0 else f"L{x:.1f},{y:.1f}"
        for index, (x, y) in enumerate(points)
    )


def geometry_paths(geometry: dict, tolerance: float = 0.001) -> list[str]:
    geometry_type = geometry["type"]
    coordinates = geometry["coordinates"]
    if geometry_type == "LineString":
        return [line_path(coordinates, tolerance)]
    if geometry_type == "MultiLineString":
        return [line_path(line, tolerance) for line in coordinates]
    if geometry_type == "Polygon":
        return [line_path(ring, tolerance) + "Z" for ring in coordinates]
    if geometry_type == "MultiPolygon":
        return [
            line_path(ring, tolerance) + "Z"
            for polygon in coordinates
            for ring in polygon
        ]
    raise ValueError(f"Unsupported geometry type: {geometry_type}")


def text(x: float, y: float, value: str, css_class: str) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{css_class}">'
        f"{html.escape(value)}</text>"
    )


def ocean_path(county: dict) -> str:
    geometry = county["features"][0]["geometry"]
    polygons = (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )
    ring = max(
        (ring for polygon in polygons for ring in polygon),
        key=len,
    )
    south_index = min(range(len(ring)), key=lambda index: ring[index][1])
    north_coast_index = min(range(len(ring)), key=lambda index: ring[index][0])
    coastline = simplify(ring[south_index : north_coast_index + 1], 0.001)
    south_x, _ = project(coastline[0])
    points = [
        (LEFT, TOP + MAP_HEIGHT),
        (south_x, TOP + MAP_HEIGHT),
        *[project(coordinate) for coordinate in coastline],
        (LEFT, TOP),
    ]
    return "M" + " ".join(
        f"{x:.1f},{y:.1f}" if index == 0 else f"L{x:.1f},{y:.1f}"
        for index, (x, y) in enumerate(points)
    ) + "Z"


def render(county: dict, transmission: dict, roads: dict, destination: Path) -> None:
    county_paths = [
        path
        for feature in county["features"]
        for path in geometry_paths(feature["geometry"], 0.0015)
    ]
    road_features = sorted(
        roads["features"],
        key=lambda feature: int(feature["properties"]["Route"]),
        reverse=True,
    )
    towns = [
        ("Leggett", -123.7147, 39.8652, 9, -8),
        ("Laytonville", -123.4828, 39.6882, 9, -8),
        ("Fort Bragg", -123.8053, 39.4457, 9, -8),
        ("Willits", -123.3556, 39.4096, 9, -8),
        ("Caspar", -123.8034, 39.3649, 9, -8),
        ("Mendocino", -123.7995, 39.3077, 9, 18),
        ("Ukiah", -123.2078, 39.1502, 9, -8),
        ("Elk", -123.7086, 39.1302, 9, -8),
        ("Boonville", -123.3661, 39.0091, 9, -8),
        ("Point Arena", -123.6914, 38.9088, 9, -8),
        ("Gualala", -123.5319, 38.7657, 9, -8),
    ]

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        '<title id="title">Road map of Mendocino County and its high-voltage grid</title>',
        '<desc id="desc">Mendocino County with Highways 1 and 101, towns, and mapped 60, 115, and 230 kilovolt transmission lines. The coastal 60 kilovolt network has relatively few connections to the larger inland grid.</desc>',
        """<defs>
          <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="5" stdDeviation="7" flood-opacity=".14"/>
          </filter>
          <style>
            .town{font:650 13px system-ui,sans-serif;fill:#173128;paint-order:stroke;stroke:#f7f4ea;stroke-width:4px;stroke-linejoin:round}
            .road-label{font:750 12px system-ui,sans-serif;fill:#6d6658;paint-order:stroke;stroke:#f7f4ea;stroke-width:4px}
            .legend-title{font:800 15px system-ui,sans-serif;fill:#173128}
            .legend-copy{font:13px system-ui,sans-serif;fill:#52675f}
          </style>
          <clipPath id="county-clip">""",
    ]
    svg.extend(f'<path d="{path}"/>' for path in county_paths)
    svg.extend(
        [
            "</clipPath></defs>",
            f'<path d="{ocean_path(county)}" fill="#cfe4e8"/>',
        ]
    )
    svg.extend(
        f'<path d="{path}" fill="#f7f4ea" stroke="#789184" stroke-width="2"/>'
        for path in county_paths
    )

    svg.append('<g clip-path="url(#county-clip)">')
    for feature in road_features:
        route = int(feature["properties"]["Route"])
        width = 4.2 if route == 101 else 3.2
        color = "#a89d87" if route == 101 else "#c2b69f"
        for path in geometry_paths(feature["geometry"], 0.001):
            svg.append(
                f'<path d="{path}" fill="none" stroke="{color}" '
                f'stroke-width="{width}" stroke-linecap="round"/>'
            )

    transmission_styles = {
        "60": ("#e09a2f", 4.5),
        "115": ("#c65b3f", 5.5),
        "230": ("#843b62", 7.0),
    }
    for feature in transmission["features"]:
        voltage = str(feature["properties"].get("kV", ""))
        if voltage not in transmission_styles:
            continue
        color, width = transmission_styles[voltage]
        for path in geometry_paths(feature["geometry"], 0.0007):
            svg.append(
                f'<path d="{path}" fill="none" stroke="#fffdf7" '
                f'stroke-width="{width + 3}" stroke-linecap="round"/>'
            )
            svg.append(
                f'<path d="{path}" fill="none" stroke="{color}" '
                f'stroke-width="{width}" stroke-linecap="round"/>'
            )
    svg.append("</g>")

    for name, longitude, latitude, dx, dy in towns:
        x, y = project([longitude, latitude])
        svg.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" '
            'fill="#173128" stroke="#fffdf7" stroke-width="2"/>'
        )
        svg.append(text(x + dx, y + dy, name, "town"))

    highway_labels = [
        ("Hwy 1", -123.79, 39.56),
        ("Hwy 101", -123.36, 39.55),
    ]
    for label, longitude, latitude in highway_labels:
        x, y = project([longitude, latitude])
        svg.append(text(x, y, label, "road-label"))

    svg.extend(
        [
            '<g transform="translate(568 48)" filter="url(#shadow)">',
            '<rect width="258" height="150" rx="14" fill="#fffdf7" stroke="#cbd4ca"/>',
            text(22, 34, "Transmission voltage", "legend-title"),
            '<path d="M24 64h55" stroke="#e09a2f" stroke-width="5" stroke-linecap="round"/>',
            text(94, 69, "60 kV", "legend-copy"),
            '<path d="M24 97h55" stroke="#c65b3f" stroke-width="6" stroke-linecap="round"/>',
            text(94, 102, "115 kV", "legend-copy"),
            '<path d="M24 130h55" stroke="#843b62" stroke-width="7" stroke-linecap="round"/>',
            text(94, 135, "230 kV", "legend-copy"),
            "</g>",
            "</svg>",
        ]
    )
    destination.write_text("\n".join(svg) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--county", type=Path)
    parser.add_argument("--transmission", type=Path)
    parser.add_argument("--roads", type=Path)
    parser.add_argument("--output", type=Path, default=Path("site/transmission-map.svg"))
    args = parser.parse_args()

    county = load_or_fetch(
        args.county,
        COUNTY_URL,
        {
            "where": "COUNTY_NAME='Mendocino County'",
            "outFields": "COUNTY_NAME",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        },
    )
    transmission = load_or_fetch(
        args.transmission,
        TRANSMISSION_URL,
        {
            "where": "1=1",
            "geometry": "-124.2,38.6,-122.7,40.1",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "Name,kV,Owner,Status,Type",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        },
    )
    roads = load_or_fetch(
        args.roads,
        ROADS_URL,
        {
            "where": "County='MEN' AND Route IN (1,101)",
            "outFields": "Route,County",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        },
    )
    render(county, transmission, roads, args.output)


if __name__ == "__main__":
    main()

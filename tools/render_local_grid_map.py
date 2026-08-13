#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import math
from pathlib import Path
from urllib.request import Request, urlopen

import geopandas as gpd
import shapely
from shapely.geometry import box


WIDTH = 600
HEIGHT = 720
MAP_LEFT = 20
MAP_TOP = 20
MAP_WIDTH = 560
MAP_HEIGHT = 680

BBOX_WGS84 = box(-123.855, 39.325, -123.78, 39.415)
OSM_ZOOM = 12
ZONE_COLORS = {
    "RL": "#8c6d31",
    "AG": "#e6ab02",
    "RMR": "#6a3d9a",
    "RR": "#e31a1c",
    "FL": "#1b9e77",
    "TP": "#006d2c",
    "OS": "#66c2a5",
    "I": "#1f78b4",
    "PF": "#7570b3",
    "Unclassified": "#969696",
}


def xml_text(value: object) -> str:
    return html.escape(str(value))


def svg_text(x: float, y: float, value: object, css_class: str) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{css_class}">'
        f"{xml_text(value)}</text>"
    )


class Projection:
    def __init__(self, bounds: tuple[float, float, float, float]) -> None:
        min_lon, min_lat, max_lon, max_lat = bounds
        self.min_x, self.min_y = world_pixel(min_lon, max_lat, OSM_ZOOM)
        self.max_x, self.max_y = world_pixel(max_lon, min_lat, OSM_ZOOM)
        self.scale = min(
            MAP_WIDTH / (self.max_x - self.min_x),
            MAP_HEIGHT / (self.max_y - self.min_y),
        )
        content_width = (self.max_x - self.min_x) * self.scale
        content_height = (self.max_y - self.min_y) * self.scale
        self.left = MAP_LEFT + (MAP_WIDTH - content_width) / 2
        self.top = MAP_TOP + (MAP_HEIGHT - content_height) / 2

    def pixel(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.left + (x - self.min_x) * self.scale,
            self.top + (y - self.min_y) * self.scale,
        )

    def point(self, longitude: float, latitude: float) -> tuple[float, float]:
        return self.pixel(*world_pixel(longitude, latitude, OSM_ZOOM))

    def path(self, geometry: object) -> str:
        paths: list[str] = []
        for part in shapely.get_parts(geometry):
            if part.geom_type == "Polygon":
                rings = [part.exterior, *part.interiors]
            elif part.geom_type == "LineString":
                rings = [part]
            else:
                continue
            for ring in rings:
                coordinates = list(ring.coords)
                commands = []
                for index, (x, y, *_) in enumerate(coordinates):
                    svg_x, svg_y = self.point(x, y)
                    commands.append(
                        f"{'M' if index == 0 else 'L'}{svg_x:.1f},{svg_y:.1f}"
                    )
                if part.geom_type == "Polygon":
                    commands.append("Z")
                paths.append(" ".join(commands))
        return " ".join(paths)


def capacity_color(value: object) -> str:
    if value is None or math.isnan(float(value)):
        return "#a9aaa4"
    capacity = float(value)
    if capacity < 200:
        return "#e76f00"
    if capacity < 300:
        return "#e6ab02"
    return "#15583b"


def western_hull_anchor(
    projection: Projection,
    geometry: object,
) -> tuple[float, float]:
    coordinates = shapely.get_coordinates(geometry.convex_hull.boundary)
    points = [projection.point(x, y) for x, y in coordinates]
    target_x = min(x for x, _ in points)
    western_ys = [y for x, y in points if x <= target_x + 0.5]
    return target_x, sum(western_ys) / len(western_ys)


def world_pixel(longitude: float, latitude: float, zoom: int) -> tuple[float, float]:
    scale = 256 * (2**zoom)
    x = (longitude + 180) / 360 * scale
    latitude_radians = math.radians(latitude)
    y = (
        1
        - math.asinh(math.tan(latitude_radians)) / math.pi
    ) / 2 * scale
    return x, y


def osm_tiles(data_dir: Path, projection: Projection) -> list[str]:
    min_lon, min_lat, max_lon, max_lat = BBOX_WGS84.bounds
    min_x, min_y = world_pixel(min_lon, max_lat, OSM_ZOOM)
    max_x, max_y = world_pixel(max_lon, min_lat, OSM_ZOOM)
    first_x, last_x = math.floor(min_x / 256), math.floor(max_x / 256)
    first_y, last_y = math.floor(min_y / 256), math.floor(max_y / 256)
    cache = data_dir / "osm-tiles" / str(OSM_ZOOM)
    images: list[str] = []
    for tile_x in range(first_x, last_x + 1):
        for tile_y in range(first_y, last_y + 1):
            path = cache / str(tile_x) / f"{tile_y}.png"
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                request = Request(
                    f"https://tile.openstreetmap.org/{OSM_ZOOM}/{tile_x}/{tile_y}.png",
                    headers={
                        "User-Agent": (
                            "mendo-coast-solar/0.1 "
                            "(https://github.com/jmacd/mendo-coast-solar)"
                        )
                    },
                )
                with urlopen(request) as response:
                    path.write_bytes(response.read())
            x, y = projection.pixel(tile_x * 256, tile_y * 256)
            width = 256 * projection.scale
            height = 256 * projection.scale
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            images.append(
                f'<image x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" '
                f'height="{height:.2f}" preserveAspectRatio="none" '
                f'href="data:image/png;base64,{encoded}"/>'
            )
    return images


def render(data_dir: Path, results_dir: Path, destination: Path) -> None:
    pge = gpd.read_file(data_dir / "pge-ica.geojson").to_crs("EPSG:4326")
    results = gpd.read_file(results_dir / "ranked-parcels.geojson").to_crs(
        "EPSG:4326"
    )
    bounds = BBOX_WGS84
    local_lines = pge[pge.intersects(bounds)].copy()
    local_candidates = results[results.intersects(bounds)].sort_values(
        "centroid_lat", ascending=False
    )
    projection = Projection(bounds.bounds)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Caspar local 12 kV grid and PG&amp;E ICA sections</title>",
        (
            '<desc id="desc">Color-coded PG&amp;E ICA distribution sections '
            "between Hare Creek and Russian Gulch.</desc>"
        ),
        """<defs>
          <style>
            .legend-title{font:800 16px system-ui,sans-serif;fill:#173128}
            .legend-copy{font:13px system-ui,sans-serif;fill:#52675f}
            .address-copy{font:10px system-ui,sans-serif;fill:#173128}
            .note{font:12px system-ui,sans-serif;fill:#52675f}
          </style>
          <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="3" stdDeviation="4" flood-opacity=".14"/>
          </filter>
          <clipPath id="map-clip">
            <rect width="600" height="720"/>
          </clipPath>
        </defs>""",
        '<rect width="600" height="720" fill="#e9eee8"/>',
        '<g clip-path="url(#map-clip)" opacity=".82">',
    ]
    svg.extend(osm_tiles(data_dir, projection))
    svg.append("</g>")

    feeder_paths: list[tuple[str, str, object]] = []
    for _, row in local_lines.iterrows():
        geometry = row.geometry.intersection(bounds)
        if geometry.is_empty:
            continue
        section = xml_text(row["CSV_LineSection"])
        capacity = row["GenericPVCapacity_kW"]
        feeder_paths.append((projection.path(geometry), section, capacity))

    for path, _, _ in feeder_paths:
        svg.append(
            f'<path d="{path}" fill="none" stroke="#fffdf7" stroke-width="8" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )

    for path, section, capacity in feeder_paths:
        capacity_text = "not published" if capacity is None else f"{capacity:g} kW"
        svg.append(
            f'<path d="{path}" fill="none" '
            f'stroke="{capacity_color(capacity)}" stroke-width="4.5" '
            'stroke-linecap="round" stroke-linejoin="round">'
            f"<title>Section {section}: generic-PV ICA {capacity_text}</title></path>"
        )

    for _, site in local_candidates.iterrows():
        geometry = site.geometry.intersection(bounds)
        if geometry.is_empty:
            continue
        zone = str(site["BASEZONE"] or "Unclassified")
        color = ZONE_COLORS.get(zone, ZONE_COLORS["Unclassified"])
        apns = xml_text(site["site_apns"])
        svg.append(
            f'<path d="{projection.path(geometry)}" fill="{color}" '
            f'fill-opacity=".34" stroke="{color}" stroke-width="3">'
            f"<title>{apns}: {xml_text(zone)}</title></path>"
        )

    anchored_candidates = []
    for _, site in local_candidates.iterrows():
        visible_geometry = site.geometry.intersection(bounds)
        if visible_geometry.is_empty:
            continue
        target_x, target_y = western_hull_anchor(projection, visible_geometry)
        anchored_candidates.append((target_y, target_x, site))
    anchored_candidates.sort(key=lambda candidate: candidate[0])
    route_x = min(candidate[1] for candidate in anchored_candidates) - 10

    address_legend = [
        '<g filter="url(#shadow)">',
        '<rect x="30" y="460" width="210" height="244" rx="12" '
        'fill="#fffdf7" fill-opacity=".94" stroke="#cbd4ca"/>',
        "</g>",
        svg_text(48, 488, "Candidate addresses", "legend-title"),
    ]
    for index, (target_y, target_x, site) in enumerate(anchored_candidates):
        y = 514 + index * 17
        address = str(site["SITUS_ADD"]).strip().title()
        if address.upper() in {"", "NONE", "N/A", "NULL"}:
            address = f"APN {site['site_apns']}"
        capacity = int(round(float(site["pge_GenericPVCapacity_kW"])))
        address = f"{address} ({capacity} kW)"
        address_legend.extend(
            [
                f'<path d="M225,{y - 4:.1f} '
                f'L{route_x:.1f},{target_y:.1f} '
                f'L{target_x:.1f},{target_y:.1f}" fill="none" '
                'stroke="#202522" stroke-width="1"/>',
                svg_text(48, y, address, "address-copy"),
            ]
        )

    svg.extend(
        [
            '<g filter="url(#shadow)">',
            '<rect x="30" y="34" width="210" height="174" rx="12" '
            'fill="#fffdf7" fill-opacity=".94" stroke="#cbd4ca"/>',
            svg_text(48, 60, "Integration", "legend-title"),
            svg_text(48, 80, "Capacity (kW)", "legend-title"),
            '<rect x="50" y="103" width="42" height="14" fill="#e76f00"/>',
            svg_text(108, 115, "<200", "legend-copy"),
            '<rect x="50" y="136" width="42" height="14" fill="#e6ab02"/>',
            svg_text(108, 148, "200–299", "legend-copy"),
            '<rect x="50" y="169" width="42" height="14" fill="#15583b"/>',
            svg_text(108, 181, "≥300", "legend-copy"),
            "</g>",
            '<g filter="url(#shadow)">',
            '<rect x="30" y="226" width="210" height="216" rx="12" '
            'fill="#fffdf7" fill-opacity=".94" stroke="#cbd4ca"/>',
            svg_text(48, 254, "Zoning", "legend-title"),
            f'<rect x="50" y="277" width="42" height="14" fill="{ZONE_COLORS["I"]}"/>',
            svg_text(108, 289, "Industrial", "legend-copy"),
            f'<rect x="50" y="310" width="42" height="14" fill="{ZONE_COLORS["RMR"]}"/>',
            svg_text(108, 322, "Remote residential", "legend-copy"),
            f'<rect x="50" y="343" width="42" height="14" fill="{ZONE_COLORS["RR"]}"/>',
            svg_text(108, 355, "Rural residential", "legend-copy"),
            f'<rect x="50" y="376" width="42" height="14" fill="{ZONE_COLORS["RL"]}"/>',
            svg_text(108, 388, "Rangeland", "legend-copy"),
            f'<rect x="50" y="409" width="42" height="14" fill="{ZONE_COLORS["PF"]}"/>',
            svg_text(108, 421, "Public facilities", "legend-copy"),
            "</g>",
            *address_legend,
            svg_text(400, 710, "© OpenStreetMap contributors", "note"),
            "</svg>",
        ]
    )
    destination.write_text("\n".join(svg) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render the Fort Bragg–Mendocino 12 kV ICA map"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--results-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("site/caspar-local-grid.svg"),
    )
    args = parser.parse_args()
    render(args.data_dir, args.results_dir, args.output)


if __name__ == "__main__":
    main()

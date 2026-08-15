from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from rasterio.features import geometry_mask, geometry_window
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely.geometry import box, mapping

from .map import write_candidate_map

ACRE_M2 = 4046.8564224


@dataclass(frozen=True)
class Terrain:
    flat_fraction: float
    open_fraction: float
    contiguous_acres: float
    mean_slope_degrees: float
    suitable_targets: tuple[tuple[float, float], ...]


def terrain_for_geometry(
    dataset: rasterio.io.DatasetReader,
    slope: np.ndarray,
    open_land: np.ndarray,
    geometry: Any,
    max_slope_degrees: float,
    viewshed_target_samples: int,
) -> Terrain:
    try:
        window = geometry_window(dataset, [mapping(geometry)])
    except rasterio.errors.WindowError:
        return Terrain(0.0, 0.0, 0.0, math.nan, ())

    row_start = int(window.row_off)
    row_end = row_start + int(window.height)
    col_start = int(window.col_off)
    col_end = col_start + int(window.width)
    window_slope = slope[row_start:row_end, col_start:col_end]
    window_open = open_land[row_start:row_end, col_start:col_end]
    transform = dataset.window_transform(window)
    inside = geometry_mask(
        [mapping(geometry)],
        out_shape=window_slope.shape,
        transform=transform,
        invert=True,
    )
    valid = inside & np.isfinite(window_slope)
    if not valid.any():
        return Terrain(0.0, 0.0, 0.0, math.nan, ())

    flat = valid & (window_slope <= max_slope_degrees)
    open_pixels = valid & window_open
    suitable = flat & open_pixels
    labels, count = ndimage.label(suitable, structure=np.ones((3, 3), dtype=np.uint8))
    suitable_targets: tuple[tuple[float, float], ...] = ()
    if count:
        component_counts = np.bincount(labels.ravel())[1:]
        largest_label = int(component_counts.argmax()) + 1
        component = np.argwhere(labels == largest_label)
        component_pixels = len(component)
        sample_count = min(viewshed_target_samples, component_pixels)
        sample_indices = np.linspace(
            0,
            component_pixels - 1,
            sample_count,
            dtype=int,
        )
        rows, columns = component[sample_indices].T
        xs, ys = rasterio.transform.xy(transform, rows, columns, offset="center")
        suitable_targets = tuple(
            (float(x), float(y)) for x, y in zip(xs, ys, strict=True)
        )
    else:
        component_pixels = 0
    pixel_area = abs(transform.a * transform.e)
    return Terrain(
        flat_fraction=float(flat.sum() / valid.sum()),
        open_fraction=float(open_pixels.sum() / valid.sum()),
        contiguous_acres=component_pixels * pixel_area / ACRE_M2,
        mean_slope_degrees=float(window_slope[valid].mean()),
        suitable_targets=suitable_targets,
    )


def slope_degrees(dataset: rasterio.io.DatasetReader) -> np.ndarray:
    elevation = dataset.read(1, masked=True).filled(np.nan).astype("float64")
    dy, dx = np.gradient(elevation, abs(dataset.transform.e), dataset.transform.a)
    return np.degrees(np.arctan(np.hypot(dx, dy)))


def aligned_land_cover(
    land_cover_path: Path,
    target: rasterio.io.DatasetReader,
) -> np.ndarray:
    aligned = np.zeros((target.height, target.width), dtype=np.uint8)
    with rasterio.open(land_cover_path) as land_cover:
        source = land_cover.read(1)
        reproject(
            source=source,
            destination=aligned,
            src_transform=land_cover.transform,
            src_crs=land_cover.crs,
            dst_transform=target.transform,
            dst_crs=target.crs,
            resampling=Resampling.nearest,
        )
    return aligned


def obstruction_heights(
    land_cover: np.ndarray,
    heights_by_class: dict[str, float],
) -> np.ndarray:
    heights = np.zeros(land_cover.shape, dtype="float32")
    for land_cover_class, height in heights_by_class.items():
        heights[land_cover == int(land_cover_class)] = float(height)
    return heights


def solar_points(path: Path, parameter: str, crs: str) -> gpd.GeoDataFrame:
    payload = json.loads(path.read_text())
    records = []
    for feature in payload["features"]:
        value = feature["properties"]["parameter"][parameter]["ANN"]
        lon, lat = feature["geometry"]["coordinates"][:2]
        records.append({"solar_kwh_m2_day": value, "lon": lon, "lat": lat})
    frame = gpd.GeoDataFrame(
        records,
        geometry=gpd.points_from_xy(
            [record["lon"] for record in records],
            [record["lat"] for record in records],
        ),
        crs="EPSG:4326",
    )
    return frame.to_crs(crs)


def _normalize(values: np.ndarray, high: float | None = None) -> np.ndarray:
    finite = values[np.isfinite(values)]
    if not len(finite):
        return np.zeros_like(values)
    upper = high if high is not None else float(np.percentile(finite, 95))
    if upper <= 0:
        return np.zeros_like(values)
    return np.clip(values / upper, 0, 1)


def _nearest_distance(points: gpd.GeoSeries, targets: gpd.GeoDataFrame) -> np.ndarray:
    union = valid_union(targets.geometry)
    return np.array([point.distance(union) for point in points], dtype=float)


def valid_union(geometries: gpd.GeoSeries) -> Any:
    valid = geometries[~geometries.is_empty & geometries.notna()].make_valid()
    if valid.empty:
        return shapely.GeometryCollection()
    return shapely.union_all(valid.array, grid_size=0.01)


def subtract_constraints(
    parcels: gpd.GeoDataFrame,
    constraints: gpd.GeoDataFrame,
) -> gpd.GeoSeries:
    index = constraints.sindex
    screened = []
    for geometry in parcels.geometry:
        matches = index.query(geometry, predicate="intersects")
        if len(matches):
            local_exclusions = valid_union(constraints.geometry.iloc[matches])
            screened.append(geometry.difference(local_exclusions))
        else:
            screened.append(geometry)
    return gpd.GeoSeries(screened, index=parcels.index, crs=parcels.crs)


def constraint_overlap_acres(
    parcels: gpd.GeoDataFrame,
    constraints: gpd.GeoDataFrame,
) -> np.ndarray:
    index = constraints.sindex
    overlaps = []
    for geometry in parcels.geometry:
        matches = index.query(geometry, predicate="intersects")
        if len(matches):
            exclusion = valid_union(constraints.geometry.iloc[matches])
            overlaps.append(geometry.intersection(exclusion).area / ACRE_M2)
        else:
            overlaps.append(0.0)
    return np.array(overlaps, dtype=float)


def jurisdiction_metrics(
    parcels: gpd.GeoDataFrame,
    municipal_boundary: gpd.GeoDataFrame,
    default_label: str,
    municipal_label: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    acres = constraint_overlap_acres(parcels, municipal_boundary)
    gross_acres = parcels.geometry.area.to_numpy(dtype=float) / ACRE_M2
    fractions = np.divide(
        acres,
        gross_acres,
        out=np.zeros_like(acres),
        where=gross_acres > 0,
    )
    labels = np.where(fractions >= 0.5, municipal_label, default_label)
    return acres, fractions, labels


def highway_metrics(
    sites: gpd.GeoDataFrame,
    highway: gpd.GeoDataFrame,
) -> tuple[np.ndarray, list[str], np.ndarray]:
    highway_geometry = valid_union(highway.geometry)
    distances = sites.geometry.distance(highway_geometry).to_numpy(dtype=float)
    sides = []
    east_scores = []
    for geometry, distance in zip(sites.geometry, distances, strict=True):
        if distance <= 0.01:
            sides.append("crosses")
            east_scores.append(0.5)
            continue
        centroid = geometry.centroid
        nearest_line = shapely.shortest_line(centroid, highway_geometry)
        coordinates = shapely.get_coordinates(nearest_line)
        highway_point = coordinates[-1]
        if centroid.x < highway_point[0]:
            sides.append("west")
            east_scores.append(0.0)
        else:
            sides.append("east")
            east_scores.append(1.0)
    return distances, sides, np.array(east_scores, dtype=float)


def terrain_line_visible(
    elevation: np.ndarray,
    transform: rasterio.Affine,
    observer: tuple[float, float, float],
    target: tuple[float, float, float],
    obstructions: np.ndarray | None = None,
    obstruction_endpoint_clearance_m: float = 0.0,
) -> bool:
    distance = math.hypot(target[0] - observer[0], target[1] - observer[1])
    pixel_size = min(abs(transform.a), abs(transform.e))
    sample_count = max(2, math.ceil(distance / (pixel_size * 0.5)))
    fractions = np.arange(1, sample_count, dtype=float) / sample_count
    xs = observer[0] + fractions * (target[0] - observer[0])
    ys = observer[1] + fractions * (target[1] - observer[1])
    rows, columns = rasterio.transform.rowcol(transform, xs, ys)
    rows = np.asarray(rows)
    columns = np.asarray(columns)
    inside = (
        (rows >= 0)
        & (rows < elevation.shape[0])
        & (columns >= 0)
        & (columns < elevation.shape[1])
    )
    if not inside.all():
        return False
    terrain = elevation[rows, columns]
    if not np.isfinite(terrain).all():
        return False
    sightline = observer[2] + fractions * (target[2] - observer[2])
    if np.any(terrain > sightline):
        return False
    if obstructions is None:
        return True
    along_line = fractions * distance
    obstruction_zone = (
        (along_line > obstruction_endpoint_clearance_m)
        & (distance - along_line > obstruction_endpoint_clearance_m)
    )
    surface = terrain + obstructions[rows, columns]
    return bool(np.all(~obstruction_zone | (surface <= sightline)))


def _sample_highway(
    highway: gpd.GeoDataFrame,
    spacing_m: float,
) -> gpd.GeoSeries:
    merged = shapely.line_merge(valid_union(highway.geometry))
    points = []
    for part in shapely.get_parts(merged):
        if part.length <= 0:
            continue
        distances = np.arange(0, part.length, spacing_m)
        points.extend(part.interpolate(float(distance)) for distance in distances)
        points.append(part.interpolate(part.length))
    return gpd.GeoSeries(points, crs=highway.crs)


def highway_viewshed_metrics(
    dataset: rasterio.io.DatasetReader,
    highway: gpd.GeoDataFrame,
    site_geometries: gpd.GeoSeries,
    site_targets: list[tuple[tuple[float, float], ...]],
    evaluate: np.ndarray,
    observer_spacing_m: float,
    max_distance_m: float,
    distance_scale_m: float,
    observer_height_m: float,
    target_height_m: float,
    obstructions: np.ndarray | None = None,
    obstruction_endpoint_clearance_m: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    elevation = dataset.read(1, masked=True).filled(np.nan).astype("float64")
    observers = _sample_highway(highway, observer_spacing_m)
    observer_frame = gpd.GeoDataFrame(geometry=observers)
    observer_index = observer_frame.sindex
    observer_elevations = np.full(len(observers), np.nan)
    for index, point in enumerate(observers):
        row, column = dataset.index(point.x, point.y)
        if 0 <= row < dataset.height and 0 <= column < dataset.width:
            observer_elevations[index] = elevation[row, column]

    exposures = np.zeros(len(site_geometries), dtype=float)
    visible_lengths = np.zeros(len(site_geometries), dtype=float)
    nearest_visible = np.full(len(site_geometries), np.nan)
    for site_index, (geometry, targets, should_evaluate) in enumerate(
        zip(site_geometries, site_targets, evaluate, strict=True)
    ):
        if not should_evaluate or not targets:
            continue
        nearby = observer_index.query(
            geometry.buffer(max_distance_m),
            predicate="intersects",
        )
        valid_observers = 0
        visible_observers = 0
        weighted_exposure = 0.0
        nearest = math.inf
        target_elevations = []
        for x, y in targets:
            row, column = dataset.index(x, y)
            if 0 <= row < dataset.height and 0 <= column < dataset.width:
                value = elevation[row, column]
                if np.isfinite(value):
                    target_elevations.append((x, y, value + target_height_m))
        if not target_elevations:
            continue
        for observer_index_value in nearby:
            observer_point = observers.iloc[observer_index_value]
            observer_elevation = observer_elevations[observer_index_value]
            if not np.isfinite(observer_elevation):
                continue
            distances = [
                math.hypot(
                    observer_point.x - target[0],
                    observer_point.y - target[1],
                )
                for target in target_elevations
            ]
            closest_distance = min(distances)
            if closest_distance > max_distance_m:
                continue
            valid_observers += 1
            observer = (
                observer_point.x,
                observer_point.y,
                observer_elevation + observer_height_m,
            )
            visible_distances = [
                distance
                for target, distance in zip(
                    target_elevations,
                    distances,
                    strict=True,
                )
                if terrain_line_visible(
                    elevation,
                    dataset.transform,
                    observer,
                    target,
                    obstructions,
                    obstruction_endpoint_clearance_m,
                )
            ]
            if visible_distances:
                visible_observers += 1
                nearest = min(nearest, min(visible_distances))
                weighted_exposure += sum(
                    math.exp(-distance / distance_scale_m)
                    for distance in visible_distances
                ) / len(
                    target_elevations
                )
        if valid_observers:
            exposures[site_index] = weighted_exposure / valid_observers
        visible_lengths[site_index] = visible_observers * observer_spacing_m
        if math.isfinite(nearest):
            nearest_visible[site_index] = nearest
    return exposures, visible_lengths, nearest_visible


def candidate_sites(
    parcels: gpd.GeoDataFrame,
    min_gross_acres: float,
) -> gpd.GeoDataFrame:
    parcels = parcels.copy()
    fallback_ids = parcels.get("FID", parcels.index.to_series()).astype(str)
    apns = parcels.get("APNFULL", fallback_ids).fillna("").astype(str)
    parcels["_apn"] = apns.where(apns.str.strip() != "", fallback_ids)
    industrial = parcels[
        parcels.get("BASEZONE", "").fillna("").astype(str).str.upper() == "I"
    ].copy()
    nonindustrial = parcels.drop(index=industrial.index)

    rows: list[dict[str, Any]] = []
    for _, parcel in nonindustrial.iterrows():
        if parcel.geometry.area / ACRE_M2 < min_gross_acres:
            continue
        row = parcel.to_dict()
        row["site_type"] = "greenfield"
        row["site_apns"] = parcel["_apn"]
        row["parcel_count"] = 1
        rows.append(row)

    if not industrial.empty:
        parent = {index: index for index in industrial.index}

        def find(index: Any) -> Any:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: Any, right: Any) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        spatial_index = industrial.sindex
        industrial_indices = list(industrial.index)
        for position, index in enumerate(industrial_indices):
            matches = spatial_index.query(
                industrial.loc[index].geometry,
                predicate="intersects",
            )
            for match in matches:
                union(index, industrial_indices[int(match)])

        groups: dict[Any, list[Any]] = {}
        for index in industrial.index:
            groups.setdefault(find(index), []).append(index)

        for indices in groups.values():
            members = industrial.loc[indices]
            geometry = valid_union(members.geometry)
            if geometry.area / ACRE_M2 < min_gross_acres:
                continue
            row = members.iloc[0].to_dict()
            row["geometry"] = geometry
            row["site_type"] = (
                "industrial_assemblage"
                if len(members) > 1
                else "industrial_brownfield"
            )
            row["site_apns"] = ",".join(sorted(members["_apn"].unique()))
            row["APNFULL"] = row["site_apns"]
            row["parcel_count"] = len(members)
            row["IMPV"] = members["IMPV"].fillna(0).astype(float).sum()
            row["FID"] = ",".join(
                sorted(members.get("FID", members.index.to_series()).astype(str))
            )
            for column in [
                "SITUS_ADD",
                "SITUS_CTY",
                "LCP_CODE",
                "GEN_PLAN",
                "BASEZONE",
                "STATUS",
            ]:
                if column not in members:
                    continue
                values = sorted(
                    value
                    for value in members[column].dropna().astype(str).unique()
                    if value.strip()
                )
                row[column] = ",".join(values)
            rows.append(row)

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=parcels.crs)


def grid_accessible_parcels(
    parcels: gpd.GeoDataFrame,
    anchor: gpd.GeoDataFrame,
    distribution_grid: gpd.GeoDataFrame,
    max_distance_m: float,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    anchor_geometry = valid_union(anchor.geometry)
    anchor_grid = distribution_grid[
        distribution_grid.geometry.intersects(anchor_geometry)
    ].copy()
    if anchor_grid.empty:
        raise ValueError("No distribution grid features intersect the scope anchor")

    matches = gpd.sjoin_nearest(
        parcels[["geometry"]],
        anchor_grid[["geometry"]],
        how="inner",
        max_distance=max_distance_m,
        distance_col="scope_grid_distance_m",
    )
    distances = matches.groupby(level=0)["scope_grid_distance_m"].min()
    selected = parcels.loc[distances.index].copy()
    selected["scope_grid_distance_m"] = distances.reindex(selected.index)
    return selected, anchor_grid


def _nearest_join(
    parcels: gpd.GeoDataFrame,
    targets: gpd.GeoDataFrame,
    columns: list[str],
    distance_column: str,
    *,
    use_centroid: bool = False,
) -> gpd.GeoDataFrame:
    geometries = parcels.geometry.centroid if use_centroid else parcels.geometry
    points = gpd.GeoDataFrame(
        geometry=geometries,
        index=parcels.index,
        crs=parcels.crs,
    )
    joined = gpd.sjoin_nearest(
        points,
        targets[columns + ["geometry"]],
        how="left",
        distance_col=distance_column,
    )
    joined = joined.sort_values(distance_column)
    return joined[~joined.index.duplicated(keep="first")].reindex(parcels.index)


def nearest_pge_join(
    parcels: gpd.GeoDataFrame,
    lines: gpd.GeoDataFrame,
    columns: list[str],
    max_distance_m: float,
) -> gpd.GeoDataFrame:
    index = lines.sindex
    rows = []
    for parcel_index, geometry in parcels.geometry.items():
        matches = index.query(
            geometry,
            predicate="dwithin",
            distance=max_distance_m,
        )
        if len(matches):
            candidates = lines.iloc[matches][columns + ["geometry"]].copy()
            candidates["pge_distance_m"] = candidates.geometry.distance(geometry)
            candidates = candidates.sort_values(
                ["pge_distance_m", "CSV_LineSection"],
                ascending=[True, True],
                na_position="last",
            )
            selected = candidates.iloc[0]
        else:
            fallback = _nearest_join(
                parcels.loc[[parcel_index]],
                lines,
                columns,
                "pge_distance_m",
            )
            selected = fallback.iloc[0]
        row = {column: selected[column] for column in columns}
        row["pge_distance_m"] = selected["pge_distance_m"]
        rows.append(row)
    return gpd.GeoDataFrame(rows, index=parcels.index)


def _known_site_results(path: Path, screened: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    sites = gpd.read_file(path).to_crs(screened.crs)
    results = []
    for _, site in sites.iterrows():
        distances = screened.geometry.distance(site.geometry)
        match_index = distances.idxmin()
        match = screened.loc[match_index]
        results.append(
            {
                "name": site.get("name", "unnamed"),
                "apn": match["apn"],
                "rank": (
                    int(match["rank"])
                    if bool(match["eligible"])
                    else None
                ),
                "score": float(match["score"]),
                "distance_m": float(distances.loc[match_index]),
                "eligible": bool(match["eligible"]),
                "eligibility_reasons": match["eligibility_reasons"],
            }
        )
    return results


def specific_yield_mwh_per_mw(
    solar_kwh_m2_day: Any,
    system_loss_fraction: float,
) -> Any:
    return solar_kwh_m2_day * 365 * (1 - system_loss_fraction)


def feeder_profiles(path: Path) -> dict[str, dict[str, float]]:
    records = json.loads(path.read_text())["records"]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        feeder_id = str(record["FeederID"]).zfill(9)
        grouped.setdefault(feeder_id, []).append(record)

    results = {}
    for feeder_id, rows in grouped.items():
        lows = [row["Low"] for row in rows if row.get("Low") is not None]
        highs = [row["High"] for row in rows if row.get("High") is not None]
        midday_lows = [
            row["Low"]
            for row in rows
            if row.get("Low") is not None
            and 10 <= int(str(row["MonthHour"]).split("_")[-1]) <= 15
        ]
        results[feeder_id] = {
            "profile_min_load_kw": float(min(lows)) if lows else math.nan,
            "profile_peak_load_kw": float(max(highs)) if highs else math.nan,
            "profile_min_midday_load_kw": (
                float(min(midday_lows)) if midday_lows else math.nan
            ),
        }
    return results


def analyze(
    config: dict[str, Any],
    data_dir: Path,
    output_dir: Path,
    known_sites_path: Path | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    crs = config["area"]["analysis_crs"]
    settings = config["analysis"]
    sources = config["sources"]

    scope_settings = config["study_scope"]
    scope_anchor = gpd.read_file(
        data_dir / sources[scope_settings["anchor_source"]]["filename"]
    ).to_crs(crs)
    scope_grid = gpd.read_file(
        data_dir / sources[scope_settings["distribution_source"]]["filename"]
    ).to_crs(crs)
    municipal_boundary = gpd.read_file(
        data_dir
        / sources[scope_settings["municipal_jurisdiction_source"]]["filename"]
    ).to_crs(crs)
    parcels = gpd.read_file(data_dir / sources["parcels"]["filename"]).to_crs(crs)
    parcels.geometry = parcels.geometry.make_valid()
    wetlands = gpd.read_file(data_dir / sources["wetlands"]["filename"]).to_crs(crs)
    protected = gpd.read_file(
        data_dir / sources["protected_lands"]["filename"]
    ).to_crs(crs)
    farmland = gpd.read_file(data_dir / sources["farmland"]["filename"]).to_crs(crs)
    fire_hazard = gpd.read_file(
        data_dir / sources["fire_hazard"]["filename"]
    ).to_crs(crs)
    transmission = gpd.read_file(data_dir / sources["transmission"]["filename"]).to_crs(crs)
    highway_1 = gpd.read_file(data_dir / sources["highway_1"]["filename"]).to_crs(crs)
    pge_ica = gpd.read_file(data_dir / sources["pge_ica"]["filename"]).to_crs(crs)
    pge_feeders = gpd.read_file(
        data_dir / sources["pge_feeders"]["filename"]
    ).to_crs(crs)

    bounds_geometry = gpd.GeoSeries(
        [box(*config["area"]["bbox"])],
        crs="EPSG:4326",
    ).to_crs(crs).iloc[0]
    scope_anchor = scope_anchor[scope_anchor.geometry.intersects(bounds_geometry)].copy()
    scope_anchor.geometry = scope_anchor.geometry.intersection(bounds_geometry)
    scope_grid = scope_grid[scope_grid.geometry.intersects(bounds_geometry)].copy()
    parcels = parcels[parcels.geometry.intersects(bounds_geometry)].copy()
    parcels, anchor_grid = grid_accessible_parcels(
        parcels,
        scope_anchor,
        scope_grid,
        scope_settings["max_grid_distance_m"],
    )
    parcel_bounds = box(*parcels.total_bounds)
    print(
        f"grid-accessible parcels: {len(parcels)} from "
        f"{len(anchor_grid)} anchor-reaching grid features",
        flush=True,
    )

    wetlands = wetlands[wetlands.geometry.intersects(parcel_bounds)]
    protected = protected[protected.geometry.intersects(parcel_bounds)]
    farmland = farmland[farmland.geometry.intersects(parcel_bounds)]
    municipal_boundary = municipal_boundary[
        municipal_boundary.geometry.intersects(parcel_bounds)
    ]
    print(
        "constraint features: "
        f"{len(wetlands)} wetlands, {len(protected)} protected, "
        f"{len(farmland)} farmland, {len(municipal_boundary)} municipal boundary",
        flush=True,
    )

    prime_farmland = farmland[
        farmland["polygon_ty"].isin(["P", "S", "U"])
    ]
    wetland_buffers = wetlands.geometry.make_valid().buffer(
        settings["wetland_buffer_m"]
    )
    wetland_constraints = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries(list(wetland_buffers), crs=crs)
    )
    protected_constraints = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries(list(protected.geometry.make_valid()), crs=crs)
    )
    farmland_constraints = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries(list(prime_farmland.geometry.make_valid()), crs=crs)
    )
    municipal_context = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries(
            list(municipal_boundary.geometry.make_valid()),
            crs=crs,
        )
    )
    constraints = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries(
            list(wetland_constraints.geometry)
            + list(protected_constraints.geometry)
            + list(farmland_constraints.geometry),
            crs=crs,
        ),
    )
    constraints = constraints[~constraints.geometry.is_empty]

    parcels = candidate_sites(parcels, settings["min_parcel_acres"])
    scope_nearest = _nearest_join(
        parcels,
        anchor_grid,
        [],
        "scope_grid_distance_m",
    )
    parcels["scope_grid_distance_m"] = scope_nearest["scope_grid_distance_m"]
    anchor_geometry = valid_union(scope_anchor.geometry)
    parcels["scope_anchor_fraction"] = (
        parcels.geometry.intersection(anchor_geometry).area
        / parcels.geometry.area.replace(0, np.nan)
    )
    parcels["scope_anchor_label"] = scope_settings["anchor_label"]
    parcels["gross_acres"] = parcels.geometry.area / ACRE_M2
    (
        parcels["municipal_jurisdiction_acres"],
        parcels["municipal_jurisdiction_fraction"],
        parcels["planning_jurisdiction"],
    ) = jurisdiction_metrics(
        parcels,
        municipal_context,
        scope_settings["default_jurisdiction"],
        scope_settings["municipal_jurisdiction_label"],
    )
    parcels["wetland_exclusion_acres"] = constraint_overlap_acres(
        parcels,
        wetland_constraints,
    )
    parcels["protected_exclusion_acres"] = constraint_overlap_acres(
        parcels,
        protected_constraints,
    )
    parcels["farmland_exclusion_acres"] = constraint_overlap_acres(
        parcels,
        farmland_constraints,
    )
    parcels.geometry = subtract_constraints(parcels, constraints)
    parcels["screenable_acres"] = parcels.geometry.area / ACRE_M2
    parcels["excluded_acres"] = parcels["gross_acres"] - parcels["screenable_acres"]
    parcels["improvement_value"] = parcels["IMPV"].fillna(0).astype(float)
    parcels["improvement_value_per_acre"] = (
        parcels["improvement_value"] / parcels["gross_acres"]
    )
    parcels = parcels[
        parcels["improvement_value_per_acre"]
        <= settings["max_improvement_value_per_acre"]
    ].copy()
    parcels = parcels[~parcels.geometry.is_empty].copy()
    print(f"parcels after area and vector exclusions: {len(parcels)}", flush=True)

    dem_path = data_dir / sources["elevation"]["filename"]
    terrain_rows = []
    with rasterio.open(dem_path) as dem:
        raster_crs = dem.crs
        raster_geometries = parcels.geometry.to_crs(raster_crs)
        raster_highway = highway_1.to_crs(raster_crs)
        slope = slope_degrees(dem)
        land_cover = aligned_land_cover(
            data_dir / sources["land_cover"]["filename"],
            dem,
        )
        greenfield_cover = np.isin(
            land_cover,
            settings["open_land_cover_classes"],
        )
        industrial_cover = np.isin(
            land_cover,
            settings["industrial_land_cover_classes"],
        )
        visual_obstructions = obstruction_heights(
            land_cover,
            settings["highway_viewshed_obstruction_heights_m"],
        )
        for geometry, site_type in zip(
            raster_geometries,
            parcels["site_type"],
            strict=True,
        ):
            terrain_rows.append(
                terrain_for_geometry(
                    dem,
                    slope,
                    (
                        industrial_cover
                        if site_type.startswith("industrial")
                        else greenfield_cover
                    ),
                    geometry,
                    settings["max_slope_degrees"],
                    settings["highway_viewshed_target_samples"],
                )
            )
        viewshed_exposure, visible_highway_m, nearest_visible_highway_m = (
            highway_viewshed_metrics(
                dem,
                raster_highway,
                raster_geometries,
                [row.suitable_targets for row in terrain_rows],
                np.array(
                    [
                        row.contiguous_acres >= settings["min_contiguous_acres"]
                        for row in terrain_rows
                    ],
                    dtype=bool,
                ),
                settings["highway_observer_spacing_m"],
                settings["highway_viewshed_max_distance_m"],
                settings["highway_viewshed_distance_scale_m"],
                settings["highway_observer_height_m"],
                settings["solar_target_height_m"],
                visual_obstructions,
                settings["highway_viewshed_endpoint_clearance_m"],
            )
        )
    print("terrain metrics complete", flush=True)

    parcels["flat_fraction"] = [row.flat_fraction for row in terrain_rows]
    parcels["open_fraction"] = [row.open_fraction for row in terrain_rows]
    parcels["contiguous_acres"] = [row.contiguous_acres for row in terrain_rows]
    parcels["mean_slope_deg"] = [row.mean_slope_degrees for row in terrain_rows]
    parcels["highway_1_viewshed_exposure"] = viewshed_exposure
    parcels["highway_1_visible_length_m"] = visible_highway_m
    parcels["highway_1_nearest_visible_distance_m"] = nearest_visible_highway_m
    parcels["estimated_mw"] = parcels["contiguous_acres"] / settings["acres_per_mw"]
    transmission_nearest = _nearest_join(
        parcels,
        transmission,
        ["Name", "kV", "Owner", "Status", "Type"],
        "transmission_distance_m",
    )
    parcels["transmission_distance_m"] = transmission_nearest[
        "transmission_distance_m"
    ]
    for column in ["Name", "kV", "Owner", "Status", "Type"]:
        parcels[f"transmission_{column}"] = transmission_nearest[column]
    (
        parcels["highway_1_distance_m"],
        parcels["highway_1_side"],
        _,
    ) = highway_metrics(parcels, highway_1)

    pge_columns = [
        "FeederId",
        "FeederName",
        "CSV_LineSection",
        "GenCapacity_kW",
        "GenericPVCapacity_kW",
        "voltage_kv",
        "phase_cnt",
        "ICA_Analysis_Date",
    ]
    pge_nearest = nearest_pge_join(
        parcels,
        pge_ica,
        pge_columns,
        settings["max_distribution_distance_m"],
    )
    print("PG&E ICA join complete", flush=True)
    parcels["pge_distance_m"] = pge_nearest["pge_distance_m"]
    for column in pge_columns:
        parcels[f"pge_{column}"] = pge_nearest[column]

    feeder_columns = [
        "FeederID",
        "Feeder_Name",
        "Substation",
        "Nominal_Voltage",
        "ResCust",
        "ComCust",
        "IndCust",
        "AgrCust",
        "OthCust",
        "Existing_DG",
        "Queued_DG",
        "Total_DG",
    ]
    feeder_by_id = (
        pge_feeders[feeder_columns]
        .drop_duplicates("FeederID")
        .set_index("FeederID")
    )
    normalized_feeder_ids = parcels["pge_FeederId"].astype(str).str.zfill(9)
    for column in feeder_columns[1:]:
        parcels[f"pge_{column}"] = normalized_feeder_ids.map(feeder_by_id[column])

    profiles = feeder_profiles(data_dir / sources["pge_load_profiles"]["filename"])
    for column in [
        "profile_min_load_kw",
        "profile_peak_load_kw",
        "profile_min_midday_load_kw",
    ]:
        parcels[f"pge_{column}"] = normalized_feeder_ids.map(
            {feeder_id: values[column] for feeder_id, values in profiles.items()}
        )

    fire_nearest = _nearest_join(
        parcels, fire_hazard, ["FHSZ_Description"], "fire_distance_m"
    )
    parcels["fire_hazard"] = fire_nearest["FHSZ_Description"].where(
        fire_nearest["fire_distance_m"] <= 0.01, "Not mapped"
    )

    solar = solar_points(
        data_dir / sources["solar"]["filename"],
        sources["solar"]["parameter"],
        crs,
    )
    nearest = _nearest_join(
        parcels,
        solar,
        ["solar_kwh_m2_day"],
        "solar_distance_m",
        use_centroid=True,
    )
    parcels["solar_kwh_m2_day"] = nearest["solar_kwh_m2_day"]
    parcels["annual_mwh_per_mw"] = specific_yield_mwh_per_mw(
        parcels["solar_kwh_m2_day"],
        settings["system_loss_fraction"],
    )
    parcels["reference_project_mw"] = np.minimum(
        parcels["estimated_mw"],
        settings["reference_solar_project_mw"],
    )
    parcels["reference_battery_mwh"] = (
        parcels["reference_project_mw"] * settings["reference_storage_hours"]
    )
    parcels["reference_annual_mwh"] = (
        parcels["reference_project_mw"] * parcels["annual_mwh_per_mw"]
    )
    parcels["reference_average_kw"] = (
        parcels["reference_annual_mwh"] * 1000 / (365 * 24)
    )
    parcels["static_pv_export_limit_mw"] = (
        parcels["pge_GenericPVCapacity_kW"].fillna(0) / 1000
    )
    parcels["reference_export_gap_mw"] = np.maximum(
        parcels["reference_project_mw"] - parcels["static_pv_export_limit_mw"],
        0,
    )
    parcels["screened_project_mw"] = np.minimum.reduce(
        [
            parcels["estimated_mw"].to_numpy(dtype=float),
            parcels["static_pv_export_limit_mw"].to_numpy(dtype=float),
            parcels["pge_profile_min_midday_load_kw"]
            .fillna(0)
            .to_numpy(dtype=float)
            / 1000,
        ]
    )
    parcels["screened_annual_mwh"] = (
        parcels["screened_project_mw"] * parcels["annual_mwh_per_mw"]
    )
    near_transmission = (
        parcels["transmission_distance_m"]
        <= settings["near_transmission_distance_m"]
    )
    parcels["interconnection_path"] = np.select(
        [
            parcels["pge_GenericPVCapacity_kW"].fillna(0)
            >= parcels["reference_project_mw"] * 1000,
            near_transmission,
        ],
        [
            "static_distribution",
            "controlled_export_or_transmission_study",
        ],
        default="controlled_export_or_distribution_upgrade",
    )
    parcels["residential_zoning"] = (
        parcels["BASEZONE"]
        .fillna("")
        .astype(str)
        .str.strip()
        .isin(settings["residential_base_zones"])
    )

    undeveloped = 1 - np.clip(
        parcels["improvement_value_per_acre"].to_numpy(dtype=float)
        / settings["max_improvement_value_per_acre"],
        0,
        1,
    )
    generation_capacity = (
        parcels["pge_GenericPVCapacity_kW"].fillna(0).to_numpy(dtype=float)
    )
    phase_count = parcels["pge_phase_cnt"].fillna(0).to_numpy(dtype=float)
    hosting_score = np.clip(generation_capacity / 2000, 0, 1)
    hosting_score *= np.where(phase_count >= 3, 1.0, 0.25)
    metrics = {
        "contiguous_land": _normalize(
            parcels["contiguous_acres"].to_numpy(dtype=float), high=20
        ),
        "flat_fraction": parcels["flat_fraction"].to_numpy(dtype=float),
        "open_land_cover": parcels["open_fraction"].to_numpy(dtype=float),
        "undeveloped": undeveloped,
        "industrial_reuse": np.where(
            parcels["site_type"].str.startswith("industrial"),
            1.0,
            0.0,
        ),
        "distribution_proximity": np.exp(
            -parcels["pge_distance_m"].to_numpy(dtype=float)
            / settings["grid_distance_scale_m"]
        ),
        "residential_demand": np.nan_to_num(
            _normalize(parcels["pge_ResCust"].to_numpy(dtype=float))
        ),
        "evening_peak_demand": np.nan_to_num(
            _normalize(
                parcels["pge_profile_peak_load_kw"].to_numpy(dtype=float)
            )
        ),
        "grid_hosting_capacity": hosting_score,
        "solar_resource": _normalize(
            parcels["solar_kwh_m2_day"].to_numpy(dtype=float)
        ),
        "transmission_proximity": np.exp(
            -parcels["transmission_distance_m"].to_numpy(dtype=float)
            / settings["grid_distance_scale_m"]
        ),
        "low_highway_visibility": 1.0
        - _normalize(
            parcels["highway_1_viewshed_exposure"].to_numpy(dtype=float),
            high=settings["highway_viewshed_high_exposure"],
        ),
    }
    score = np.zeros(len(parcels), dtype=float)
    for name, weight in settings["weights"].items():
        score += float(weight) * metrics[name]
        parcels[f"score_{name}"] = metrics[name]
    parcels["score"] = score

    centroids = gpd.GeoSeries(
        parcels.geometry.centroid,
        index=parcels.index,
        crs=parcels.crs,
    ).to_crs("EPSG:4326")
    parcels["centroid_lon"] = centroids.x
    parcels["centroid_lat"] = centroids.y

    storage_gate_columns = {
        "insufficient_open_flat_acres": (
            parcels["contiguous_acres"] < settings["min_contiguous_acres"]
        ),
        "distribution_line_too_far": (
            parcels["pge_distance_m"] > settings["max_distribution_distance_m"]
        ),
        "not_three_phase": (
            parcels["pge_phase_cnt"] < settings["required_phase_count"]
        ),
        "excluded_base_zoning": (
            parcels["BASEZONE"]
            .fillna("")
            .astype(str)
            .str.strip()
            .isin(settings["excluded_base_zones"])
        ),
    }
    parcels["eligibility_reasons"] = [
        ",".join(
            name
            for name, failed in storage_gate_columns.items()
            if bool(failed.iloc[i])
        )
        for i in range(len(parcels))
    ]
    parcels["eligible"] = parcels["eligibility_reasons"] == ""
    distribution_gate_columns = {
        **storage_gate_columns,
        "insufficient_static_pv_ica": (
            parcels["pge_GenericPVCapacity_kW"]
            < settings["min_generation_capacity_kw"]
        ),
    }
    parcels["distribution_readiness_reasons"] = [
        ",".join(
            name
            for name, failed in distribution_gate_columns.items()
            if bool(failed.iloc[i])
        )
        for i in range(len(parcels))
    ]
    parcels["distribution_ready"] = (
        parcels["distribution_readiness_reasons"] == ""
    )
    parcels["rank"] = np.nan
    eligible_order = parcels[parcels["eligible"]].sort_values(
        ["score", "contiguous_acres"],
        ascending=False,
    ).index
    parcels.loc[eligible_order, "rank"] = np.arange(1, len(eligible_order) + 1)
    print(f"rankable solar-storage sites: {len(eligible_order)}", flush=True)
    fallback_ids = parcels.get("FID", parcels.index.to_series()).astype(str)
    apns = parcels.get("APNFULL", fallback_ids).fillna("").astype(str)
    parcels["apn"] = apns.where(apns.str.strip() != "", fallback_ids)

    public_columns = [
        "rank",
        "eligible",
        "eligibility_reasons",
        "distribution_ready",
        "distribution_readiness_reasons",
        "apn",
        "site_apns",
        "site_type",
        "parcel_count",
        "residential_zoning",
        "SITUS_ADD",
        "SITUS_CTY",
        "FID",
        "centroid_lon",
        "centroid_lat",
        "score",
        "scope_grid_distance_m",
        "scope_anchor_fraction",
        "scope_anchor_label",
        "planning_jurisdiction",
        "municipal_jurisdiction_acres",
        "municipal_jurisdiction_fraction",
        "gross_acres",
        "screenable_acres",
        "excluded_acres",
        "wetland_exclusion_acres",
        "protected_exclusion_acres",
        "farmland_exclusion_acres",
        "improvement_value",
        "improvement_value_per_acre",
        "flat_fraction",
        "open_fraction",
        "contiguous_acres",
        "mean_slope_deg",
        "estimated_mw",
        "reference_project_mw",
        "reference_battery_mwh",
        "reference_annual_mwh",
        "reference_average_kw",
        "static_pv_export_limit_mw",
        "reference_export_gap_mw",
        "interconnection_path",
        "screened_project_mw",
        "screened_annual_mwh",
        "transmission_distance_m",
        "transmission_Name",
        "transmission_kV",
        "transmission_Owner",
        "transmission_Status",
        "transmission_Type",
        "highway_1_side",
        "highway_1_distance_m",
        "highway_1_viewshed_exposure",
        "highway_1_visible_length_m",
        "highway_1_nearest_visible_distance_m",
        "pge_distance_m",
        "pge_FeederId",
        "pge_FeederName",
        "pge_CSV_LineSection",
        "pge_GenCapacity_kW",
        "pge_GenericPVCapacity_kW",
        "pge_voltage_kv",
        "pge_phase_cnt",
        "pge_ICA_Analysis_Date",
        "pge_Feeder_Name",
        "pge_Substation",
        "pge_Nominal_Voltage",
        "pge_ResCust",
        "pge_ComCust",
        "pge_IndCust",
        "pge_AgrCust",
        "pge_OthCust",
        "pge_Existing_DG",
        "pge_Queued_DG",
        "pge_Total_DG",
        "pge_profile_min_load_kw",
        "pge_profile_peak_load_kw",
        "pge_profile_min_midday_load_kw",
        "fire_hazard",
        "solar_kwh_m2_day",
        "annual_mwh_per_mw",
        "LCP_CODE",
        "GEN_PLAN",
        "BASEZONE",
        "score_contiguous_land",
        "score_flat_fraction",
        "score_open_land_cover",
        "score_undeveloped",
        "score_industrial_reuse",
        "score_distribution_proximity",
        "score_residential_demand",
        "score_evening_peak_demand",
        "score_grid_hosting_capacity",
        "score_solar_resource",
        "score_transmission_proximity",
        "score_low_highway_visibility",
        "geometry",
    ]
    public_columns = [column for column in public_columns if column in parcels.columns]
    screened = parcels[public_columns].sort_values(
        ["eligible", "score"],
        ascending=False,
    )
    public = screened[screened["eligible"]].copy()
    public["rank"] = public["rank"].astype(int)
    ica_columns = [
        "FeederId",
        "FeederName",
        "CSV_LineSection",
        "GenCapacity_kW",
        "GenericPVCapacity_kW",
        "voltage_kv",
        "phase_cnt",
        "ICA_Analysis_Date",
        "geometry",
    ]
    (output_dir / "ica-sections.geojson").write_text(
        pge_ica[ica_columns].to_crs("EPSG:4326").to_json(drop_id=True)
    )
    (output_dir / "distribution-grid.geojson").write_text(
        anchor_grid.to_crs("EPSG:4326").to_json(drop_id=True)
    )
    (output_dir / "ranked-parcels.geojson").write_text(
        public.to_crs("EPSG:4326").to_json(drop_id=True)
    )
    grid_candidate_columns = [
        "rank",
        "site_apns",
        "SITUS_ADD",
        "SITUS_CTY",
        "BASEZONE",
        "planning_jurisdiction",
        "score",
        "contiguous_acres",
        "pge_GenericPVCapacity_kW",
        "pge_distance_m",
        "geometry",
    ]
    (output_dir / "grid-candidates.geojson").write_text(
        public[grid_candidate_columns].to_crs("EPSG:4326").to_json(drop_id=True)
    )
    public.drop(columns="geometry").to_csv(output_dir / "ranked-parcels.csv", index=False)
    write_candidate_map(public, output_dir / "candidate-map.html")
    distribution_ready = screened[screened["distribution_ready"]].copy()
    (output_dir / "distribution-ready-parcels.geojson").write_text(
        distribution_ready.to_crs("EPSG:4326").to_json(drop_id=True)
    )
    distribution_ready.drop(columns="geometry").to_csv(
        output_dir / "distribution-ready-parcels.csv",
        index=False,
    )
    (output_dir / "screened-parcels.geojson").write_text(
        screened.to_crs("EPSG:4326").to_json(drop_id=True)
    )
    screened.drop(columns="geometry").to_csv(
        output_dir / "screened-parcels.csv",
        index=False,
    )

    known_results = (
        _known_site_results(known_sites_path, screened)
        if known_sites_path is not None
        else []
    )
    zoning_counts = (
        public["BASEZONE"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "Unclassified")
        .value_counts()
    )
    residential_count = int(public["residential_zoning"].sum())
    report_lines = [
        f"# {config['area']['name']} solar screening",
        "",
        f"Ranked solar-storage sites: {len(public)}",
        f"Static distribution-ready sites: {len(distribution_ready)}",
        "",
        "This is a regional screening model, not a permitting, biological,",
        "survey, title, or PG&E interconnection determination.",
        "",
        "## Zoning summary",
        "",
        f"Residential (RR or RMR): {residential_count} of {len(public)} "
        f"({residential_count / len(public):.1%})",
        "",
        *(
            f"- {zone}: {count}"
            for zone, count in zoning_counts.items()
        ),
        "",
        "## Known-site checks",
        "",
    ]
    if known_results:
        report_lines.extend(
            f"- {result['name']}: "
            f"{'rank ' + str(result['rank']) if result['eligible'] else 'ineligible: ' + result['eligibility_reasons']} "
            f"(APN {result['apn']}, score {result['score']:.3f}, "
            f"{result['distance_m']:.0f} m away)"
            for result in known_results
        )
    else:
        report_lines.append(
            "No known-sites GeoJSON was supplied. Add named points or polygons to "
            "measure whether expected sites rank highly."
        )
    report_lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- PG&E ICA is illustrative planning data, not an interconnection guarantee.",
            "- Static ICA is reported but is not a hard gate for storage-oriented ranking.",
            "- Residential customers and peak load describe an entire feeder, not a town.",
            "- Reference battery sizing is illustrative; no hourly dispatch is simulated.",
            "- The nearest mapped line may not be the feasible point of interconnection.",
            "- NASA POWER is too coarse to resolve local coastal fog and shading.",
            "- Wetlands are screened with a planning buffer; project-specific buffers vary.",
            "- CPAD and prime-farmland overlays are conservative screening exclusions.",
            "- Land inside the Fort Bragg city limits is excluded from county screening.",
            "- Assessed improvement value is a proxy; aerial review must confirm open land.",
            "- Coastal Zone and parcel boundaries are representational, not survey boundaries.",
            "- Zoning fields are reported but not scored as a legal entitlement judgment.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(report_lines))

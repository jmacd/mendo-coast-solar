from pathlib import Path
import tomllib

import geopandas as gpd
import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box, LineString

from solar_siting.analysis import (
    ACRE_M2,
    _normalize,
    candidate_sites,
    first_public_road_sides,
    grid_accessible_parcels,
    highway_metrics,
    highway_viewshed_metrics,
    inland_county_boundary,
    jurisdiction_metrics,
    nearest_pge_join,
    specific_yield_mwh_per_mw,
    terrain_line_visible,
)


def test_normalize_clips_and_preserves_missing_values():
    values = np.array([0.0, 5.0, 10.0, np.nan])

    result = _normalize(values, high=10)

    np.testing.assert_allclose(result[:3], [0.0, 0.5, 1.0])
    assert np.isnan(result[3])


def test_normalize_handles_empty_finite_input():
    result = _normalize(np.array([np.nan]))

    np.testing.assert_allclose(result, [0.0])


def test_specific_yield_has_physical_units():
    result = specific_yield_mwh_per_mw(4.35, 0.14)

    assert result == pytest.approx(1365.465)


def test_weights_prioritize_generation_ica_and_distribution_distance():
    config_path = Path(__file__).parents[1] / "config" / "mendocino.toml"
    with config_path.open("rb") as config_file:
        weights = tomllib.load(config_file)["analysis"]["weights"]

    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["contiguous_land"] == 0.05
    assert weights["distribution_proximity"] == 0.225
    assert weights["grid_hosting_capacity"] == 0.225
    for removed in [
        "industrial_reuse",
        "residential_demand",
        "evening_peak_demand",
        "transmission_proximity",
    ]:
        assert removed not in weights


def test_candidate_sites_combine_sections_with_same_apn_only():
    side = (6 * ACRE_M2) ** 0.5
    parcels = gpd.GeoDataFrame(
        {
            "APNFULL": ["100", "100", "200"],
            "FID": [1, 2, 3],
            "IMPV": [1000, 1000, 2000],
            "BASEZONE": ["RL", "RL", "I"],
            "LCP_CODE": ["R", "R", "I"],
            "GEN_PLAN": ["RL", "RL", "I"],
            "STATUS": ["A", "A", "A"],
        },
        geometry=[
            box(0, 0, side, side),
            box(side, 0, 2 * side, side),
            box(2 * side, 0, 3 * side, side),
        ],
        crs="EPSG:3310",
    )

    result = candidate_sites(parcels, min_gross_acres=10)

    assert len(result) == 1
    assert result.iloc[0]["site_type"] == "greenfield"
    assert result.iloc[0]["site_apns"] == "100"
    assert result.iloc[0]["parcel_count"] == 1
    assert result.iloc[0]["source_section_count"] == 2
    assert result.iloc[0]["IMPV"] == 1000
    assert result.iloc[0].geometry.area / ACRE_M2 == pytest.approx(12, abs=0.001)


def test_nearest_pge_join_does_not_prefer_distant_high_ica_section():
    parcels = gpd.GeoDataFrame(
        geometry=[box(0, 0, 10, 10)],
        crs="EPSG:3310",
    )
    lines = gpd.GeoDataFrame(
        {
            "CSV_LineSection": ["nearest", "higher-ica"],
            "GenericPVCapacity_kW": [186.0, 319.0],
            "phase_cnt": [3, 3],
        },
        geometry=[
            LineString([(20, 0), (20, 10)]),
            LineString([(450, 0), (450, 10)]),
        ],
        crs=parcels.crs,
    )

    result = nearest_pge_join(
        parcels,
        lines,
        ["CSV_LineSection", "GenericPVCapacity_kW", "phase_cnt"],
        max_distance_m=1000,
    )

    assert result.iloc[0]["CSV_LineSection"] == "nearest"
    assert result.iloc[0]["GenericPVCapacity_kW"] == 186
    assert result.iloc[0]["pge_distance_m"] == pytest.approx(10)


def test_grid_accessible_parcels_follow_only_grid_that_reaches_anchor():
    parcels = gpd.GeoDataFrame(
        {"name": ["coastal", "inland", "too-far", "unrelated"]},
        geometry=[
            box(0, 0, 10, 10),
            box(190, 0, 200, 10),
            box(300, 0, 310, 10),
            box(190, 190, 200, 200),
        ],
        crs="EPSG:3310",
    )
    anchor = gpd.GeoDataFrame(
        geometry=[box(-10, -10, 20, 20)],
        crs=parcels.crs,
    )
    grid = gpd.GeoDataFrame(
        {"feeder": ["coastal-reaching", "inland-only"]},
        geometry=[
            LineString([(5, 5), (205, 5)]),
            LineString([(195, 195), (250, 195)]),
        ],
        crs=parcels.crs,
    )

    selected, selected_grid = grid_accessible_parcels(
        parcels,
        anchor,
        grid,
        max_distance_m=20,
    )

    assert selected["name"].tolist() == ["coastal", "inland"]
    assert selected_grid["feeder"].tolist() == ["coastal-reaching"]
    np.testing.assert_allclose(selected["scope_grid_distance_m"], [0, 0])


def test_jurisdiction_metrics_label_parcels_by_majority_overlap():
    side = ACRE_M2**0.5
    parcels = gpd.GeoDataFrame(
        geometry=[
            box(0, 0, side, side),
            box(side, 0, 2 * side, side),
        ],
        crs="EPSG:3310",
    )
    city = gpd.GeoDataFrame(
        geometry=[box(0, 0, 1.5 * side, side)],
        crs=parcels.crs,
    )

    acres, fractions, labels = jurisdiction_metrics(
        parcels,
        city,
        "Mendocino County",
        "City of Fort Bragg",
    )

    np.testing.assert_allclose(acres, [1, 0.5])
    np.testing.assert_allclose(fractions, [1, 0.5])
    assert labels.tolist() == ["City of Fort Bragg", "City of Fort Bragg"]


def test_inland_county_boundary_omits_western_edge():
    county = gpd.GeoDataFrame(
        {"COUNTY_NAME": ["Test County"]},
        geometry=[box(0, 0, 100_000, 100_000)],
        crs="EPSG:3310",
    )

    result = inland_county_boundary(county)
    coordinates = np.asarray(result.geometry.iloc[0].coords)

    assert result.iloc[0]["COUNTY_NAME"] == "Test County"
    assert np.any(coordinates[:, 0] == 100_000)
    assert not np.any(
        (coordinates[:-1, 0] == 0) & (coordinates[1:, 0] == 0)
    )


def test_highway_metrics_classify_east_west_and_crossing():
    sites = gpd.GeoDataFrame(
        geometry=[
            box(-20, 0, -10, 10),
            box(10, 0, 20, 10),
            box(-5, 20, 5, 30),
        ],
        crs="EPSG:3310",
    )
    highway = gpd.GeoDataFrame(
        geometry=[box(-0.01, -10, 0.01, 40).boundary],
        crs=sites.crs,
    )

    distances, sides, scores = highway_metrics(sites, highway)

    np.testing.assert_allclose(distances, [10, 10, 0], atol=0.02)
    assert sides == ["west", "east", "crosses"]
    np.testing.assert_allclose(scores, [0, 1, 0.5])


def test_highway_metrics_compare_side_at_site_latitude():
    sites = gpd.GeoDataFrame(
        geometry=[box(-1, 9, 1, 11)],
        crs="EPSG:3310",
    )
    highway = gpd.GeoDataFrame(
        geometry=[LineString([(10, 10), (-5, 0)])],
        crs=sites.crs,
    )

    _, sides, scores = highway_metrics(sites, highway)

    assert sides == ["west"]
    np.testing.assert_allclose(scores, [0])


def test_first_public_road_sides_use_westernmost_road():
    sites = gpd.GeoDataFrame(
        geometry=[
            box(-20, 0, -10, 10),
            box(10, 0, 20, 10),
            box(-5, 0, 5, 10),
            box(35, 0, 45, 10),
        ],
        crs="EPSG:3310",
    )
    roads = gpd.GeoDataFrame(
        geometry=[
            LineString([(0, -10), (0, 20)]),
            LineString([(40, -10), (40, 20)]),
        ],
        crs=sites.crs,
    )

    sides = first_public_road_sides(sites, roads)

    assert sides == ["west", "east", "crosses", "east"]


def test_terrain_line_visible_detects_blocking_ridge():
    transform = from_origin(0, 5, 1, 1)
    elevation = np.zeros((5, 5), dtype=float)
    observer = (0.5, 2.5, 1.7)
    target = (4.5, 2.5, 3.0)

    assert terrain_line_visible(elevation, transform, observer, target)

    elevation[:, 2] = 20
    assert not terrain_line_visible(elevation, transform, observer, target)


def test_terrain_line_visible_detects_land_cover_obstruction():
    transform = from_origin(0, 5, 1, 1)
    elevation = np.zeros((5, 5), dtype=float)
    obstructions = np.zeros((5, 5), dtype=float)
    obstructions[:, 2] = 10

    assert not terrain_line_visible(
        elevation,
        transform,
        (0.5, 2.5, 1.7),
        (4.5, 2.5, 3.0),
        obstructions,
    )


def test_highway_viewshed_metrics_aggregate_visible_observers():
    transform = from_origin(0, 200, 10, 10)
    highway = gpd.GeoDataFrame(
        geometry=[LineString([(5, 55), (5, 145)])],
        crs="EPSG:3310",
    )
    sites = gpd.GeoSeries(
        [box(140, 90, 160, 110)],
        crs=highway.crs,
    )
    targets = [((150.0, 100.0),)]
    profile = {
        "driver": "GTiff",
        "height": 20,
        "width": 20,
        "count": 1,
        "dtype": "float32",
        "crs": highway.crs,
        "transform": transform,
    }

    with MemoryFile() as memory:
        with memory.open(**profile) as dataset:
            dataset.write(np.zeros((20, 20), dtype="float32"), 1)
            exposure, visible_length, nearest_visible = highway_viewshed_metrics(
                dataset,
                highway,
                sites,
                targets,
                np.array([True]),
                observer_spacing_m=20,
                max_distance_m=200,
                distance_scale_m=1000,
                observer_height_m=1.7,
                target_height_m=3.0,
            )
            obstructions = np.zeros((20, 20), dtype=float)
            obstructions[:, 8] = 20
            blocked_exposure, blocked_length, blocked_nearest = (
                highway_viewshed_metrics(
                    dataset,
                    highway,
                    sites,
                    targets,
                    np.array([True]),
                    observer_spacing_m=20,
                    max_distance_m=200,
                    distance_scale_m=1000,
                    observer_height_m=1.7,
                    target_height_m=3.0,
                    obstructions=obstructions,
                )
            )

    observer_distances = [
        np.hypot(145, target_y - 100)
        for target_y in [55, 75, 95, 115, 135, 145]
    ]
    expected_exposure = np.mean(np.exp(-np.array(observer_distances) / 1000))
    assert exposure[0] == pytest.approx(expected_exposure)
    assert visible_length[0] == 120
    assert nearest_visible[0] == pytest.approx(min(observer_distances))
    assert blocked_exposure[0] == 0
    assert blocked_length[0] == 0
    assert np.isnan(blocked_nearest[0])

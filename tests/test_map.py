import geopandas as gpd
from shapely.geometry import box

from solar_siting.map import write_candidate_map


def test_candidate_map_embeds_sites_and_zoning(tmp_path):
    sites = gpd.GeoDataFrame(
        {
            "rank": [1],
            "site_apns": ["1180901200"],
            "BASEZONE": ["RR"],
            "GEN_PLAN": ["RR10"],
            "site_type": ["greenfield"],
            "scope_anchor_label": ["Coastal Zone"],
            "scope_anchor_fraction": [0.75],
            "scope_grid_distance_m": [20],
            "score": [0.8],
            "gross_acres": [30.0],
            "contiguous_acres": [25.0],
            "wetland_exclusion_acres": [1.0],
            "reference_project_mw": [1.0],
            "reference_battery_mwh": [4.0],
            "pge_FeederName": ["TEST 1101"],
            "pge_ResCust": [100],
            "pge_profile_peak_load_kw": [500],
            "pge_GenCapacity_kW": [175],
            "pge_GenericPVCapacity_kW": [250],
            "highway_1_side": ["east"],
            "highway_1_distance_m": [58],
            "highway_1_viewshed_exposure": [0.042],
            "highway_1_visible_length_m": [1200],
            "highway_1_nearest_visible_distance_m": [125],
            "interconnection_path": ["controlled_export_or_distribution_upgrade"],
        },
        geometry=[box(0, 0, 100, 100)],
        crs="EPSG:3310",
    )
    destination = tmp_path / "candidate-map.html"

    write_candidate_map(sites, destination)

    content = destination.read_text()
    assert "1180901200" in content
    assert "Rural Residential" in content
    assert "#e31a1c" in content
    assert "p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" in content
    assert 'id="candidate-rows"' in content
    assert "selectItem(item" in content
    assert 'data-sort="score"' in content
    assert 'data-sort="scope_anchor_fraction"' in content
    assert 'data-sort="pge_GenCapacity_kW"' in content
    assert 'data-sort="pge_GenericPVCapacity_kW"' in content
    assert 'data-sort="reference_project_mw"' not in content
    assert 'data-sort="reference_battery_mwh"' not in content
    assert 'data-sort="pge_profile_peak_load_kw"' not in content
    assert 'data-sort="interconnection_path"' not in content
    assert "minmax(0, 40%) minmax(0, 60%)" in content
    assert '["ica-sections.geojson", "12 kV distribution"]' in content
    assert '["transmission-lines.geojson", "Transmission network"]' in content
    assert '"distribution-substations.geojson"' in content
    assert '"county-boundary.geojson"' in content
    assert 'layerControl.addOverlay(distributionLayer, "12 kV distribution")' in content
    assert '`Transmission (${voltages.join("/")} kV)`' in content
    assert 'layerControl.addOverlay(substationLayer, "Distribution substations")' in content
    assert 'layerControl.addOverlay(countyLayer, "Mendocino County boundary")' in content
    assert 'href="map-theme.css"' in content
    assert 'src="map-infrastructure.js"' in content
    assert "MapInfrastructure.transmissionStyle" in content
    assert "Coastal Zone" in content
    assert '<option value="RR">Rural Residential: RR</option>' in content
    assert '<option value="RMR">Remote Residential: RMR</option>' in content
    assert '<option value="focus">AG/FL/TP/RL/I</option>' in content
    assert 'new Set(["AG", "FL", "TP", "RL", "I"])' in content
    assert 'id="hide-west" type="checkbox" checked' in content
    assert 'id="hide-zero-ica" type="checkbox" checked' in content
    assert 'properties.highway_1_side === "west"' in content
    assert '"highway_1_viewshed_exposure":0.042' in content
    assert "Nearest visible view" in content
    assert 'href="downloads.html"' in content

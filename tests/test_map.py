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
            "pge_distance_m": [84],
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
    assert 'id="search"' not in content
    assert "feeder substations shown" not in content
    assert 'document.querySelector("#infrastructure-status").hidden = true' in content
    assert "selectItem(item" in content
    assert 'data-sort="score"' in content
    assert 'data-sort="scope_anchor_fraction"' in content
    assert 'data-sort="pge_GenCapacity_kW"' in content
    assert 'data-sort="pge_GenericPVCapacity_kW"' in content
    assert 'data-sort="pge_distance_m"' in content
    assert "Minimum 12 kV distance" in content
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
    assert 'layerControl.addOverlay(countyLayer, "Mendocino County boundary")' not in content
    assert "const countyLayer = L.geoJSON(county" in content
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
    assert "Only show non-zero ICA" in content
    assert "Number(properties.pge_GenCapacity_kW)" in content
    assert "Candidate counts by zone" in content
    assert '<details class="zone-summary" open>' not in content
    assert "scrollbar-gutter" not in content
    assert content.index('class="zone-code">AG') < content.index('class="zone-code">FL')
    assert content.index('class="zone-code">FL') < content.index('class="zone-code">TP')
    assert content.index('class="zone-code">TP') < content.index('class="zone-code">RL')
    assert content.index('class="zone-code">RL') < content.index('class="zone-code">I')
    assert '<tr data-zone="RR"><th><span class="zone-code">RR</span>' in content
    assert '<td data-total-column="0">1</td>' in content
    assert "function updateZoneCounts(filter)" in content
    assert "row.hidden = !visible" in content
    assert "updateZoneCounts(zoneFilter);" in content
    assert '["west", "crosses"].includes' in content
    assert '"highway_1_viewshed_exposure":0.042' in content
    assert "Nearest visible view" in content


def test_candidate_map_uses_u_for_unclassified_zone(tmp_path):
    sites = gpd.GeoDataFrame(
        {
            "scope_anchor_label": ["Coastal Zone"],
            "BASEZONE": [""],
            "highway_1_side": ["east"],
            "pge_GenCapacity_kW": [100],
        },
        geometry=[box(0, 0, 10, 10)],
        crs="EPSG:3310",
    )
    destination = tmp_path / "candidate-map.html"

    write_candidate_map(sites, destination)

    content = destination.read_text()
    assert (
        '<span class="zone-code">U</span>'
        '<span class="zone-name">Unclassified</span>'
    ) in content
    assert 'return zone === "Unclassified" ? "U" : zone;' in content


def test_candidate_map_counts_crossing_parcels_with_west_exclusion(tmp_path):
    sites = gpd.GeoDataFrame(
        {
            "scope_anchor_label": ["Coastal Zone"] * 3,
            "BASEZONE": ["AG", "AG", "RR"],
            "highway_1_side": ["east", "west", "crosses"],
            "pge_GenCapacity_kW": [100, 100, 100],
        },
        geometry=[
            box(0, 0, 10, 10),
            box(20, 0, 30, 10),
            box(40, 0, 50, 10),
        ],
        crs="EPSG:3310",
    )
    destination = tmp_path / "candidate-map.html"

    write_candidate_map(sites, destination)

    content = destination.read_text()
    assert (
        '<tr data-zone="AG"><th><span class="zone-code">AG</span>'
        '<span class="zone-name">Agricultural</span></th>'
        "<td>2</td><td>1</td><td>2</td><td>1</td>"
    ) in content
    assert (
        '<tr data-zone="RR"><th><span class="zone-code">RR</span>'
        '<span class="zone-name">Rural Residential</span></th>'
        "<td>1</td><td>0</td><td>1</td><td>0</td>"
    ) in content
    assert (
        '<tr class="total"><th>Total</th>'
        '<td data-total-column="0">3</td>'
        '<td data-total-column="1">1</td>'
        '<td data-total-column="2">3</td>'
        '<td data-total-column="3">1</td>'
    ) in content

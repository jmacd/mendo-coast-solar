from pathlib import Path


SITE = Path(__file__).parents[1] / "site"
EXPLORER = SITE / "grid-explorer.html"


def test_candidate_explorer_loads_layers_and_ranks_visible_candidates():
    content = EXPLORER.read_text()

    assert 'fetch("ica-sections.geojson")' in content
    assert 'fetch("distribution-grid.geojson")' in content
    assert 'fetch("ranked-parcels.geojson")' in content
    assert 'fetch("transmission-lines.geojson")' in content
    assert 'fetch("distribution-substations.geojson")' in content
    assert "feature => intersectsView(feature, bounds)" in content
    assert "localRank: visibleRanks.get(candidateId(feature))" in content
    assert "filteredCandidates = candidates" in content
    assert "button.disabled = !isInView" in content
    assert "in view of ${filteredCandidates.length}" in content
    assert "function updateDisplayedFromScroll()" in content
    assert 'list.addEventListener("scroll", updateDisplayedFromScroll)' in content
    assert ".slice(0, MAX_VISIBLE)" in content
    assert "County #${esc(properties.rank)}" not in content
    assert "#status[hidden] { display: none; }" in content
    assert "#candidate-list {" in content
    assert "flex: 1 1 auto;" in content
    assert "min-height: 0;" in content
    assert '"#7b817e"' in content
    assert "pge_GenCapacity_kW" in content
    assert "Generation ICA" in content
    assert "PV ICA (secondary)" in content
    assert "Minimum 12 kV distance" in content
    assert '["get", "pge_GenCapacity_kW"]' in content
    assert '["get", "GenericPVCapacity_kW"]' not in content
    assert "let activeApn = null" in content
    assert "new maplibregl.Popup" not in content
    assert "center: [-123.75, 39.23]" in content
    assert 'id="ica-filter"' in content
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in content
    assert '<option value="nonzero">Non-zero only</option>' in content
    assert 'id="road-filter"' in content
    assert '<option value="highway-1">Highway 1</option>' in content
    assert '<option value="public-road">First public road</option>' in content
    assert '<option value="all">No east-of constraint</option>' in content
    assert 'id="zone-filter"' in content
    assert '<option value="all">All zones</option>' in content
    assert '<option value="focus">AG / FL / TP / RL / I</option>' in content
    assert '<option value="RR">Rural residential (RR)</option>' in content
    assert '<option value="RMR">Remote residential (RMR)</option>' in content
    assert '<option value="other">Other</option>' in content
    assert "function zoneMatches(zone)" in content
    assert '["west", "crosses"].includes(roadSide)' in content
    assert '["==", ["get", roadProperty], "east"]' in content
    assert "highway_1_side" in content
    assert "first_public_road_side" in content
    assert 'id="candidate-sort"' in content
    assert '<option value="score">Score / county rank</option>' in content
    assert '<option value="ica">Generation ICA</option>' in content
    assert '<option value="acres">Suitable acres</option>' in content
    assert '<option value="distance">12 kV distance</option>' in content
    assert "function compareCandidates(left, right)" in content
    assert 'candidateSort.value === "distance" ? 1 : -1' in content
    assert ".sort(compareCandidates)" in content
    assert "function northToSouth(left, right)" in content
    assert "function rankWindowThenNorth(left, right)" in content
    assert "visibleRanks = new Map(" in content
    assert "visibleCandidates.sort(rankWindowThenNorth)" in content
    assert 'id="previous-page"' in content
    assert '<span>Rank</span><span>Zoning</span><span>Details</span>' in content
    assert 'id="next-page"' in content
    assert "let candidatePage = 0" in content
    assert "candidatePage = 0;" in content
    assert "filteredCandidates.slice(" in content
    assert 'class="zone-code"' in content
    assert 'id="show-all"' in content
    assert '<button id="show-all" type="button">Show all</button>' in content
    assert "function showAllCandidates(animate = true)" in content
    assert "const allFilteredCandidates = candidates.filter(passesCandidateFilters)" in content
    assert "showAllCandidates(false);" in content
    assert "map.resize();" in content
    assert "map.fitBounds([[extent[0], extent[1]], [extent[2], extent[3]]]" in content
    assert 'id="basemap"' in content
    assert 'id="show-transmission"' in content
    assert 'id="show-substations"' in content
    assert 'class="map-options"' in content
    assert 'id="candidate-table-drawer"' not in content
    assert "suitable ac &middot;" in content
    assert "m to 12 kV" in content
    assert "const MAX_VISIBLE = 10" in content
    assert 'map.addSource("aerial"' in content
    assert 'map.addSource("transmission"' in content
    assert 'map.addSource("substations"' in content
    assert "parcelCenter(feature)" in content
    assert "<h1>Mendocino Coast Solar Sites</h1>" in content
    assert 'class="map-legend-control"' in content
    assert ".map-legend-control .legends { grid-template-columns: 1fr; }" in content
    assert 'id="zone-legend"' not in content
    assert "function renderZoneLegend()" not in content
    assert 'class="zone-summary"' in content
    assert "Candidate counts by zone" in content
    assert "Each cell: all / non-zero Generation ICA" in content
    assert "function renderZoneCounts()" in content
    assert "function appendZoneCountRow(label, features, total = false)" in content
    assert 'feature.properties.first_public_road_side === "east"' in content
    assert 'feature.properties.highway_1_side === "east"' in content
    assert 'id: "candidate-highlight-fill"' in content
    assert '"line-opacity": .9, "line-width": 2.25' in content
    assert 'id: "candidate-highlight-outline"' not in content
    assert 'href="map-theme.css"' in content

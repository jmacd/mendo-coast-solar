from pathlib import Path


EXPLORER = Path(__file__).parents[1] / "site" / "grid-explorer.html"


def test_grid_explorer_loads_generated_layers_and_ranks_visible_candidates():
    content = EXPLORER.read_text()

    assert 'fetch("ica-sections.geojson")' in content
    assert 'fetch("distribution-grid.geojson")' in content
    assert 'fetch("grid-candidates.geojson")' in content
    assert ".filter(feature => intersectsView(feature, bounds))" in content
    assert "localRank: visibleCandidates.indexOf(feature) + 1" in content
    assert "County #${esc(properties.rank)}" in content
    assert "#status[hidden] { display: none; }" in content
    assert '"#7b817e"' in content
    assert "pge_GenCapacity_kW" in content
    assert "Generation ICA" in content
    assert "PV ICA (secondary)" in content
    assert "Minimum 12 kV distance" in content
    assert '["get", "pge_GenCapacity_kW"]' in content
    assert '["get", "GenericPVCapacity_kW"]' not in content
    assert "let activeApn = null" in content
    assert "new maplibregl.Popup" not in content
    assert "[-123.855, 39.325]" in content
    assert "[-123.78, 39.415]" in content
    assert 'id="hide-west" type="checkbox" checked' in content
    assert '["west", "crosses"].includes(highwaySide)' in content
    assert '["==", ["get", "highway_1_side"], "east"]' in content
    assert 'id="hide-zero-ica" type="checkbox" checked' in content
    assert "highway_1_side" in content
    assert "parcelCenter(feature)" in content
    assert 'id="zone-legend" aria-live="polite"' in content
    assert "function renderZoneLegend()" in content
    assert "for (const feature of visibleCandidates)" in content
    assert "renderZoneLegend();" in content
    assert "No candidates in view" in content
    assert ".legend-zoning { display: none; }" not in content
    assert 'id: "candidate-highlight-fill"' in content
    assert 'href="map-theme.css"' in content

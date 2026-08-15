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
    assert "Generic generation ICA" in content
    assert "Generic PV ICA" in content
    assert "let activeApn = null" in content
    assert "new maplibregl.Popup" not in content
    assert "[-123.855, 39.325]" in content
    assert "[-123.78, 39.415]" in content

from pathlib import Path


SITE = Path(__file__).parents[1] / "site"


def test_county_overview_uses_shared_map_assets_and_generated_layers():
    content = (SITE / "county-grid.html").read_text()
    index = (SITE / "index.html").read_text()

    assert 'src="county-grid.html"' in index
    assert 'href="map-theme.css"' in content
    assert 'src="map-infrastructure.js"' in content
    assert 'fetch("transmission-lines.geojson")' not in content
    assert '"transmission-lines.geojson"' in content
    assert '"distribution-substations.geojson"' in content
    assert '"county-boundary.geojson"' in content
    assert "MapInfrastructure.transmissionStyle" in content
    assert "MapInfrastructure.substationMarker" in content
    assert "<aside" not in content
    assert "map.fitBounds(countyLayer.getBounds()" in content


def test_story_and_pages_use_canonical_candidate_explorer():
    index = (SITE / "index.html").read_text()
    downloads = (SITE / "downloads.html").read_text()
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "pages.yml"
    ).read_text()

    assert 'src="grid-explorer.html"' in index
    assert 'href="ranked-parcels.geojson">Candidates</a>' in downloads
    assert "cp output/candidate-map.html" not in workflow

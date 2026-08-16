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

from __future__ import annotations

import html as html_module
import json
from pathlib import Path

import geopandas as gpd


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
    "U": "#969696",
}

ZONE_LABELS = {
    "RL": "Rangeland",
    "AG": "Agricultural",
    "RMR": "Remote Residential",
    "RR": "Rural Residential",
    "FL": "Forest Lands",
    "TP": "Timberland Production",
    "OS": "Open Space",
    "I": "Industrial",
    "PF": "Public Facilities",
    "U": "Unclassified",
}


def write_candidate_map(sites: gpd.GeoDataFrame, destination: Path) -> None:
    web_sites = sites.to_crs("EPSG:4326").copy()
    web_sites["map_zone"] = (
        web_sites["BASEZONE"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "Unclassified")
    )
    payload = json.loads(web_sites.to_json(drop_id=True))
    anchor_label = html_module.escape(str(sites["scope_anchor_label"].iloc[0]))
    data = json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")
    colors = json.dumps(ZONE_COLORS, separators=(",", ":"))
    labels = json.dumps(ZONE_LABELS, separators=(",", ":"))
    preferred_zones = ["AG", "FL", "TP", "RL", "I"]
    observed_zones = sorted(set(web_sites["map_zone"]) - set(preferred_zones))
    zone_rows = []
    for zone in [*preferred_zones, *observed_zones, None]:
        subset = web_sites if zone is None else web_sites[web_sites["map_zone"] == zone]
        west_or_crossing = (
            subset["highway_1_side"]
            .fillna("")
            .astype(str)
            .str.lower()
            .isin(["west", "crosses"])
        )
        zero_generation_ica = (
            subset["pge_GenCapacity_kW"].notna()
            & subset["pge_GenCapacity_kW"].astype(float).eq(0)
        )
        display_zone = "U" if zone == "Unclassified" else zone
        zone_label = (
            "Total"
            if zone is None
            else (
                f'<span class="zone-code">{html_module.escape(display_zone)}</span>'
                f'<span class="zone-name">{html_module.escape(ZONE_LABELS.get(zone, zone))}</span>'
            )
        )
        counts = [
            len(subset),
            int((~west_or_crossing).sum()),
            int((~zero_generation_ica).sum()),
            int((~west_or_crossing & ~zero_generation_ica).sum()),
        ]
        if zone is None:
            cells = "".join(
                f'<td data-total-column="{index}">{count}</td>'
                for index, count in enumerate(counts)
            )
            zone_rows.append(f'<tr class="total"><th>{zone_label}</th>{cells}</tr>')
        else:
            cells = "".join(f"<td>{count}</td>" for count in counts)
            zone_rows.append(
                f'<tr data-zone="{html_module.escape(zone)}">'
                f"<th>{zone_label}</th>{cells}</tr>"
            )
    zone_count_rows = "".join(zone_rows)

    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mendocino Coast solar candidates</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <style>
    :root { color-scheme: light; font: 14px/1.35 system-ui, sans-serif; }
    * { box-sizing: border-box; }
    html, body, #app { height: 100%; margin: 0; }
    #app { display: grid; grid-template-columns: minmax(0, 40%) minmax(0, 60%); }
    #sidebar {
      background: #f7f7f5;
      border-right: 1px solid #aaa;
      display: flex;
      flex-direction: column;
      min-height: 0;
      z-index: 1001;
    }
    #map { height: 100%; min-width: 0; }
    header {
      background: white;
      border-bottom: 1px solid #bbb;
      padding: 14px;
    }
    h1 { font-size: 18px; line-height: 1.15; margin: 0 0 5px; }
    header p { color: #555; margin: 4px 0 10px; }
    .controls select {
      border: 1px solid #999;
      border-radius: 4px;
      font: inherit;
      min-width: 0;
      padding: 7px 8px;
      width: 100%;
    }
    .filter-controls {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 16px;
      margin-top: 8px;
    }
    .filter-controls label {
      align-items: center;
      color: #444;
      display: flex;
      font-size: 12px;
      gap: 5px;
    }
    .filter-controls input { accent-color: #173128; margin: 0; }
    .zone-summary {
      border-top: 1px solid #ddd;
      margin-top: 9px;
      padding-top: 7px;
    }
    .zone-summary summary {
      cursor: pointer;
      font-size: 12px;
      font-weight: 700;
    }
    .zone-counts {
      border-collapse: collapse;
      font-size: 10px;
      margin-top: 5px;
      width: 100%;
    }
    .zone-counts th, .zone-counts td {
      border-bottom: 1px solid #ddd;
      padding: 2px 5px;
    }
    .zone-counts thead th {
      background: white;
      position: sticky;
      text-align: right;
      top: 0;
    }
    .zone-counts thead th:first-child,
    .zone-counts tbody th { text-align: left; }
    .zone-counts td { text-align: right; }
    .zone-counts .zone-code { display: inline-block; font-weight: 750; width: 26px; }
    .zone-counts .zone-name { color: #666; font-weight: 400; }
    .zone-counts .total { background: #edf3ed; font-weight: 750; }
    #result-summary { color: #444; font-size: 12px; margin-top: 8px; }
    #infrastructure-status { color: #555; font-size: 11px; margin-top: 4px; }
    .station-label {
      background: rgba(255, 255, 255, .88);
      border: 1px solid #444;
      box-shadow: none;
      color: #222;
      font-size: 10px;
      font-weight: 700;
      padding: 1px 4px;
    }
    #candidate-list { min-height: 0; overflow: auto; }
    table.candidates {
      background: white;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 12px;
      min-width: 820px;
      width: 100%;
    }
    .candidates th {
      background: #e7e7e3;
      border-bottom: 1px solid #888;
      border-right: 1px solid #ccc;
      padding: 0;
      position: sticky;
      text-align: left;
      top: 0;
      white-space: nowrap;
      z-index: 2;
    }
    .candidates th button {
      background: none;
      border: 0;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
      padding: 8px 7px;
      text-align: left;
      width: 100%;
    }
    .candidates th button:hover { background: #d7e5ee; }
    .candidates td {
      border-bottom: 1px solid #ddd;
      padding: 6px 7px;
      vertical-align: top;
    }
    .candidates tbody tr.candidate-row {
      border-left: 5px solid var(--zone-color);
      cursor: pointer;
    }
    .candidates tbody tr.candidate-row:hover { background: #f0f6fa; }
    .candidates tbody tr.candidate-row.selected {
      background: #cfe8f6;
      box-shadow: 5px 0 0 #111 inset;
    }
    .candidate-detail td {
      background: #edf7fc;
      border-left: 5px solid var(--zone-color);
      padding: 12px 16px 16px;
    }
    .parcel-details { max-width: 620px; }
    .parcel-details > strong { font-size: 14px; }
    .parcel-details > div { color: #555; margin: 2px 0 8px; }
    .parcel-details table { border-collapse: collapse; width: 100%; }
    .parcel-details th, .parcel-details td {
      background: transparent;
      border: 0;
      padding: 3px 8px 3px 0;
      text-align: left;
      vertical-align: top;
    }
    .parcel-details th { white-space: nowrap; }
    .candidates .number { text-align: right; white-space: nowrap; }
    .candidates .rank { font-size: 14px; font-weight: 750; }
    .candidates .apn {
      display: block;
      font-family: ui-monospace, monospace;
      font-weight: 700;
      white-space: nowrap;
    }
    .candidates .address { color: #555; display: block; white-space: nowrap; }
    .zone {
      border: 2px solid var(--zone-color);
      border-radius: 10px;
      display: inline-block;
      font-weight: 700;
      padding: 1px 6px;
      white-space: nowrap;
    }
    .side-east { color: #176b2c; font-weight: 700; }
    .side-west { color: #a62620; font-weight: 700; }
    .side-crosses { color: #8a5700; font-weight: 700; }
    .leaflet-popup-content { min-width: 280px; }
    .candidate-popup .leaflet-popup-tip-container {
      left: 12px;
      margin-left: 0;
    }
    @media (max-width: 900px) {
      #app { grid-template-columns: 1fr; grid-template-rows: 48% 52%; }
      #sidebar { border-bottom: 1px solid #888; border-right: 0; }
    }
  </style>
  <link rel="stylesheet" href="map-theme.css">
</head>
<body>
<div id="app">
  <aside id="sidebar" class="map-sidebar">
    <header class="map-header">
      <h1 class="map-title">Mendocino Coast solar candidates</h1>
      <div class="controls">
        <select id="zone-filter" aria-label="Filter zoning">
          <option value="focus">AG/FL/TP/RL/I</option>
          <option value="RR">Rural Residential: RR</option>
          <option value="RMR">Remote Residential: RMR</option>
          <option value="RL">Rangeland: RL</option>
          <option value="AG">Agricultural: AG</option>
          <option value="I">Industrial: I</option>
          <option value="all">All zoning</option>
          <option value="residential">Residential: RR and RMR</option>
          <option value="other">Other zoning</option>
        </select>
      </div>
      <div class="filter-controls" aria-label="Candidate exclusions">
        <label><input id="hide-west" type="checkbox" checked>
          Only show east of Highway 1</label>
        <label><input id="hide-zero-ica" type="checkbox" checked>
          Only show non-zero ICA</label>
      </div>
      <details class="zone-summary">
        <summary>Candidate counts by zone</summary>
        <div class="zone-count-wrap">
          <table class="zone-counts">
            <thead><tr>
              <th>Zone</th>
              <th>All</th>
              <th title="Show only east of Highway 1">East side</th>
              <th title="Show only non-zero Generation ICA">ICA > 0</th>
              <th title="Show both exclusions">Both</th>
            </tr></thead>
            <tbody>__ZONE_COUNT_ROWS__</tbody>
          </table>
        </div>
      </details>
      <div id="result-summary"></div>
      <div id="infrastructure-status" role="status">Loading grid infrastructure...</div>
    </header>
    <main id="candidate-list">
      <table class="candidates">
        <thead><tr>
          <th><button data-sort="rank" data-type="number">Rank</button></th>
          <th><button data-sort="site_apns">APN / address</button></th>
          <th><button data-sort="map_zone">Zone</button></th>
          <th><button data-sort="scope_anchor_fraction" data-type="number">__ANCHOR_LABEL__ %</button></th>
          <th><button data-sort="score" data-type="number">Score</button></th>
          <th><button data-sort="contiguous_acres" data-type="number">Suitable ac</button></th>
          <th><button data-sort="gross_acres" data-type="number">Gross ac</button></th>
          <th><button data-sort="pge_GenCapacity_kW" data-type="number">Generation ICA kW</button></th>
          <th><button data-sort="pge_GenericPVCapacity_kW" data-type="number">PV ICA kW (secondary)</button></th>
          <th><button data-sort="pge_distance_m" data-type="number">12 kV distance m</button></th>
          <th><button data-sort="highway_1_side">Hwy 1 side</button></th>
          <th><button data-sort="highway_1_distance_m" data-type="number">Hwy dist m</button></th>
          <th><button data-sort="highway_1_viewshed_exposure" data-type="number">Scenic exposure</button></th>
          <th><button data-sort="highway_1_visible_length_m" data-type="number">Visible Hwy m</button></th>
        </tr></thead>
        <tbody id="candidate-rows"></tbody>
      </table>
    </main>
  </aside>
  <div id="map"></div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script src="map-infrastructure.js?v=2"></script>
<script>
const candidates = __DATA__;
const colors = __COLORS__;
const labels = __LABELS__;
const focusZones = new Set(["AG", "FL", "TP", "RL", "I"]);
const residentialZones = new Set(["RR", "RMR"]);
const map = L.map("map", { preferCanvas: true });
const candidateRenderer = L.canvas({ padding: 0.5, tolerance: 8 });
map.createPane("infrastructure-lines");
map.getPane("infrastructure-lines").style.zIndex = 350;
map.createPane("infrastructure-stations");
map.getPane("infrastructure-stations").style.zIndex = 650;
const substationRenderer = L.svg({ pane: "infrastructure-stations" });
const imagery = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { attribution: "Imagery &copy; Esri and contributors", maxZoom: 19 }
);
const streets = L.tileLayer(
  "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  { attribution: "&copy; OpenStreetMap contributors", maxZoom: 19 }
).addTo(map);
const layerControl = L.control.layers(
  { "Street map": streets, "Aerial imagery": imagery },
  null,
  { collapsed: false, position: "bottomright" }
).addTo(map);

async function loadInfrastructure() {
  const resources = [
    ["ica-sections.geojson", "12 kV distribution"],
    ["transmission-lines.geojson", "Transmission network"],
    ["distribution-substations.geojson", "Distribution substations"],
    ["county-boundary.geojson", "Mendocino County boundary"]
  ];
  const responses = await Promise.all(resources.map(([url]) => fetch(url)));
  const failed = responses
    .map((response, index) => response.ok ? null : resources[index][1])
    .filter(Boolean);
  if (failed.length) {
    throw new Error(`Could not load ${failed.join(", ")}`);
  }
  const [distribution, transmission, substations, county] = await Promise.all(
    responses.map(response => response.json())
  );
  const countyLayer = L.geoJSON(county, {
    pane: "infrastructure-lines",
    style: MapInfrastructure.countyStyle,
    onEachFeature: (feature, layer) => layer.bindTooltip(
      esc(feature.properties.COUNTY_NAME || "Mendocino County boundary"),
      { sticky: true }
    )
  }).addTo(map);
  const distributionLayer = L.geoJSON(distribution, {
    pane: "infrastructure-lines",
    style: { color: "#e76f00", opacity: .58, weight: 1.35 },
    onEachFeature: (feature, layer) => layer.bindTooltip(
      MapInfrastructure.tooltip(feature.properties, [
        ["FeederName", "Feeder"],
        ["CSV_LineSection", "Section"],
        ["GenCapacity_kW", "Generation ICA kW"],
        ["GenericPVCapacity_kW", "PV ICA kW (secondary)"]
      ], esc),
      { sticky: true }
    )
  }).addTo(map);
  const transmissionLayer = L.geoJSON(transmission, {
    pane: "infrastructure-lines",
    style: MapInfrastructure.transmissionStyle,
    onEachFeature: (feature, layer) => layer.bindTooltip(
      MapInfrastructure.tooltip(feature.properties, [
        ["TLINE_NAME", "Transmission line"],
        ["RATEDKV", "Rated kV"]
      ], esc),
      { sticky: true }
    )
  }).addTo(map);
  const substationLayer = L.geoJSON(substations, {
    pane: "infrastructure-stations",
    pointToLayer: (feature, latlng) => MapInfrastructure.substationMarker(
      latlng,
      "infrastructure-stations",
      substationRenderer
    ),
    onEachFeature: (feature, layer) => {
      const properties = feature.properties;
      layer.bindTooltip(esc(properties.SubstationName || "Distribution substation"), {
        className: "station-label",
        direction: "right",
        permanent: true
      });
      layer.bindPopup(MapInfrastructure.tooltip(properties, [
        ["SubstationName", "Substation"],
        ["SubstationID", "ID"],
        ["Voltage_kV", "Voltage kV"],
        ["NUMBANKS", "Banks"],
        ["Existing_DG", "Existing DG kW"],
        ["Queued_DG", "Queued DG kW"]
      ], esc));
    }
  }).addTo(map);
  layerControl.addOverlay(distributionLayer, "12 kV distribution");
  const voltages = [...new Set(
    transmission.features.map(feature => Number(feature.properties.RATEDKV))
  )].filter(Number.isFinite).sort((left, right) => left - right);
  layerControl.addOverlay(
    transmissionLayer,
    `Transmission (${voltages.join("/")} kV)`
  );
  layerControl.addOverlay(substationLayer, "Distribution substations");
  document.querySelector("#infrastructure-status").hidden = true;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
}
function number(value, digits = 1) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : "Not available";
}
function humanize(value) {
  return String(value ?? "").replaceAll("_", " ");
}
function zoneCode(zone) {
  return zone === "Unclassified" ? "U" : zone;
}
function address(properties) {
  const clean = value => {
    const text = String(value ?? "").trim();
    return ["NONE", "N/A", "NULL"].includes(text.toUpperCase()) ? "" : text;
  };
  const situs = clean(properties.SITUS_ADD);
  const city = clean(properties.SITUS_CTY);
  if (situs || city) return [situs, city].filter(Boolean).join(", ");
  return `${number(properties.centroid_lat, 5)}, ${number(properties.centroid_lon, 5)}`;
}
function baseStyle(feature) {
  const zone = feature.properties.map_zone;
  return {
    color: colors[zone] || colors.Unclassified,
    fillColor: colors[zone] || colors.Unclassified,
    fillOpacity: 0.42,
    opacity: 0.95,
    weight: Number(feature.properties.rank) <= 25 ? 2.5 : 1.25
  };
}
function popup(properties) {
  return `<div class="parcel-details">
    <strong>Rank ${esc(properties.rank)}: ${esc(properties.site_apns)}</strong>
    <div>${esc(address(properties))}</div>
    <table>
      <tr><th>Zone</th><td>${esc(zoneCode(properties.map_zone))} - ${esc(labels[properties.map_zone] || "")}</td></tr>
      <tr><th>__ANCHOR_LABEL__</th><td>${number(Number(properties.scope_anchor_fraction) * 100, 0)}% of parcel</td></tr>
      <tr><th>Grid-scope distance</th><td>${number(properties.scope_grid_distance_m, 0)} m</td></tr>
      <tr><th>Score</th><td>${number(properties.score, 3)}</td></tr>
      <tr><th>Gross / suitable</th><td>${number(properties.gross_acres)} / ${number(properties.contiguous_acres)} acres</td></tr>
      <tr><th>Wetland exclusion</th><td>${number(properties.wetland_exclusion_acres)} acres</td></tr>
      <tr><th>Reference system</th><td>${number(properties.reference_project_mw)} MW PV / ${number(properties.reference_battery_mwh)} MWh</td></tr>
      <tr><th>Feeder</th><td>${esc(properties.pge_FeederName)}</td></tr>
      <tr><th>Feeder peak</th><td>${number(Number(properties.pge_profile_peak_load_kw) / 1000, 2)} MW</td></tr>
      <tr><th>Generation ICA</th><td>${number(properties.pge_GenCapacity_kW, 0)} kW</td></tr>
      <tr><th>PV ICA (secondary)</th><td>${number(properties.pge_GenericPVCapacity_kW, 0)} kW</td></tr>
      <tr><th>Minimum 12 kV distance</th><td>${number(properties.pge_distance_m, 0)} m to the mapped ICA section</td></tr>
      <tr><th>Highway 1</th><td>${esc(properties.highway_1_side)}, ${number(properties.highway_1_distance_m, 0)} m</td></tr>
      <tr><th>Scenic exposure</th><td>${number(Number(properties.highway_1_viewshed_exposure) * 100, 1)}%; visible from about ${number(properties.highway_1_visible_length_m, 0)} m of highway</td></tr>
      <tr><th>Nearest visible view</th><td>${number(properties.highway_1_nearest_visible_distance_m, 0)} m</td></tr>
      <tr><th>Connection</th><td>${esc(humanize(properties.interconnection_path))}</td></tr>
    </table>
  </div>`;
}

const items = [];
for (const feature of candidates.features) {
  const item = {
    feature,
    layer: null,
    popupLayer: null,
    row: null,
    detailRow: null,
    visible: false
  };
  const layer = L.geoJSON(feature, {
    renderer: candidateRenderer,
    style: baseStyle,
    onEachFeature: (item, polygon) => {
      polygon.bindPopup(popup(item.properties), {
        autoPanPadding: L.point(40, 40),
        className: "candidate-popup",
        offset: L.point(280, 0)
      });
      polygon.bindTooltip(
        `#${esc(item.properties.rank)} ${esc(item.properties.site_apns)} (${esc(item.properties.map_zone)})`,
        { sticky: true }
      );
    }
  });
  item.layer = layer;
  layer.eachLayer(polygon => polygon.on("click", () => {
    item.popupLayer = polygon;
    selectItem(item, true, true, true);
  }));
  items.push(item);
}
items.sort((left, right) =>
  Number(left.feature.properties.rank) - Number(right.feature.properties.rank)
);

const rows = document.querySelector("#candidate-rows");
for (const item of items) {
  const properties = item.feature.properties;
  const zone = properties.map_zone;
  const row = document.createElement("tr");
  row.className = "candidate-row";
  row.style.setProperty("--zone-color", colors[zone] || colors.Unclassified);
  row.setAttribute("aria-expanded", "false");
  row.tabIndex = 0;
  row.innerHTML = `
    <td class="number rank">${esc(properties.rank)}</td>
    <td><span class="apn">${esc(properties.site_apns)}</span>
      <span class="address">${esc(address(properties))}</span></td>
    <td><span class="zone" title="${esc(labels[zone] || zone)}">${esc(zoneCode(zone))}</span></td>
    <td class="number">${number(Number(properties.scope_anchor_fraction) * 100, 0)}%</td>
    <td class="number">${number(properties.score, 3)}</td>
    <td class="number">${number(properties.contiguous_acres)}</td>
    <td class="number">${number(properties.gross_acres)}</td>
    <td class="number">${number(properties.pge_GenCapacity_kW, 0)}</td>
    <td class="number">${number(properties.pge_GenericPVCapacity_kW, 0)}</td>
    <td class="number">${number(properties.pge_distance_m, 0)}</td>
    <td class="side-${esc(properties.highway_1_side)}">${esc(properties.highway_1_side)}</td>
    <td class="number">${number(properties.highway_1_distance_m, 0)}</td>
    <td class="number">${number(Number(properties.highway_1_viewshed_exposure) * 100, 1)}%</td>
    <td class="number">${number(properties.highway_1_visible_length_m, 0)}</td>`;
  const detailRow = document.createElement("tr");
  const detailId = `candidate-detail-${properties.rank}`;
  detailRow.className = "candidate-detail";
  detailRow.id = detailId;
  detailRow.hidden = true;
  detailRow.style.setProperty("--zone-color", colors[zone] || colors.Unclassified);
  detailRow.innerHTML = `<td colspan="14">${popup(properties)}</td>`;
  row.setAttribute("aria-controls", detailId);
  row.addEventListener("click", () => toggleRow(item));
  row.addEventListener("keydown", event => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    toggleRow(item);
  });
  item.row = row;
  item.detailRow = detailRow;
  rows.appendChild(row);
  rows.appendChild(detailRow);
}

let selected = null;
function clearSelection() {
  if (!selected) return;
  selected.row.classList.remove("selected");
  selected.row.setAttribute("aria-expanded", "false");
  selected.detailRow.hidden = true;
  selected.layer.setStyle(baseStyle(selected.feature));
  if (selected.popupLayer) selected.popupLayer.closePopup();
  selected = null;
}
function toggleRow(item) {
  if (selected === item) {
    clearSelection();
    return;
  }
  selectItem(item, true, false);
}
function selectItem(item, zoomMap, scrollList, showPopup = false) {
  clearSelection();
  selected = item;
  item.row.classList.add("selected");
  item.row.setAttribute("aria-expanded", "true");
  item.detailRow.hidden = false;
  item.row.after(item.detailRow);
  item.layer.setStyle({
    ...baseStyle(item.feature),
    color: "#111",
    fillOpacity: 0.68,
    weight: 5
  });
  item.layer.bringToFront();
  if (zoomMap) {
    if (item.popupLayer) item.popupLayer.closePopup();
    const bounds = item.layer.getBounds();
    const fitZoom = map.getBoundsZoom(bounds, false, [50, 50]);
    const contextZoom = Math.max(map.getMinZoom(), Math.min(17, fitZoom - 3));
    map.setView(bounds.getCenter(), contextZoom, { animate: false });
    if (showPopup && item.popupLayer) item.popupLayer.openPopup();
  } else if (showPopup) {
    if (item.popupLayer) item.popupLayer.openPopup();
  }
  if (scrollList) {
    item.row.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
  }
}

let sortColumn = "rank";
let sortDirection = 1;
function sortRows() {
  items.sort((left, right) => {
    const leftValue = left.feature.properties[sortColumn];
    const rightValue = right.feature.properties[sortColumn];
    const numeric = document.querySelector(
      `button[data-sort="${sortColumn}"]`
    )?.dataset.type === "number";
    if (numeric) {
      return sortDirection * (Number(leftValue) - Number(rightValue));
    }
    return sortDirection * String(leftValue ?? "").localeCompare(
      String(rightValue ?? "")
    );
  });
  for (const item of items) {
    rows.appendChild(item.row);
    rows.appendChild(item.detailRow);
  }
  for (const button of document.querySelectorAll("th button[data-sort]")) {
    const label = button.textContent.replace(/[ ▲▼]$/, "");
    button.textContent = button.dataset.sort === sortColumn
      ? `${label} ${sortDirection > 0 ? "▲" : "▼"}`
      : label;
  }
}
for (const button of document.querySelectorAll("th button[data-sort]")) {
  button.addEventListener("click", () => {
    const column = button.dataset.sort;
    sortDirection = column === sortColumn ? -sortDirection : 1;
    sortColumn = column;
    sortRows();
  });
}

function zoneMatches(zone, filter) {
  if (filter === "all") return true;
  if (filter === "focus") return focusZones.has(zone);
  if (filter === "residential") return residentialZones.has(zone);
  if (filter === "other") return !focusZones.has(zone);
  return zone === filter;
}
function updateZoneCounts(filter) {
  const totals = [0, 0, 0, 0];
  for (const row of document.querySelectorAll(".zone-counts tr[data-zone]")) {
    const visible = zoneMatches(row.dataset.zone, filter);
    row.hidden = !visible;
    if (!visible) continue;
    [...row.querySelectorAll("td")].forEach((cell, index) => {
      totals[index] += Number(cell.textContent);
    });
  }
  totals.forEach((total, index) => {
    document.querySelector(`[data-total-column="${index}"]`).textContent = total;
  });
}
function applyFilters(fitMap = false) {
  const zoneFilter = document.querySelector("#zone-filter").value;
  updateZoneCounts(zoneFilter);
  const hideWest = document.querySelector("#hide-west").checked;
  const hideZeroIca = document.querySelector("#hide-zero-ica").checked;
  const visibleLayers = [];
  for (const item of items) {
    const properties = item.feature.properties;
    const generationIca = Number(properties.pge_GenCapacity_kW);
    const hasZeroIca = properties.pge_GenCapacity_kW !== null
      && Number.isFinite(generationIca)
      && generationIca === 0;
    const westOrCrossing = ["west", "crosses"].includes(
      properties.highway_1_side
    );
    const visible = zoneMatches(properties.map_zone, zoneFilter)
      && !(hideWest && westOrCrossing)
      && !(hideZeroIca && hasZeroIca);
    item.row.hidden = !visible;
    item.detailRow.hidden = !visible || item !== selected;
    if (visible && !item.visible) item.layer.addTo(map);
    if (!visible && item.visible) map.removeLayer(item.layer);
    item.visible = visible;
    if (visible) visibleLayers.push(item.layer);
  }
  document.querySelector("#result-summary").textContent =
    `${visibleLayers.length} of ${items.length} candidates shown`;
  if (fitMap && visibleLayers.length) {
    map.fitBounds(L.featureGroup(visibleLayers).getBounds(), { padding: [20, 20] });
  }
}
document.querySelector("#zone-filter").addEventListener("change", () => applyFilters(false));
document.querySelector("#hide-west").addEventListener("change", () => applyFilters(false));
document.querySelector("#hide-zero-ica").addEventListener("change", () => applyFilters(false));
sortRows();
applyFilters(true);
loadInfrastructure().catch(error => {
  const status = document.querySelector("#infrastructure-status");
  status.hidden = false;
  status.textContent = error.message;
});
</script>
</body>
</html>
"""
    html = (
        template.replace("__DATA__", data)
        .replace("__COLORS__", colors)
        .replace("__LABELS__", labels)
        .replace("__ANCHOR_LABEL__", anchor_label)
        .replace("__ZONE_COUNT_ROWS__", zone_count_rows)
    )
    destination.write_text(html)

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
    "Unclassified": "#969696",
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
    "Unclassified": "Unclassified",
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

    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mendocino Coast solar-storage candidates</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <style>
    :root { color-scheme: light; font: 14px/1.35 system-ui, sans-serif; }
    * { box-sizing: border-box; }
    html, body, #app { height: 100%; margin: 0; }
    #app { display: grid; grid-template-columns: minmax(650px, 58%) 1fr; }
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
    .controls { display: grid; gap: 7px; grid-template-columns: 1fr 125px; }
    .controls input, .controls select {
      border: 1px solid #999;
      border-radius: 4px;
      font: inherit;
      min-width: 0;
      padding: 7px 8px;
      width: 100%;
    }
    #result-summary { color: #444; font-size: 12px; margin-top: 8px; }
    #candidate-list { min-height: 0; overflow: auto; }
    table.candidates {
      background: white;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 12px;
      min-width: 1000px;
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
    .candidates tbody tr {
      border-left: 5px solid var(--zone-color);
      cursor: pointer;
    }
    .candidates tbody tr:hover { background: #f0f6fa; }
    .candidates tbody tr.selected {
      background: #cfe8f6;
      box-shadow: 5px 0 0 #111 inset;
    }
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
    footer {
      background: white;
      border-top: 1px solid #bbb;
      color: #555;
      font-size: 11px;
      padding: 7px 12px;
    }
    .leaflet-popup-content { min-width: 280px; }
    .leaflet-popup-content table { border-collapse: collapse; width: 100%; }
    .leaflet-popup-content th {
      padding-right: 8px;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }
    @media (max-width: 900px) {
      #app { grid-template-columns: 1fr; grid-template-rows: 48% 52%; }
      #sidebar { border-bottom: 1px solid #888; border-right: 0; }
    }
  </style>
</head>
<body>
<div id="app">
  <aside id="sidebar">
    <header>
      <h1>Mendocino Coast solar-storage candidates</h1>
      <p>Sort any column. Selecting a row locates its parcel; selecting a
      parcel highlights its row.</p>
      <div class="controls">
        <input id="search" type="search" placeholder="APN, address, feeder..."
          aria-label="Search candidates">
        <select id="zone-filter" aria-label="Filter zoning">
          <option value="focus">RR/RMR/RL/AG/Industrial</option>
          <option value="all">All zoning</option>
          <option value="residential">Residential: RR and RMR</option>
          <option value="RL">Rangeland: RL</option>
          <option value="AG">Agricultural: AG</option>
          <option value="I">Industrial: I</option>
          <option value="other">Other zoning</option>
        </select>
      </div>
      <div id="result-summary"></div>
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
          <th><button data-sort="reference_project_mw" data-type="number">PV MW</button></th>
          <th><button data-sort="reference_battery_mwh" data-type="number">Battery MWh</button></th>
          <th><button data-sort="pge_GenericPVCapacity_kW" data-type="number">Static ICA kW</button></th>
          <th><button data-sort="pge_profile_peak_load_kw" data-type="number">Peak MW</button></th>
          <th><button data-sort="highway_1_side">Hwy 1 side</button></th>
          <th><button data-sort="highway_1_distance_m" data-type="number">Hwy dist m</button></th>
          <th><button data-sort="highway_1_viewshed_exposure" data-type="number">Scenic exposure</button></th>
          <th><button data-sort="highway_1_visible_length_m" data-type="number">Visible Hwy m</button></th>
          <th><button data-sort="interconnection_path">Connection</button></th>
        </tr></thead>
        <tbody id="candidate-rows"></tbody>
      </table>
    </main>
    <footer>Screening candidates, not approved projects. Street and aerial
      basemaps can be switched using the map control.
      <a href="downloads.html">Download data and report</a>.</footer>
  </aside>
  <div id="map"></div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
const candidates = __DATA__;
const colors = __COLORS__;
const labels = __LABELS__;
const focusZones = new Set(["RR", "RMR", "RL", "AG", "I"]);
const residentialZones = new Set(["RR", "RMR"]);
const map = L.map("map", { preferCanvas: true });
const imagery = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { attribution: "Imagery &copy; Esri and contributors", maxZoom: 19 }
);
const streets = L.tileLayer(
  "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  { attribution: "&copy; OpenStreetMap contributors", maxZoom: 19 }
).addTo(map);
L.control.layers(
  { "Street map": streets, "Aerial imagery": imagery },
  null,
  { collapsed: false }
).addTo(map);

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
  return `<strong>Rank ${esc(properties.rank)}: ${esc(properties.site_apns)}</strong>
    <div>${esc(address(properties))}</div>
    <table>
      <tr><th>Zone</th><td>${esc(properties.map_zone)} - ${esc(labels[properties.map_zone] || "")}</td></tr>
      <tr><th>__ANCHOR_LABEL__</th><td>${number(Number(properties.scope_anchor_fraction) * 100, 0)}% of parcel</td></tr>
      <tr><th>Grid-scope distance</th><td>${number(properties.scope_grid_distance_m, 0)} m</td></tr>
      <tr><th>Score</th><td>${number(properties.score, 3)}</td></tr>
      <tr><th>Gross / suitable</th><td>${number(properties.gross_acres)} / ${number(properties.contiguous_acres)} acres</td></tr>
      <tr><th>Wetland exclusion</th><td>${number(properties.wetland_exclusion_acres)} acres</td></tr>
      <tr><th>Reference system</th><td>${number(properties.reference_project_mw)} MW PV / ${number(properties.reference_battery_mwh)} MWh</td></tr>
      <tr><th>Feeder</th><td>${esc(properties.pge_FeederName)}</td></tr>
      <tr><th>Feeder peak</th><td>${number(Number(properties.pge_profile_peak_load_kw) / 1000, 2)} MW</td></tr>
      <tr><th>Static PV ICA</th><td>${number(properties.pge_GenericPVCapacity_kW, 0)} kW</td></tr>
      <tr><th>Highway 1</th><td>${esc(properties.highway_1_side)}, ${number(properties.highway_1_distance_m, 0)} m</td></tr>
      <tr><th>Scenic exposure</th><td>${number(Number(properties.highway_1_viewshed_exposure) * 100, 1)}%; visible from about ${number(properties.highway_1_visible_length_m, 0)} m of highway</td></tr>
      <tr><th>Nearest visible view</th><td>${number(properties.highway_1_nearest_visible_distance_m, 0)} m</td></tr>
      <tr><th>Connection</th><td>${esc(humanize(properties.interconnection_path))}</td></tr>
    </table>`;
}

const items = [];
for (const feature of candidates.features) {
  const layer = L.geoJSON(feature, {
    style: baseStyle,
    onEachFeature: (item, polygon) => {
      polygon.bindPopup(popup(item.properties));
      polygon.bindTooltip(
        `#${esc(item.properties.rank)} ${esc(item.properties.site_apns)} (${esc(item.properties.map_zone)})`,
        { sticky: true }
      );
    }
  });
  const item = { feature, layer, row: null, visible: false };
  layer.eachLayer(polygon => polygon.on("click", () => selectItem(item, false, true)));
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
  row.style.setProperty("--zone-color", colors[zone] || colors.Unclassified);
  row.innerHTML = `
    <td class="number rank">${esc(properties.rank)}</td>
    <td><span class="apn">${esc(properties.site_apns)}</span>
      <span class="address">${esc(address(properties))}</span></td>
    <td><span class="zone">${esc(zone)}</span></td>
    <td class="number">${number(Number(properties.scope_anchor_fraction) * 100, 0)}%</td>
    <td class="number">${number(properties.score, 3)}</td>
    <td class="number">${number(properties.contiguous_acres)}</td>
    <td class="number">${number(properties.gross_acres)}</td>
    <td class="number">${number(properties.reference_project_mw)}</td>
    <td class="number">${number(properties.reference_battery_mwh)}</td>
    <td class="number">${number(properties.pge_GenericPVCapacity_kW, 0)}</td>
    <td class="number">${number(Number(properties.pge_profile_peak_load_kw) / 1000, 2)}</td>
    <td class="side-${esc(properties.highway_1_side)}">${esc(properties.highway_1_side)}</td>
    <td class="number">${number(properties.highway_1_distance_m, 0)}</td>
    <td class="number">${number(Number(properties.highway_1_viewshed_exposure) * 100, 1)}%</td>
    <td class="number">${number(properties.highway_1_visible_length_m, 0)}</td>
    <td>${esc(humanize(properties.interconnection_path))}</td>`;
  row.addEventListener("click", () => selectItem(item, true, false));
  item.row = row;
  rows.appendChild(row);
}

let selected = null;
function selectItem(item, zoomMap, scrollList) {
  if (selected) {
    selected.row.classList.remove("selected");
    selected.layer.setStyle(baseStyle(selected.feature));
  }
  selected = item;
  item.row.classList.add("selected");
  item.layer.setStyle({
    ...baseStyle(item.feature),
    color: "#111",
    fillOpacity: 0.68,
    weight: 5
  });
  item.layer.bringToFront();
  if (zoomMap) map.fitBounds(item.layer.getBounds(), { maxZoom: 17, padding: [35, 35] });
  if (scrollList) item.row.scrollIntoView({ behavior: "smooth", block: "center" });
  item.layer.openPopup();
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
  for (const item of items) rows.appendChild(item.row);
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
function applyFilters(fitMap = false) {
  const query = document.querySelector("#search").value.trim().toLowerCase();
  const zoneFilter = document.querySelector("#zone-filter").value;
  const visibleLayers = [];
  for (const item of items) {
    const properties = item.feature.properties;
    const text = [
      properties.site_apns, properties.SITUS_ADD, properties.SITUS_CTY,
      properties.map_zone, labels[properties.map_zone],
      properties.pge_FeederName
    ].join(" ").toLowerCase();
    const visible = zoneMatches(properties.map_zone, zoneFilter)
      && (!query || text.includes(query));
    item.row.hidden = !visible;
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
document.querySelector("#search").addEventListener("input", () => applyFilters(false));
document.querySelector("#zone-filter").addEventListener("change", () => applyFilters(true));
sortRows();
applyFilters(true);
if (items.length) selectItem(items[0], false, false);
</script>
</body>
</html>
"""
    html = (
        template.replace("__DATA__", data)
        .replace("__COLORS__", colors)
        .replace("__LABELS__", labels)
        .replace("__ANCHOR_LABEL__", anchor_label)
    )
    destination.write_text(html)

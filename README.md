# Mendocino Coast solar siting study

This package downloads public GIS and PG&E planning data, screens parcels
within reach of distribution feeders that serve the Mendocino coast, and
produces maps and tables for reviewing community-scale solar sites.

The study introduction, published explorer, and downloadable results are available
at <https://jmacd.github.io/mendo-coast-solar/>. GitHub Actions tests the model,
rebuilds the analysis, and deploys the generated site on pushes to `main`,
manual runs, and the weekly schedule.

The current model is a reproducible first-pass screen. It identifies land that
is open, relatively flat, lightly developed, outside selected environmental
constraints, and near mapped electrical infrastructure. It is not a permit,
title report, biological survey, engineering design, or PG&E interconnection
determination.

Read [STUDY_ANALYSIS.md](STUDY_ANALYSIS.md) for the study history, results,
interpretation of the Caspar parcel, and recommended solar-storage work.

## Requirements

- Python 3.11 or newer
- Internet access to the public services in `config/mendocino.toml`
- Several gigabytes of free disk space
- QGIS or another GIS viewer is optional

The first acquisition can take a substantial amount of time because the
program downloads countywide vectors and 30-meter rasters. Subsequent runs use
the local cache.

## Install

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
```

Run the tests:

```sh
.venv/bin/pytest -q
```

## Reproduce the study

Acquire every configured dataset and run the analysis:

```sh
.venv/bin/solar-siting run
```

The command uses:

- `config/mendocino.toml` for sources, study bounds, thresholds, and weights
- `data/` for downloaded and derived source data
- `output/` for results

Both output directories are ignored by Git because they are reproducible and
can be large. `published/` contains the result snapshot from the original
study; automated deployments publish a fresh run directly without modifying
the repository.

To separate acquisition from analysis:

```sh
.venv/bin/solar-siting fetch
.venv/bin/solar-siting analyze
```

To discard the download cache and retrieve current source data:

```sh
.venv/bin/solar-siting run --refresh
```

Remote datasets change over time, so a refreshed result may differ from the
result documented in this repository. Save `data/provenance.json` with any
published analysis if exact source versions matter.

### Custom paths or configuration

Global options precede the subcommand:

```sh
.venv/bin/solar-siting \
  --config config/mendocino.toml \
  --data-dir data \
  --output-dir output \
  run
```

Copy the TOML file and change the copy when testing alternative thresholds.
This preserves the original assumptions for comparison.

## Outputs

| File | Purpose |
|---|---|
| `output/ranked-parcels.csv` | Primary solar-storage ranking |
| `output/ranked-parcels.geojson` | Ranked site geometry for QGIS or web maps |
| `output/candidate-map.html` | Interactive aerial map colored by base zoning |
| `output/grid-candidates.geojson` | Lightweight candidate layer for the local grid explorer |
| `output/ica-sections.geojson` | Published PG&E ICA sections for the grid explorer |
| `output/distribution-grid.geojson` | Coast-serving feeder geometry for the grid explorer |
| `output/distribution-substations.geojson` | Published PG&E distribution-substation points |
| `output/transmission-lines.geojson` | Published PG&E 60, 115, and 230 kV transmission lines |
| `output/distribution-ready-parcels.*` | Subset with at least 500 kW of static PV ICA |
| `output/screened-parcels.csv` | All analyzed parcels, including failed gates |
| `output/screened-parcels.geojson` | Screened parcel geometry and diagnostics |
| `output/report.md` | Run summary, known-site checks, and limitations |
| `data/provenance.json` | Source URLs, retrieval times, counts, and SHA-256 hashes |

GeoJSON coordinates are WGS84 longitude and latitude. Acreage and distance
calculations use California Albers, EPSG:3310.

Serve the output directory locally so basemap providers receive a normal web
referrer:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory output
```

Then open <http://127.0.0.1:8765/candidate-map.html>. The side-by-side explorer
links a sortable ranking table and map polygons in both directions and supports
searches by APN, County situs address, town, zone, or feeder. The map needs
internet access for Leaflet and aerial or street-map tiles; candidate geometry
and attributes are embedded in the HTML.

Generate the detailed Fort Bragg–Mendocino 12 kV map after running the analysis:

```sh
python tools/render_local_grid_map.py
```

The resulting `site/caspar-local-grid.svg` overlays color-coded PG&E ICA
sections and zoning-colored candidate parcels on an OpenStreetMap basemap.
Candidate addresses and static-PV ICA values are connected to parcel
boundaries. Basemap tiles are downloaded once to `data/osm-tiles/` and cached
for later renders.

The landing page uses `site/grid-explorer.html` for the live version of this
view. It renders a crisp vector basemap, follows pan and zoom anywhere along
the coast, and re-ranks the best candidates in the visible region. The
county-wide ranking remains available in `candidate-map.html`.

Useful output fields include:

- `apn`, `FID`, `centroid_lat`, and `centroid_lon`
- `BASEZONE` and `residential_zoning` (`RR` and `RMR` only)
- `scope_grid_distance_m`, `scope_anchor_fraction`, and `scope_anchor_label`
- `gross_acres`, `screenable_acres`, and `contiguous_acres`
- `flat_fraction`, `open_fraction`, and `mean_slope_deg`
- `pge_distance_m`, line section, voltage, phase count, and published ICA
- feeder customer, distributed-generation, and load-profile summaries
- `transmission_distance_m`
- `highway_1_side`, distance, terrain-viewshed exposure, visible highway
  length, and nearest visible view
- `eligible`, `eligibility_reasons`, component scores, and final `score`

County data can contain several geometry components with the same APN. `FID`
distinguishes those source features.

## Inspect results

Open both GeoJSON files in QGIS. Add current aerial imagery and inspect:

1. Whether the mapped open area is actually clear and usable.
2. Buildings, roads, tree shadows, access, and neighboring land uses.
3. Parcel components and jurisdictional boundaries.
4. Wetlands, protected land, farmland, fire hazard, and transmission lines.
5. The reason each promising near miss failed.

The CSV can be sorted directly. For example, to find storage candidates that
do not meet the static PV ICA threshold, filter:

```text
eligible == True
distribution_readiness_reasons == insufficient_static_pv_ica
```

Those are especially relevant for solar-plus-storage, controlled-export, or
potential grid-upgrade studies.

## Validate a known site

Create a WGS84 GeoJSON file containing named points or polygons:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {"name": "known Caspar candidate"},
      "geometry": {
        "type": "Point",
        "coordinates": [-123.80577, 39.36347]
      }
    }
  ]
}
```

Run:

```sh
.venv/bin/solar-siting analyze --known-sites known-sites.geojson
```

`output/report.md` records the nearest analyzed parcel, its eligibility, and
failed gates. Keep private locations outside Git when appropriate.

## Data sources

The manifest currently retrieves:

- California Coastal Commission Coastal Zone
- Mendocino County parcels and assessor attributes
- US Fish and Wildlife Service National Wetlands Inventory
- California Protected Areas Database
- California Important Farmland
- CAL FIRE hazard zones
- California Energy Commission transmission lines
- Caltrans State Highway Network Route 1 geometry
- PG&E distribution ICA line sections
- PG&E distribution substations and published transmission lines
- PG&E feeder summaries and monthly-hour load profiles
- USGS 3DEP elevation
- USGS/MRLC NLCD 2021 land cover
- NASA POWER solar climatology
- CDTFA/CDT Fort Bragg city limits

URLs and requested fields are declared in `config/mendocino.toml`. Acquisition
supports paginated ArcGIS vectors, related ArcGIS tables, tiled ArcGIS image
services, WCS rasters, and NASA POWER JSON.

## Current screening method

The study scope is configured in `[study_scope]`. For Mendocino, the program
selects distribution-feeder features that intersect the Coastal Zone and then
retains full parcel geometries within one kilometer of those coastal-reaching
feeders. This captures accessible inland parcels without treating the Coastal
Zone as an electrical boundary. Other counties can substitute different
anchor and distribution source keys in configuration. Parcels are processed
as follows:

1. Select complete parcels within the configured distance of distribution
   feeders that reach the study anchor.
2. Remove wetlands with a 30-meter planning buffer.
3. Remove CPAD protected lands.
4. Remove Prime, Statewide Importance, and Unique farmland.
5. Classify sites by Mendocino County or City of Fort Bragg planning
   jurisdiction without subtracting incorporated land.
6. Exclude parcels with County base zoning `OS` (Open Space).
7. Combine touching industrial parcels into candidate assemblages; keep other
   parcels as individual candidates.
8. Keep sites of at least 10 gross acres with no more than $10,000 of assessed
   improvement value per gross acre.
9. Use 30-meter elevation and land-cover cells to locate contiguous land at or
   below 10 degrees slope. Greenfields use NLCD classes 31, 52, 71, and 81.
   Industrial reuse candidates may also use low-intensity developed classes 21
   and 22.
10. Join nearby PG&E three-phase distribution sections and feeder information.
11. Calculate solar resource, local-demand, infrastructure, land, and
    development metrics.

Current hard eligibility requires:

- At least 10 contiguous open and flat acres
- A three-phase PG&E section within 1 kilometer
- The development-intensity threshold described above

The primary weighted score combines contiguous land, flatness, allowed cover,
low development intensity, industrial reuse, distribution and transmission
proximity, feeder residential customers, feeder peak demand, static PV ICA,
solar climatology, and low terrain visibility from Highway 1. Static ICA is
deliberately a small scoring factor, not a hard gate. The separate
`distribution-ready-parcels` output applies the 500 kW static-PV threshold.

The scenic model samples official Route 1 geometry every 100 meters and tests
terrain line-of-sight to nine representative cells in each site's largest
contiguous suitable solar area. It uses the 30-meter USGS 3DEP elevation
raster, a 1.7-meter highway observer, a 3-meter solar target, and a 5-kilometer
view radius. Forest and woody-wetland NLCD classes add conservative visual
obstruction heights of 12 to 20 meters; a 30-meter endpoint clearance prevents
coarse land-cover pixels from placing vegetation on the highway or solar
clearing. The exposure index averages the visible target fraction at each
observer, discounted exponentially by viewing distance with a 1-kilometer
scale. An exposure of 0.04 is configured as the high-exposure end of the
15-percent scenic score.

The output retains east/west/crossing and direct highway distance for context,
but neither affects the score. It also reports raw exposure, approximate
visible highway length, and nearest visible viewing distance.

Industrial zoning is used only as a reuse indicator; zoning and Local Coastal
Program fields are not interpreted as legal entitlement.

## Critical interpretation: solar plus storage

Static ICA describes an **uncontrolled distribution-export screen**, not the
maximum amount of solar that can be installed on a parcel.
For example, APN `1180901200` has approximately 25.8 contiguous open/flat acres
and land capacity well above 1 MW, but its nearby 12 kV section publishes only
128 kW of general-generation ICA and 186 kW of generic-PV capacity.

A 1 MW array can still be a plausible concept if a battery and certified power
control system keep instantaneous export within an approved static or
time-varying limit. Installed PV power, daily generated energy, battery charge
power, battery energy, and grid export power are different quantities.

The existing `screened_project_mw` field is therefore conservative: it is the
minimum of land potential, static ICA, and minimum daytime feeder load. Do not
interpret it as the parcel's maximum feasible PV nameplate.

California Rule 21 Limited Generation Profiles may permit nameplate capacity
above static hosting capacity when certified controls enforce an approved
export schedule. A formal PG&E study remains necessary.

The model also records proximity to transmission but does not assess
transmission interconnection. APN `1180901200` is approximately 3 meters from
a mapped operational PG&E 60 kV line. A connection there would be a distinct,
more expensive transmission-level project whose available capacity is not
described by distribution ICA.

## Limitations

- PG&E ICA is planning information, not permission to interconnect.
- The selected mapped line may not be the feasible point of interconnection.
- Public transmission geometry does not reveal capacity, easements, protection
  requirements, substation work, or upgrade cost.
- NASA POWER is too coarse to resolve coastal fog and local shading.
- The Highway 1 viewshed combines a 30-meter bare-earth DEM with categorical
  NLCD forest-height assumptions. It is not a measured surface model and can
  miss or misstate individual trees, buildings, hedges, berms, and proposed
  screening.
- Highway observer and solar target heights are planning assumptions, not a
  project-specific visual simulation. Field photographs and a LiDAR surface
  model should replace them during feasibility review.
- Monthly-hour feeder ranges are not an actual Caspar hourly load series.
- Assessed improvement value and NLCD are imperfect proxies for undeveloped
  land.
- NWI does not replace wetland delineation.
- Public parcel and jurisdictional boundaries are representational.
- No sensitive-habitat, cultural-resource, title, access, geotechnical,
  erosion, flood, or full permitting review has been performed.

## Current storage ranking and next development

The model now retains both a strategic solar-storage ranking and a static
distribution-ready subset. Its 1 MW PV / 4 MWh battery reference case is for
comparison only; no hourly dispatch is yet simulated.

The next development should add hourly coastal solar, actual aggregated
community load, battery dispatch and losses, curtailment, static and Limited
Generation Profile export limits, evening delivery, resilience loads, and
estimated interconnection upgrade gaps.

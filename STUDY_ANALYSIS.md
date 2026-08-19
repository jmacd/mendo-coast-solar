# Mendocino Coast community solar siting analysis

## Purpose

This study began with a practical local observation: Caspar has land that may
support a community-scale solar field, and similar sites may exist elsewhere
along the Mendocino Coast. The goal was to replace accidental discovery with a
repeatable public-data method that could:

- Search parcels within reach of grid feeders serving the Mendocino coast.
- Find at least 10 contiguous usable acres.
- Prefer undeveloped or lightly developed land.
- Account for terrain, land cover, environmental constraints, and electrical
  infrastructure.
- Identify sites capable of serving coastal communities rather than exporting
  power inland.
- Test the method against locally known parcels.

The work produced the Python package in this directory. It downloads the
source data, caches it with provenance, performs parcel-scale GIS analysis,
and writes ranked and diagnostic CSV and GeoJSON outputs.

## Evolution of the question

The initial question was framed as ground-mounted solar siting. Discussion and
validation changed the energy concept in several important ways:

1. A useful site should accommodate at least 10 acres of contiguous solar,
   corresponding to community or small grid scale rather than a rooftop
   installation.
2. Fort Bragg should be excluded because its incorporated territory has a
   separate planning process; the study is intended for County jurisdiction.
3. One initially top-ranked parcel was the former Noyo mill/headlands site.
   Local knowledge identified industrial contamination and Fort Bragg
   jurisdiction, demonstrating why public-data ranking requires validation.
4. A coast-wide ranking over-concentrated results near Elk. That happened
   because southern parcels had more open land and higher published PG&E
   distribution hosting capacity.
5. Caspar's load is weighted toward winter evenings, and coastal solar is
   intermittent. A realistic project therefore requires battery storage.
6. Static distribution hosting capacity constrains instantaneous export, not
   installed solar nameplate or daily energy production.
7. APN `1180901200` lies immediately beside a mapped operational PG&E 60 kV
   line, creating a separate potential transmission-interconnection pathway
   that the first model does not evaluate.
8. Restricting parcels to the Coastal Zone omitted inland sites served by the
   same local 12 kV grid, including a strong candidate near County Road 409.
9. Local map re-ranking made a county-wide municipal exclusion unnecessary.
   Fort Bragg parcels are now retained and labeled with their separate planning
   jurisdiction.

The resulting conclusion is not simply "find the highest-scoring solar
parcel." The proper next question is:

> Which sites can produce and store enough energy for a coastal community,
> deliver it when needed, and interconnect through controlled distribution
> export, feasible upgrades, or transmission?

## Reproducible data foundation

The study uses public sources declared in `config/mendocino.toml`:

| Subject | Source and use |
|---|---|
| Study anchor | California Coastal Commission Coastal Zone |
| Parcel scope | Full parcels within 1 kilometer of distribution feeders that intersect the study anchor |
| Parcels | Mendocino County parcels, APNs, acreage, improvements, zoning, and LCP fields |
| Wetlands | USFWS National Wetlands Inventory |
| Protected land | California Protected Areas Database |
| Farmland | California Important Farmland |
| Fire | CAL FIRE hazard zones, retained as context |
| Transmission | California Energy Commission lines |
| Distribution | PG&E ICA/GRIP line sections |
| Feeders | PG&E feeder customers, distributed generation, and monthly-hour load ranges |
| Terrain | USGS 3DEP elevation |
| Land cover | USGS/MRLC NLCD 2021 |
| Solar | NASA POWER climatology |
| City limits | CDTFA/CDT Fort Bragg land boundary |

Acquisition records URLs, retrieval times, feature counts, and SHA-256 hashes
in `data/provenance.json`. ArcGIS object IDs are retrieved first and features
are downloaded in batches. Large rasters are tiled. Vector data are clipped to
the coastal acquisition envelope before caching.

California Albers (`EPSG:3310`) is used for acreage and distance calculations.
Web outputs are converted to WGS84.

## Land analysis

The program selects complete County parcels within one kilometer of mapped
distribution feeders that intersect the Coastal Zone. The Coastal Zone is an
anchor for identifying coast-serving feeders, not a parcel cutoff. It then:

- Repairs invalid parcel and constraint geometry.
- Removes NWI wetlands with a configurable 30-meter planning buffer.
- Removes CPAD protected land.
- Removes Prime, Statewide Importance, and Unique farmland.
- Retains Fort Bragg parcels and labels their separate planning jurisdiction.
- Calculates gross, excluded, and screenable acreage.
- Uses assessed improvement value per acre as a development-intensity proxy.

For each remaining parcel, 30-meter raster cells must satisfy both:

- Slope no greater than 10 degrees.
- NLCD open cover: barren, shrub, grassland, or pasture.

Connected raster cells are measured to find the largest contiguous open and
flat area. Forest and developed cells do not count as usable solar acreage.

The hard land requirement is 10 contiguous acres. The assumed planning density
is 5.5 acres per MW, used only to estimate physical nameplate potential.

## Electrical analysis

### Distribution sections

The model assigns each site its nearest mapped PG&E ICA line section. It does
not assume that a more distant section with higher published ICA is a feasible
point of interconnection. The one-kilometer distance and three-phase
requirements are then applied to that nearest section.

It records:

- Feeder and substation
- Line-section identifier
- Minimum straight-line distance from the screened candidate geometry to that
  mapped 12 kV ICA section
- Nominal voltage and phase count
- General generation ICA
- Generic-PV ICA
- Existing and queued distributed generation
- Residential, commercial, industrial, agricultural, and other customers
- Monthly-hour low and high feeder load values

The initial model required three-phase service and at least 500 kW of
published general-generation ICA. The storage-oriented revision retains the
three-phase and distance gates, uses generation ICA as a small score rather
than a hard threshold, and reports PV ICA as secondary context.

The same section distance drives the distribution-proximity score:
`exp(-distance / 1,000 meters)`. It is a lower bound rather than a designed
connection route. The utility-selected interconnection point, conductor route,
access, easements, poles, and switching can make the actual extension longer
and more expensive.

### Feeder demand

The available PG&E profile is not a continuous measured Caspar load series. It
contains monthly-hour low and high values for the entire feeder. The model
derives:

- Minimum load
- Peak load
- Minimum load from 10 a.m. through 3 p.m.

Minimum daytime load was initially used as a conservative bound on direct
solar absorption. Discussion revealed that this is not the central community
objective because local demand peaks after solar production.

For the `FORT BRAGG A 1102` feeder associated with Caspar, the downloaded data
show:

- Minimum daytime load: approximately 1,146 kW
- Peak load: approximately 3,840 kW
- Peak timing: winter evenings, especially December around 6-8 p.m.
- Residential customers: 2,730
- Commercial customers: 272
- Existing distributed generation: approximately 2,555 kW
- Queued distributed generation: approximately 2,892 kW

These are feeder-wide values, not Caspar-only consumption.

### Transmission

The model currently calculates distance to mapped transmission lines but does
not use transmission in eligibility or estimate available transmission
capacity.

The downloaded California Energy Commission layer contains 11 transmission
features inside the study acquisition bounds. Every feature is identified as
an operational, overhead, PG&E-owned 60 kV line. The mapped network follows
the coast from Fort Bragg south through Mendocino, Elk, Point Arena, and
Gualala, with several links running east toward the inland system.

This establishes the voltage and mapped topology, not the ability to export a
new project's output. The public data used by this study does not provide:

- Thermal ratings or present loading of the 60 kV lines
- Normal and contingency transfer limits
- Voltage or reactive-power limits
- Available transmission capacity or deliverability
- The effect of active interconnection-queue projects
- A project-specific point of interconnection or network-upgrade cost

PG&E's ICA values cannot fill this gap. They describe changing conditions on
individual 12 kV distribution sections. For example, the nearest mapped
Caspar section reports 186 kW of generic-PV ICA. Another section near the
historic Caspar mill area reports 319 kW, but the model does not assign that
more distant section to the Fern Creek site. Neither number describes the
adjacent 60 kV transmission line.

A developer proposing a transmission-level wholesale generator must identify
a point of interconnection and enter the CAISO generator-interconnection
process. Power-flow, short-circuit, stability, reliability, and deliverability
studies determine whether network upgrades are required. Consequently, the
defensible first conclusion is not that an inland upgrade is certainly
required. It is that a developer cannot infer an available path to the
wholesale market from the mapped 60 kV line, and must treat inland transfer
capability and upgrade cost as unresolved project risks until formal study.

For APN `1180901200`, the nearest mapped feature is:

- PG&E
- Operational
- 60 kV
- Overhead
- Approximately 3 meters from the parcel geometry

This is potentially important, but line proximity alone does not establish a
right or ability to interconnect. A transmission project may require a
switching station, project substation, protection, metering, communications,
easements, system studies, and network upgrades. Its cost and regulatory path
would differ substantially from a 12 kV distribution connection.

## Scoring and first result

The first-pass score combines:

- Contiguous usable land
- Flat fraction
- Open-cover fraction
- Low development intensity
- Distribution proximity
- Published grid hosting capacity
- Solar climatology

With Fort Bragg excluded, the original hard-gated run processed:

- 10,112 Coastal Zone parcel features
- 1,332 parcels after coarse land, constraint, and development screening
- 10 parcels passing every original hard gate

All 10 eligible results are near Elk and connect conceptually to `ELK 1101`,
where published general-generation ICA is approximately 820 kW. The highest
original result was APN `1271100800`.

This concentration is a model result, not a recommendation to generate the
coast's power in Elk. The hard ICA threshold rewards locations where PG&E
currently publishes more spare distribution-export capacity and excludes
strategically useful sites that require controls or upgrades.

## Storage-oriented reranking

The revised primary ranking assumes the objective is solar plus storage serving
local coastal homes. It:

- Removes static ICA as a hard eligibility gate.
- Gives generation ICA and minimum 12 kV distance 22.5 percent each.
- Uses a 1 MW PV / 4 MWh battery reference case for comparable reporting.
- Reports the generation ICA export limit and reference-project export gap.
- Reports controlled-export, distribution-upgrade, and nearby-transmission
  study paths without treating them as approvals.
- Combines multiple source geometry sections sharing one APN.
- Allows low-intensity developed NLCD classes on industrial reuse sites.
- Reports industrial reuse, feeder demand, and transmission proximity without
  using them in the score.
- Retains wetland and other planning exclusions as measured acreage losses.
- Excludes County Open Space (`OS`) zoning.
- Rewards low terrain visibility from Highway 1.

The grid-corridor run starts with 15,927 grid-accessible parcel features,
creates 2,381 candidate sites after coarse constraints, and finds 208 sites
with at least 10 contiguous suitable acres, a three-phase section within 1
kilometer, and acceptable assessed improvement intensity. Both published ICA
values are reported without imposing a minimum ICA threshold.

The highest-ranked sites now occur on the higher-demand Fort Bragg/Caspar
feeders rather than exclusively around Elk. The former mill assemblage ranks
first, the Road 409/Prairie Way candidate ranks second, and APN `1180901200`
ranks eighteenth.

The Highway 1 factor now performs terrain line-of-sight tests instead of using
east or west location as a proxy. It:

- Samples the official Caltrans Route 1 geometry every 100 meters.
- Samples nine cells across each site's largest contiguous suitable solar area.
- Uses the 30-meter USGS 3DEP bare-earth elevation raster.
- Adds conservative obstruction heights for NLCD deciduous, evergreen, mixed
  forest, and woody-wetland classes.
- Ignores vegetation within 30 meters of highway and target endpoints so a
  coarse land-cover pixel does not place trees on the road or solar clearing.
- Places highway observers 1.7 meters above terrain and solar targets 3 meters
  above terrain.
- Tests observers within 5 kilometers and discounts exposure exponentially
  with a 1-kilometer distance scale.
- Reports the distance-weighted exposure index, approximate length of highway
  with a view, and nearest visible view.

The low-visibility component is 15 percent of the total score. A raw exposure
index of 0.04 is treated as the high-exposure end of that component. The
east/west/crossing label and direct highway distance remain descriptive but no
longer affect ranking.

This correction directly tests the locally identified scenic parcel. The APN
is `1180503000` (not `1180500300`, which is absent from the downloaded County
layer). The vegetation-aware model estimates it is visible from approximately
0.9 kilometers of sampled highway, with the nearest visible view about 30
meters away and a 2.81-percent exposure index. It ranks 23rd rather than first.
APN `1180901200` has a 2.51-percent exposure index, approximately 0.6
kilometers of visible highway, and a nearest visible view about 119 meters
away; it ranks eighteenth.

This remains a screening viewshed, not a project visual-impact study. The
NLCD obstruction heights are categorical assumptions, not measured tree
heights, and omit individual buildings, hedges, and proposed screening.
Thirty-meter cells can also miss road cuts, berms, small ridges, and narrow
view corridors. Field photography and a LiDAR surface model should be used
before a planning conclusion.

### Former mill assemblage

The three adjacent industrial APNs `0172613300`, `0172613400`, and
`0172613500` were initially missed because parcel boundaries were treated as
site boundaries and developed NLCD classes were rejected. Together they form
one approximately 35.97-acre industrial candidate.

The revised result is:

| Measure | Result |
|---|---:|
| Solar-storage rank | 1 of 208 |
| Gross GIS area | 35.97 acres |
| Wetland planning exclusion | 14.38 acres |
| Screenable area after all vector exclusions | 21.58 acres |
| Largest contiguous suitable area | 11.34 acres |
| Land-based PV potential | 2.06 MW |
| Reference PV | 1.00 MW |
| Reference battery | 4.00 MWh |
| Reference annual generation | 1,546 MWh |
| Reference average power | 176 kW |
| Generation ICA | 167 kW |
| Reference static export gap | 833 kW |
| Feeder residential customers | 2,730 |
| Feeder peak load | 3.84 MW |
| Highway viewshed exposure | 0.0% |
| Approximate visible highway length | 0 km |
| Nearest visible highway view | None modeled |
| Nearest mapped transmission | 60 kV, approximately 323 meters |

This ranking quantifies both sides of the local judgment. The wetland removes
about 40 percent of gross acreage under the planning-buffer assumption, and
the remaining contiguous area is only modestly above the 10-acre threshold.
On the positive side, the site is flat, sunny in the coarse climatology,
already zoned industrial, has low assessed improvements relative to acreage,
serves a feeder with substantial residential and winter-evening demand, and
offers a comparatively low-noise, low-routine-traffic reuse of mill land.

Solar-storage equipment is not silent. Inverters, transformers, battery HVAC,
and emergency equipment require acoustic study, setbacks, screening, and
careful placement. Construction traffic, contamination, wetlands, and
remediation remain due-diligence issues rather than hidden score adjustments.

## Zoning composition

The primary ranking contains 208 sites. Open Space zoning is excluded. `RL` is
Rangeland and is not counted as residential. Only `RR` (Rural Residential) and
`RMR` (Remote Residential) are classified as residential in this summary.

`site/grid-explorer.html` visualizes these sites over street or aerial imagery.
It ranks compact candidate cards within the current map viewport and can fit all
filtered candidates on request. Cards can be sorted by score, Generation ICA,
suitable acres, or 12 kV distance, and expand to show land, grid, zoning, road,
and visibility attributes.

| Base zone | Meaning | Sites | Share |
|---|---|---:|---:|
| `RL` | Rangeland | 125 | 60.1% |
| `AG` | Agricultural | 39 | 18.8% |
| `RMR` | Remote Residential | 13 | 6.3% |
| `RR` | Rural Residential | 10 | 4.8% |
| Unclassified | Blank County base-zone value | 7 | 3.4% |
| `FL` | Forest Lands | 6 | 2.9% |
| `TP` | Timberland Production | 5 | 2.4% |
| `PF` | Public Facilities | 2 | 1.0% |
| `I` | Industrial | 1 | 0.5% |

Therefore, **23 of 208 candidates (11.1 percent)** are residentially zoned:
13 RMR and 10 RR. They represent approximately 784 gross acres, 419 contiguous
suitable acres, and 76.2 MW of theoretical land-based PV potential.

Residential zoning is concentrated near the top because the storage-oriented
score rewards feeder residential customers and evening demand: 5 of the top
10 sites and 12 of the top 25 are RR or RMR. That concentration is a warning,
not necessarily a virtue. Utility-scale solar-storage may conflict with
residential character, neighbors, access, views, or permitted-use rules. A
future policy screen should either penalize residential zoning or place these
sites in a separate category rather than allowing local-demand scoring to
dominate land-use compatibility.

## Caspar-area findings

Expanding the scope beyond the Coastal Zone revealed APN `1185001100` at
14000 Prairie Way near County Road 409. Only about 32.5 percent of its parcel
geometry lies inside the Coastal Zone, so the previous boundary clip omitted
most of the site. The revised screen estimates 31.6 contiguous suitable acres
on 43.2 gross acres. Its nearest mapped section intersects the parcel and
publishes 128 kW of generation ICA and 186 kW of PV ICA, the same values
assigned to Fern Creek. It ranks second overall and warrants direct comparison
with Fern Creek, subject to confirming Public Facilities zoning, ownership,
existing uses, access, environmental constraints, and interconnection
feasibility.

These Caspar parcels illustrate why published ICA is reported as a diagnostic
rather than used as a minimum threshold:

| APN | Approximate location | Contiguous open/flat acres | Land potential | Nearby general-generation ICA |
|---|---|---:|---:|---:|
| `1180503000` | 39.36648, -123.81254 | 16.7 | 3.03 MW | 229 kW |
| `1180901200` | 39.36347, -123.80577 | 25.8 | 4.69 MW | 128 kW |
| `1180600900` | 39.36625, -123.80574 | 14.2 | 2.59 MW | 128 kW |
| `1181405700` | 39.35477, -123.81060 | 10.7 | 1.94 MW | 229 kW |
| `1181405800` | 39.35231, -123.81047 | 22.7 | 4.12 MW | 229 kW |
| `1181504500` | 39.35194, -123.80571 | 18.7 | 3.40 MW | 128 kW |

These acreages are raster-screening estimates, not surveyed buildable areas.

### APN 1180901200

This known parcel is a valuable model check:

| Attribute | First-pass result |
|---|---:|
| Gross area | Approximately 30.2 acres |
| Contiguous open/flat area | Approximately 25.8 acres |
| Land-based PV potential | Approximately 4.69 MW |
| Nearest mapped 12 kV distribution section | Approximately 13 meters |
| Distribution phases | Three |
| General-generation ICA | 128 kW |
| Generic-PV ICA | 186 kW |
| ICA limiting criterion | Voltage |
| Limiting period | April at 1 p.m. |
| ICA analysis date observed | October 2025 |

The voltage constraint is plausible on a rural distribution branch. High solar
output can cause local voltage rise even when the feeder as a whole has more
load than the project produces. Loads may be upstream or on other branches,
line impedance matters, and existing or queued generators may consume
available capacity.

## Power, energy, and the 128 kW figure

The most important correction from the study is that power and energy must not
be conflated:

- MW or kW measures instantaneous power.
- MWh or kWh measures energy over time.
- "kW/h" is not the appropriate unit for average daily production.

A 1 MW array producing for five equivalent full-sun hours generates about
5 MWh that day. Spread over 24 hours, that is an average of about 208 kW.
Nevertheless, the array can approach 1 MW around midday. The grid must be able
to handle the instantaneous export unless a battery, controls, or curtailment
prevents it.

The 128 kW ICA number therefore does not necessarily prohibit 1 MW of panels.
It indicates the published static general-generation export capability of the
nearest mapped distribution section under PG&E's assumptions.

A simplified 1 MW solar-storage concept might:

1. Generate 5 MWh on a favorable day.
2. Export no more than an approved limit at any instant.
3. Charge a battery with excess midday generation.
4. Discharge during evening demand.
5. Curtail solar if the battery is full and export is constrained.

If export were fixed at 128 kW, five solar hours could export about 0.64 MWh
directly. Approximately 4.36 MWh would remain for storage or curtailment.
After losses, a battery might deliver roughly 3.9 MWh over another 30 hours
at 128 kW. This is an illustration, not a design; real performance
requires hourly weather, load, equipment, reserve, degradation, and seasonal
analysis.

California Rule 21 Limited Generation Profiles create a possible pathway for
nameplate generation above static ICA when certified controls enforce an
approved time-varying export schedule. PG&E still applies technical screens,
and permission is project-specific.

## Why storage is fundamental

Storage is not an optional scoring bonus for this use case:

- Coastal fog makes solar production variable.
- Caspar-area demand is not concentrated at midday.
- The feeder's observed high values occur on winter evenings.
- Storage can smooth short solar variation and shift energy into evening
  hours.
- Export controls can prevent instantaneous flow from exceeding an approved
  distribution limit.
- A battery may also support resilience, although operating as a community
  microgrid requires additional switching, protection, controls, and tariffs.

Battery power and battery energy must be modeled separately. A 1 MW / 4 MWh
battery can nominally discharge at 1 MW for four hours; it cannot cover several
cloudy days without substantially more stored energy or grid support.

Storage also does not by itself remove interconnection constraints. Charging
may create load, discharging creates generation, and PG&E must approve the
operating envelope and failure behavior.

## Serving Caspar

"Caspar-generated power for Caspar" can describe different arrangements:

### Locally matched procurement

A local project could sell energy through Sonoma Clean Power or another
authorized arrangement while PG&E continues to deliver electricity. Caspar
consumption could be matched contractually to local generation, even though
electrons mix on the grid. This is likely the most practical initial structure.

### Community microgrid

A defined section of distribution system could island during outages and serve
critical local loads from solar and storage. The electrical island boundary
may not match a civic or district boundary. PG&E switching, protection,
communications, black-start capability, and an approved tariff or agreement
would be required.

### Independent local utility

Owning wires and supplying all residents directly is much more difficult.
California Government Code section 61100 does not clearly grant an ordinary
community services district broad solar-electric utility authority. Its
express generation provision concerns hydroelectric facilities associated
with district water and wastewater operations. Any proposal for a district to
become an electric utility requires specialized legal, LAFCO, regulatory, and
financial analysis.

The practical institutional path may therefore combine a local public or
cooperative project entity, Sonoma Clean Power procurement, PG&E delivery, and
a narrower resilience microgrid.

## What the current model does well

- Repeats a coast-wide search from public sources.
- Uses physically valid projected acreage.
- Measures contiguous terrain and open cover rather than gross parcel acreage.
- Explains why near misses fail.
- Includes distribution phase, voltage, ICA, feeder, customer, DG, and load
  information.
- Preserves source provenance and caching.
- Demonstrated the value of local validation by separating planning
  jurisdictions and recognizing Caspar solar-storage opportunities hidden by
  the hard ICA gate.

## What the current model does not yet answer

- Caspar's actual hourly and seasonal energy use
- Hourly coastal solar production and fog variability
- Battery charge/discharge dispatch, efficiency, degradation, and reserve
- Curtailed energy
- Static versus time-varying approved export
- Distribution upgrade cost
- Transmission hosting capacity or interconnection cost
- Community microgrid electrical boundaries
- Ownership, title, access, easements, and contamination
- Detailed habitat, cultural, geotechnical, erosion, and permitting constraints
- Project economics and procurement structure

NASA POWER solar climatology is too coarse for the local fog question. The
assessor improvement field is only a development proxy, and 30-meter NLCD can
miss buildings, narrow clearings, and trees.

## Recommended next study

### 1. Establish Caspar load

Request anonymized aggregated hourly or 15-minute load for a defined Caspar
boundary from PG&E and/or Sonoma Clean Power. Derive:

- Annual MWh
- Monthly energy
- Seasonal and daily peaks
- Evening peak duration
- Critical outage load

### 2. Establish local solar production

Use at least one year of nearby measured irradiance or production if available.
Combine it with a long-term weather series and explicitly represent fog,
seasonality, and consecutive low-production days.

### 3. Simulate solar-storage dispatch

For each candidate, test combinations of:

- PV nameplate MW
- Battery charging and discharging MW
- Battery MWh
- Round-trip efficiency
- State-of-charge limits and resilience reserve
- Static export limits
- Limited Generation Profiles
- Curtailment

Report annual delivered MWh, percentage of Caspar demand served, winter-evening
delivery, curtailed energy, battery cycles, and unmet resilience load.

### 4. Separate interconnection pathways

Produce distinct feasibility cases:

- Existing 12 kV distribution with controlled export
- Upgraded distribution connection
- 60 kV transmission connection
- Islandable critical-load microgrid

Do not use distribution ICA to estimate transmission capacity.

### 5. Rank by community area

Avoid a single coast-wide list dominated by one feeder. Rank the best sites per
community or feeder and distinguish:

- Immediately exportable sites
- Strategic solar-storage sites
- Sites requiring distribution upgrades
- Sites potentially suitable for transmission interconnection

### 6. Perform due diligence on APN 1180901200

The parcel warrants a focused feasibility study because it combines substantial
screened land, a known local use case, three-phase distribution, and immediate
60 kV proximity. Next checks should include:

- Title, ownership, access, and transmission easements
- Current aerial and field review
- Wetlands, habitat, cultural, and geotechnical review
- Local zoning and Coastal Development Permit pathway
- PG&E pre-application discussion for controlled 12 kV export
- PG&E/CAISO guidance on a 60 kV point of interconnection
- Caspar load aggregation and battery dispatch scenarios

## Present conclusion

The program narrowed 15,927 grid-accessible parcel features to a reviewable
set. The storage-oriented revision ranks strategic sites and reports both
published ICA values without using either as a minimum threshold.

For the project now under consideration, APN `1180901200` should be treated as
a strong strategic candidate for solar plus storage. A 1 MW array is not
contradicted by the 128 kW generation ICA figure if approved controls, storage,
and curtailment keep export within an acceptable envelope. The nearby 60 kV
line may create a second, larger interconnection option. Both paths require formal engineering
and utility study, but neither is represented fairly by the static-ICA subset
alone.

The former mill assemblage is also a credible result rather than a model
exception: after explicitly subtracting its wetland constraint and recognizing
industrial reuse across all three APNs, it ranks first. Its position should be
treated as a reason for field, environmental, neighborhood, and
interconnection study—not as a finding that the site is permit-ready.

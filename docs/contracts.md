# Contracts

Every JSON file wire reads or writes has a Pydantic model; the model is
the source of truth and this page summarizes it. All models reject
unknown fields unless noted.

## HarnessContract (`<name>.contract.json`, `src/wire/contract.py`)

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | `1` | |
| `contract_id` | `WH-…` | |
| `name`, `revision` | text | |
| `ipc_class` | 1, 2, 3 (default 2) | IPC/WHMA-A-620 class |
| `ambient_temperature_c` | number (default 25) | drives temperature derating |
| `connectors[]` | `HarnessConnector` | `id` `C<n>`, `family`, `housing`, `mate`, `rated_current_a`, `rated_voltage_v`, `mating_cycles` (30), `keying`, `sealed`, `temp_rating_c`, `cavity_count`, `cavities[]` (`id`, `terminal`, `accepts_mm2` `[min, max]`), `source` |
| `wire_types[]` | `WireType` | `id` `WT<n>`, `name`, `spec` (see `wire_standards`), `gauge_mm2`, `outer_diameter_mm`, `resistance_ohm_per_km`, `ampacity_a`, `reference_temp_c`, `temp_derating[]`, `insulation_rating_v`, `insulation_temp_c`, `min_bend_factor`, `shield` (`none`/`braid`/`foil`), `flex_class` (`static`/`dynamic`/`high_flex`), `source` |
| `nets[]` | `HarnessNet` | `id` `N<n>`, `ref`, `signal_class` (`power`, `ground`, `signal`, `analog`, `data`, `highspeed`, `shield`), `voltage_v`, `current_a`, `max_voltage_drop_v`, `shield_required`, `twisted_pair_with`, `source` |
| `wires[]` | `HarnessWire` | `id` `W<n>`, `wire_type`, `net`, `color`, `from_endpoint`/`to_endpoint` (connector + cavity, or splice), `length_m`, `strip_a_mm`/`strip_b_mm` (4.0), `terminal_a`/`terminal_b`, `route` |
| `routes[]` | `HarnessRoute` | `id` `RT<n>`, `segments[]` (`id` `S<n>`, `length_m`, `min_bend_radius_mm`), `protection` (`none`, `tape`, `tube`, `conduit`, `sleeve`), `flex_required`, `anchors[]` (ordered anchor names) |
| `splices[]` | `HarnessSplice` | `id` `SP<n>`, `kind` (`crimp`, `solder`, `ultrasonic`, `ferrule`) |
| `segregations[]` | `SegregationPolicy` | `classes` (pair of signal classes), `rule` (`no_shared_route`, `no_shared_connector`) |
| `service` | `ServiceExpectation` | `mating_cycles`, `flex_cycles` |
| `imported_sources[]` | `ImportedSource` | `id` `I<n>`, `system` (`manual`, `circuit`, `mech`, `csv`, `kbl`, `vec`), `ref` (workspace-relative path), `sha256`, `description`, `anchors[]`, `anchor_points[]` (`name`, `kind` `clip`/`grommet`/`breakout`/`other`, `position_mm` `[x, y, z]`) |
| `drawing` | `DrawingInfo` | ISO 7200 title-block data: `legal_owner` (≤40), `responsible_dept` (≤20), `technical_reference` (≤30), `created_by`/`approved_by` (≤30), `date_of_issue` (`YYYY-MM-DD`, requires `approved_by`), `supplementary_title` (≤60), `classification` (key words, ≤25), `language` (ISO 639, default `en`), `owner_logo` (`{path, sha256}`: an `.svg`/`.png` relative to the contract directory, ≤256 KiB, printed in the Legal owner cell; a missing file, path escape or digest mismatch fails the export); the document status is derived (`In preparation` → `In approval` → `Released`) |

Element `source` (`system`, `ref`) records where an imported element came
from.

## Intake (`<name>.intake.json`, `src/wire/intake.py`)

`contract_sha256`, `requirements[]` (`R<n>`, `text`, `source`
`user`/`agent`, `speaker`), `assumptions[]` (`A<n>`, `text`, `rationale`,
optional `evidence`), `open_questions[]` (`Q<n>`, `text`, optional
`evidence`), `element_sources` (element id → list of `R*`/`A*`/`I*`
ids). `evidence` is `{kind: image|document|cad_file, path, sha256,
note}` and is hash-checked. The intake report (`IntakeReport`) lists
unmapped, unknown and assumption-only elements, open questions, evidence
errors, and the verdict `ready` or `blocked`.

## Import sources (`src/wire/imports.py`)

- Connectivity JSON (`ConnectivitySource`): `schema_version` 1,
  `system` (`circuit`, `csv`, `kbl`, `vec`), `connectors[]` (`ref`,
  `family_hint`, `housing`, `rated_current_a` 3.0, `rated_voltage_v` 250,
  `cavities[]`), `nets[]` (`ref`, `signal_class`, `voltage_v`,
  `current_a`).
- CSV: rows with `connector`/`ref`, `cavity`, `family_hint`, `housing`,
  `net`, `signal_class`, `voltage_v`, `current_a`.
- Mech envelope (`EnvelopeSource`): `schema_version` 1, `system`
  `mech`, `anchors[]` (`name`, `kind`, `position_mm`).

## Gate report and design report

`run_gates` returns `{schema_version, gate: "wire-harness", design,
verdict, summary, checks[]}`; `design` holds the contract name, id,
revision and sha256; `summary` counts pass/fail/unknown; each check has
`id` (the gate name), `subject`, `status` (`pass`/`fail`/`unknown`),
`measured`, `limit`, `detail`. Gates: `connectivity`, `cavity_occupancy`, `splice_integrity`,
`netlist_coverage`, `shielding_pairing`, `ampacity`, `voltage_drop`,
`insulation_rating`, `bend_radius`, `segregation`,
`terminal_compatibility`, `connector_rating`, `housing_compatibility`,
`anchor_resolution`, `route_geometry`, `import_freshness`,
`manifest_integrity`. Any `fail` or `unknown` makes the verdict `fail`.

`design-report.json` is the gate report plus `elements` (counts, signal
classes, total wire length), `imported_sources` (`id`, `system`, `ref`,
`sha256`) and `vision_points` (`image`, `checklist`) for each rendered
raster present in the export directory.
`design-report.md` is the same content for people.

## Manifest and provenance

`manifest.json` holds the contract sha256 and every projection with its
sha256; `provenance.json` records the generator version, license,
contract name/id/revision/sha256, imported sources, tool versions and the
diagram renderer (`drawio-desktop`).
`manifest_integrity` re-hashes the files.

## Advisory visual review

`review-visual-<slug>.advisory.json` (`src/wire/advisory.py`):
`{tool: "vision_review", stage, status, summary, artifacts, detail}`
where `detail` is `image_path`, `image_sha256`, `model`, `checklist`
(`harness_diagram`, `route_plan`, `intake_image`,
`built_harness_photo`, `sister_artifact`), `impression` (400+
characters, three sentences) and `findings[]` (`category`, `severity`
`error`/`warning`/`info`, `note`, optional normalized `bbox`). Categories:
`missing_connection`, `wrong_connector`, `routing_anomaly`,
`label_collision`, `text_outside_frame`, `dimension_legibility`,
`ambiguous_notation`, `missing_dimension`, `missing_manufacturing_info`,
`design_intent`, `datasheet_mismatch`, `other`.

## VRP records

Inputs in `src/wire/records.py`:

- `DecisionInput`: `id`, `stage`, `question`, `principles[]`,
  `options[]` (`name`, `pros[]`, `cons[]`, at least two), `chosen`,
  `rationale`, `assumptions[]`, `unknowns[]`, `risks[]`, `revisit_when`,
  `decided_by` (`agent`/`user`), `evidence[]` (`path` or `reference`).
- `StageImpressionInput`: `stage`, `artifacts[]`, `impression`.
- `VisionReviewInput`: `image_path` or `source_event_id`, `model`,
  `checklist`, `findings[]` (`category`, `severity`, `note`),
  `impression`.

Stored records add `schema_version`, `plugin: wire`, `sequence`,
`event_id` (sha256) and `recorded_at`; artifact paths are stored with
their sha256.

## SLP v2

Request and response schemas: [sister-cooperation.md](sister-cooperation.md).

# Data dictionary and synthetic-data contract

This document describes the operational tables created by `backend/app/models.py`
and the deterministic synthetic generator. Ground-truth labels and anomaly
fixtures are exported separately from operational planner inputs.

## Conventions and lifecycle

- Generated identifiers are immutable within a dataset: `ORD-YYYY-000001`,
  `DEL-YYYY-000001`, `VEH-000001`, `DRV-000001`, `RTE-YYYY-000001`, and
  `STOP-<route-id>-001`. The year is the generation reference date's year.
- Coordinates are decimal degrees in the synthetic Bengaluru region
  (latitude 12.7-13.4, longitude 77.3-78.1). The deliberately out-of-region
  site is labeled and excluded from automatic routing.
- Weight uses kilograms, volume uses cubic metres, distance uses kilometres,
  service/travel/delay/duration use minutes, and times are local wall-clock
  times on the record's effective or route date.
- Operational state progresses from `UNASSIGNED` to `PLANNED`, then to
  `DELIVERED`, `DELAYED`, or `FAILED`. An unassigned delivery has an explicit
  outcome and reason after route planning. Simulation updates the current
  outcome and appends an immutable `OutcomeEvent`.
- `effective_to = NULL` means there is no scheduled end date. Effective ranges
  are inclusive. Generator-created capacity and time-window records start on
  the dataset reference date.
- Generator reproducibility is identified by the pair `(seed, reference_date)`.
  The manifest checksum covers generated master/transaction records, traffic
  samples, and ground-truth labels/fixtures; it does not cover later route
  plans, simulation events, or user accounts.

## Entities and fields

### CustomerSite (`sites`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | positive database key | yes | Primary key |
| `site_code` | string(32) | yes | `SITE-` plus zero-padded counter | yes | Unique, immutable within generated dataset |
| `name` | string(120) | yes | synthetic company name | no | Non-empty |
| `address` | string(255) | yes | synthetic street address | no | Non-empty |
| `latitude` | float | yes | decimal degrees | no | In configured region, unless labeled out-of-region case |
| `longitude` | float | yes | decimal degrees | no | In configured region, unless labeled out-of-region case |
| `region` | string(80) | yes | `Bengaluru` for generated sites | no | Matches coordinate-region classification |
| `active` | boolean | yes | true/false | no | Inactive sites are not valid delivery destinations |

**Relationship:** one site has many orders and deliveries. It may be the origin
or destination of many travel-matrix rows.

### Order (`orders`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | string(32) | yes | `ORD-YYYY-NNNNNN` | yes | Primary key; year matches reference date |
| `site_id` | integer FK | yes | existing `sites.id` | no | Must match the delivery's site |
| `order_date` | date | yes | ISO date | no | Not after the dataset reference date for baseline orders |
| `priority` | string(16) | yes | `LOW`, `NORMAL`, `HIGH` | no | Must be an allowed priority |
| `status` | string(24) | yes | `OPEN`, `PLANNED`, `COMPLETED`, `CANCELLED` | no | Must follow the order lifecycle |

**Relationship:** one order has one or more deliveries; one site has many orders.

### Delivery (`deliveries`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | string(32) | yes | `DEL-YYYY-NNNNNN` | yes | Primary key |
| `order_id` | string FK | yes | existing `orders.id` | no | Order and delivery site IDs must match |
| `site_id` | integer FK | yes | existing `sites.id` | no | Must reference a site |
| `weight` | float | yes | kg | no | Greater than zero |
| `volume` | float | yes | m3 | no | Greater than zero |
| `service_minutes` | integer | yes | minutes | no | Positive integer |
| `priority` | string(16) | yes | `LOW`, `NORMAL`, `HIGH` | no | Must be an allowed priority |
| `status` | string(24) | yes | `UNASSIGNED`, `PLANNED`, `DELIVERED`, `DELAYED`, `FAILED` | no | Must follow the delivery lifecycle |
| `earliest` | time | yes | local time | no | Must be no later than `latest`; compatibility copy of `TimeWindow.starts_at` |
| `latest` | time | yes | local time | no | Must be no earlier than `earliest`; compatibility copy of `TimeWindow.ends_at` |

**Relationship:** each delivery belongs to one order and one site. It has one
normalized time window, zero or more vehicle-type restrictions, zero or one
current outcome, and zero or more route-stop/history records over its lifecycle.

### Vehicle (`vehicles`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | string(24) | yes | `VEH-NNNNNN` | yes | Primary key |
| `vehicle_type` | string(32) | yes | `VAN`, `TRUCK` | no | Must match a supported type |
| `weight_capacity` | float | yes | kg | no | Positive; legacy capacity fallback |
| `volume_capacity` | float | yes | m3 | no | Positive; legacy capacity fallback |
| `available` | boolean | yes | true/false | no | Only available vehicles enter planning |
| `latitude` | float | yes | decimal degrees | no | Valid depot/vehicle coordinates |
| `longitude` | float | yes | decimal degrees | no | Valid depot/vehicle coordinates |

**Relationship:** one vehicle has effective-dated capacity records and many
routes over time. A route uses exactly one vehicle.

### VehicleCapacity (`vehicle_capacities`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | positive database key | yes | Primary key |
| `vehicle_id` | string FK | yes | existing `vehicles.id` | no | Vehicle must exist |
| `effective_from` | date | yes | ISO date | composite | Must be on/before use date |
| `effective_to` | date, nullable | no | ISO date or null | composite | Must be on/after `effective_from` |
| `weight_capacity_kg` | float | yes | kg | no | Positive |
| `volume_capacity_m3` | float | yes | m3 | no | Positive |

**Relationship:** many capacity versions can belong to one vehicle, with at
most one applicable version for a vehicle/date. `(vehicle_id, effective_from)`
is unique. The compatibility capacity fields remain on `Vehicle`.

### Driver (`drivers`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | string(24) | yes | `DRV-NNNNNN` | yes | Primary key |
| `name` | string(120) | yes | synthetic name | no | Non-empty |
| `active` | boolean | yes | true/false | no | Only active drivers enter planning |

**Relationship:** one driver has many shifts and routes; each route uses one driver.

### Shift (`shifts`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | positive database key | yes | Primary key |
| `driver_id` | string FK | yes | existing `drivers.id` | no | Driver must exist |
| `shift_date` | date | yes | ISO date | no | Matches route planning date |
| `starts` | time | yes | local time | no | Earlier than `ends` |
| `ends` | time | yes | local time | no | Later than `starts` |
| `max_minutes` | integer | yes | minutes | no | Positive; route duration cannot exceed it |

### TravelTimeMatrix (`travel_time_matrix`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | positive database key | yes | Primary key |
| `scenario_date` | date | yes | ISO date | no | Exact route date for matrix lookup |
| `from_site_id` | integer FK, nullable | no | site ID; null means depot | no | Existing site when non-null |
| `to_site_id` | integer FK | yes | existing site ID | no | Existing destination site |
| `travel_minutes` | integer | yes | minutes | no | Non-negative |
| `scenario` | string(24) | yes | `NORMAL`, `BUSY`, `LIGHT` | no | Supported scenario |

**Relationship:** each row references a destination and optionally an origin
site. The generator stores depot-to-site samples for 30 consecutive dates and
a complete directed site-to-site matrix for the reference date. The optimizer
uses exact date/edge samples when available and uses site-specific traffic
factors from depot samples for dates without a complete matrix.

### TimeWindow (`time_windows`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | positive database key | yes | Primary key |
| `delivery_id` | string FK | yes | existing `deliveries.id` | yes | One normalized window per delivery |
| `starts_at` | time | yes | local time | no | Earlier than `ends_at` |
| `ends_at` | time | yes | local time | no | Later than `starts_at` |
| `effective_from` | date | yes | ISO date | no | On/before route date |
| `effective_to` | date, nullable | no | ISO date or null | no | On/after `effective_from` |

### Route (`routes`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | string(32) | yes | `RTE-YYYY-NNNNNN` | yes | Primary key |
| `route_date` | date | yes | ISO date | no | Must have applicable shifts/windows |
| `vehicle_id` | string FK | yes | existing `vehicles.id` | no | Vehicle capacity must not be exceeded |
| `driver_id` | string FK | yes | existing `drivers.id` | no | Driver shift must not be exceeded |
| `status` | string(24) | yes | `PLANNED`, `COMPLETED` | no | Must follow route lifecycle |
| `distance_km` | float | yes | km | no | Non-negative derived route distance |
| `duration_minutes` | integer | yes | minutes | no | Non-negative; within driver's shift |

**Relationship:** a route has ordered stops; each route uses one vehicle and one
driver. Each delivery may appear at most once in operational route stops.

### RouteStop (`route_stops`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | positive database key | yes | Primary key |
| `stop_code` | string(64) | yes | `STOP-<route-id>-NNN` | yes | Unique, immutable |
| `route_id` | string FK | yes | existing `routes.id` | `(route_id, sequence)` | Route must exist |
| `delivery_id` | string FK | yes | existing `deliveries.id` | no | Delivery may not be duplicated across stops |
| `sequence` | integer | yes | starts at 1 | `(route_id, sequence)` | Contiguous route order |
| `planned_arrival` | datetime | yes | route local date/time | no | Within window and after previous departure |

### DeliveryOutcome (`outcomes`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | positive database key | yes | Primary key |
| `delivery_id` | string FK | yes | existing `deliveries.id` | yes | One current outcome per delivery |
| `route_id` | string FK, nullable | no | existing route ID or null | no | Null for unassigned deliveries |
| `status` | string(24) | yes | `UNASSIGNED`, `DELIVERED`, `DELAYED`, `FAILED` | no | Derived by planner/simulator |
| `reason` | string(64), nullable | no | documented reason code | no | Required for failed/unassigned outcomes |
| `delay_minutes` | integer | yes | minutes | no | Non-negative, derived from actual vs planned arrival |
| `actual_arrival` | datetime, nullable | no | ISO datetime | no | Set by simulation |

### OutcomeEvent (`outcome_events`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | positive database key | yes | Primary key |
| `delivery_id` | string snapshot | yes | delivery ID at simulation time | no | Snapshot intentionally has no FK so history survives data replacement |
| `route_id` | string snapshot, nullable | no | route ID at simulation time | no | Snapshot intentionally has no FK |
| `status` | string(24) | yes | `DELIVERED`, `DELAYED`, `FAILED` | no | Deterministic simulation rule |
| `reason` | string(64), nullable | no | reason code | no | Failure/exception explanation |
| `delay_minutes` | integer | yes | minutes | no | Non-negative |
| `actual_arrival` | datetime, nullable | no | ISO datetime | no | Simulated arrival |
| `actual_departure` | datetime, nullable | no | ISO datetime | no | Actual arrival plus service duration |
| `recorded_at` | datetime | yes | UTC stored as naive datetime | no | Event creation timestamp; append-only |

### DeliveryVehicleRestriction (`delivery_vehicle_restrictions`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `delivery_id` | string FK | yes | existing `deliveries.id` | composite | Delivery must exist |
| `vehicle_type` | string(32) | yes | `VAN`, `TRUCK` | composite | Planner may only use matching vehicle types |

The composite primary key `(delivery_id, vehicle_type)` is a bridge table
supporting the many-to-many relation between deliveries and allowed vehicle
types.

### GroundTruth (`ground_truth`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | positive database key | yes | Primary key |
| `entity_type` | string(32) | yes | entity class name | no | Identifies labeled entity |
| `entity_id` | string(64) | yes | referenced entity ID | no | Must point to the labeled operational row |
| `issue_type` | string(64) | yes | documented anomaly code | no | Kept out of planner inputs |
| `expected_decision` | string(120) | yes | expected handling | no | Human-readable expected outcome |

### GroundTruthFixture (`ground_truth_fixtures`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | string(64) | yes | deterministic `ANOMALY-*` ID | yes | Primary key |
| `issue_type` | string(64) | yes | over-capacity, duplicate/omitted stop, arrival order, shift exceeded | no | Validator checks that evidence demonstrates the issue |
| `evidence_json` | string | yes | JSON scenario evidence | no | Valid JSON with reference date and issue-specific evidence |
| `expected_decision` | string(160) | yes | expected handling | no | Must not be empty |

Fixtures are deliberately separate from optimizer input tables, so negative
examples do not compromise the valid operational baseline.

### DatasetManifest (`dataset_manifests`)

| Field | Type | Required | Allowed values / units | Unique | Validation |
|---|---|---:|---|---:|---|
| `id` | integer | yes | fixed value 1 for current dataset | yes | Primary key |
| `seed` | integer | yes | deterministic RNG seed | no | Combined with reference date identifies generation |
| `reference_date` | date | yes | ISO date | no | Anchors IDs, shifts, windows, and traffic |
| `counts_json` | string | yes | JSON counts | no | Reconciles generated row totals |
| `source_manifest_json` | string | yes | JSON provenance | no | Records synthetic origin, transforms, license, and discarded fields |
| `checksum_sha256` | string(64) | yes | lowercase SHA-256 | no | Deterministic generated-data checksum |
| `generated_at` | datetime | yes | UTC stored as naive datetime | no | Generation timestamp; excluded from checksum |

## Cardinalities and optional relationships

| Relationship | Cardinality | Optionality / constraints |
|---|---|---|
| Site -> Order | 1:N | Every order has exactly one site |
| Order -> Delivery | 1:N | Every delivery has exactly one order |
| Site -> Delivery | 1:N | Every delivery has exactly one site; must match its order's site |
| Vehicle -> VehicleCapacity | 1:N over effective dates | At most one effective record per vehicle/date |
| Delivery -> TimeWindow | 1:1 | One effective window; legacy delivery times mirror it |
| Delivery <-> allowed vehicle type | N:M | `delivery_vehicle_restrictions` is the bridge table |
| Driver -> Shift | 1:N | Each shift belongs to one driver and one date |
| Vehicle -> Route | 1:N | Each route has exactly one vehicle |
| Driver -> Route | 1:N | Each route has exactly one driver |
| Route -> RouteStop | 1:N | Stop sequence is unique and contiguous per route |
| Delivery -> RouteStop | 0:1 current plan | No duplicate operational stop; may remain unassigned |
| Delivery -> Outcome | 0:1 current state | Outcome may be absent before planning |
| Delivery -> OutcomeEvent | 1:N over history | Snapshot IDs are intentionally not foreign keys |
| Site -> TravelTimeMatrix | 1:N | Origin can be null for depot; destination is required |
| Labeled entity -> GroundTruth | 0:N | Labels are excluded from planner input |

## Validation and exports

`GET /api/v1/data/validate` checks key joins, enums, effective dates, time
windows, route ordering, capacity, shift duration, outcomes, matrix references,
and fixture evidence. A labeled out-of-region site is reported as a warning and
is excluded by the optimizer; an unlabeled one is an error.

Manager-only exports:

- `GET /api/v1/data/export.json`: all operational tables, a separate `ground_truth`
  section, and the dataset manifest.
- `GET /api/v1/data/export.zip`: one CSV per operational table plus separate
  `ground_truth.csv`, `ground_truth_fixtures.csv`, and `manifest.json`.
- `GET /api/v1/data/export.sql`: SQLite schema and seed statements for domain
  data; authentication users and sessions are deliberately excluded.
- `GET /api/v1/data/export.csv`: compatibility export containing deliveries only.

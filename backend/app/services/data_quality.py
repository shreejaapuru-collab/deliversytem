import csv
import hashlib
import io
import json
import math
import zipfile
from datetime import date, datetime, time, timedelta

from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateTable

from app.models import (
    DatasetManifest,
    Delivery,
    DeliveryVehicleRestriction,
    Driver,
    GroundTruth,
    GroundTruthFixture,
    Order,
    Outcome,
    OutcomeEvent,
    Route,
    RouteStop,
    Shift,
    Site,
    TimeWindow,
    TravelTimeMatrix,
    Vehicle,
    VehicleCapacity,
)

OPERATIONAL_MODELS = (
    Site,
    Order,
    Delivery,
    Vehicle,
    VehicleCapacity,
    DeliveryVehicleRestriction,
    Driver,
    Shift,
    TimeWindow,
    TravelTimeMatrix,
    Route,
    RouteStop,
    Outcome,
    OutcomeEvent,
)
GENERATED_MODELS = (
    Site,
    Order,
    Delivery,
    Vehicle,
    VehicleCapacity,
    DeliveryVehicleRestriction,
    Driver,
    Shift,
    TimeWindow,
    TravelTimeMatrix,
)
SQL_MODELS = OPERATIONAL_MODELS + (
    GroundTruth,
    GroundTruthFixture,
    DatasetManifest,
)


def _value(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _records(db, model):
    primary_keys = [
        getattr(model, column.name)
        for column in model.__table__.primary_key.columns
    ]
    rows = db.query(model).order_by(*primary_keys).all()
    return [
        {
            column.name: _value(getattr(row, column.name))
            for column in model.__table__.columns
        }
        for row in rows
    ]


def _canonical_records(db, model):
    records = _records(db, model)
    return sorted(
        records,
        key=lambda record: json.dumps(record, sort_keys=True, separators=(",", ":")),
    )


def dataset_checksum(db):
    payload = {
        model.__tablename__: _canonical_records(db, model)
        for model in GENERATED_MODELS
    }
    payload["ground_truth"] = _canonical_records(db, GroundTruth)
    payload["ground_truth_fixtures"] = _canonical_records(db, GroundTruthFixture)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_manifest(db):
    row = db.query(DatasetManifest).filter_by(id=1).first()
    return None if row is None else json.loads(row.source_manifest_json)


def validate_data(db):
    """Validate persisted entities and report labeled exceptions separately."""
    errors = []
    warnings = []
    sites = {row.id: row for row in db.query(Site).all()}
    orders = {row.id: row for row in db.query(Order).all()}
    deliveries = {row.id: row for row in db.query(Delivery).all()}
    vehicles = {row.id: row for row in db.query(Vehicle).all()}
    drivers = {row.id: row for row in db.query(Driver).all()}
    time_windows = {
        row.delivery_id: row for row in db.query(TimeWindow).all()
    }
    capacity_by_vehicle = {}
    manifest = db.query(DatasetManifest).filter_by(id=1).first()
    reference_date = manifest.reference_date if manifest else date.today()
    for capacity in db.query(VehicleCapacity).all():
        if (
            capacity.effective_from <= reference_date
            and (capacity.effective_to is None or capacity.effective_to >= reference_date)
        ):
            existing = capacity_by_vehicle.get(capacity.vehicle_id)
            if existing is None or capacity.effective_from > existing.effective_from:
                capacity_by_vehicle[capacity.vehicle_id] = capacity
        if capacity.effective_to and capacity.effective_to < capacity.effective_from:
            errors.append(f"{capacity.vehicle_id}: capacity effective dates are reversed")

    ground_truth = {
        (row.entity_type, row.entity_id): row.issue_type
        for row in db.query(GroundTruth).all()
    }
    allowed_delivery_statuses = {
        "UNASSIGNED", "PLANNED", "DELIVERED", "DELAYED", "FAILED"
    }
    allowed_priorities = {"LOW", "NORMAL", "HIGH"}
    allowed_outcome_statuses = {"UNASSIGNED", "DELIVERED", "DELAYED", "FAILED"}

    for site in sites.values():
        outside = not (
            12.7 <= site.latitude <= 13.4 and 77.3 <= site.longitude <= 78.1
        )
        if outside:
            label = ground_truth.get(("Site", str(site.id)))
            message = f"{site.site_code}: coordinates are outside the defined region"
            (warnings if label == "COORDINATE_OUTSIDE_DEFINED_REGION" else errors).append(
                message
            )

    for order in orders.values():
        if order.site_id not in sites:
            errors.append(f"{order.id}: missing site {order.site_id}")
        if order.status not in {"OPEN", "PLANNED", "COMPLETED", "CANCELLED"}:
            errors.append(f"{order.id}: invalid order status {order.status}")
        if order.priority not in allowed_priorities:
            errors.append(f"{order.id}: invalid priority {order.priority}")

    for delivery in deliveries.values():
        if delivery.order_id not in orders:
            errors.append(f"{delivery.id}: missing order {delivery.order_id}")
        if delivery.site_id not in sites:
            errors.append(f"{delivery.id}: missing site {delivery.site_id}")
        elif orders.get(delivery.order_id) and orders[delivery.order_id].site_id != delivery.site_id:
            errors.append(f"{delivery.id}: order and delivery site IDs do not match")
        if delivery.earliest > delivery.latest:
            errors.append(f"{delivery.id}: earliest time is after latest time")
        if delivery.weight <= 0 or delivery.volume <= 0 or delivery.service_minutes <= 0:
            errors.append(f"{delivery.id}: weight, volume, and service time must be positive")
        if delivery.priority not in allowed_priorities:
            errors.append(f"{delivery.id}: invalid priority {delivery.priority}")
        if delivery.status not in allowed_delivery_statuses:
            errors.append(f"{delivery.id}: invalid status {delivery.status}")
        window = time_windows.get(delivery.id)
        if manifest and window is None:
            errors.append(f"{delivery.id}: missing normalized time-window record")
        if window:
            if window.starts_at >= window.ends_at:
                errors.append(f"{delivery.id}: invalid persisted time window")
            if (delivery.earliest, delivery.latest) != (window.starts_at, window.ends_at):
                errors.append(f"{delivery.id}: delivery and time-window values disagree")
            if window.effective_to and window.effective_to < window.effective_from:
                errors.append(f"{delivery.id}: time-window effective dates are reversed")

    for vehicle in vehicles.values():
        if vehicle.vehicle_type not in {"VAN", "TRUCK"}:
            errors.append(f"{vehicle.id}: invalid vehicle type {vehicle.vehicle_type}")
        capacity = capacity_by_vehicle.get(vehicle.id)
        if manifest and capacity is None:
            errors.append(f"{vehicle.id}: missing effective vehicle-capacity record")
        weight_capacity = capacity.weight_capacity_kg if capacity else vehicle.weight_capacity
        volume_capacity = capacity.volume_capacity_m3 if capacity else vehicle.volume_capacity
        if weight_capacity <= 0 or volume_capacity <= 0:
            errors.append(f"{vehicle.id}: capacities must be positive")

    for shift in db.query(Shift).all():
        if shift.driver_id not in drivers:
            errors.append(f"Shift {shift.id}: missing driver {shift.driver_id}")
        if shift.ends <= shift.starts or shift.max_minutes <= 0:
            errors.append(f"Shift {shift.id}: invalid shift interval or duration")

    for restriction in db.query(DeliveryVehicleRestriction).all():
        if restriction.delivery_id not in deliveries:
            errors.append(f"Restriction: missing delivery {restriction.delivery_id}")
        if restriction.vehicle_type not in {"VAN", "TRUCK"}:
            errors.append(f"Restriction: invalid vehicle type {restriction.vehicle_type}")

    for matrix_row in db.query(TravelTimeMatrix).all():
        if matrix_row.to_site_id not in sites:
            errors.append(f"Travel matrix row {matrix_row.id}: missing destination site")
        if matrix_row.from_site_id is not None and matrix_row.from_site_id not in sites:
            errors.append(f"Travel matrix row {matrix_row.id}: missing origin site")
        if matrix_row.travel_minutes < 0:
            errors.append(f"Travel matrix row {matrix_row.id}: negative travel time")
        if matrix_row.scenario not in {"NORMAL", "BUSY", "LIGHT"}:
            errors.append(f"Travel matrix row {matrix_row.id}: invalid traffic scenario")

    route_ids = {row.id for row in db.query(Route.id).all()}
    stops_by_route = {}
    seen_delivery_stops = set()
    for stop in db.query(RouteStop).all():
        if stop.route_id not in route_ids:
            errors.append(f"Stop {stop.stop_code}: missing route {stop.route_id}")
        if stop.delivery_id not in deliveries:
            errors.append(f"Stop {stop.stop_code}: missing delivery {stop.delivery_id}")
        if stop.delivery_id in seen_delivery_stops:
            errors.append(f"{stop.delivery_id}: appears more than once in route stops")
        seen_delivery_stops.add(stop.delivery_id)
        stops_by_route.setdefault(stop.route_id, []).append(stop)

    outcomes = {row.delivery_id: row for row in db.query(Outcome).all()}
    for outcome in outcomes.values():
        if outcome.delivery_id not in deliveries:
            errors.append(f"Outcome {outcome.id}: missing delivery {outcome.delivery_id}")
        if outcome.route_id is not None and not db.query(Route).filter_by(id=outcome.route_id).first():
            errors.append(f"Outcome {outcome.id}: missing route {outcome.route_id}")
        if outcome.status not in allowed_outcome_statuses:
            errors.append(f"Outcome {outcome.id}: invalid status {outcome.status}")
        if outcome.status == "FAILED" and not outcome.reason:
            errors.append(f"Outcome {outcome.id}: failed delivery has no reason")

    for route in db.query(Route).all():
        if route.vehicle_id not in vehicles or route.driver_id not in drivers:
            errors.append(f"{route.id}: vehicle or driver foreign key is invalid")
            continue
        route_stops = sorted(stops_by_route.get(route.id, []), key=lambda row: row.sequence)
        if len(route_stops) != len({stop.sequence for stop in route_stops}):
            errors.append(f"{route.id}: duplicate stop sequence")
        if route_stops and [stop.sequence for stop in route_stops] != list(
            range(1, len(route_stops) + 1)
        ):
            errors.append(f"{route.id}: stop sequence is not contiguous")
        for previous, current in zip(route_stops, route_stops[1:]):
            previous_delivery = deliveries.get(previous.delivery_id)
            if previous_delivery and current.planned_arrival < previous.planned_arrival + timedelta(
                minutes=previous_delivery.service_minutes
            ):
                errors.append(f"{route.id}: arrival precedes previous stop departure")
        total_weight = sum(
            deliveries[stop.delivery_id].weight
            for stop in route_stops
            if stop.delivery_id in deliveries
        )
        total_volume = sum(
            deliveries[stop.delivery_id].volume
            for stop in route_stops
            if stop.delivery_id in deliveries
        )
        capacity = capacity_by_vehicle.get(route.vehicle_id)
        vehicle = vehicles[route.vehicle_id]
        weight_capacity = capacity.weight_capacity_kg if capacity else vehicle.weight_capacity
        volume_capacity = capacity.volume_capacity_m3 if capacity else vehicle.volume_capacity
        if total_weight > weight_capacity:
            errors.append(f"{route.id}: route exceeds vehicle weight capacity")
        if total_volume > volume_capacity:
            errors.append(f"{route.id}: route exceeds vehicle volume capacity")
        shift = (
            db.query(Shift)
            .filter_by(driver_id=route.driver_id, shift_date=route.route_date)
            .first()
        )
        if shift and route.duration_minutes > shift.max_minutes:
            errors.append(f"{route.id}: driver shift duration is exceeded")
        for stop in route_stops:
            delivery = deliveries.get(stop.delivery_id)
            if delivery is None:
                continue
            if not delivery.earliest <= stop.planned_arrival.time() <= delivery.latest:
                errors.append(f"{route.id}: {delivery.id} is outside its time window")
            if sites.get(delivery.site_id) and not (
                12.7 <= sites[delivery.site_id].latitude <= 13.4
                and 77.3 <= sites[delivery.site_id].longitude <= 78.1
            ):
                errors.append(f"{route.id}: contains an out-of-region site")

    if db.query(Route).count():
        for delivery in deliveries.values():
            if delivery.status == "UNASSIGNED" and (
                delivery.id not in outcomes or not outcomes[delivery.id].reason
            ):
                errors.append(f"{delivery.id}: unassigned delivery has no reason")
            if delivery.status == "PLANNED" and not any(
                stop.delivery_id == delivery.id
                for route_stops in stops_by_route.values()
                for stop in route_stops
            ):
                errors.append(f"{delivery.id}: marked planned but has no route stop")

    for fixture in db.query(GroundTruthFixture).all():
        try:
            evidence = json.loads(fixture.evidence_json)
        except json.JSONDecodeError:
            errors.append(f"{fixture.id}: ground-truth fixture evidence is invalid JSON")
            continue
        if not fixture.expected_decision or evidence.get("reference_date") is None:
            errors.append(f"{fixture.id}: ground-truth fixture is incomplete")
            continue
        if fixture.issue_type == "ROUTE_EXCEEDS_WEIGHT_CAPACITY":
            if evidence.get("total_weight_kg", 0) <= evidence.get("capacity_kg", 0):
                errors.append(f"{fixture.id}: capacity fixture does not exceed capacity")
        elif fixture.issue_type == "DUPLICATE_STOP":
            stop_ids = [
                stop["delivery_id"] for stop in evidence.get("stops", [])
            ]
            if len(stop_ids) == len(set(stop_ids)):
                errors.append(f"{fixture.id}: duplicate-stop fixture has no duplicate")
        elif fixture.issue_type == "OMITTED_STOP":
            if evidence.get("expected_delivery_id") in evidence.get(
                "actual_stop_delivery_ids", []
            ):
                errors.append(f"{fixture.id}: omitted-stop fixture includes its missing stop")
        elif fixture.issue_type == "ARRIVAL_BEFORE_PREVIOUS_DEPARTURE":
            previous_departure = datetime.fromisoformat(
                evidence["previous_arrival"]
            ) + timedelta(minutes=evidence["previous_service_minutes"])
            next_arrival = datetime.fromisoformat(evidence["next_arrival"])
            if next_arrival >= previous_departure:
                errors.append(f"{fixture.id}: arrival-order fixture is not out of order")
        elif fixture.issue_type == "DRIVER_SHIFT_EXCEEDED":
            if time.fromisoformat(evidence["route_end"]) <= time.fromisoformat(
                evidence["shift_end"]
            ):
                errors.append(f"{fixture.id}: shift fixture does not exceed the shift")

    return {
        "valid": not errors,
        "sites": len(sites),
        "orders": len(orders),
        "deliveries": len(deliveries),
        "vehicles": len(vehicles),
        "route_stops": db.query(RouteStop).count(),
        "travel_time_rows": db.query(TravelTimeMatrix).count(),
        "ground_truth_labels": db.query(GroundTruth).count(),
        "ground_truth_fixtures": db.query(GroundTruthFixture).count(),
        "error_count": len(errors),
        "errors": errors,
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def _export_ground_truth(db):
    return {
        "labels": _records(db, GroundTruth),
        "fixtures": _records(db, GroundTruthFixture),
    }


def export_json(db):
    """Export all operational data separately from ground-truth labels."""
    payload = {
        model.__tablename__: _records(db, model)
        for model in OPERATIONAL_MODELS
    }
    manifest = db.query(DatasetManifest).filter_by(id=1).first()
    payload["ground_truth"] = _export_ground_truth(db)
    payload["manifest"] = (
        None
        if manifest is None
        else {
            "seed": manifest.seed,
            "reference_date": manifest.reference_date.isoformat(),
            "counts": json.loads(manifest.counts_json),
            "source": json.loads(manifest.source_manifest_json),
            "checksum_sha256": manifest.checksum_sha256,
            "generated_at": manifest.generated_at.isoformat(),
        }
    )
    return payload


def export_delivery_csv(db):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow([column.name for column in Delivery.__table__.columns])
    for row in db.query(Delivery).order_by(Delivery.id).all():
        writer.writerow([_value(getattr(row, column.name)) for column in Delivery.__table__.columns])
    return stream.getvalue()


def export_csv_zip(db):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for model in OPERATIONAL_MODELS:
            csv_stream = io.StringIO(newline="")
            writer = csv.writer(csv_stream)
            columns = [column.name for column in model.__table__.columns]
            writer.writerow(columns)
            for row in db.query(model).all():
                writer.writerow([_value(getattr(row, name)) for name in columns])
            archive.writestr(f"{model.__tablename__}.csv", csv_stream.getvalue())

        for filename, rows, columns in (
            (
                "ground_truth.csv",
                db.query(GroundTruth).all(),
                [column.name for column in GroundTruth.__table__.columns],
            ),
            (
                "ground_truth_fixtures.csv",
                db.query(GroundTruthFixture).all(),
                [column.name for column in GroundTruthFixture.__table__.columns],
            ),
        ):
            csv_stream = io.StringIO(newline="")
            writer = csv.writer(csv_stream)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([_value(getattr(row, name)) for name in columns])
            archive.writestr(filename, csv_stream.getvalue())
        archive.writestr(
            "manifest.json",
            json.dumps(export_json(db)["manifest"], indent=2, sort_keys=True),
        )
    return stream.getvalue()


def _sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Cannot export non-finite numeric values to SQL")
        return repr(value)
    if isinstance(value, (date, datetime, time)):
        value = value.isoformat()
    return "'" + str(value).replace("'", "''") + "'"


def export_sql(db):
    """Create a SQLite schema+seed export without authentication tables."""
    dialect = sqlite.dialect()
    tables = [
        model.__table__
        for model in SQL_MODELS
    ]
    included = {table.name for table in tables}
    ordered_tables = [
        table for table in Site.metadata.sorted_tables if table.name in included
    ]
    statements = [
        "-- Smart Delivery Operations synthetic dataset export",
        "PRAGMA foreign_keys=OFF;",
    ]
    statements.extend(
        str(CreateTable(table, if_not_exists=True).compile(dialect=dialect)).strip() + ";"
        for table in ordered_tables
    )
    for table in ordered_tables:
        rows = db.execute(table.select()).mappings().all()
        if not rows:
            continue
        column_names = [column.name for column in table.columns]
        quoted_columns = ", ".join(
            dialect.identifier_preparer.quote(name) for name in column_names
        )
        quoted_table = dialect.identifier_preparer.quote(table.name)
        for row in rows:
            values = ", ".join(_sql_literal(row[name]) for name in column_names)
            statements.append(
                f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({values});"
            )
    statements.append("PRAGMA foreign_keys=ON;")
    return "\n".join(statements) + "\n"

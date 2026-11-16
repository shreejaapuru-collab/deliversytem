import json
import random
from datetime import date, datetime, time, timedelta

from faker import Faker
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models import (
    DatasetManifest,
    Delivery,
    DeliveryVehicleRestriction,
    Driver,
    GroundTruth,
    GroundTruthFixture,
    Order,
    Outcome,
    Route,
    RouteStop,
    Shift,
    Site,
    TimeWindow,
    TravelTimeMatrix,
    Vehicle,
    VehicleCapacity,
)
from app.schemas import GenerateRequest
from app.services.data_quality import dataset_checksum


SITE_REGION = {"min_latitude": 12.7, "max_latitude": 13.4, "min_longitude": 77.3, "max_longitude": 78.1}
DEPOT = (12.9716, 77.5946)
SCENARIOS = ("NORMAL", "BUSY", "LIGHT")


def _distance_km(origin, destination):
    latitude = (origin[0] - destination[0]) * 111
    longitude = (origin[1] - destination[1]) * 103
    return (latitude**2 + longitude**2) ** 0.5


def _site_time_minutes(origin, destination, rng):
    return max(1, int(round(_distance_km(origin, destination) * 3)) + rng.randint(0, 20))


def _time_window(rng):
    starts = (time(8), time(9), time(10), time(12), time(14))
    start = rng.choice(starts)
    ends = tuple(end for end in (time(12), time(14), time(16), time(18)) if end > start)
    return start, rng.choice(ends)


def _scenario_fixtures(reference_date, deliveries, vehicles, drivers):
    date_text = reference_date.isoformat()
    normal_delivery = deliveries[0].id
    second_delivery = deliveries[min(1, len(deliveries) - 1)].id
    overweight = max(deliveries, key=lambda row: row.weight)
    vehicle = max(vehicles, key=lambda row: row.weight_capacity)
    driver = drivers[0]
    route_id = f"RTE-{reference_date.year}-900001"
    first_arrival = datetime.combine(reference_date, time(10, 0))
    early_arrival = first_arrival + timedelta(minutes=5)

    scenarios = [
        (
            "ANOMALY-ROUTE-OVER-CAPACITY",
            "ROUTE_EXCEEDS_WEIGHT_CAPACITY",
            {
                "vehicle_id": vehicle.id,
                "delivery_ids": [overweight.id],
                "total_weight_kg": overweight.weight,
                "capacity_kg": vehicle.weight_capacity,
            },
            "Reject or reassign the route; preserve the capacity exception.",
        ),
        (
            "ANOMALY-DUPLICATE-STOP",
            "DUPLICATE_STOP",
            {
                "route_id": route_id,
                "stops": [
                    {"delivery_id": normal_delivery, "sequence": 1},
                    {"delivery_id": normal_delivery, "sequence": 2},
                ],
            },
            "Flag the duplicate delivery stop and retain one valid assignment.",
        ),
        (
            "ANOMALY-OMITTED-STOP",
            "OMITTED_STOP",
            {
                "route_id": route_id,
                "expected_delivery_id": second_delivery,
                "actual_stop_delivery_ids": [normal_delivery],
            },
            "Flag the missing stop; assign it elsewhere or mark it unserved.",
        ),
        (
            "ANOMALY-ARRIVAL-BEFORE-DEPARTURE",
            "ARRIVAL_BEFORE_PREVIOUS_DEPARTURE",
            {
                "route_id": route_id,
                "previous_delivery_id": normal_delivery,
                "previous_arrival": first_arrival.isoformat(),
                "previous_service_minutes": 30,
                "next_delivery_id": second_delivery,
                "next_arrival": early_arrival.isoformat(),
            },
            "Flag the impossible arrival ordering; do not accept the route.",
        ),
        (
            "ANOMALY-SHIFT-EXCEEDED",
            "DRIVER_SHIFT_EXCEEDED",
            {
                "driver_id": driver.id,
                "shift_start": "08:00",
                "shift_end": "18:00",
                "route_end": "18:30",
            },
            "Flag the shift overrun and re-plan within the driver's shift.",
        ),
    ]
    return [
        GroundTruthFixture(
            id=fixture_id,
            issue_type=issue_type,
            evidence_json=json.dumps(
                {"reference_date": date_text, **evidence},
                sort_keys=True,
                separators=(",", ":"),
            ),
            expected_decision=expected,
        )
        for fixture_id, issue_type, evidence, expected in scenarios
    ]


def generate_data(db: Session, request: GenerateRequest) -> dict:
    """Create reproducible operational records and isolated labeled edge fixtures."""
    for model in (
        Outcome,
        GroundTruth,
        GroundTruthFixture,
        DatasetManifest,
        TravelTimeMatrix,
        RouteStop,
        Route,
        DeliveryVehicleRestriction,
        TimeWindow,
        VehicleCapacity,
        Delivery,
        Order,
        Shift,
        Vehicle,
        Driver,
        Site,
    ):
        db.query(model).delete()
    db.commit()

    rng = random.Random(request.seed)
    fake = Faker()
    fake.seed_instance(request.seed)
    reference_date = request.reference_date
    sites = []
    for index in range(1, request.sites + 1):
        outside_region = request.sites > 1 and index == request.sites
        sites.append(
            Site(
                site_code=f"SITE-{index:04d}",
                name=fake.company(),
                address=fake.street_address(),
                latitude=14.0 if outside_region else 12.7 + rng.random() * 0.7,
                longitude=80.0 if outside_region else 77.3 + rng.random() * 0.8,
                region="Bengaluru",
            )
        )
    db.add_all(sites)
    db.flush()

    drivers = [
        Driver(id=f"DRV-{index:06d}", name=fake.name())
        for index in range(1, request.vehicles + 1)
    ]
    vehicles = []
    for index in range(1, request.vehicles + 1):
        vehicle_type = "VAN" if index % 2 else "TRUCK"
        weight_capacity = (
            600 + rng.randint(0, 300)
            if vehicle_type == "VAN"
            else 1000 + rng.randint(0, 500)
        )
        volume_capacity = (
            6 + rng.randint(0, 6)
            if vehicle_type == "VAN"
            else 12 + rng.randint(0, 8)
        )
        vehicles.append(
            Vehicle(
                id=f"VEH-{index:06d}",
                vehicle_type=vehicle_type,
                weight_capacity=weight_capacity,
                volume_capacity=volume_capacity,
                latitude=DEPOT[0],
                longitude=DEPOT[1],
            )
        )
    db.add_all(drivers + vehicles)
    db.flush()

    capacities = [
        VehicleCapacity(
            vehicle_id=vehicle.id,
            effective_from=reference_date,
            weight_capacity_kg=vehicle.weight_capacity,
            volume_capacity_m3=vehicle.volume_capacity,
        )
        for vehicle in vehicles
    ]
    shifts = [
        Shift(
            driver_id=driver.id,
            shift_date=reference_date,
            starts=time(8),
            ends=time(18),
            max_minutes=480,
        )
        for driver in drivers
    ]
    db.add_all(capacities + shifts)

    orders, deliveries, time_windows, restrictions = [], [], [], []
    ground_truth = []
    max_weight_capacity = max(vehicle.weight_capacity for vehicle in vehicles)
    if request.sites > 1:
        ground_truth.append(
            GroundTruth(
                entity_type="Site",
                entity_id=str(sites[-1].id),
                issue_type="COORDINATE_OUTSIDE_DEFINED_REGION",
                expected_decision="Flag for coordinate review; exclude from automatic routing",
            )
        )
    for index in range(1, request.deliveries + 1):
        if request.sites > 1 and request.deliveries > 1 and index == request.deliveries - 1:
            site = sites[-1]
        else:
            site = sites[rng.randrange(len(sites))]
        order_id = f"ORD-{reference_date.year}-{index:06d}"
        delivery_id = f"DEL-{reference_date.year}-{index:06d}"
        order = Order(id=order_id, site_id=site.id, order_date=reference_date)
        if index == request.deliveries:
            weight = float(max_weight_capacity + 100)
        else:
            weight = round(rng.uniform(1, 40), 2)
        starts_at, ends_at = _time_window(rng)
        delivery = Delivery(
            id=delivery_id,
            order_id=order_id,
            site_id=site.id,
            weight=weight,
            volume=round(rng.uniform(0.05, 0.8), 2),
            service_minutes=rng.randint(5, 20),
            priority=rng.choice(["LOW", "NORMAL", "HIGH"]),
            earliest=starts_at,
            latest=ends_at,
        )
        orders.append(order)
        deliveries.append(delivery)
        time_windows.append(
            TimeWindow(
                delivery_id=delivery_id,
                starts_at=starts_at,
                ends_at=ends_at,
                effective_from=reference_date,
            )
        )
        if index % 10 == 0:
            restricted_type = vehicles[(index // 10) % len(vehicles)].vehicle_type
            restrictions.append(
                DeliveryVehicleRestriction(
                    delivery_id=delivery_id,
                    vehicle_type=restricted_type,
                )
            )

        if index == request.deliveries:
            ground_truth.append(
                GroundTruth(
                    entity_type="Delivery",
                    entity_id=delivery_id,
                    issue_type="EXCEEDS_VEHICLE_WEIGHT_CAPACITY",
                    expected_decision="Leave unassigned with a capacity reason",
                )
            )
    db.add_all(orders + deliveries + time_windows + restrictions + ground_truth)
    db.add_all(_scenario_fixtures(reference_date, deliveries, vehicles, drivers))
    db.flush()

    # Store depot samples for 30 days and a complete directed site-to-site
    # matrix for the requested planning date. This keeps full-scale generation
    # practical while giving the optimizer real edge-level travel observations.
    for day_offset in range(30):
        scenario_date = reference_date + timedelta(days=day_offset)
        daily_scenario = SCENARIOS[day_offset % len(SCENARIOS)]
        depot_rows = [
            {
                "scenario_date": scenario_date,
                "from_site_id": None,
                "to_site_id": site.id,
                "travel_minutes": _site_time_minutes(
                    DEPOT, (site.latitude, site.longitude), rng
                ),
                "scenario": daily_scenario,
            }
            for site in sites
        ]
        db.execute(insert(TravelTimeMatrix), depot_rows)

    pair_rows = []
    for origin in sites:
        origin_coordinates = (origin.latitude, origin.longitude)
        for destination in sites:
            if origin.id == destination.id:
                continue
            pair_rows.append(
                {
                    "scenario_date": reference_date,
                    "from_site_id": origin.id,
                    "to_site_id": destination.id,
                    "travel_minutes": _site_time_minutes(
                        origin_coordinates,
                        (destination.latitude, destination.longitude),
                        rng,
                    ),
                    "scenario": "NORMAL",
                }
            )
            if len(pair_rows) >= 10000:
                db.execute(insert(TravelTimeMatrix), pair_rows)
                pair_rows.clear()
    if pair_rows:
        db.execute(insert(TravelTimeMatrix), pair_rows)

    counts = {
        "sites": len(sites),
        "orders": len(orders),
        "deliveries": len(deliveries),
        "vehicles": len(vehicles),
        "vehicle_capacities": len(capacities),
        "drivers": len(drivers),
        "shifts": len(shifts),
        "time_windows": len(time_windows),
        "vehicle_restrictions": len(restrictions),
        "travel_time_rows": db.query(TravelTimeMatrix).count(),
        "ground_truth_labels": len(ground_truth),
        "ground_truth_fixtures": 5,
    }
    source_manifest = {
        "data_origin": "synthetic",
        "generator": "backend/app/services/generator.py",
        "generator_version": "1.1",
        "seed": request.seed,
        "reference_date": reference_date.isoformat(),
        "external_sources": [],
        "license": "Not applicable; no external data is used.",
        "retrieval_date": None,
        "attribution": None,
        "transformations": [
            "Seeded synthetic site, order, delivery, fleet, shift, restriction, and traffic generation.",
            "One labeled overweight delivery and one labeled out-of-region site.",
            "Negative route cases are stored as ground-truth fixtures, not optimizer inputs.",
        ],
        "fields_discarded": [],
    }
    db.add(
        DatasetManifest(
            id=1,
            seed=request.seed,
            reference_date=reference_date,
            counts_json=json.dumps(counts, sort_keys=True),
            source_manifest_json=json.dumps(source_manifest, sort_keys=True),
            checksum_sha256="",
        )
    )
    db.flush()
    manifest = db.query(DatasetManifest).filter_by(id=1).one()
    manifest.checksum_sha256 = dataset_checksum(db)
    db.commit()
    return {
        **counts,
        "seed": request.seed,
        "reference_date": reference_date.isoformat(),
        "checksum_sha256": manifest.checksum_sha256,
    }

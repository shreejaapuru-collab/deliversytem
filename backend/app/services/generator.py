import random
from datetime import date, time

from faker import Faker
from sqlalchemy.orm import Session

from app.models import (Delivery, Driver, GroundTruth, Order, Outcome,
                        Route, RouteStop, Shift, Site, TravelTimeMatrix, Vehicle)
from app.schemas import GenerateRequest


def generate_data(db: Session, request: GenerateRequest) -> dict:
    """Create a fresh, reproducible synthetic dataset."""
    db.query(Outcome).delete()
    db.query(GroundTruth).delete()
    db.query(TravelTimeMatrix).delete()
    db.query(RouteStop).delete()
    db.query(Route).delete()
    db.query(Delivery).delete()
    db.query(Order).delete()
    db.query(Shift).delete()
    db.query(Vehicle).delete()
    db.query(Driver).delete()
    db.query(Site).delete()
    db.commit()
    rng = random.Random(request.seed)
    fake = Faker()
    Faker.seed(request.seed)
    sites = [Site(site_code=f"SITE-{i:04d}", name=fake.company(), address=fake.street_address(),
                  latitude=12.7 + rng.random() * .7, longitude=77.3 + rng.random() * .8, region="Bengaluru")
             for i in range(1, request.sites + 1)]
    db.add_all(sites)
    db.flush()
    drivers = [Driver(id=f"DRV-{i:06d}", name=fake.name()) for i in range(1, max(2, request.vehicles) + 1)]
    vehicles = [Vehicle(id=f"VEH-{i:06d}", vehicle_type="VAN", weight_capacity=500 + rng.randint(0, 500),
                        volume_capacity=5 + rng.randint(0, 10), latitude=12.9716, longitude=77.5946)
                for i in range(1, request.vehicles + 1)]
    db.add_all(drivers + vehicles)
    db.flush()
    today = date.today()
    db.add_all([Shift(driver_id=driver.id, shift_date=today, starts=time(8), ends=time(18), max_minutes=480) for driver in drivers])
    orders, deliveries = [], []
    ground_truth = []
    for i in range(1, request.deliveries + 1):
        site = sites[rng.randrange(len(sites))]
        order_id, delivery_id = f"ORD-2026-{i:06d}", f"DEL-2026-{i:06d}"
        orders.append(Order(id=order_id, site_id=site.id, order_date=today))
        weight = 1100.0 if i == request.deliveries else round(rng.uniform(1, 40), 2)
        deliveries.append(Delivery(id=delivery_id, order_id=order_id, site_id=site.id,
                                   weight=weight, volume=round(rng.uniform(.05, .8), 2),
                                   service_minutes=rng.randint(5, 20), priority=rng.choice(["LOW", "NORMAL", "HIGH"])))
        if i == request.deliveries:
            ground_truth.append(GroundTruth(entity_type="Delivery", entity_id=delivery_id,
                                            issue_type="EXCEEDS_VEHICLE_WEIGHT_CAPACITY",
                                            expected_decision="Leave unassigned with a capacity reason"))
    db.add_all(orders + deliveries)
    db.add_all(ground_truth)
    # Keep a reproducible 30-day synthetic traffic sample for depot/site pairs.
    from datetime import timedelta
    for day_offset in range(30):
        scenario_date = today + timedelta(days=day_offset)
        for site in sites:
            base = int(round((((site.latitude - 12.9716) * 111) ** 2 +
                              ((site.longitude - 77.5946) * 103) ** 2) ** 0.5 * 3))
            db.add(TravelTimeMatrix(scenario_date=scenario_date, from_site_id=None,
                                    to_site_id=site.id, travel_minutes=max(1, base + rng.randint(0, 20)),
                                    scenario=rng.choice(["NORMAL", "BUSY", "LIGHT"])))
    db.commit()
    return {"sites": len(sites), "orders": len(orders), "deliveries": len(deliveries), "vehicles": len(vehicles), "drivers": len(drivers), "seed": request.seed}


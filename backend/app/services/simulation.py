from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models import Outcome, OutcomeEvent, Route, RouteStop, Shift, TravelTimeMatrix

DEPOT_SITE_ID = None


def simulate(db: Session, route_id: str) -> dict:
    route = db.query(Route).options(joinedload(Route.stops).joinedload(RouteStop.delivery)).filter_by(id=route_id).first()
    if route is None:
        raise LookupError("Route not found")
    shift = (
        db.query(Shift)
        .filter_by(driver_id=route.driver_id, shift_date=route.route_date)
        .first()
    )
    previous_departure = datetime.combine(
        route.route_date, shift.starts if shift else time(8, 0)
    )
    shift_end = datetime.combine(
        route.route_date, shift.ends if shift else time(18, 0)
    )
    matrix = {
        (row.from_site_id, row.to_site_id): row.travel_minutes
        for row in db.query(TravelTimeMatrix)
        .filter(TravelTimeMatrix.scenario_date == route.route_date)
        .all()
    }
    results = []
    for stop in route.stops:
        is_success = int(stop.delivery_id[-2:]) % 17 != 0
        scheduled_delay = max(0, int(stop.sequence % 4) * 3)
        origin_site_id = (
            route.stops[stop.sequence - 2].delivery.site_id
            if stop.sequence > 1 and stop.sequence <= len(route.stops)
            else DEPOT_SITE_ID
        )
        travel_minutes = matrix.get(
            (origin_site_id, stop.delivery.site_id),
            max(1, int(round(stop.route.distance_km / max(1, len(route.stops)) * 3))),
        )
        planned_plus_delay = stop.planned_arrival + timedelta(minutes=scheduled_delay)
        actual_arrival = max(
            planned_plus_delay,
            previous_departure + timedelta(minutes=travel_minutes),
        )
        actual_departure = actual_arrival + timedelta(
            minutes=stop.delivery.service_minutes
        )
        if not is_success:
            status, reason = "FAILED", "CUSTOMER_UNAVAILABLE"
        elif actual_departure > shift_end:
            status, reason = "DELAYED", "DRIVER_SHIFT_EXCEEDED"
        elif actual_arrival.time() > stop.delivery.latest:
            status, reason = "DELAYED", "OUTSIDE_TIME_WINDOW"
        elif actual_arrival > stop.planned_arrival:
            status, reason = "DELAYED", "TRAFFIC_DELAY"
        else:
            status, reason = "DELIVERED", None
        outcome = db.query(Outcome).filter_by(delivery_id=stop.delivery_id).first()
        if outcome is None:
            outcome = Outcome(delivery_id=stop.delivery_id)
            db.add(outcome)
        outcome.route_id = route.id
        outcome.status = status
        outcome.reason = reason
        outcome.delay_minutes = max(
            0, int((actual_arrival - stop.planned_arrival).total_seconds() // 60)
        )
        outcome.actual_arrival = actual_arrival
        db.add(OutcomeEvent(
            delivery_id=stop.delivery_id,
            route_id=route.id,
            status=status,
            reason=reason,
            delay_minutes=outcome.delay_minutes,
            actual_arrival=actual_arrival,
            actual_departure=actual_departure,
        ))
        stop.delivery.status = status
        results.append({
            "delivery_id": stop.delivery_id,
            "status": status,
            "delay_minutes": outcome.delay_minutes,
            "reason": reason,
            "actual_arrival": actual_arrival.isoformat(),
            "actual_departure": actual_departure.isoformat(),
        })
        previous_departure = actual_departure
    route.status = "COMPLETED"
    db.commit()
    return {"route_id": route_id, "results": results}


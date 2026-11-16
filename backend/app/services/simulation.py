from sqlalchemy.orm import Session, joinedload

from app.models import Outcome, OutcomeEvent, Route, RouteStop


def simulate(db: Session, route_id: str) -> dict:
    route = db.query(Route).options(joinedload(Route.stops).joinedload(RouteStop.delivery)).filter_by(id=route_id).first()
    if route is None:
        raise LookupError("Route not found")
    results = []
    for stop in route.stops:
        # Stable outcomes make repeat simulations easy to compare.
        is_success = int(stop.delivery_id[-2:]) % 17 != 0
        delay = max(0, int(stop.sequence % 4) * 3)
        status = "DELIVERED" if is_success and delay == 0 else "DELAYED" if is_success else "FAILED"
        outcome = db.query(Outcome).filter_by(delivery_id=stop.delivery_id).first()
        if outcome is None:
            outcome = Outcome(delivery_id=stop.delivery_id)
            db.add(outcome)
        outcome.route_id, outcome.status = route.id, status
        outcome.reason = None if is_success else "CUSTOMER_UNAVAILABLE"
        outcome.delay_minutes = delay
        db.add(OutcomeEvent(
            delivery_id=stop.delivery_id,
            route_id=route.id,
            status=status,
            reason=outcome.reason,
            delay_minutes=delay,
        ))
        stop.delivery.status = status
        results.append({"delivery_id": stop.delivery_id, "status": status, "delay_minutes": delay, "reason": outcome.reason})
    route.status = "COMPLETED"
    db.commit()
    return {"route_id": route_id, "results": results}


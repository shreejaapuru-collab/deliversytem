import csv
import io
from app.models import Delivery, GroundTruth, Order, RouteStop, Site


def validate_data(db):
    """Return a small, reviewable validation summary for stored records."""
    errors = []
    deliveries = db.query(Delivery).all()
    for delivery in deliveries:
        if not db.query(Order).filter_by(id=delivery.order_id).first():
            errors.append(f"{delivery.id}: missing order {delivery.order_id}")
        if not db.query(Site).filter_by(id=delivery.site_id).first():
            errors.append(f"{delivery.id}: missing site {delivery.site_id}")
        if delivery.earliest > delivery.latest:
            errors.append(f"{delivery.id}: earliest time is after latest time")
        if delivery.weight <= 0 or delivery.volume <= 0 or delivery.service_minutes <= 0:
            errors.append(f"{delivery.id}: weight, volume, and service time must be positive")

    stops = db.query(RouteStop).all()
    seen_deliveries = set()
    for stop in stops:
        if stop.delivery_id in seen_deliveries:
            errors.append(f"{stop.delivery_id}: appears more than once in route stops")
        seen_deliveries.add(stop.delivery_id)

    return {
        "valid": not errors,
        "sites": db.query(Site).count(),
        "orders": db.query(Order).count(),
        "deliveries": len(deliveries),
        "route_stops": len(stops),
        "error_count": len(errors),
        "errors": errors,
    }


def export_json(db):
    """Export the operational records and labels in separate sections."""
    return {
        "sites": [
            {"id": row.id, "site_code": row.site_code, "name": row.name,
             "latitude": row.latitude, "longitude": row.longitude, "region": row.region}
            for row in db.query(Site).order_by(Site.id).all()
        ],
        "orders": [
            {"id": row.id, "site_id": row.site_id, "order_date": row.order_date.isoformat(),
             "priority": row.priority, "status": row.status}
            for row in db.query(Order).order_by(Order.id).all()
        ],
        "deliveries": [
            {"id": row.id, "order_id": row.order_id, "site_id": row.site_id,
             "weight": row.weight, "volume": row.volume, "service_minutes": row.service_minutes,
             "priority": row.priority, "status": row.status,
             "earliest": row.earliest.isoformat(), "latest": row.latest.isoformat()}
            for row in db.query(Delivery).order_by(Delivery.id).all()
        ],
        "ground_truth": [
            {"entity_type": row.entity_type, "entity_id": row.entity_id,
             "issue_type": row.issue_type, "expected_decision": row.expected_decision}
            for row in db.query(GroundTruth).order_by(GroundTruth.id).all()
        ],
    }


def export_delivery_csv(db):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["delivery_id", "order_id", "site_id", "weight", "volume", "service_minutes", "priority", "status", "earliest", "latest"])
    for row in db.query(Delivery).order_by(Delivery.id).all():
        writer.writerow([row.id, row.order_id, row.site_id, row.weight, row.volume,
                         row.service_minutes, row.priority, row.status,
                         row.earliest.isoformat(), row.latest.isoformat()])
    return stream.getvalue()


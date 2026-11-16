from datetime import datetime, time, timedelta
from math import ceil, hypot

from sqlalchemy.orm import Session

from app.models import (
    Delivery,
    DeliveryVehicleRestriction,
    Driver,
    Outcome,
    Route,
    RouteStop,
    Shift,
    TimeWindow,
    TravelTimeMatrix,
    Vehicle,
    VehicleCapacity,
)

REGION_BOUNDS = (12.7, 13.4, 77.3, 78.1)
DEPOT = (12.9716, 77.5946)


def km(a_lat, a_lon, b_lat, b_lon):
    return hypot((a_lat - b_lat) * 111, (a_lon - b_lon) * 103)


def _is_in_region(site):
    min_latitude, max_latitude, min_longitude, max_longitude = REGION_BOUNDS
    return (
        min_latitude <= site.latitude <= max_latitude
        and min_longitude <= site.longitude <= max_longitude
    )


def _record_unassigned(db, delivery, reason):
    delivery.status = "UNASSIGNED"
    outcome = db.query(Outcome).filter_by(delivery_id=delivery.id).first()
    if outcome is None:
        outcome = Outcome(delivery_id=delivery.id)
        db.add(outcome)
    outcome.route_id = None
    outcome.status = "UNASSIGNED"
    outcome.reason = reason
    outcome.delay_minutes = 0
    outcome.actual_arrival = None


def optimize(db: Session, route_date, seconds: int) -> dict:
    """Plan deliveries using observed travel times and operational constraints."""
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError as exc:
        raise RuntimeError(
            "Route optimization needs OR-Tools. Install backend/requirements.txt first."
        ) from exc

    pending = (
        db.query(Delivery)
        .filter(Delivery.status == "UNASSIGNED")
        .order_by(Delivery.id)
        .all()
    )
    vehicles = (
        db.query(Vehicle)
        .filter(Vehicle.available.is_(True))
        .order_by(Vehicle.id)
        .all()
    )
    drivers = (
        db.query(Driver)
        .filter(Driver.active.is_(True))
        .order_by(Driver.id)
        .all()
    )

    # Clear previous solver outcomes for deliveries being replanned.
    for delivery in pending:
        previous = db.query(Outcome).filter_by(delivery_id=delivery.id).first()
        if previous is not None:
            db.delete(previous)

    valid_deliveries = []
    for delivery in pending:
        if not _is_in_region(delivery.site):
            _record_unassigned(db, delivery, "COORDINATE_OUTSIDE_DEFINED_REGION")
        else:
            valid_deliveries.append(delivery)

    fleet_size = min(len(vehicles), len(drivers))
    vehicles = vehicles[:fleet_size]
    drivers = drivers[:fleet_size]
    restrictions = {}
    if valid_deliveries:
        for row in (
            db.query(DeliveryVehicleRestriction)
            .filter(
                DeliveryVehicleRestriction.delivery_id.in_(
                    [delivery.id for delivery in valid_deliveries]
                )
            )
            .all()
        ):
            restrictions.setdefault(row.delivery_id, set()).add(row.vehicle_type)

    if not vehicles or not drivers:
        for delivery in valid_deliveries:
            _record_unassigned(db, delivery, "NO_AVAILABLE_VEHICLE_OR_DRIVER")
        db.commit()
        return {
            "status": "NO_WORK",
            "routes_created": 0,
            "assigned": 0,
            "unassigned": len(pending),
        }

    eligible_deliveries = []
    for delivery in valid_deliveries:
        allowed_types = restrictions.get(delivery.id)
        if allowed_types and not any(
            vehicle.vehicle_type in allowed_types for vehicle in vehicles
        ):
            _record_unassigned(db, delivery, "NO_ALLOWED_VEHICLE_TYPE")
        else:
            eligible_deliveries.append(delivery)
    valid_deliveries = eligible_deliveries

    if not valid_deliveries:
        db.commit()
        return {
            "status": "NO_WORK",
            "routes_created": 0,
            "assigned": 0,
            "unassigned": len(pending),
        }

    # Prefer the effective-dated records; legacy fields remain as a migration fallback.
    capacity_records = (
        db.query(VehicleCapacity)
        .filter(
            VehicleCapacity.vehicle_id.in_([vehicle.id for vehicle in vehicles]),
            VehicleCapacity.effective_from <= route_date,
        )
        .all()
    )
    capacities = {}
    for capacity in capacity_records:
        if capacity.effective_to and capacity.effective_to < route_date:
            continue
        current = capacities.get(capacity.vehicle_id)
        if current is None or capacity.effective_from > current.effective_from:
            capacities[capacity.vehicle_id] = capacity

    shifts = {
        shift.driver_id: shift
        for shift in db.query(Shift)
        .filter(
            Shift.shift_date == route_date,
            Shift.driver_id.in_([driver.id for driver in drivers]),
        )
        .all()
    }
    time_windows = {
        window.delivery_id: window
        for window in db.query(TimeWindow)
        .filter(TimeWindow.delivery_id.in_([delivery.id for delivery in valid_deliveries]))
        .filter(TimeWindow.effective_from <= route_date)
        .all()
        if window.effective_to is None or window.effective_to >= route_date
    }

    matrix_rows = (
        db.query(TravelTimeMatrix)
        .filter(TravelTimeMatrix.scenario_date == route_date)
        .all()
    )
    depot_minutes = {}
    pair_minutes = {}
    for row in matrix_rows:
        if row.from_site_id is None:
            depot_minutes[row.to_site_id] = row.travel_minutes
        else:
            pair_minutes[(row.from_site_id, row.to_site_id)] = row.travel_minutes

    depot = DEPOT
    coords = [depot] + [
        (delivery.site.latitude, delivery.site.longitude)
        for delivery in valid_deliveries
    ]
    count = len(coords)
    fleet = len(vehicles)
    manager = pywrapcp.RoutingIndexManager(count, fleet, 0)
    routing = pywrapcp.RoutingModel(manager)
    distances = [[km(*a, *b) for b in coords] for a in coords]

    def edge_minutes(from_node, to_node):
        destination = valid_deliveries[to_node - 1]
        if from_node == 0:
            observed = depot_minutes.get(destination.site_id)
            if observed is not None:
                return observed
            return max(1, int(round(distances[from_node][to_node] * 3)))

        origin = valid_deliveries[from_node - 1]
        observed = pair_minutes.get((origin.site_id, destination.site_id))
        if observed is not None:
            return observed

        # Older datasets and non-reference dates contain depot samples only.
        direct_distance = distances[from_node][to_node]
        origin_depot_distance = max(
            1.0, km(*depot, origin.site.latitude, origin.site.longitude)
        )
        destination_depot_distance = max(
            1.0, km(*depot, destination.site.latitude, destination.site.longitude)
        )
        origin_factor = depot_minutes.get(origin.site_id, origin_depot_distance * 3)
        destination_factor = depot_minutes.get(
            destination.site_id, destination_depot_distance * 3
        )
        traffic_factor = (
            origin_factor / (origin_depot_distance * 3)
            + destination_factor / (destination_depot_distance * 3)
        ) / 2
        return max(1, int(round(direct_distance * 3 * traffic_factor)))

    def minutes(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        travel_time = edge_minutes(from_node, to_node)
        service_time = (
            valid_deliveries[from_node - 1].service_minutes
            if from_node != 0
            else 0
        )
        return travel_time + service_time

    time_callback = routing.RegisterTransitCallback(minutes)
    routing.SetArcCostEvaluatorOfAllVehicles(time_callback)
    routing.AddDimension(time_callback, 600, 600, False, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")

    for vehicle_index, driver in enumerate(drivers):
        shift = shifts.get(driver.id)
        shift_start = shift.starts if shift else time(8, 0)
        shift_end = shift.ends if shift else time(18, 0)
        start_minute = shift_start.hour * 60 + shift_start.minute
        end_minute = shift_end.hour * 60 + shift_end.minute
        if end_minute <= start_minute:
            raise ValueError(f"Driver {driver.id} has an invalid shift on {route_date}.")

        start_offset = max(0, start_minute - 8 * 60)
        start_index = routing.Start(vehicle_index)
        end_index = routing.End(vehicle_index)
        time_dimension.CumulVar(start_index).SetRange(start_offset, start_offset)
        shift_length = end_minute - start_minute
        if shift:
            shift_length = min(shift_length, shift.max_minutes)
        time_dimension.CumulVar(end_index).SetMax(start_offset + shift_length)

    for node, delivery in enumerate(valid_deliveries, 1):
        index = manager.NodeToIndex(node)
        window = time_windows.get(delivery.id)
        earliest = window.starts_at if window else delivery.earliest
        latest = window.ends_at if window else delivery.latest
        if latest < earliest:
            raise ValueError(f"Delivery {delivery.id} has an invalid time window.")
        start = earliest.hour * 60 + earliest.minute - 8 * 60
        end = latest.hour * 60 + latest.minute - 8 * 60
        time_dimension.CumulVar(index).SetRange(max(0, start), max(0, end))
        routing.AddDisjunction([index], 100_000)

        allowed_types = restrictions.get(delivery.id)
        if allowed_types:
            allowed_indices = [
                vehicle_index
                for vehicle_index, vehicle in enumerate(vehicles)
                if vehicle.vehicle_type in allowed_types
            ]
            routing.SetAllowedVehiclesForIndex(allowed_indices, index)

    def weight_demand(index):
        node = manager.IndexToNode(index)
        return 0 if node == 0 else ceil(valid_deliveries[node - 1].weight)

    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(weight_demand),
        0,
        [
            int(
                capacities[vehicle.id].weight_capacity_kg
                if vehicle.id in capacities
                else vehicle.weight_capacity
            )
            for vehicle in vehicles
        ],
        True,
        "WeightCapacity",
    )

    def volume_demand(index):
        node = manager.IndexToNode(index)
        return 0 if node == 0 else ceil(valid_deliveries[node - 1].volume * 100)

    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(volume_demand),
        0,
        [
            int(
                (capacities[vehicle.id].volume_capacity_m3 if vehicle.id in capacities else vehicle.volume_capacity)
                * 100
            )
            for vehicle in vehicles
        ],
        True,
        "VolumeCapacity",
    )

    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    parameters.time_limit.FromSeconds(seconds)
    solution = routing.SolveWithParameters(parameters)

    if solution is None:
        for delivery in valid_deliveries:
            _record_unassigned(db, delivery, "NO_FEASIBLE_ROUTE")
        db.commit()
        return {
            "status": "INFEASIBLE",
            "routes_created": 0,
            "assigned": 0,
            "unassigned": len(pending),
        }

    existing_routes = db.query(Route).filter(Route.route_date == route_date).count()
    created_route_ids = []
    assigned_delivery_ids = set()

    for vehicle_index, vehicle in enumerate(vehicles):
        index = routing.Start(vehicle_index)
        ordered_stops = []
        distance = 0.0
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                ordered_stops.append((node, valid_deliveries[node - 1]))
            next_index = solution.Value(routing.NextVar(index))
            next_node = manager.IndexToNode(next_index)
            distance += distances[node][next_node]
            index = next_index
        if not ordered_stops:
            continue

        route_id = (
            f"RTE-{route_date.year}-"
            f"{existing_routes + len(created_route_ids) + 1:06d}"
        )
        start_index = routing.Start(vehicle_index)
        finish_index = routing.End(vehicle_index)
        start_time = solution.Value(time_dimension.CumulVar(start_index))
        finish_time = solution.Value(time_dimension.CumulVar(finish_index))
        route = Route(
            id=route_id,
            route_date=route_date,
            vehicle_id=vehicle.id,
            driver_id=drivers[vehicle_index].id,
            status="PLANNED",
            distance_km=round(distance, 2),
            duration_minutes=finish_time - start_time,
        )
        db.add(route)
        for sequence, (node, delivery) in enumerate(ordered_stops, 1):
            arrival_minutes = solution.Value(
                time_dimension.CumulVar(manager.NodeToIndex(node))
            )
            planned_arrival = datetime.combine(route_date, time(8, 0)) + timedelta(
                minutes=arrival_minutes
            )
            db.add(
                RouteStop(
                    route=route,
                    stop_code=f"STOP-{route_id}-{sequence:03d}",
                    delivery_id=delivery.id,
                    sequence=sequence,
                    planned_arrival=planned_arrival,
                )
            )
            delivery.status = "PLANNED"
            assigned_delivery_ids.add(delivery.id)
        created_route_ids.append(route_id)

    for delivery in valid_deliveries:
        if delivery.id not in assigned_delivery_ids:
            _record_unassigned(db, delivery, "NO_FEASIBLE_CAPACITY_OR_WINDOW")

    db.commit()
    return {
        "status": "FEASIBLE",
        "routes_created": len(created_route_ids),
        "route_ids": created_route_ids,
        "assigned": len(assigned_delivery_ids),
        "unassigned": len(pending) - len(assigned_delivery_ids),
    }

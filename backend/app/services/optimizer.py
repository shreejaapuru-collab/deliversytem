from datetime import datetime, time, timedelta
from math import hypot

from sqlalchemy.orm import Session

from app.models import Delivery, Driver, Outcome, Route, RouteStop, Shift, Vehicle


def km(a_lat, a_lon, b_lat, b_lon):
    # A local approximation is enough for the synthetic Bengaluru test region.
    return hypot((a_lat - b_lat) * 111, (a_lon - b_lon) * 103)


def optimize(db: Session, route_date, seconds: int) -> dict:
    """Plan deliveries with time-window, weight, volume, and driver-shift limits."""
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError as exc:
        raise RuntimeError(
            "Route optimization needs OR-Tools. Install backend/requirements.txt first."
        ) from exc

    deliveries = db.query(Delivery).filter(Delivery.status == "UNASSIGNED").all()
    vehicles = db.query(Vehicle).filter(Vehicle.available.is_(True)).all()
    drivers = db.query(Driver).filter(Driver.active.is_(True)).all()

    if not deliveries or not vehicles or not drivers:
        return {
            "status": "NO_WORK",
            "routes_created": 0,
            "unassigned": len(deliveries),
        }

    depot = (12.9716, 77.5946)
    coords = [depot] + [
        (delivery.site.latitude, delivery.site.longitude)
        for delivery in deliveries
    ]

    count = len(coords)
    fleet = min(len(vehicles), len(drivers))
    vehicles = vehicles[:fleet]
    drivers = drivers[:fleet]

    shifts = {
        shift.driver_id: shift
        for shift in db.query(Shift)
        .filter(
            Shift.shift_date == route_date,
            Shift.driver_id.in_([driver.id for driver in drivers]),
        )
        .all()
    }

    manager = pywrapcp.RoutingIndexManager(count, fleet, 0)
    routing = pywrapcp.RoutingModel(manager)
    distances = [[km(*a, *b) for b in coords] for a in coords]

    def minutes(from_index, to_index):
        """Return travel plus service time at the departure stop."""
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)

        travel_minutes = int(
            round(distances[from_node][to_node] * 3)
        )

        service_minutes = (
            deliveries[from_node - 1].service_minutes
            if from_node != 0
            else 0
        )

        return travel_minutes + service_minutes

    time_callback = routing.RegisterTransitCallback(minutes)
    routing.SetArcCostEvaluatorOfAllVehicles(time_callback)

    # Time values are measured in minutes from 08:00.
    routing.AddDimension(
        time_callback,
        600,
        600,
        False,
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    # Set each driver's starting and ending times from their shift record.
    # If a shift is missing, use an 08:00 to 18:00 default shift.
    for vehicle_index, driver in enumerate(drivers):
        shift = shifts.get(driver.id)
        shift_start = shift.starts if shift else time(8, 0)
        shift_end = shift.ends if shift else time(18, 0)

        start_minute = shift_start.hour * 60 + shift_start.minute
        end_minute = shift_end.hour * 60 + shift_end.minute

        if end_minute <= start_minute:
            raise ValueError(
                f"Driver {driver.id} has an invalid shift on {route_date}."
            )

        start_index = routing.Start(vehicle_index)
        end_index = routing.End(vehicle_index)

        start_offset = start_minute - 8 * 60
        start_offset = max(0, start_offset)

        time_dimension.CumulVar(start_index).SetRange(
            start_offset,
            start_offset,
        )

        shift_length = end_minute - start_minute
        if shift:
            shift_length = min(shift_length, shift.max_minutes)

        time_dimension.CumulVar(end_index).SetMax(
            start_offset + shift_length
        )

    # Apply each delivery's allowed arrival window.
    for node, delivery in enumerate(deliveries, 1):
        index = manager.NodeToIndex(node)

        earliest = (
            delivery.earliest.hour * 60
            + delivery.earliest.minute
            - 8 * 60
        )
        latest = (
            delivery.latest.hour * 60
            + delivery.latest.minute
            - 8 * 60
        )

        if latest < earliest:
            raise ValueError(
                f"Delivery {delivery.id} has an invalid time window."
            )

        time_dimension.CumulVar(index).SetRange(
            max(0, earliest),
            max(0, latest),
        )

        # Allow the solver to leave a delivery unassigned if it cannot
        # find a route that respects the constraints.
        routing.AddDisjunction([index], 100_000)

    # Add the vehicle weight-capacity constraint.
    def weight_demand(index):
        node = manager.IndexToNode(index)
        if node == 0:
            return 0
        return int(round(deliveries[node - 1].weight))

    weight_callback = routing.RegisterUnaryTransitCallback(weight_demand)

    routing.AddDimensionWithVehicleCapacity(
        weight_callback,
        0,
        [int(vehicle.weight_capacity) for vehicle in vehicles],
        True,
        "WeightCapacity",
    )

    # Add the vehicle volume-capacity constraint.
    # Multiplying by 100 keeps decimal volume values as integers for OR-Tools.
    def volume_demand(index):
        node = manager.IndexToNode(index)
        if node == 0:
            return 0
        return int(round(deliveries[node - 1].volume * 100))

    volume_callback = routing.RegisterUnaryTransitCallback(volume_demand)

    routing.AddDimensionWithVehicleCapacity(
        volume_callback,
        0,
        [
            int(round(vehicle.volume_capacity * 100))
            for vehicle in vehicles
        ],
        True,
        "VolumeCapacity",
    )

    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    parameters.time_limit.FromSeconds(seconds)

    solution = routing.SolveWithParameters(parameters)

    if solution is None:
        return {
            "status": "INFEASIBLE",
            "routes_created": 0,
            "unassigned": len(deliveries),
        }

    existing_routes = (
        db.query(Route)
        .filter(Route.route_date == route_date)
        .count()
    )

    created_route_ids = []
    assigned_delivery_ids = set()

    for vehicle_index, vehicle in enumerate(vehicles):
        index = routing.Start(vehicle_index)
        ordered_stops = []
        distance = 0.0

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)

            if node != 0:
                ordered_stops.append((node, deliveries[node - 1]))

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

        start_time = solution.Value(
            time_dimension.CumulVar(start_index)
        )
        finish_time = solution.Value(
            time_dimension.CumulVar(finish_index)
        )
        duration = finish_time - start_time

        route = Route(
            id=route_id,
            route_date=route_date,
            vehicle_id=vehicle.id,
            driver_id=drivers[vehicle_index].id,
            status="PLANNED",
            distance_km=round(distance, 2),
            duration_minutes=duration,
        )
        db.add(route)

        for sequence, (node, delivery) in enumerate(ordered_stops, 1):
            arrival_minutes = solution.Value(
                time_dimension.CumulVar(manager.NodeToIndex(node))
            )
            planned_arrival = (
                datetime.combine(route_date, time(8, 0))
                + timedelta(minutes=arrival_minutes)
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

    # Record deliveries the solver could not place on a route.
    for delivery in deliveries:
        if (
            delivery.id not in assigned_delivery_ids
            and not db.query(Outcome)
            .filter_by(delivery_id=delivery.id)
            .first()
        ):
            db.add(
                Outcome(
                    delivery_id=delivery.id,
                    status="UNASSIGNED",
                    reason="NO_FEASIBLE_CAPACITY_OR_WINDOW",
                )
            )

    db.commit()

    return {
        "status": "FEASIBLE",
        "routes_created": len(created_route_ids),
        "route_ids": created_route_ids,
        "assigned": len(assigned_delivery_ids),
        "unassigned": len(deliveries) - len(assigned_delivery_ids),
    }

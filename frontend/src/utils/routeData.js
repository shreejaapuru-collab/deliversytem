export function getRouteSummary(route) {
  return {
    id: route.id,
    date: route.route_date,
    distanceKm: Number(route.distance_km || 0),
    durationMinutes: Number(route.duration_minutes || 0),
    status: route.status || 'PLANNED',
  };
}

const EARTH_RADIUS_KM = 6371;

export function distanceKm(from, to) {
  const radians = (degrees) => (degrees * Math.PI) / 180;
  const dLat = radians(to.latitude - from.latitude);
  const dLon = radians(to.longitude - from.longitude);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(radians(from.latitude)) * Math.cos(radians(to.latitude)) * Math.sin(dLon / 2) ** 2;
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function formatCoordinates(latitude, longitude) {
  return `${Number(latitude).toFixed(4)}, ${Number(longitude).toFixed(4)}`;
}

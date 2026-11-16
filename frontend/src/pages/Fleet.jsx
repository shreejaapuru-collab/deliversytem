import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Truck, Users } from 'lucide-react';
import { fleetApi, getErrorMessage } from '../api_services.js';
import { DataTable, ErrorState, Loading, PageHeading, StatusPill } from '../components/Ui.jsx';

export default function Fleet() {
  const [vehicles, setVehicles] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { const [vehicleRows, driverRows] = await Promise.all([fleetApi.vehicles(), fleetApi.drivers()]); setVehicles(vehicleRows); setDrivers(driverRows); }
    catch (issue) { setError(getErrorMessage(issue)); }
    finally { setLoading(false); }
  }, [refreshKey]);
  useEffect(() => { load(); }, [load]);

  return <>
    <PageHeading eyebrow="FLEET MANAGEMENT" title="Fleet & drivers" description="See vehicle capacity, availability, and active drivers." action={<button className="button secondary" onClick={() => setRefreshKey((n) => n + 1)}><RefreshCw size={16} /> Refresh</button>} />
    {loading ? <Loading /> : error ? <ErrorState message={error} onRetry={load} /> : <>
      <section className="panel records-panel"><div className="records-toolbar"><div className="panel-title-line"><Truck size={17} /><h2>Vehicles</h2><span className="count-badge">{vehicles.length}</span></div></div><DataTable rows={vehicles} rowKey="id" emptyTitle="No vehicles yet" columns={[
        { key: 'id', label: 'Vehicle ID', render: (v) => <strong className="id-cell">{v}</strong> }, { key: 'vehicle_type', label: 'Type' },
        { key: 'weight_capacity', label: 'Weight capacity', render: (v) => `${Number(v).toLocaleString()} kg` }, { key: 'volume_capacity', label: 'Volume capacity', render: (v) => `${v} m³` },
        { key: 'available', label: 'Availability', render: (v) => <StatusPill value={v ? 'Available' : 'Unavailable'} /> },
        { key: 'latitude', label: 'Depot', render: (v, row) => `${Number(v).toFixed(3)}, ${Number(row.longitude).toFixed(3)}` },
      ]} /></section>
      <section className="panel records-panel" style={{ marginTop: 16 }}><div className="records-toolbar"><div className="panel-title-line"><Users size={17} /><h2>Drivers</h2><span className="count-badge">{drivers.length}</span></div></div><DataTable rows={drivers} rowKey="id" emptyTitle="No drivers yet" columns={[
        { key: 'id', label: 'Driver ID', render: (v) => <strong className="id-cell">{v}</strong> }, { key: 'name', label: 'Name' },
        { key: 'active', label: 'Status', render: (v) => <StatusPill value={v ? 'Active' : 'Inactive'} /> },
      ]} /></section>
    </>}
  </>;
}


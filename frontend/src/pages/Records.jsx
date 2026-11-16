import { useCallback, useEffect, useState } from 'react';
import { Boxes, Package, RefreshCw, Search, Truck } from 'lucide-react';
import { apiRequest, getErrorMessage } from '../api_services.js';
import { DataTable, ErrorState, Loading, PageHeading, StatusPill } from '../components/Ui.jsx';

const pages = {
  deliveries: { title: 'Deliveries', eyebrow: 'ORDERS & DELIVERY', description: 'Track delivery demand, service windows, and current status.', icon: Package, endpoint: '/deliveries', searchable: true, columns: [
    { key: 'id', label: 'Delivery ID', render: (v) => <strong className="id-cell">{v}</strong> },
    { key: 'site_id', label: 'Site ref' }, { key: 'weight', label: 'Weight', render: (v) => `${Number(v).toFixed(1)} kg` },
    { key: 'volume', label: 'Volume', render: (v) => `${Number(v).toFixed(2)} m³` },
    { key: 'priority', label: 'Priority', render: (v) => <span className={`priority ${String(v).toLowerCase()}`}>{v}</span> },
    { key: 'earliest', label: 'Window', render: (v, row) => `${String(v).slice(0, 5)} – ${String(row.latest).slice(0, 5)}` },
    { key: 'status', label: 'Status', render: (v) => <StatusPill value={v} /> },
  ] },
  sites: { title: 'Customer sites', eyebrow: 'NETWORK LOCATIONS', description: 'Your delivery locations and their operating coordinates.', icon: Boxes, endpoint: '/sites', searchable: true, columns: [
    { key: 'site_code', label: 'Site code', render: (v) => <strong className="id-cell">{v}</strong> }, { key: 'name', label: 'Site name' },
    { key: 'address', label: 'Address' }, { key: 'region', label: 'Region' },
    { key: 'latitude', label: 'Coordinates', render: (v, row) => `${Number(v).toFixed(4)}, ${Number(row.longitude).toFixed(4)}` },
    { key: 'active', label: 'Status', render: (v) => <StatusPill value={v ? 'Active' : 'Inactive'} /> },
  ] },
  fleet: { title: 'Fleet & drivers', eyebrow: 'FLEET MANAGEMENT', description: 'Available vehicles and the drivers supporting your routes.', icon: Truck, endpoint: '/vehicles', columns: [
    { key: 'id', label: 'Vehicle ID', render: (v) => <strong className="id-cell">{v}</strong> }, { key: 'vehicle_type', label: 'Type' },
    { key: 'weight_capacity', label: 'Weight capacity', render: (v) => `${Number(v).toLocaleString()} kg` },
    { key: 'volume_capacity', label: 'Volume capacity', render: (v) => `${v} m³` },
    { key: 'available', label: 'Availability', render: (v) => <StatusPill value={v ? 'Available' : 'Unavailable'} /> },
    { key: 'location', label: 'Start location', render: (_, row) => `${Number(row.latitude).toFixed(3)}, ${Number(row.longitude).toFixed(3)}` },
  ] },
};

export default function Records({ type }) {
  const page = pages[type];
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const limit = 20;

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const suffix = type === 'deliveries' && query ? `?status=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}` :
        type === 'sites' && query ? `?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}` : `?limit=${limit}&offset=${offset}`;
      const result = await apiRequest(`${page.endpoint}${suffix}`);
      setRows(Array.isArray(result) ? result : result.items || []);
      setTotal(Array.isArray(result) ? result.length : result.total || 0);
    } catch (issue) { setError(getErrorMessage(issue)); }
    finally { setLoading(false); }
  }, [page.endpoint, type, query, offset, refresh]);

  useEffect(() => { load(); }, [load]);

  return <>
    <PageHeading eyebrow={page.eyebrow} title={page.title} description={page.description} action={<button className="button secondary" onClick={() => setRefresh((n) => n + 1)}><RefreshCw size={16} /> Refresh</button>} />
    <section className="panel records-panel">
      <div className="records-toolbar"><div><div className="panel-title-line"><h2>{page.title}</h2><span className="count-badge">{total.toLocaleString()}</span></div><p>Live records from your delivery database</p></div>
        <div className="record-controls">{page.searchable && <label className="search-box"><Search size={16} /><input aria-label="Search records" placeholder={type === 'deliveries' ? 'Filter by status…' : 'Search site names…'} value={query} onChange={(event) => { setOffset(0); setQuery(event.target.value); }} /></label>}</div>
      </div>
      {loading ? <Loading /> : error ? <ErrorState message={error} onRetry={load} /> : <DataTable columns={page.columns} rows={rows} rowKey={type === 'sites' ? 'site_code' : 'id'} emptyTitle={`No ${page.title.toLowerCase()} found`} emptyMessage="Generate records from the manager role, then refresh this page." />}
      {!loading && !error && total > limit && <div className="pagination"><span>Showing {offset + 1}–{Math.min(offset + limit, total)} of {total}</span><div><button className="button secondary small" disabled={offset === 0} onClick={() => setOffset((n) => Math.max(0, n - limit))}>Previous</button><button className="button secondary small" disabled={offset + limit >= total} onClick={() => setOffset((n) => n + limit)}>Next</button></div></div>}
    </section>
  </>;
}


import { useState } from 'react';
import { Database, RefreshCw, ShieldAlert } from 'lucide-react';
import { apiRequest, getErrorMessage } from '../api_services.js';
import { PageHeading } from '../components/Ui.jsx';

export default function DataManagement() {
  const [size, setSize] = useState('starter');
  const [seed, setSeed] = useState(20261022);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  async function generate(event) {
    event.preventDefault();
    const counts = size === 'starter' ? { sites: 30, deliveries: 100, vehicles: 10 } : { sites: 500, deliveries: 2000, vehicles: 100 };
    const confirmed = window.confirm(`Generate ${size} data? This replaces the current synthetic sites, deliveries, routes and outcomes in the database.`);
    if (!confirmed) return;
    setBusy(true); setError(''); setResult(null);
    try { setResult(await apiRequest('/data/generate', { method: 'POST', timeout: 300000, data: { ...counts, seed: Number(seed) } })); }
    catch (issue) { setError(getErrorMessage(issue)); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeading eyebrow="DATA TOOLS" title="Data management" description="Create a reproducible synthetic dataset for the delivery workspace." />
    <div className="planner-layout"><section className="panel planner-form-panel"><div className="planner-icon"><Database size={20} /></div><h2>Generate synthetic records</h2><p>Use the same seed to generate consistent sample sites, orders, deliveries, vehicles, drivers and shifts.</p>
      <form onSubmit={generate}><label className="field-label" htmlFor="dataset-size">Dataset size</label><div className="date-input"><select id="dataset-size" value={size} onChange={(event) => setSize(event.target.value)}><option value="starter">Starter · 30 sites, 100 deliveries, 10 vehicles</option><option value="full">Full · 500 sites, 2,000 deliveries, 100 vehicles</option></select></div>
        <label className="field-label" htmlFor="dataset-seed">Random seed</label><div className="date-input"><input id="dataset-seed" type="number" min="0" value={seed} onChange={(event) => setSeed(event.target.value)} required /></div>
        <button className="button primary full-width" disabled={busy}>{busy ? <span className="mini-spinner light" /> : <RefreshCw size={16} />}{busy ? 'Generating…' : 'Generate dataset'}</button></form>
      {error && <div className="notice error-notice compact"><ShieldAlert size={17} /><span>{error}</span></div>}
      {result && <div className="notice success-notice compact"><Database size={17} /><span>Created {result.sites} sites, {result.orders} orders, {result.deliveries} deliveries, {result.vehicles} vehicles, and {result.drivers} drivers with seed {result.seed}.</span></div>}
    </section><section className="panel planner-info-panel"><div className="panel-heading"><div><h2>Before you generate</h2><p>This action writes to the backend database</p></div></div><div className="info-footnote">Sign in with an operations manager account to generate data. Generating data clears the current delivery, route and simulation records before replacing them. Use this for a local demo or development database.</div></section></div>
  </>;
}

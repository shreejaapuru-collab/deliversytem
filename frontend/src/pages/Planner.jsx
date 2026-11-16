import { useState } from 'react';
import { CalendarDays, CheckCircle2, CircleAlert, Map, Play, Route, Truck } from 'lucide-react';
import { apiRequest, getErrorMessage } from '../api_services.js';
import { PageHeading } from '../components/Ui.jsx';

export default function Planner() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false); const [result, setResult] = useState(null); const [error, setError] = useState('');
  async function plan(event) { event.preventDefault(); setBusy(true); setError(''); setResult(null); try { setResult(await apiRequest('/optimization/run', { method: 'POST', data: { route_date: date, time_limit_seconds: 5 } })); } catch (issue) { setError(getErrorMessage(issue)); } finally { setBusy(false); } }
  return <>
    <PageHeading eyebrow="SMART PLANNING" title="Route planner" description="Build efficient routes from your unassigned deliveries." />
    <div className="planner-layout"><section className="panel planner-form-panel"><div className="planner-icon"><Map size={20} /></div><h2>Start a planning run</h2><p>Choose a route date and let the optimizer assign deliveries to available vehicles while respecting capacity and customer time windows.</p>
      <form onSubmit={plan}><label className="field-label" htmlFor="route-date">Planning date</label><div className="date-input"><CalendarDays size={17} /><input id="route-date" type="date" value={date} onChange={(event) => setDate(event.target.value)} required /></div><button className="button primary full-width" disabled={busy}>{busy ? <span className="mini-spinner light" /> : <Play size={16} />}{busy ? 'Planning routes…' : 'Run optimization'}</button></form>
      {error && <div className="notice error-notice compact"><CircleAlert size={17} /><span>{error}</span></div>}
      {result && <div className={`notice ${result.status === 'FEASIBLE' ? 'success-notice' : 'error-notice'} compact`}><CheckCircle2 size={17} /><span>{result.status === 'FEASIBLE' ? `Created ${result.routes_created} route(s), assigned ${result.assigned} delivery(s); ${result.unassigned} remain unassigned.` : `${result.status}: ${result.unassigned ?? 0} delivery(s) remain unassigned.`}</span></div>}
    </section><section className="panel planner-info-panel"><div className="panel-heading"><div><h2>What the optimizer considers</h2><p>Each run works from live backend records</p></div></div><div className="constraint-list"><div><span className="constraint-icon blue"><Truck size={17} /></span><div><strong>Vehicle capacity</strong><small>Routes stay within available vehicle weight limits.</small></div></div><div><span className="constraint-icon purple"><CalendarDays size={17} /></span><div><strong>Delivery time windows</strong><small>Stops are planned around their customer delivery windows.</small></div></div><div><span className="constraint-icon green"><Route size={17} /></span><div><strong>Route distance</strong><small>The solver aims to reduce travel distance across routes.</small></div></div></div><div className="info-footnote">Install OR-Tools in the backend environment for route optimization to run.</div></section></div>
  </>;
}


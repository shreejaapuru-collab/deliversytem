import { useCallback, useEffect, useState } from 'react';
import { Activity, Boxes, CheckCheck, Clock3, Package, RefreshCw, Route, Truck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiRequest, getErrorMessage } from '../api_services.js';
import { ErrorState, Loading, MetricCard, PageHeading, StatusPill } from '../components/Ui.jsx';
import { useAccess } from '../context/AccessContext.jsx';

function Bar({ label, count, total, color }) {
  const width = total ? Math.max(count ? 3 : 0, (count / total) * 100) : 0;
  return <div className="bar-row"><div className="bar-label"><span>{label}</span><strong>{count}</strong></div><div className="bar-track"><span style={{ width: `${width}%`, background: color }} /></div></div>;
}

export default function Dashboard() {
  const { role } = useAccess();
  const [data, setData] = useState(null);
  const [counts, setCounts] = useState({});
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [summary, deliveries, sites, routes] = await Promise.allSettled([
        apiRequest('/dashboard/summary'), apiRequest('/deliveries?limit=1'),
        apiRequest('/sites?limit=1'), apiRequest('/routes'),
      ]);
      if (summary.status === 'fulfilled') setData(summary.value);
      else if (deliveries.status === 'rejected') throw deliveries.reason;
      setCounts({ deliveries: deliveries.status === 'fulfilled' ? deliveries.value.total : undefined,
        sites: sites.status === 'fulfilled' ? sites.value.total : undefined,
        routes: routes.status === 'fulfilled' ? routes.value.length : undefined });
    } catch (issue) { setError(getErrorMessage(issue)); }
    finally { setLoading(false); }
  }, [refresh]);

  useEffect(() => { load(); }, [load]);

  const total = data?.total_deliveries ?? counts.deliveries ?? 0;
  const successful = data?.successful_deliveries ?? 0;
  const failed = data?.failed_deliveries ?? 0;
  const unassigned = data?.unassigned_deliveries ?? 0;

  if (loading) return <><PageHeading eyebrow="MONDAY, LIVE OVERVIEW" title="Good morning" description="Here’s what’s happening across your delivery network." /><Loading /></>;
  if (error) return <><PageHeading eyebrow="LIVE OVERVIEW" title="Delivery network" description="A clear view of today’s operations." action={<button className="button secondary" onClick={() => setRefresh((n) => n + 1)}><RefreshCw size={16} /> Refresh</button>} /><ErrorState message={error} onRetry={() => setRefresh((n) => n + 1)} /></>;

  const statuses = [
    ['Delivered', successful, '#2e9d73'], ['Failed', failed, '#dc6e62'],
    ['Unassigned', unassigned, '#dda13d'], ['Other / pending', Math.max(0, total - successful - failed - unassigned), '#7091ba'],
  ];
  return <>
    <PageHeading eyebrow="LIVE OVERVIEW" title="Delivery network" description="A clear view of your delivery operations at a glance." action={<button className="button secondary" onClick={() => setRefresh((n) => n + 1)}><RefreshCw size={16} /> Refresh</button>} />
    <div className="welcome-strip"><div className="welcome-symbol"><Activity size={19} /></div><div><strong>Your operation, at a glance</strong><span>Live data from your delivery database. Your account role controls which operations are available.</span></div><Link to="/deliveries" className="welcome-link">View deliveries <span>→</span></Link></div>
    <div className="metrics-grid">
      <MetricCard label="Total deliveries" value={total.toLocaleString()} note="in the system" icon={Package} tone="blue" />
      <MetricCard label="Completed" value={successful.toLocaleString()} note="delivered successfully" icon={CheckCheck} tone="green" />
      <MetricCard label="On-time rate" value={data ? `${data.on_time_rate_percent}%` : '—'} note="of successful deliveries" icon={Clock3} tone="purple" />
      <MetricCard label="Needs attention" value={(failed + unassigned).toLocaleString()} note={`${failed} failed · ${unassigned} unassigned`} icon={Activity} tone="amber" />
    </div>
    <div className="dashboard-grid">
      <section className="panel delivery-panel"><div className="panel-heading"><div><h2>Delivery status</h2><p>Current mix across {total.toLocaleString()} deliveries</p></div><span className="live-tag"><i /> Live</span></div>
        {total ? <div className="status-chart"><div className="donut-wrap"><div className="donut" style={{ '--done': `${total ? successful / total * 100 : 0}%` }}><div><strong>{successful}</strong><span>delivered</span></div></div></div><div className="bar-list">{statuses.map(([label, count, color]) => <Bar key={label} label={label} count={count} total={total} color={color} />)}</div></div> : <div className="chart-empty"><Boxes size={22} /><strong>No delivery records yet</strong><span>Generate your starter data to see live stats.</span>{role === 'operations_manager' && <Link className="button secondary small" to="/data">Generate starter data</Link>}</div>}
      </section>
      <section className="panel quick-panel"><div className="panel-heading"><div><h2>Quick access</h2><p>Common operations</p></div></div><div className="quick-links">
        <Link to="/deliveries"><span className="quick-icon blue"><Package size={17} /></span><span><strong>Delivery list</strong><small>{counts.deliveries ?? total} records</small></span><span className="quick-arrow">↗</span></Link>
        <Link to="/sites"><span className="quick-icon purple"><Boxes size={17} /></span><span><strong>Customer sites</strong><small>{counts.sites ?? '—'} locations</small></span><span className="quick-arrow">↗</span></Link>
        <Link to="/routes"><span className="quick-icon green"><Route size={17} /></span><span><strong>Planned routes</strong><small>{counts.routes ?? data?.routes ?? '—'} routes</small></span><span className="quick-arrow">↗</span></Link>
        <Link to="/fleet"><span className="quick-icon amber"><Truck size={17} /></span><span><strong>Fleet & drivers</strong><small>Availability and shifts</small></span><span className="quick-arrow">↗</span></Link>
      </div></section>
    </div>
    <section className="panel bottom-panel"><div className="bottom-icon"><Activity size={18} /></div><div><strong>Account permissions</strong><p>Planners can optimize routes, carriers can run delivery simulations, analysts can view performance, and operations managers can generate data.</p></div><StatusPill value="Connected" /></section>
  </>;
}


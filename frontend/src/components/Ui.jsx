import { ArrowDownRight, ArrowUpRight, CircleAlert, LoaderCircle, Search } from 'lucide-react';

export function PageHeading({ eyebrow, title, description, action }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action && <div className="heading-action">{action}</div>}</div>;
}

export function MetricCard({ label, value, note, icon: Icon, tone = 'blue', trend }) {
  return <article className="metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={18} /></span></div><div className="metric-value">{value ?? '—'}</div><div className="metric-note">{trend && <span className={`trend ${trend > 0 ? 'up' : 'down'}`}>{trend > 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{Math.abs(trend)}%</span>}{note}</div></article>;
}

export function Loading({ label = 'Loading your operations data…' }) {
  return <div className="loading-state"><LoaderCircle className="spin" size={22} /><span>{label}</span></div>;
}

export function ErrorState({ message, onRetry }) {
  return <div className="notice error-notice"><CircleAlert size={18} /><div><strong>Couldn’t load this information</strong><p>{message}</p>{onRetry && <button className="text-button" onClick={onRetry}>Try again</button>}</div></div>;
}

export function EmptyState({ title, message, action }) {
  return <div className="empty-state"><div className="empty-icon"><Search size={20} /></div><strong>{title}</strong><p>{message}</p>{action}</div>;
}

export function StatusPill({ value }) {
  const status = String(value || 'unknown').toLowerCase().replaceAll('_', ' ');
  const tone = status.includes('deliver') || status === 'completed' ? 'green' : status.includes('fail') ? 'red' : status.includes('delay') ? 'amber' : status.includes('plan') || status.includes('open') ? 'blue' : 'gray';
  return <span className={`status-pill ${tone}`}><span />{status}</span>;
}

export function DataTable({ columns, rows, rowKey, emptyTitle = 'Nothing to show yet', emptyMessage = 'This list will appear when the backend has records.' }) {
  if (!rows?.length) return <EmptyState title={emptyTitle} message={emptyMessage} />;
  return <div className="table-scroll"><table><thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={rowKey ? row[rowKey] : index}>{columns.map((column) => <td key={column.key}>{column.render ? column.render(row[column.key], row) : row[column.key] ?? '—'}</td>)}</tr>)}</tbody></table></div>;
}


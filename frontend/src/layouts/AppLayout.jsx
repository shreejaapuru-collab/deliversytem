import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { Activity, Boxes, ChevronDown, CircleHelp, LayoutDashboard, LogOut, Map, Menu, PackageCheck, Route, Truck, X } from 'lucide-react';
import { roleOptions, useAccess } from '../context/AccessContext.jsx';
import { FLEET_ROLES } from '../utils/constants.js';

const links = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/deliveries', label: 'Deliveries', icon: PackageCheck },
  { to: '/sites', label: 'Customer sites', icon: Boxes },
  { to: '/fleet', label: 'Fleet & drivers', icon: Truck, roles: FLEET_ROLES },
  { to: '/data', label: 'Data management', icon: Boxes, roles: ['operations_manager'] },
  { to: '/routes', label: 'Routes', icon: Route },
  { to: '/planner', label: 'Route planner', icon: Map, roles: ['planner', 'operations_manager'] },
];

export default function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { role, user, signOut } = useAccess();
  const roleLabel = roleOptions.find((option) => option.id === role)?.label || 'Carrier / warehouse';

  const sidebar = <>
    <div className="brand"><div className="brand-mark"><Route size={19} strokeWidth={2.4} /></div><div><strong>routewise</strong><span>DELIVERY OPERATIONS</span></div></div>
    <div className="workspace-label">WORKSPACE</div>
    <nav className="side-nav">{links.filter((link) => !link.roles || link.roles.includes(role)).map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} onClick={() => setMobileOpen(false)} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Icon size={18} strokeWidth={1.9} /><span>{label}</span></NavLink>)}</nav>
    <div className="sidebar-bottom"><div className="side-help"><CircleHelp size={17} /><span>API docs</span><a href="http://127.0.0.1:8000/api/v1/docs" target="_blank" rel="noreferrer">↗</a></div><div className="profile-card"><div className="avatar">{(user?.username || roleLabel).slice(0, 1).toUpperCase()}</div><div className="profile-copy"><strong>{user?.username}</strong><span>{roleLabel}</span></div><ChevronDown size={15} /></div></div>
  </>;

  return <div className="app-frame"><aside className="sidebar desktop-sidebar">{sidebar}</aside>{mobileOpen && <div className="mobile-scrim" onClick={() => setMobileOpen(false)} />}<aside className={`sidebar mobile-sidebar ${mobileOpen ? 'mobile-open' : ''}`}><button className="mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={20} /></button>{sidebar}</aside>
    <main className="main-area"><header className="topbar"><button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu size={20} /></button><div className="crumb"><span>Operations</span><span className="crumb-slash">/</span><strong>Delivery network</strong></div>
      <div className="user-session"><span><strong>{user?.username}</strong><small>{roleLabel}</small></span><button className="button secondary small" onClick={signOut}><LogOut size={14} /> Log out</button></div>
    </header><div className="page-content"><Outlet /></div><footer className="app-footer"><span>Routewise operations</span><span><Activity size={13} /> Connected to local API</span></footer></main></div>;
}


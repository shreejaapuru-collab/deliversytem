import { Navigate, Route, Routes } from 'react-router-dom';
import AppLayout from './layouts/AppLayout.jsx';
import RoleRoute from './routes/RoleRoute.jsx';
import AuthPage from './pages/AuthPage.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Planner from './pages/Planner.jsx';
import Records from './pages/Records.jsx';
import RoutesPage from './pages/Routes.jsx';
import Fleet from './pages/Fleet.jsx';
import DataManagement from './pages/DataManagement.jsx';
import { Loading } from './components/Ui.jsx';
import { useAccess } from './context/AccessContext.jsx';
import { FLEET_ROLES, PLANNER_ROLES } from './utils/constants.js';

function AccessDenied() {
  return <section className="panel"><h1>Access is limited for this account</h1><p>Your account role does not have permission for this page.</p></section>;
}

export default function App() {
  const { user, loading } = useAccess();
  if (loading) return <Loading label="Checking your session…" />;
  if (!user) return <AuthPage />;

  return <Routes><Route element={<AppLayout />}>
    <Route index element={<Dashboard />} />
    <Route path="deliveries" element={<Records type="deliveries" />} />
    <Route path="sites" element={<Records type="sites" />} />
    <Route path="fleet" element={<RoleRoute roles={FLEET_ROLES}><Fleet /></RoleRoute>} />
    <Route path="routes" element={<RoutesPage />} />
    <Route path="planner" element={<RoleRoute roles={PLANNER_ROLES}><Planner /></RoleRoute>} />
    <Route path="data" element={<RoleRoute roles={['operations_manager']}><DataManagement /></RoleRoute>} />
    <Route path="access-denied" element={<AccessDenied />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Route></Routes>;
}

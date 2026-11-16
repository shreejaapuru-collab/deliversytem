import { Navigate, useLocation } from 'react-router-dom';
import { useAccess } from '../context/AccessContext.jsx';

export default function RoleRoute({ roles, children }) {
  const { role } = useAccess();
  const location = useLocation();
  if (!roles.includes(role)) return <Navigate to="/access-denied" replace state={{ from: location.pathname }} />;
  return children;
}

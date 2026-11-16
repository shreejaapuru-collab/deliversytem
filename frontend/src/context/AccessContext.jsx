import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { authApi, getErrorMessage } from '../api_services.js';

export const roleOptions = [
  { id: 'supplier', label: 'Supplier' },
  { id: 'planner', label: 'Planner' },
  { id: 'carrier_warehouse_operator', label: 'Carrier / warehouse' },
  { id: 'logistics_analyst', label: 'Logistics analyst' },
  { id: 'operations_manager', label: 'Operations manager' },
];

const AccessContext = createContext(null);

export function AccessProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');

  function clearSession() {
    localStorage.removeItem('delivery_access_token');
    localStorage.removeItem('delivery_role_key');
    localStorage.removeItem('delivery_role');
    setUser(null);
  }

  useEffect(() => {
    localStorage.removeItem('delivery_role_key');
    localStorage.removeItem('delivery_role');
    const token = localStorage.getItem('delivery_access_token');
    let active = true;

    function handleExpiredSession() {
      if (active) clearSession();
    }
    window.addEventListener('session-expired', handleExpiredSession);

    if (!token) {
      setLoading(false);
      return () => {
        active = false;
        window.removeEventListener('session-expired', handleExpiredSession);
      };
    }

    authApi.currentUser()
      .then((currentUser) => { if (active) setUser(currentUser); })
      .catch((error) => {
        if (!active) return;
        if (error.response?.status === 401) clearSession();
        else setNotice(getErrorMessage(error));
      })
      .finally(() => { if (active) setLoading(false); });

    return () => {
      active = false;
      window.removeEventListener('session-expired', handleExpiredSession);
    };
  }, []);

  async function signIn(credentials) {
    const result = await authApi.login(credentials);
    localStorage.setItem('delivery_access_token', result.access_token);
    setNotice('');
    setUser(result.user);
  }

  async function signUp(credentials) {
    const result = await authApi.register(credentials);
    localStorage.setItem('delivery_access_token', result.access_token);
    setNotice('');
    setUser(result.user);
  }

  async function signOut() {
    let logoutNotice = '';
    try {
      await authApi.logout();
    } catch (error) {
      logoutNotice = `Signed out on this device, but the server could not invalidate the session: ${getErrorMessage(error)}`;
    }
    clearSession();
    setNotice(logoutNotice);
  }

  const value = useMemo(() => ({
    user,
    role: user?.role,
    loading,
    notice,
    signIn,
    signUp,
    signOut,
  }), [user, loading, notice]);

  return <AccessContext.Provider value={value}>{children}</AccessContext.Provider>;
}

export function useAccess() {
  const context = useContext(AccessContext);
  if (!context) throw new Error('useAccess must be used inside AccessProvider');
  return context;
}

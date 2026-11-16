import axios from 'axios';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1',
  timeout: 15000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('delivery_access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use((response) => response, (error) => {
  const url = error.config?.url || '';
  if (error.response?.status === 401 && !url.includes('/auth/login') && !url.includes('/auth/register')) {
    localStorage.removeItem('delivery_access_token');
    window.dispatchEvent(new Event('session-expired'));
  }
  return Promise.reject(error);
});

export function getErrorMessage(error) {
  if (error.response?.status === 401 && error.config?.url?.endsWith('/auth/login')) return 'Incorrect username or password.';
  if (error.response?.status === 401) return 'Your session has expired. Please log in again.';
  if (error.response?.status === 403) return 'This role does not have permission for that action.';
  if (error.response?.status === 503) return error.response.data?.detail || 'A required backend service is not installed yet.';
  if (error.code === 'ERR_NETWORK') return 'Cannot reach the backend. Start the API at http://127.0.0.1:8000.';
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join('; ');
  return detail || error.message || 'Something went wrong. Please try again.';
}

export const request = (url, options = {}) => api.request({ url, ...options }).then(({ data }) => data);
export const authApi = {
  login: (credentials) => request('/auth/login', { method: 'POST', data: credentials }),
  register: (credentials) => request('/auth/register', { method: 'POST', data: credentials }),
  currentUser: () => request('/auth/me'),
  logout: () => request('/auth/logout', { method: 'POST' }),
};
export const dashboardApi = { summary: () => request('/dashboard/summary') };
export const deliveryApi = {
  list: ({ status, limit = 20, offset = 0 } = {}) => request('/deliveries', { params: { status, limit, offset } }),
  simulate: (routeId) => request(`/simulation/${routeId}/run`, { method: 'POST' }),
};
export const siteApi = { list: ({ q, limit = 20, offset = 0 } = {}) => request('/sites', { params: { q, limit, offset } }) };
export const fleetApi = { vehicles: () => request('/vehicles'), drivers: () => request('/drivers') };
export const routeApi = {
  list: () => request('/routes'),
  optimize: (payload) => request('/optimization/run', { method: 'POST', data: payload }),
};

export const apiRequest = request;

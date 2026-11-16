import { useEffect, useState } from 'react';
import { request, getErrorMessage } from '../api_services.js';

export default function useApi(url, options = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    request(url, options).then((result) => { if (active) { setData(result); setError(''); } })
      .catch((issue) => { if (active) setError(getErrorMessage(issue)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [url, refreshKey]);

  return { data, loading, error, refresh: () => setRefreshKey((value) => value + 1) };
}

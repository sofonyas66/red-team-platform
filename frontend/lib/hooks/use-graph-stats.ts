import { useState, useEffect, useCallback } from 'react';
import api from '../api-client';
import { GraphStats } from '../types/graph';
import { useAuth } from '../auth-context';

export function useGraphStats() {
  const { token, isAuthenticated, isLoading: authLoading } = useAuth();
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    if (!isAuthenticated || !token) return;

    try {
      setIsLoading(true);
      const { data } = await api.get<GraphStats>('/graph/stats');
      setStats(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch graph stats');
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, token]);

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      fetchStats();
    } else if (!authLoading && !isAuthenticated) {
      setIsLoading(false);
    }
  }, [authLoading, isAuthenticated, fetchStats]);

  return { stats, isLoading: isLoading || authLoading, error, refetch: fetchStats };
}

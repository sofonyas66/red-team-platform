import api, { getEngagementId } from '../api-client';
import { GraphStats } from '../types/graph';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth-context';
import { useState, useEffect } from 'react';

export function useGraphStats() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [engagementId, setEngagementIdState] = useState<string | null>(() => getEngagementId());

  useEffect(() => {
    const handler = () => setEngagementIdState(getEngagementId());
    window.addEventListener('storage', handler);
    window.addEventListener('engagement-change', handler);
    return () => {
      window.removeEventListener('storage', handler);
      window.removeEventListener('engagement-change', handler);
    };
  }, []);

  const query = useQuery<GraphStats, Error>({
    queryKey: ['graph-stats', engagementId],
    queryFn: async () => {
      if (!engagementId) throw new Error('No engagement selected');
      const { data } = await api.get<GraphStats>('/graph/stats', { params: { engagement_id: engagementId } });
      return data;
    },
    enabled: !!isAuthenticated && !!engagementId && !authLoading,
    staleTime: 0,
  });

  return {
    stats: query.data ?? null,
    isLoading: query.isLoading || authLoading,
    error: query.error?.message || null,
    refetch: query.refetch,
  };
}

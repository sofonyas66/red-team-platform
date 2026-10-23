import api, { getEngagementId, setEngagementId } from '../api-client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect } from 'react';

export interface Engagement {
  id: string;
  name: string;
}

export function useIngestionHistory() {
  return useQuery({
    queryKey: ['ingestion-history'],
    queryFn: async () => {
      const response = await api.get('/ingestion/history');
      return response.data.history || [];
    },
  });
}

export function useWorkspace() {
  return useQuery({
    queryKey: ['workspace'],
    queryFn: async () => {
      const response = await api.get('/me');
      return response.data;
    },
  });
}

export function useEngagements() {
  const queryClient = useQueryClient();
  const [selectedEngagementId, setSelectedIdState] = useState<string | null>(null);

  useEffect(() => {
    setSelectedIdState(getEngagementId());
  }, []);

  const selectEngagement = (id: string | null) => {
    setEngagementId(id);
    setSelectedIdState(id);
    queryClient.invalidateQueries({ queryKey: ['attack-paths'] });
    queryClient.invalidateQueries({ queryKey: ['graph-stats'] });
  };

  const engagementsQuery = useQuery({
    queryKey: ['engagements'],
    queryFn: async () => {
      const response = await api.get<Engagement[]>('/engagements');
      const data = response.data || [];
      const currentId = getEngagementId();
      if (currentId && !data.some(e => e.id === currentId)) {
        setEngagementId(null);
        setSelectedIdState(null);
      } else if (data.length === 1 && !currentId) {
        setEngagementId(data[0].id);
        setSelectedIdState(data[0].id);
      } else if (data.length > 0 && !currentId) {
        // keep auto-select first engagement for backward compatibility when none selected
        setEngagementId(data[0].id);
        setSelectedIdState(data[0].id);
      }
      return data;
    },
  });

  return {
    ...engagementsQuery,
    selectedEngagementId,
    selectEngagement,
  };
}

export function useAttackPaths(source?: string, target?: string) {
  const engagementId = getEngagementId();
  return useQuery({
    queryKey: ['attack-paths', engagementId, source, target],
    queryFn: async () => {
      if (!engagementId || !source || !target) return [];
      const response = await api.get('/paths', {
        params: { source, target, engagement_id: engagementId }
      });
      return response.data || [];
    },
    enabled: !!engagementId && !!source && !!target,
  });
}

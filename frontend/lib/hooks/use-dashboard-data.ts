import api, { getEngagementId, setEngagementId } from '../api-client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect } from 'react';

export interface Engagement {
  id: string;
  name: string;
}

export function useIngestionHistory() {
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
  return useQuery({
    queryKey: ['ingestion-history', engagementId],
    queryFn: async () => {
      const response = await api.get('/ingestion/history');
      const history = response.data.history || [];
      if (!engagementId) return history;
      return history.filter((r: any) => String(r.engagement_id) === engagementId);
    },
    enabled: true,
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
  const [selectedEngagementId, setSelectedIdState] = useState<string | null>(() => getEngagementId());

  useEffect(() => {
    const updateFromStorage = () => setSelectedIdState(getEngagementId());
    window.addEventListener('storage', updateFromStorage);
    window.addEventListener('engagement-change', updateFromStorage);
    return () => {
      window.removeEventListener('storage', updateFromStorage);
      window.removeEventListener('engagement-change', updateFromStorage);
    };
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

export function useTopPaths() {
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
  return useQuery({
    queryKey: ['top-paths', engagementId],
    queryFn: async () => {
      if (!engagementId) return [];
      const response = await api.get('/paths/top', {
        params: { engagement_id: engagementId, limit: 10 }
      });
      return response.data || [];
    },
    enabled: !!engagementId,
  });
}

export function useAttackPaths(source?: string, target?: string) {
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

export interface OverviewResponse {
  engagement: {
    id: string;
    name: string;
  };
  asset_count: number;
  relationship_count: number;
  top_paths: Array<{
    source: string;
    target: string;
    hops: number;
    nodes: string[];
    rels: string[];
    score: number | null;
    label: string;
    steps: number;
    source_privileged: boolean;
  }>;
  rel_type_breakdown: Record<string, number>;
  privileged_accounts: number;
  recent_ingestion: Array<{
    filename: string;
    status: string;
    ingested_at: string;
  }>;
  pipeline: {
    ingested: boolean;
    last_ingested_at: string | null;
    paths_found: number;
    threat_actors: boolean;
  };
}

export function useOverview() {
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
  return useQuery({
    queryKey: ['overview', engagementId],
    queryFn: async () => {
      if (!engagementId) return null;
      const response = await api.get<OverviewResponse>('/overview', {
        params: { engagement_id: engagementId }
      });
      return response.data;
    },
    enabled: !!engagementId,
  });
}

export function useGraphNodes() {
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
  return useQuery({
    queryKey: ['graph-nodes', engagementId],
    queryFn: async () => {
      if (!engagementId) return { users: [], computers: [] };
      const response = await api.get('/graph/nodes', {
        params: { engagement_id: engagementId }
      });
      return response.data || { users: [], computers: [] };
    },
    enabled: !!engagementId,
  });
}

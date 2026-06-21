import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';

export type NodeRecord = {
  id: string;
  name: string | null;
  labels: Record<string, string>;
  registered_at: string;
  last_seen_at: string | null;
};

export type RegisterNodeInput = {
  node_id: string;
  name?: string;
  labels?: Record<string, string>;
};

export type RegisteredNode = NodeRecord & {
  service_key_plaintext_once: string;
};

export type NodePlacement = {
  agent_id: number;
  node_id: string;
  pinned_at: string;
  pinned_by: string | null;
  updated_at: string;
};

export type NodeAgentOption = {
  agent_id: number;
  agent_name: string;
  status: string;
  provenance: string;
};

function invalidateNodes(queryClient: ReturnType<typeof useQueryClient>): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: ['nodes'] });
}

export function useNodesQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['nodes'],
    queryFn: () => api.get<NodeRecord[]>('/admin/nodes'),
  });
}

export function useNodeAgentsQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['node-agents'],
    queryFn: () => api.get<NodeAgentOption[]>('/admin/agents?include_archived=true'),
  });
}

export function useRegisterNodeMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: RegisterNodeInput) => api.post<RegisteredNode>('/admin/nodes', input),
    onSuccess: async () => {
      await invalidateNodes(queryClient);
    },
  });
}

export function useDeleteNodeMutation(nodeId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete<void>(`/admin/nodes/${nodeId}`, { 'X-Confirm': 'true' }),
    onSuccess: async () => {
      await invalidateNodes(queryClient);
    },
  });
}

export function usePinAgentMutation(nodeId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: { agent_id: number }) => api.post<NodePlacement>(`/admin/nodes/${nodeId}/pin`, input),
    onSuccess: async () => {
      await invalidateNodes(queryClient);
    },
  });
}

export function useUnpinAgentMutation(nodeId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (agentId: number) => api.delete<void>(`/admin/nodes/${nodeId}/pin?agent_id=${agentId}`),
    onSuccess: async () => {
      await invalidateNodes(queryClient);
    },
  });
}

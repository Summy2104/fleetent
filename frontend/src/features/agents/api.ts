import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';

export type AgentListItem = {
  agent_name: string;
  status: string;
  provenance: string;
  system_prompt?: string;
  allowed_tools?: string[];
};

export type CreateAgentInput = {
  name: string;
  system_prompt: string;
  allowed_tools: string[];
};

export type AgentDetail = {
  agent: string;
  allowed_tools: string[];
  status: string;
  system_prompt: string;
};

export type AgentVersion = {
  id: number;
  is_active: boolean;
  version: number;
};

export function useAgentsQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['agents'],
    queryFn: () => api.get<AgentListItem[]>('/admin/agents?include_archived=true'),
  });
}

export function useCreateAgentMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateAgentInput) => api.post('/admin/agents', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}

export function useAgentDetailQuery(name: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(name),
    queryKey: ['agents', name],
    queryFn: () => api.get<AgentDetail>(`/admin/agents/${name}`),
  });
}

export function useUpdateAgentMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: Pick<CreateAgentInput, 'allowed_tools' | 'system_prompt'>) =>
      api.patch(`/admin/agents/${name}`, input),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['agents'] }),
        queryClient.invalidateQueries({ queryKey: ['agents', name] }),
      ]);
    },
  });
}

export function useAgentLifecycleMutation(name: string, action: string, headers?: HeadersInit) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post(`/admin/agents/${name}/${action}`, undefined, headers),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['agents'] }),
        queryClient.invalidateQueries({ queryKey: ['agents', name] }),
      ]);
    },
  });
}

export function useCloneAgentMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (newName: string) => api.post(`/admin/agents/${name}/clone`, { new_name: newName }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}

export function useDeleteAgentMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete(`/admin/agents/${name}`, { 'X-Confirm': 'true' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['agents'] });
      queryClient.removeQueries({ queryKey: ['agents', name] });
    },
  });
}

export function useAgentVersionsQuery(name: string | null, enabled: boolean) {
  const api = useAdminApi();

  return useQuery({
    enabled: enabled && Boolean(name),
    queryKey: ['agent-versions', name],
    queryFn: () => api.get<AgentVersion[]>(`/admin/agents/${name}/versions`),
  });
}

export function useActivateAgentVersionMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (version: number) => api.post(`/admin/agents/${name}/versions/${version}/activate`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['agent-versions', name] });
    },
  });
}

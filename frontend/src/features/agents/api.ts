import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';

export type AgentRuntime = {
  phase?: string | null;
  health?: string | null;
  pid?: number | null;
  node_id?: string | null;
  reported_at?: string | null;
};

export type AgentPlacement = {
  node_id: string;
  pinned_at?: string | null;
  pinned_by?: string | null;
};

export type AgentListItem = {
  agent_name: string;
  is_default?: boolean;
  status: string;
  provenance: string;
  system_prompt?: string;
  allowed_tools?: string[];
  // Node-reported runtime state (null when no node has reported) and node binding.
  runtime?: AgentRuntime | null;
  placement?: AgentPlacement | null;
};

// Opaque per-agent model policy authored by the console. The known shape is
// ``{ routes: { <route>: [{ provider_id }] }, __credential_slots__: {...} }``; kept loose so
// non-route keys (e.g. credential slots) survive an edit round-trip untouched.
export type AgentModelOverrides = Record<string, unknown>;

export type CreateAgentInput = {
  name: string;
  system_prompt: string;
  allowed_tools: string[];
  model_overrides?: AgentModelOverrides;
};

export type UpdateAgentInput = {
  system_prompt?: string;
  allowed_tools?: string[];
  model_overrides?: AgentModelOverrides;
  config_overrides_yaml?: string;
};

export type AgentDetail = {
  agent: string;
  allowed_tools: string[];
  model_overrides?: AgentModelOverrides;
  config_overrides_yaml?: string;
  status: string;
  system_prompt: string;
  supports_dm?: boolean;
  supports_groups?: boolean;
  runtime?: AgentRuntime | null;
  placement?: AgentPlacement | null;
};

export type AgentVersion = {
  id: number;
  is_active: boolean;
  version: number;
};

export type AgentSkillBinding = {
  enabled: boolean;
  skill_name: string;
};

export type AgentBindings = {
  mcp_servers: string[];
  users: string[];
  groups: AgentImGroupInput[];
};

export type AgentOauthGrant = {
  run_as: string;
  service_id: string;
};

export type AgentOauthBindings = {
  agent: string;
  connector_ids: string[];
  service_grants: AgentOauthGrant[];
};

export type AgentKnowledgeBaseBindings = {
  agent: string;
  kb_ids: string[];
};

export type AgentImCapabilitiesInput = {
  supports_dm: boolean;
  supports_groups: boolean;
};

export type AgentImGroupInput = {
  group_id: string;
  platform: string;
};

export type AgentOauthBindingInput = {
  connectorId: string;
  runAs: 'agent' | 'user';
};

export type AgentSecretRecord = {
  env_name: string;
  mode: string;
  status: string;
};

export type AgentSecretsResponse = {
  agent: string;
  secrets: AgentSecretRecord[];
};

const AGENTS_QUERY_KEY = ['agents'] as const;

function agentDetailKey(name: string | null) {
  return ['agents', name] as const;
}

function agentVersionsKey(name: string | null) {
  return ['agent-versions', name] as const;
}

function agentSkillsKey(name: string | null) {
  return ['agents', name, 'skills'] as const;
}

function agentBindingsKey(name: string | null) {
  return ['agents', name, 'bindings'] as const;
}

function agentOauthBindingsKey(name: string | null) {
  return ['agents', name, 'oauth-bindings'] as const;
}

function agentKbsKey(name: string | null) {
  return ['agents', name, 'kbs'] as const;
}

function agentSecretsKey(name: string | null) {
  return ['agents', name, 'secrets'] as const;
}

async function invalidateAgentCoreQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  name: string
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: AGENTS_QUERY_KEY }),
    queryClient.invalidateQueries({ queryKey: agentDetailKey(name) }),
  ]);
}

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
      await queryClient.invalidateQueries({ queryKey: AGENTS_QUERY_KEY });
    },
  });
}

export function useAgentDetailQuery(name: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(name),
    queryKey: agentDetailKey(name),
    queryFn: () => api.get<AgentDetail>(`/admin/agents/${name}`),
  });
}

export function useUpdateAgentMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateAgentInput) => api.patch(`/admin/agents/${name}`, input),
    onSuccess: async () => {
      await invalidateAgentCoreQueries(queryClient, name);
    },
  });
}

export function useAgentLifecycleMutation(name: string, action: string, headers?: HeadersInit) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post(`/admin/agents/${name}/${action}`, undefined, headers),
    onSuccess: async () => {
      await invalidateAgentCoreQueries(queryClient, name);
    },
  });
}

export function useCloneAgentMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (newName: string) => api.post(`/admin/agents/${name}/clone`, { new_name: newName }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: AGENTS_QUERY_KEY });
    },
  });
}

export function useDeleteAgentMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete(`/admin/agents/${name}`, { 'X-Confirm': 'true' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: AGENTS_QUERY_KEY });
      queryClient.removeQueries({ queryKey: agentDetailKey(name) });
    },
  });
}

export function useAgentVersionsQuery(name: string | null, enabled: boolean) {
  const api = useAdminApi();

  return useQuery({
    enabled: enabled && Boolean(name),
    queryKey: agentVersionsKey(name),
    queryFn: () => api.get<AgentVersion[]>(`/admin/agents/${name}/versions`),
  });
}

export function useActivateAgentVersionMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (version: number) => api.post(`/admin/agents/${name}/versions/${version}/activate`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentVersionsKey(name) });
    },
  });
}

export function useAgentSkillsQuery(name: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(name),
    queryKey: agentSkillsKey(name),
    queryFn: () => api.get<AgentSkillBinding[]>(`/admin/agents/${name}/skills`),
  });
}

export function useSetAgentSkillMutation(name: string, skillName: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: Pick<AgentSkillBinding, 'enabled'>) =>
      api.put<{ agent: string; enabled: boolean; skill_name: string }>(
        `/admin/agents/${name}/skills/${skillName}`,
        input
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentSkillsKey(name) });
    },
  });
}

export function useAgentBindingsQuery(name: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(name),
    queryKey: agentBindingsKey(name),
    queryFn: () => api.get<AgentBindings>(`/admin/agents/${name}/bindings`),
  });
}

export function useBindAgentMcpMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (serverId: string) =>
      api.post<{ agent: string; bound: boolean; server_id: string }>(
        `/admin/agents/${name}/bindings/mcp/${serverId}`
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentBindingsKey(name) });
    },
  });
}

export function useUnbindAgentMcpMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (serverId: string) =>
      api.delete<{ agent: string; bound: boolean; server_id: string }>(
        `/admin/agents/${name}/bindings/mcp/${serverId}`
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentBindingsKey(name) });
    },
  });
}

export function useAgentOauthBindingsQuery(name: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(name),
    queryKey: agentOauthBindingsKey(name),
    queryFn: () => api.get<AgentOauthBindings>(`/admin/agents/${name}/bindings/oauth`),
  });
}

export function useBindAgentOauthMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ connectorId, runAs }: AgentOauthBindingInput) =>
      api.post<{ agent: string; bound: boolean; connector_id: string; run_as: string }>(
        `/admin/agents/${name}/bindings/oauth/${connectorId}`,
        { run_as: runAs }
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentOauthBindingsKey(name) });
    },
  });
}

export function useUnbindAgentOauthMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (connectorId: string) =>
      api.delete<{ agent: string; bound: boolean; connector_id: string }>(
        `/admin/agents/${name}/bindings/oauth/${connectorId}`
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentOauthBindingsKey(name) });
    },
  });
}

export function useAgentKbsQuery(name: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(name),
    queryKey: agentKbsKey(name),
    queryFn: () => api.get<AgentKnowledgeBaseBindings>(`/admin/agents/${name}/kbs`),
  });
}

export function useBindAgentKbMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (kbId: string) =>
      api.post<{ agent: string; bound: boolean; kb_id: string }>(`/admin/agents/${name}/kbs`, {
        kb_id: kbId,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentKbsKey(name) });
    },
  });
}

export function useUnbindAgentKbMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (kbId: string) =>
      api.delete<{ agent: string; bound: boolean; kb_id: string }>(`/admin/agents/${name}/kbs/${kbId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentKbsKey(name) });
    },
  });
}

export function useBindAgentUserMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: string) =>
      api.post<{ agent: string; bound: boolean; user_id: string }>(
        `/admin/agents/${name}/bindings/users/${userId}`
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentBindingsKey(name) });
    },
  });
}

export function useUnbindAgentUserMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: string) =>
      api.delete<{ agent: string; bound: boolean; user_id: string }>(
        `/admin/agents/${name}/bindings/users/${userId}`
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentBindingsKey(name) });
    },
  });
}

export function useSetAgentImCapabilitiesMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: AgentImCapabilitiesInput) =>
      api.put<{ agent: string; supports_dm: boolean; supports_groups: boolean }>(
        `/admin/agents/${name}/im-capabilities`,
        input
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentDetailKey(name) });
    },
  });
}

export function useAddAgentImGroupMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: AgentImGroupInput) =>
      api.post<{ agent: string; bound: boolean; group_id: string; platform: string }>(
        `/admin/agents/${name}/bindings/groups`,
        input
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentBindingsKey(name) });
    },
  });
}

export function useRemoveAgentImGroupMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ group_id, platform }: AgentImGroupInput) =>
      api.delete<void>(`/admin/agents/${name}/bindings/groups/${platform}/${group_id}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentBindingsKey(name) });
    },
  });
}

export function useSetDefaultAgentMutation(name: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.put<{ agent: string; is_default: boolean }>(`/admin/agents/${name}/default`, {}),
    onSuccess: async () => {
      await invalidateAgentCoreQueries(queryClient, name);
    },
  });
}

export function useClearDefaultAgentMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete<{ cleared: boolean }>('/admin/agents/default'),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: AGENTS_QUERY_KEY });
    },
  });
}

export function useAgentSecretsQuery(name: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(name),
    queryKey: agentSecretsKey(name),
    queryFn: () => api.get<AgentSecretsResponse>(`/admin/agents/${name}/secrets`),
  });
}

export function useSetAgentSecretMutation(name: string, envName: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (value: string) =>
      api.put<{ env_name: string; status: string }>(`/admin/agents/${name}/secrets/${envName}`, { value }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentSecretsKey(name) });
    },
  });
}

export function useDeleteAgentSecretMutation(name: string, envName: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      api.delete<{ env_name: string; status: string }>(`/admin/agents/${name}/secrets/${envName}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentSecretsKey(name) });
    },
  });
}

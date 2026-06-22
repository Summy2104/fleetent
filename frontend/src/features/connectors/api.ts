import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';

export type ConnectorRecord = {
  id: string;
  display_name: string;
  protocol: 'oauth2' | 'apikey';
  enabled: boolean;
  oauth_config?: Record<string, unknown>;
};

export type ConnectorEditInput = Partial<Pick<ConnectorRecord, 'display_name' | 'enabled' | 'protocol'>> & {
  oauth_config?: Record<string, unknown>;
};

export type ConnectorLifecycle = {
  connector_id: string;
  refresh_ok: number;
  refresh_failed: number;
  reauths: number;
  active_grants?: number;
  last_refresh_at?: string | null;
  last_refresh_success?: boolean;
};

export type ConnectorGrant = {
  user_id: string;
  connector_id: string;
  status: string;
  scopes?: string[];
  agent_id?: number | null;
};

export type ConnectorGrantsResponse = {
  grants: ConnectorGrant[];
  consent_hint: string;
};

export type ConnectorBindingsResponse = {
  service_id: string;
  agent_ids: number[];
};

export type OffboardingResponse = {
  user_id: string;
  revoked: string[];
  failed: string[];
};

export type ConnectorAuthorizeResponse = {
  authorize_url: string;
};

export type ConnectorCredentialInput = {
  api_key: string;
};

export type ConnectorTestResponse = {
  success: boolean;
  connector_id: string;
  enabled?: boolean;
  token_valid?: boolean;
  active_grants?: number;
  last_refresh?: string | null;
  display_name?: string;
  error?: string;
};

export type McpServerRecord = {
  id: string;
  transport: string;
  url?: string;
  command?: string;
  args?: string[];
  enabled?: boolean;
  status: string;
  tool_count: number;
  agent_id: number | null;
};

export type McpServerInput = {
  id: string;
  transport: string;
  url?: string;
  command?: string;
  args?: string[];
  agent_id?: number | null;
  enabled?: boolean;
};

export type McpServerEditInput = Partial<McpServerInput>;

export type McpServerToolsResponse = {
  connected: boolean;
  tools: Array<{ name: string; description?: string }>;
  error?: string;
};

export type McpDoctorResponse = {
  checks: Array<Record<string, unknown>>;
};

export type McpReconnectResponse = {
  server_id: string;
  reconnected: boolean;
};

export type McpTestResponse = {
  success: boolean;
  server_id: string;
  connected: boolean;
  transport?: string;
  tools_count?: number;
  tools?: unknown[];
  error?: string;
};

const CONNECTORS_QUERY_KEY = ['connectors'];
const CONNECTOR_GRANTS_QUERY_KEY = ['connectors', 'grants'];
const MCP_SERVERS_QUERY_KEY = ['mcp', 'servers'];

async function invalidateConnectorLists(queryClient: ReturnType<typeof useQueryClient>): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: CONNECTORS_QUERY_KEY }),
    queryClient.invalidateQueries({ queryKey: CONNECTOR_GRANTS_QUERY_KEY }),
  ]);
}

export function useConnectorsQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: CONNECTORS_QUERY_KEY,
    queryFn: () => api.get<ConnectorRecord[]>('/admin/connectors'),
  });
}

export function useCreateConnectorMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ConnectorRecord) => api.post<ConnectorRecord>('/admin/connectors', input),
    onSuccess: async () => {
      await invalidateConnectorLists(queryClient);
    },
  });
}

export function useUpdateConnectorMutation(connectorId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ConnectorEditInput) =>
      api.put<ConnectorRecord>(`/admin/connectors/${connectorId}`, input),
    onSuccess: async () => {
      await invalidateConnectorLists(queryClient);
      await queryClient.invalidateQueries({ queryKey: ['connectors', connectorId, 'lifecycle'] });
      await queryClient.invalidateQueries({ queryKey: ['connectors', connectorId, 'bindings'] });
    },
  });
}

export function useDeleteConnectorMutation(connectorId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete<{ success: boolean; connector_id: string }>(`/admin/connectors/${connectorId}`),
    onSuccess: async () => {
      await invalidateConnectorLists(queryClient);
      queryClient.removeQueries({ queryKey: ['connectors', connectorId, 'lifecycle'] });
      queryClient.removeQueries({ queryKey: ['connectors', connectorId, 'bindings'] });
    },
  });
}

export function useConnectorLifecycleQuery(connectorId: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(connectorId),
    queryKey: ['connectors', connectorId, 'lifecycle'],
    queryFn: () => api.get<ConnectorLifecycle>(`/admin/connectors/${connectorId}/lifecycle`),
  });
}

export function useConnectorAgentBindingsQuery(connectorId: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(connectorId),
    queryKey: ['connectors', connectorId, 'bindings'],
    queryFn: () => api.get<ConnectorBindingsResponse>(`/admin/connectors/${connectorId}/bindings/agents`),
  });
}

export function useConnectorGrantsQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: CONNECTOR_GRANTS_QUERY_KEY,
    queryFn: () => api.get<ConnectorGrantsResponse>('/admin/connectors/grants'),
  });
}

export function useOffboardingQuery(userId: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(userId),
    queryKey: ['connectors', 'offboarding', userId],
    queryFn: () => api.get<OffboardingResponse>(`/admin/connectors/offboarding/${userId}`),
  });
}

export function useConnectorAuthorizeQuery(connectorId: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(connectorId),
    queryKey: ['connectors', connectorId, 'authorize'],
    queryFn: () => api.get<ConnectorAuthorizeResponse>(`/admin/connectors/authorize/${connectorId}`),
  });
}

export function useConnectorCredentialsMutation(connectorId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ConnectorCredentialInput) =>
      api.post<{ submitted: boolean; service_id: string }>(`/admin/connectors/${connectorId}/credentials`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: CONNECTOR_GRANTS_QUERY_KEY });
    },
  });
}

export function useConnectorTestMutation(connectorId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<ConnectorTestResponse>(`/admin/connectors/${connectorId}/test`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['connectors', connectorId, 'lifecycle'] });
    },
  });
}

export function useRevokeConnectorGrantMutation(userId: string, connectorId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      api.post<{ revoked: boolean; user_id: string; connector_id: string }>(
        `/admin/connectors/grants/${userId}/${connectorId}/revoke`,
        undefined,
        { 'X-Confirm': 'true' }
      ),
    onSuccess: async () => {
      await invalidateConnectorLists(queryClient);
    },
  });
}

export function useMcpServersQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: MCP_SERVERS_QUERY_KEY,
    queryFn: () => api.get<McpServerRecord[]>('/admin/mcp/servers'),
  });
}

export function useCreateMcpServerMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: McpServerInput) => api.post<{ success: boolean; server_id: string }>('/admin/mcp/servers', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MCP_SERVERS_QUERY_KEY });
    },
  });
}

export function useUpdateMcpServerMutation(serverId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: McpServerEditInput) =>
      api.put<{ success: boolean; server_id: string }>(`/admin/mcp/servers/${serverId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MCP_SERVERS_QUERY_KEY });
      await queryClient.invalidateQueries({ queryKey: ['mcp', 'servers', serverId, 'tools'] });
    },
  });
}

export function useDeleteMcpServerMutation(serverId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete<{ success: boolean; server_id: string }>(`/admin/mcp/servers/${serverId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MCP_SERVERS_QUERY_KEY });
      queryClient.removeQueries({ queryKey: ['mcp', 'servers', serverId, 'tools'] });
    },
  });
}

export function useMcpServerToolsQuery(serverId: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(serverId),
    queryKey: ['mcp', 'servers', serverId, 'tools'],
    queryFn: () => api.get<McpServerToolsResponse>(`/admin/mcp/servers/${serverId}/tools`),
  });
}

export function useMcpDoctorQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['mcp', 'doctor'],
    queryFn: () => api.get<McpDoctorResponse>('/admin/mcp/doctor'),
  });
}

export function useMcpReconnectMutation(serverId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<McpReconnectResponse>(`/admin/mcp/servers/${serverId}/reconnect`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MCP_SERVERS_QUERY_KEY });
    },
  });
}

export function useMcpServerTestMutation(serverId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<McpTestResponse>(`/admin/mcp/servers/${serverId}/test`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['mcp', 'servers', serverId, 'tools'] });
    },
  });
}

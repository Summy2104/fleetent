import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export type McpAuthType = 'none' | 'api_key' | 'oauth_client_credentials' | 'api_key_per_user'

export type McpApiKeyAuthConfig = {
  key_env: string
}

export type McpOAuthClientCredentialsAuthConfig = {
  token_url: string
  client_id: string
  client_secret_env: string
  scope: string
}

// per-user dynamic api-key/bearer (mcp-per-user-apikey): no static key — only server-level
// *method* settings. The user supplies their own key at runtime, isolated by triple.
export type McpApiKeyPerUserAuthConfig = {
  header_style: 'bearer' | 'x_api_key'
  credential_input: 'form' | 'tool' | 'both'
}

export type McpAuthConfig =
  | Record<string, never>
  | McpApiKeyAuthConfig
  | McpOAuthClientCredentialsAuthConfig
  | McpApiKeyPerUserAuthConfig

export const MCP_AUTH_FORM_FIELDS = {
  api_key: ['key_env'],
  oauth_client_credentials: ['token_url', 'client_id', 'client_secret_env', 'scope'],
  api_key_per_user: ['header_style', 'credential_input'],
} as const

export type McpServerRecord = {
  id: string
  transport: string
  url?: string
  auth_type: McpAuthType
  auth_config: McpAuthConfig
  command?: string
  args?: string[]
  env?: Record<string, string>
  headers?: Record<string, string>
  enabled?: boolean
  status: string
  tool_count: number
  agent_id: number | null
}

export type McpServerInput = {
  id: string
  transport: string
  auth_type: McpAuthType
  auth_config: McpAuthConfig
  url?: string
  command?: string
  args?: string[]
  agent_id?: number | null
  enabled?: boolean
  env?: Record<string, string>
  headers?: Record<string, string>
}

export type McpServerEditInput = Partial<McpServerInput>

export type McpServerToolsResponse = {
  connected: boolean
  tools: Array<{ name: string; description?: string }>
  error?: string
}

export type McpDoctorResponse = {
  checks: Array<Record<string, unknown>>
}

export type McpReconnectResponse = {
  server_id: string
  reconnected: boolean
}

export type McpTestResponse = {
  success: boolean
  server_id: string
  connected: boolean
  transport?: string
  tools_count?: number
  tools?: unknown[]
  error?: string
}

const MCP_SERVERS_QUERY_KEY = ['mcp', 'servers']

export function useMcpServersQuery() {
  const api = useAdminApi()

  return useQuery({
    queryKey: MCP_SERVERS_QUERY_KEY,
    queryFn: () => api.get<McpServerRecord[]>('/admin/mcp/servers'),
  })
}

export function useCreateMcpServerMutation() {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: McpServerInput) =>
      api.post<{ success: boolean; server_id: string }>('/admin/mcp/servers', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MCP_SERVERS_QUERY_KEY })
    },
  })
}

export function useUpdateMcpServerMutation(serverId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: McpServerEditInput) =>
      api.put<{ success: boolean; server_id: string }>(`/admin/mcp/servers/${serverId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MCP_SERVERS_QUERY_KEY })
      await queryClient.invalidateQueries({ queryKey: ['mcp', 'servers', serverId, 'tools'] })
    },
  })
}

export function useDeleteMcpServerMutation(serverId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.delete<{ success: boolean; server_id: string }>(`/admin/mcp/servers/${serverId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MCP_SERVERS_QUERY_KEY })
      queryClient.removeQueries({ queryKey: ['mcp', 'servers', serverId, 'tools'] })
    },
  })
}

export function useMcpServerToolsQuery(serverId: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(serverId),
    queryKey: ['mcp', 'servers', serverId, 'tools'],
    queryFn: () => api.get<McpServerToolsResponse>(`/admin/mcp/servers/${serverId}/tools`),
  })
}

export function useMcpDoctorQuery() {
  const api = useAdminApi()

  return useQuery({
    queryKey: ['mcp', 'doctor'],
    queryFn: () => api.get<McpDoctorResponse>('/admin/mcp/doctor'),
  })
}

export function useMcpReconnectMutation(serverId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.post<McpReconnectResponse>(`/admin/mcp/servers/${serverId}/reconnect`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MCP_SERVERS_QUERY_KEY })
    },
  })
}

export function useMcpServerTestMutation(serverId: string) {
  const api = useAdminApi()

  return useMutation({
    mutationFn: () => api.post<McpTestResponse>(`/admin/mcp/servers/${serverId}/test`),
  })
}

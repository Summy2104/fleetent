import { useMutation, useQuery } from '@tanstack/react-query'

import { useAuthSession } from '@/app/auth'
import { useAdminApi } from '@/lib/api-client'

export type StatsOverview = {
  agent_id: string
  approvals: Record<string, unknown>
  cost: Record<string, unknown>
  performance: Record<string, unknown>
  usage: Record<string, unknown>
}

export type StatsCompareRow = {
  agent_id: string
  value: number
}

export type StatsTools = {
  coverage: Record<string, unknown>
  top_tools: {
    top: Array<[string, number]>
  }
}

export type PerUserStatsRow = Record<string, unknown> & {
  user_id: string
}

export type UserRequestRow = Record<string, unknown> & {
  request_id: string
  session_id?: string
}

export type StatsTrace = {
  events: Array<Record<string, unknown>>
  subagents: Array<Record<string, unknown>>
} & Record<string, unknown>

export type StatsExportInput = {
  agentId?: string
  view?: string
}

export type StatsExportResult = {
  blob: Blob
  contentType: string
  fileName: string
}

function buildQuery(params: Record<string, string | null | undefined>): string {
  const searchParams = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value) {
      searchParams.set(key, value)
    }
  }
  const query = searchParams.toString()
  return query ? `?${query}` : ''
}

function parseFileName(contentDisposition: string | null, fallback: string): string {
  const match = contentDisposition?.match(/filename="?([^"]+)"?/i)
  return match?.[1] ?? fallback
}

export function useAgentOverviewQuery(agentId: string | null, window = '7d') {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(agentId),
    queryKey: ['stats', 'overview', agentId, window],
    queryFn: () => api.get<StatsOverview>(`/admin/stats/agents/${agentId}/overview${buildQuery({ window })}`),
  })
}

export function useCompareAgentsQuery(agentIds: string[], key = 'calls') {
  const api = useAdminApi()
  const agents = agentIds.filter(Boolean).join(',')

  return useQuery({
    enabled: agentIds.length > 0,
    queryKey: ['stats', 'compare', agents, key],
    queryFn: () => api.get<StatsCompareRow[]>(`/admin/stats/compare${buildQuery({ agents, key })}`),
  })
}

export function useAgentToolsQuery(agentId: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(agentId),
    queryKey: ['stats', 'tools', agentId],
    queryFn: () => api.get<StatsTools>(`/admin/stats/agents/${agentId}/tools`),
  })
}

export function usePerUserStatsQuery(agentId?: string | null, sortBy = 'total_tokens') {
  const api = useAdminApi()

  return useQuery({
    queryKey: ['stats', 'per-user', agentId ?? null, sortBy],
    queryFn: () =>
      api.get<PerUserStatsRow[]>(
        `/admin/stats/per-user${buildQuery({ agent_id: agentId ?? undefined, sort_by: sortBy })}`
      ),
  })
}

export function useUserRequestsQuery(userId: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(userId),
    queryKey: ['stats', 'user-requests', userId],
    queryFn: () => api.get<UserRequestRow[]>(`/admin/stats/users/${userId}/requests`),
  })
}

export function useRequestDetailQuery(requestId: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(requestId),
    queryKey: ['stats', 'request-detail', requestId],
    queryFn: () => api.get<StatsTrace>(`/admin/stats/requests/${requestId}`),
  })
}

export function useSessionTraceQuery(sessionId: string | null, userId: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(sessionId && userId),
    queryKey: ['stats', 'session-trace', sessionId, userId],
    queryFn: () =>
      api.get<StatsTrace>(`/admin/stats/sessions/${sessionId}/trace${buildQuery({ user_id: userId ?? undefined })}`),
  })
}

export function useStatsExportMutation() {
  const auth = useAuthSession()

  return useMutation({
    mutationFn: async ({ agentId, view = 'per-user' }: StatsExportInput): Promise<StatsExportResult> => {
      const headers = new Headers()
      if (auth.token) {
        headers.set('authorization', `Session ${auth.token}`)
      }

      const response = await fetch(
        `${auth.baseUrl}/admin/stats/export${buildQuery({
          agent_id: agentId,
          view,
        })}`,
        {
          headers,
          method: 'POST',
        }
      )

      if (!response.ok) {
        throw new Error(`request failed: ${response.status}`)
      }

      const contentType = response.headers.get('content-type') ?? 'application/octet-stream'
      const body = await response.text()
      const blob = new Blob([body], { type: contentType }) as Blob & {
        text?: () => Promise<string>
      }
      blob.text = () => Promise.resolve(body)

      return {
        blob,
        contentType,
        fileName: parseFileName(response.headers.get('content-disposition'), `stats-${view}.csv`),
      }
    },
  })
}

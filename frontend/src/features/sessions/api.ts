import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export type SessionListItem = {
  session_id: string
  origin: string
  status: string
  takeover_actor?: string | null
  takeover_at?: string | null
  agent_name?: string | null
  user_id?: string | null
  channel?: string | null
  updated_at?: string | null
  turns?: number
  message_count?: number
}

export type SessionTranscriptEntry = {
  role: string
  content: string
}

export type SessionDetail = {
  meta: SessionListItem
  transcript: SessionTranscriptEntry[]
}

export type SessionsFilter = {
  status?: string
  userId?: string
  agentName?: string
}

export type InjectSessionInput = {
  role: string
  content: string
}

export type ResetSessionInput = {
  keepTurns: number
}

export type BulkSessionInput = {
  action: 'end' | 'clear'
  sessionIds: string[]
}

function sessionDetailKey(sessionId: string | null): [string, string | null] {
  return ['sessions', sessionId]
}

export function useSessionsQuery(filters: SessionsFilter = {}) {
  const api = useAdminApi()

  return useQuery({
    queryKey: ['sessions', filters],
    queryFn: () => {
      const params = new URLSearchParams()
      if (filters.status) {
        params.set('status', filters.status)
      }
      if (filters.userId) {
        params.set('user_id', filters.userId)
      }
      if (filters.agentName) {
        params.set('agent_name', filters.agentName)
      }
      const query = params.toString()
      return api.get<SessionListItem[]>(`/admin/sessions${query ? `?${query}` : ''}`)
    },
  })
}

export function useSessionDetailQuery(sessionId: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(sessionId),
    queryKey: sessionDetailKey(sessionId),
    queryFn: () => api.get<SessionDetail>(`/admin/sessions/${sessionId}`),
  })
}

async function invalidateSessionQueries(queryClient: ReturnType<typeof useQueryClient>, sessionId: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['sessions'] }),
    queryClient.invalidateQueries({ queryKey: sessionDetailKey(sessionId) }),
  ])
}

function useSessionActionMutation<TInput = void>(
  sessionId: string,
  action: string,
  options: {
    body?: (input: TInput) => unknown
    headers?: HeadersInit
  } = {}
) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: TInput) =>
      api.post(`/admin/sessions/${sessionId}/${action}`, options.body?.(input), options.headers),
    onSuccess: async () => {
      await invalidateSessionQueries(queryClient, sessionId)
    },
  })
}

export function useTakeoverSessionMutation(sessionId: string) {
  return useSessionActionMutation(sessionId, 'takeover')
}

export function useReleaseSessionMutation(sessionId: string) {
  return useSessionActionMutation(sessionId, 'release')
}

export function useInjectSessionMutation(sessionId: string) {
  return useSessionActionMutation<InjectSessionInput>(sessionId, 'inject', {
    body: (input) => input,
  })
}

export function useForceEndSessionMutation(sessionId: string) {
  return useSessionActionMutation(sessionId, 'force-end', { headers: { 'X-Confirm': 'true' } })
}

export function useClearSessionMutation(sessionId: string) {
  return useSessionActionMutation(sessionId, 'clear', { headers: { 'X-Confirm': 'true' } })
}

export function useResetSessionMutation(sessionId: string) {
  return useSessionActionMutation<ResetSessionInput>(sessionId, 'reset', {
    body: (input) => ({ keep_turns: input.keepTurns }),
    headers: { 'X-Confirm': 'true' },
  })
}

export function useBulkSessionMutation() {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: BulkSessionInput) =>
      api.post(
        '/admin/sessions/bulk',
        {
          action: input.action,
          session_ids: input.sessionIds,
        },
        { 'X-Confirm': 'true' }
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}

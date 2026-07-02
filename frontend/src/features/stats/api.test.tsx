import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '@/app/auth'
import {
  useAgentOverviewQuery,
  useAgentToolsQuery,
  useCompareAgentsQuery,
  usePerUserStatsQuery,
  useRequestDetailQuery,
  useSessionTraceQuery,
  useStatsExportMutation,
  useUserRequestsQuery,
} from '@/features/stats/api'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

function createWrapper(): ({ children }: { children: ReactNode }) => JSX.Element {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </AuthProvider>
    )
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('stats api', () => {
  it('loads read-only statistics queries from the existing admin stats endpoints', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/stats/agents/:agentId/overview`, ({ params, request }) => {
        const url = new URL(request.url)
        expect(request.headers.get('authorization')).toBe('Session session-token')
        expect(params.agentId).toBe('alpha')
        expect(url.searchParams.get('window')).toBe('30d')
        return HttpResponse.json({
          agent_id: 'alpha',
          usage: { calls: 12, total_tokens: 1234 },
          performance: { p95_ms: 800 },
          approvals: { approved: 4, denied: 1 },
          cost: { currency: 'USD', total: 1.23 },
        })
      }),
      http.get(`${API_BASE_URL}/admin/stats/compare`, ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('agents')).toBe('alpha,beta')
        expect(url.searchParams.get('key')).toBe('calls')
        return HttpResponse.json([
          { agent_id: 'alpha', value: 12 },
          { agent_id: 'beta', value: 7 },
        ])
      }),
      http.get(`${API_BASE_URL}/admin/stats/agents/:agentId/tools`, ({ params }) => {
        expect(params.agentId).toBe('alpha')
        return HttpResponse.json({
          coverage: { allowed: 3, used: 2 },
          top_tools: {
            top: [
              ['read_file', 8],
              ['write_file', 3],
            ],
          },
        })
      }),
      http.get(`${API_BASE_URL}/admin/stats/per-user`, ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('agent_id')).toBe('alpha')
        expect(url.searchParams.get('sort_by')).toBe('calls')
        return HttpResponse.json([
          { user_id: 'u1', calls: 12, total_tokens: 800 },
          { user_id: 'u2', calls: 8, total_tokens: 500 },
        ])
      }),
      http.get(`${API_BASE_URL}/admin/stats/users/:userId/requests`, ({ params }) => {
        expect(params.userId).toBe('u1')
        return HttpResponse.json([
          { request_id: 'req-1', session_id: 'sess-1', turns: 3 },
          { request_id: 'req-2', session_id: 'sess-2', turns: 2 },
        ])
      }),
      http.get(`${API_BASE_URL}/admin/stats/requests/:requestId`, ({ params }) => {
        expect(params.requestId).toBe('req-1')
        return HttpResponse.json({
          request_id: 'req-1',
          events: [{ kind: 'user', text: 'hello' }],
          subagents: [],
        })
      }),
      http.get(`${API_BASE_URL}/admin/stats/sessions/:sessionId/trace`, ({ params, request }) => {
        const url = new URL(request.url)
        expect(params.sessionId).toBe('sess-1')
        expect(url.searchParams.get('user_id')).toBe('u1')
        return HttpResponse.json({
          session_id: 'sess-1',
          events: [{ kind: 'assistant', text: 'ack' }],
          subagents: [],
        })
      })
    )

    const wrapper = createWrapper()
    const overview = renderHook(() => useAgentOverviewQuery('alpha', '30d'), { wrapper })
    const compare = renderHook(() => useCompareAgentsQuery(['alpha', 'beta'], 'calls'), { wrapper })
    const tools = renderHook(() => useAgentToolsQuery('alpha'), { wrapper })
    const perUser = renderHook(() => usePerUserStatsQuery('alpha', 'calls'), { wrapper })
    const userRequests = renderHook(() => useUserRequestsQuery('u1'), { wrapper })
    const requestDetail = renderHook(() => useRequestDetailQuery('req-1'), { wrapper })
    const sessionTrace = renderHook(() => useSessionTraceQuery('sess-1', 'u1'), { wrapper })

    await waitFor(() => {
      expect(overview.result.current.data?.usage.calls).toBe(12)
      expect(compare.result.current.data?.[1]?.agent_id).toBe('beta')
      expect(tools.result.current.data?.top_tools.top[0]).toEqual(['read_file', 8])
      expect(perUser.result.current.data?.[0]?.user_id).toBe('u1')
      expect(userRequests.result.current.data?.[0]?.request_id).toBe('req-1')
      expect(requestDetail.result.current.data?.events[0]?.text).toBe('hello')
      expect(sessionTrace.result.current.data?.events[0]?.text).toBe('ack')
    })
  })

  it('posts exports and returns the downloaded file metadata', async () => {
    server.use(
      http.post(`${API_BASE_URL}/admin/stats/export`, ({ request }) => {
        const url = new URL(request.url)
        expect(request.headers.get('authorization')).toBe('Session session-token')
        expect(url.searchParams.get('view')).toBe('tools')
        expect(url.searchParams.get('agent_id')).toBe('alpha')
        return new HttpResponse('tool,calls\nread_file,8\n', {
          headers: {
            'Content-Disposition': 'attachment; filename="stats-tools.csv"',
            'Content-Type': 'text/csv',
          },
        })
      })
    )

    const wrapper = createWrapper()
    const exportMutation = renderHook(() => useStatsExportMutation(), { wrapper })

    const result = await exportMutation.result.current.mutateAsync({
      agentId: 'alpha',
      view: 'tools',
    })

    expect(result.fileName).toBe('stats-tools.csv')
    expect(result.contentType).toBe('text/csv')
    expect(await result.blob.text()).toContain('read_file,8')
  })
})

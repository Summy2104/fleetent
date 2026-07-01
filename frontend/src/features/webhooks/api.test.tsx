import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/app/auth'
import {
  useCreateWebhookSourceMutation,
  useDeleteWebhookSourceMutation,
  useWebhookSourcesQuery,
} from '@/features/webhooks/api'
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

describe('webhooks api', () => {
  it('loads webhook sources and refreshes the list after create and delete mutations', async () => {
    let listRequests = 0
    let sources = [
      {
        agent_id: 1,
        enabled: true,
        has_secret: false,
        id: 'github-ci',
        message_template: null,
        reply_target: null,
        user_id: 'user-a',
      },
    ]

    server.use(
      http.get(`${API_BASE_URL}/admin/webhooks/sources`, ({ request }) => {
        listRequests += 1
        expect(request.headers.get('authorization')).toBe('Session session-token')
        return HttpResponse.json(sources)
      }),
      http.post(`${API_BASE_URL}/admin/webhooks/sources`, async ({ request }) => {
        expect(await request.json()).toEqual({
          agent_id: 2,
          enabled: true,
          id: 'slack-alerts',
          message_template: null,
          reply_target: null,
          secret: 'topsecret',
          user_id: 'user-b',
        })
        const created = {
          agent_id: 2,
          enabled: true,
          has_secret: true,
          id: 'slack-alerts',
          message_template: null,
          reply_target: null,
          user_id: 'user-b',
        }
        sources = [...sources, created]
        return HttpResponse.json(created, { status: 201 })
      }),
      http.delete(`${API_BASE_URL}/admin/webhooks/sources/:sourceId`, ({ params }) => {
        sources = sources.filter((source) => source.id !== params.sourceId)
        return new HttpResponse(null, { status: 204 })
      })
    )

    const wrapper = createWrapper()
    const sourcesQuery = renderHook(() => useWebhookSourcesQuery(), { wrapper })

    await waitFor(() => {
      expect(sourcesQuery.result.current.data?.[0]?.id).toBe('github-ci')
    })

    const createSource = renderHook(() => useCreateWebhookSourceMutation(), { wrapper })
    const deleteSource = renderHook(() => useDeleteWebhookSourceMutation('slack-alerts'), { wrapper })

    const initialListRequests = listRequests
    await createSource.result.current.mutateAsync({
      agent_id: 2,
      enabled: true,
      id: 'slack-alerts',
      message_template: null,
      reply_target: null,
      secret: 'topsecret',
      user_id: 'user-b',
    })
    await waitFor(() => {
      expect(listRequests).toBeGreaterThan(initialListRequests)
      expect(sourcesQuery.result.current.data?.map((source) => source.id)).toEqual(['github-ci', 'slack-alerts'])
    })

    const beforeDelete = listRequests
    await deleteSource.result.current.mutateAsync()
    await waitFor(() => {
      expect(listRequests).toBeGreaterThan(beforeDelete)
      expect(sourcesQuery.result.current.data?.map((source) => source.id)).toEqual(['github-ci'])
    })
  })
})

import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { auditRowsToCsv, useAuditLogsQuery } from '@/features/audit/api'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

function createWrapper(): ({ children }: { children: ReactNode }) => JSX.Element {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </AuthProvider>
    )
  }
}

describe('audit api', () => {
  it('loads audit logs with backend-supported filters', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/audit`, ({ request }) => {
        const url = new URL(request.url)
        expect(request.headers.get('authorization')).toBe('Session session-token')
        expect(url.searchParams.get('actor')).toBe('admin-1')
        expect(url.searchParams.get('action')).toBe('rotate_key')
        expect(url.searchParams.get('target_id')).toBe('user-1')
        expect(url.searchParams.has('since')).toBe(false)
        return HttpResponse.json([
          {
            id: 1,
            actor_user_id: 'admin-1',
            action: 'rotate_key',
            target_type: 'user',
            target_id: 'user-1',
            detail: { source: 'ui' },
            batch_id: null,
            created_at: '2026-06-27T09:00:00+00:00',
          },
        ])
      })
    )

    const query = renderHook(() => useAuditLogsQuery({ action: 'rotate_key', actor: 'admin-1', targetId: 'user-1' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(query.result.current.data?.[0]?.action).toBe('rotate_key')
    })
  })

  it('serializes the date range as since/until query params', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/audit`, ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('since')).toBe('2026-06-27T00:00:00')
        expect(url.searchParams.get('until')).toBe('2026-06-28T23:59:59.999')
        return HttpResponse.json([])
      })
    )

    const query = renderHook(
      () => useAuditLogsQuery({ since: '2026-06-27T00:00:00', until: '2026-06-28T23:59:59.999' }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(query.result.current.isSuccess).toBe(true)
    })
  })

  it('serializes the current audit rows as CSV', () => {
    const csv = auditRowsToCsv([
      {
        id: 1,
        actor_user_id: 'admin-1',
        action: 'rotate_key',
        target_type: 'user',
        target_id: 'user-1',
        detail: { note: 'hello, world' },
        batch_id: null,
        created_at: '2026-06-27T09:00:00+00:00',
      },
    ])

    expect(csv).toContain('created_at,actor_user_id,action,target_type,target_id,detail,batch_id')
    expect(csv).toContain('"hello, world"')
  })
})

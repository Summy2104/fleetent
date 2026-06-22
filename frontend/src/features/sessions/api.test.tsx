import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import {
  useBulkSessionMutation,
  useClearSessionMutation,
  useForceEndSessionMutation,
  useInjectSessionMutation,
  useSessionDetailQuery,
  useSessionsQuery,
  useResetSessionMutation,
  useReleaseSessionMutation,
  useTakeoverSessionMutation,
} from '@/features/sessions/api';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

function createWrapper(): ({ children }: { children: ReactNode }) => JSX.Element {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <AuthProvider
        baseUrl={API_BASE_URL}
        initialToken="session-token"
      >
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </AuthProvider>
    );
  };
}

describe('sessions api', () => {
  it('loads the sessions list and session detail', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/sessions`, ({ request }) => {
        const url = new URL(request.url);
        expect(request.headers.get('authorization')).toBe('Session session-token');
        expect(url.searchParams.get('status')).toBe('active');
        expect(url.searchParams.get('user_id')).toBe('user-1');
        expect(url.searchParams.get('agent_name')).toBe('alpha');
        return HttpResponse.json([
          {
            session_id: 'sess-1',
            origin: 'im',
            status: 'active',
            agent_name: 'alpha',
            user_id: 'user-1',
            channel: 'slack',
            updated_at: '2026-06-21T10:00:00Z',
          },
        ]);
      }),
      http.get(`${API_BASE_URL}/admin/sessions/sess-1`, () =>
        HttpResponse.json({
          meta: {
            session_id: 'sess-1',
            origin: 'im',
            status: 'active',
            agent_name: 'alpha',
          },
          transcript: [{ role: 'user', content: 'hello' }],
        })
      )
    );

    const wrapper = createWrapper();
    const sessions = renderHook(
      () => useSessionsQuery({ agentName: 'alpha', status: 'active', userId: 'user-1' }),
      { wrapper }
    );
    const detail = renderHook(() => useSessionDetailQuery('sess-1'), { wrapper });

    await waitFor(() => {
      expect(sessions.result.current.data?.[0]?.session_id).toBe('sess-1');
    });
    await waitFor(() => {
      expect(detail.result.current.data?.transcript[0]?.content).toBe('hello');
    });
  });

  it('routes governance mutations to the right endpoints and refreshes list/detail queries', async () => {
    let listRequestCount = 0;
    let detailRequestCount = 0;
    const operations: string[] = [];

    server.use(
      http.get(`${API_BASE_URL}/admin/sessions`, () => {
        listRequestCount += 1;
        return HttpResponse.json([
          {
            session_id: 'sess-1',
            origin: 'im',
            status: 'active',
            agent_name: 'alpha',
            user_id: 'user-1',
            updated_at: '2026-06-21T10:00:00Z',
          },
        ]);
      }),
      http.get(`${API_BASE_URL}/admin/sessions/sess-1`, () => {
        detailRequestCount += 1;
        return HttpResponse.json({
          meta: {
            session_id: 'sess-1',
            origin: 'im',
            status: 'active',
            agent_name: 'alpha',
          },
          transcript: [{ role: 'user', content: `turn-${detailRequestCount}` }],
        });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/sess-1/takeover`, () => {
        operations.push('takeover');
        return HttpResponse.json({ session_id: 'sess-1', taken_over: true });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/sess-1/release`, () => {
        operations.push('release');
        return HttpResponse.json({ session_id: 'sess-1', taken_over: false });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/sess-1/inject`, async ({ request }) => {
        operations.push('inject');
        expect(await request.json()).toEqual({ content: 'manual reply', role: 'human_agent' });
        return HttpResponse.json({ injected: true, session_id: 'sess-1' });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/sess-1/force-end`, ({ request }) => {
        operations.push('force-end');
        expect(request.headers.get('x-confirm')).toBe('true');
        return HttpResponse.json({ session_id: 'sess-1', status: 'ended' });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/sess-1/clear`, ({ request }) => {
        operations.push('clear');
        expect(request.headers.get('x-confirm')).toBe('true');
        return HttpResponse.json({ cleared: true, session_id: 'sess-1' });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/sess-1/reset`, async ({ request }) => {
        operations.push('reset');
        expect(request.headers.get('x-confirm')).toBe('true');
        expect(await request.json()).toEqual({ keep_turns: 2 });
        return HttpResponse.json({ keep_turns: 2, session_id: 'sess-1' });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/bulk`, async ({ request }) => {
        operations.push('bulk');
        expect(request.headers.get('x-confirm')).toBe('true');
        expect(await request.json()).toEqual({ action: 'clear', session_ids: ['sess-1', 'sess-2'] });
        return HttpResponse.json({ action: 'clear', batch_id: 'batch-1', count: 2 });
      })
    );

    const wrapper = createWrapper();
    renderHook(() => useSessionsQuery(), { wrapper });
    renderHook(() => useSessionDetailQuery('sess-1'), { wrapper });

    await waitFor(() => {
      expect(listRequestCount).toBe(1);
      expect(detailRequestCount).toBe(1);
    });

    const takeover = renderHook(() => useTakeoverSessionMutation('sess-1'), { wrapper });
    const release = renderHook(() => useReleaseSessionMutation('sess-1'), { wrapper });
    const inject = renderHook(() => useInjectSessionMutation('sess-1'), { wrapper });
    const forceEnd = renderHook(() => useForceEndSessionMutation('sess-1'), { wrapper });
    const clear = renderHook(() => useClearSessionMutation('sess-1'), { wrapper });
    const reset = renderHook(() => useResetSessionMutation('sess-1'), { wrapper });
    const bulk = renderHook(() => useBulkSessionMutation(), { wrapper });

    let previousListCount = listRequestCount;
    let previousDetailCount = detailRequestCount;

    await takeover.result.current.mutateAsync();
    await waitFor(() => {
      expect(listRequestCount).toBeGreaterThan(previousListCount);
      expect(detailRequestCount).toBeGreaterThan(previousDetailCount);
    });
    previousListCount = listRequestCount;
    previousDetailCount = detailRequestCount;

    await release.result.current.mutateAsync();
    await waitFor(() => {
      expect(listRequestCount).toBeGreaterThan(previousListCount);
      expect(detailRequestCount).toBeGreaterThan(previousDetailCount);
    });
    previousListCount = listRequestCount;
    previousDetailCount = detailRequestCount;

    await inject.result.current.mutateAsync({ content: 'manual reply', role: 'human_agent' });
    await waitFor(() => {
      expect(listRequestCount).toBeGreaterThan(previousListCount);
      expect(detailRequestCount).toBeGreaterThan(previousDetailCount);
    });
    previousListCount = listRequestCount;
    previousDetailCount = detailRequestCount;

    await forceEnd.result.current.mutateAsync();
    await waitFor(() => {
      expect(listRequestCount).toBeGreaterThan(previousListCount);
      expect(detailRequestCount).toBeGreaterThan(previousDetailCount);
    });
    previousListCount = listRequestCount;
    previousDetailCount = detailRequestCount;

    await clear.result.current.mutateAsync();
    await waitFor(() => {
      expect(listRequestCount).toBeGreaterThan(previousListCount);
      expect(detailRequestCount).toBeGreaterThan(previousDetailCount);
    });
    previousListCount = listRequestCount;
    previousDetailCount = detailRequestCount;

    await reset.result.current.mutateAsync({ keepTurns: 2 });
    await waitFor(() => {
      expect(listRequestCount).toBeGreaterThan(previousListCount);
      expect(detailRequestCount).toBeGreaterThan(previousDetailCount);
    });
    previousListCount = listRequestCount;
    previousDetailCount = detailRequestCount;

    await bulk.result.current.mutateAsync({ action: 'clear', sessionIds: ['sess-1', 'sess-2'] });
    await waitFor(() => {
      expect(listRequestCount).toBeGreaterThan(previousListCount);
      expect(detailRequestCount).toBeGreaterThan(previousDetailCount);
    });

    expect(operations).toEqual(['takeover', 'release', 'inject', 'force-end', 'clear', 'reset', 'bulk']);
  });
});

import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import {
  useCreateMappingMutation,
  useDeleteMappingMutation,
  useImMappingsQuery,
} from '@/features/im-identities/api';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

function createWrapper(): ({ children }: { children: ReactNode }) => JSX.Element {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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

describe('im-identities api', () => {
  it('loads mappings and refreshes the list after create and delete', async () => {
    let listRequests = 0;
    let mappings = [
      {
        created_at: '2026-06-21T09:00:00Z',
        id: 1,
        platform: 'slack',
        platform_user_id: 'U1',
        user_email: 'alice@example.com',
        user_id: 'user-alice',
        user_name: 'Alice',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/im-identities`, ({ request }) => {
        listRequests += 1;
        expect(request.headers.get('authorization')).toBe('Session session-token');
        return HttpResponse.json(mappings);
      }),
      http.post(`${API_BASE_URL}/admin/im-identities`, async ({ request }) => {
        expect(await request.json()).toEqual({
          platform: 'telegram',
          platform_user_id: 'T1',
          user_id: 'user-bob',
        });
        mappings = [
          ...mappings,
          {
            created_at: '2026-06-21T11:00:00Z',
            id: 2,
            platform: 'telegram',
            platform_user_id: 'T1',
            user_email: null,
            user_id: 'user-bob',
            user_name: 'Bob',
          },
        ];
        return HttpResponse.json(mappings[1], { status: 201 });
      }),
      http.delete(`${API_BASE_URL}/admin/im-identities/:id`, ({ params }) => {
        mappings = mappings.filter((mapping) => mapping.id !== Number(params.id));
        return new HttpResponse(null, { status: 204 });
      })
    );

    const wrapper = createWrapper();
    const mappingsQuery = renderHook(() => useImMappingsQuery(), { wrapper });

    await waitFor(() => {
      expect(mappingsQuery.result.current.data?.[0]?.user_name).toBe('Alice');
    });

    const createMapping = renderHook(() => useCreateMappingMutation(), { wrapper });
    const deleteMapping = renderHook(() => useDeleteMappingMutation(), { wrapper });

    const created = await createMapping.result.current.mutateAsync({
      platform: 'telegram',
      platform_user_id: 'T1',
      user_id: 'user-bob',
    });
    expect(created.id).toBe(2);
    await waitFor(() => {
      expect(mappingsQuery.result.current.data?.map((mapping) => mapping.id)).toEqual([1, 2]);
    });

    const beforeDelete = listRequests;
    await deleteMapping.result.current.mutateAsync(2);
    await waitFor(() => {
      expect(listRequests).toBeGreaterThan(beforeDelete);
      expect(mappingsQuery.result.current.data?.map((mapping) => mapping.id)).toEqual([1]);
    });
  });
});

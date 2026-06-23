import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import {
  useDeleteNodeMutation,
  useNodePlacementsQuery,
  useNodesQuery,
  usePinAgentMutation,
  useRegisterNodeMutation,
  useUnpinAgentMutation,
} from '@/features/nodes/api';
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

describe('nodes api', () => {
  it('loads nodes and refreshes the list after register, delete, pin, and unpin mutations', async () => {
    let listRequests = 0;
    let nodes = [
      {
        id: 'node-a',
        labels: { region: 'eu' },
        last_seen_at: '2026-06-21T10:00:00Z',
        name: 'Node A',
        registered_at: '2026-06-21T09:00:00Z',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/nodes`, ({ request }) => {
        listRequests += 1;
        expect(request.headers.get('authorization')).toBe('Session session-token');
        return HttpResponse.json(nodes);
      }),
      http.post(`${API_BASE_URL}/admin/nodes`, async ({ request }) => {
        expect(await request.json()).toEqual({
          labels: { region: 'us', rack: 'r1' },
          name: 'Node B',
          node_id: 'node-b',
        });
        nodes = [
          ...nodes,
          {
            id: 'node-b',
            labels: { region: 'us', rack: 'r1' },
            last_seen_at: null,
            name: 'Node B',
            registered_at: '2026-06-21T11:00:00Z',
            service_key_plaintext_once: 'ma-secret',
          },
        ];
        return HttpResponse.json(nodes[1], { status: 201 });
      }),
      http.delete(`${API_BASE_URL}/admin/nodes/:nodeId`, ({ params, request }) => {
        expect(params.nodeId).toBe('node-b');
        expect(request.headers.get('x-confirm')).toBe('true');
        nodes = nodes.filter((node) => node.id !== params.nodeId);
        return new HttpResponse(null, { status: 204 });
      }),
      http.post(`${API_BASE_URL}/admin/nodes/:nodeId/pin`, async ({ params, request }) => {
        expect(params.nodeId).toBe('node-a');
        expect(await request.json()).toEqual({ agent_id: 7 });
        return HttpResponse.json({
          agent_id: 7,
          node_id: 'node-a',
          pinned_at: '2026-06-21T11:10:00Z',
          pinned_by: null,
          updated_at: '2026-06-21T11:10:00Z',
        });
      }),
      http.delete(`${API_BASE_URL}/admin/nodes/:nodeId/pin`, ({ params, request }) => {
        expect(params.nodeId).toBe('node-a');
        expect(new URL(request.url).searchParams.get('agent_id')).toBe('7');
        return new HttpResponse(null, { status: 204 });
      })
    );

    const wrapper = createWrapper();
    const nodesQuery = renderHook(() => useNodesQuery(), { wrapper });

    await waitFor(() => {
      expect(nodesQuery.result.current.data?.[0]?.id).toBe('node-a');
    });

    const registerNode = renderHook(() => useRegisterNodeMutation(), { wrapper });
    const deleteNode = renderHook(() => useDeleteNodeMutation('node-b'), { wrapper });
    const pinAgent = renderHook(() => usePinAgentMutation('node-a'), { wrapper });
    const unpinAgent = renderHook(() => useUnpinAgentMutation('node-a'), { wrapper });

    const initialListRequests = listRequests;
    const registered = await registerNode.result.current.mutateAsync({
      labels: { region: 'us', rack: 'r1' },
      name: 'Node B',
      node_id: 'node-b',
    });
    expect(registered.service_key_plaintext_once).toBe('ma-secret');
    await waitFor(() => {
      expect(listRequests).toBeGreaterThan(initialListRequests);
      expect(nodesQuery.result.current.data?.map((node) => node.id)).toEqual(['node-a', 'node-b']);
    });

    const pinResult = await pinAgent.result.current.mutateAsync({ agent_id: 7 });
    expect(pinResult.node_id).toBe('node-a');

    const beforeUnpin = listRequests;
    await unpinAgent.result.current.mutateAsync(7);
    await waitFor(() => {
      expect(listRequests).toBeGreaterThan(beforeUnpin);
    });

    const beforeDelete = listRequests;
    await deleteNode.result.current.mutateAsync();
    await waitFor(() => {
      expect(listRequests).toBeGreaterThan(beforeDelete);
      expect(nodesQuery.result.current.data?.map((node) => node.id)).toEqual(['node-a']);
    });
  });

  it('loads placements for a node and refetches after pin and unpin', async () => {
    let placementRequests = 0;
    let placements: Array<{
      agent_id: number;
      agent_name: string | null;
      node_id: string;
      pinned_at: string;
      pinned_by: string | null;
      updated_at: string;
    }> = [];

    server.use(
      http.get(`${API_BASE_URL}/admin/nodes/node-a/placements`, ({ request }) => {
        placementRequests += 1;
        expect(request.headers.get('authorization')).toBe('Session session-token');
        return HttpResponse.json(placements);
      }),
      http.post(`${API_BASE_URL}/admin/nodes/node-a/pin`, async ({ request }) => {
        expect(await request.json()).toEqual({ agent_id: 7 });
        placements = [
          {
            agent_id: 7,
            agent_name: 'alpha',
            node_id: 'node-a',
            pinned_at: '2026-06-21T11:10:00Z',
            pinned_by: null,
            updated_at: '2026-06-21T11:10:00Z',
          },
        ];
        return HttpResponse.json(placements[0]);
      }),
      http.delete(`${API_BASE_URL}/admin/nodes/node-a/pin`, ({ request }) => {
        expect(new URL(request.url).searchParams.get('agent_id')).toBe('7');
        placements = [];
        return new HttpResponse(null, { status: 204 });
      })
    );

    const wrapper = createWrapper();
    const placementsQuery = renderHook(() => useNodePlacementsQuery('node-a'), { wrapper });
    const pinAgent = renderHook(() => usePinAgentMutation('node-a'), { wrapper });
    const unpinAgent = renderHook(() => useUnpinAgentMutation('node-a'), { wrapper });

    await waitFor(() => {
      expect(placementsQuery.result.current.data).toEqual([]);
    });

    const beforePin = placementRequests;
    await pinAgent.result.current.mutateAsync({ agent_id: 7 });
    await waitFor(() => {
      expect(placementRequests).toBeGreaterThan(beforePin);
      expect(placementsQuery.result.current.data?.[0]?.agent_name).toBe('alpha');
    });

    const beforeUnpin = placementRequests;
    await unpinAgent.result.current.mutateAsync(7);
    await waitFor(() => {
      expect(placementRequests).toBeGreaterThan(beforeUnpin);
      expect(placementsQuery.result.current.data).toEqual([]);
    });
  });
});

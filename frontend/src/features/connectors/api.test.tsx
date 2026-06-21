import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import {
  useConnectorAgentBindingsQuery,
  useConnectorAuthorizeQuery,
  useConnectorCredentialsMutation,
  useConnectorLifecycleQuery,
  useConnectorTestMutation,
  useConnectorsQuery,
  useCreateConnectorMutation,
  useDeleteConnectorMutation,
  useMcpDoctorQuery,
  useMcpReconnectMutation,
  useMcpServerTestMutation,
  useMcpServerToolsQuery,
  useMcpServersQuery,
  useOffboardingQuery,
  useRevokeConnectorGrantMutation,
  useUpdateConnectorMutation,
  useUpdateMcpServerMutation,
  useCreateMcpServerMutation,
  useDeleteMcpServerMutation,
  useConnectorGrantsQuery,
} from '@/features/connectors/api';
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

describe('connectors api', () => {
  it('loads oauth connector resources and refreshes connector and grant queries after mutations', async () => {
    let connectorsListCount = 0;
    let grantsListCount = 0;
    const calls: string[] = [];
    let connector = {
      id: 'github',
      display_name: 'GitHub',
      protocol: 'oauth2',
      enabled: true,
      oauth_config: {
        authorize: 'https://github.com/login/oauth/authorize',
        client_id: 'cid',
      },
    };
    const lifecycle = {
      connector_id: 'github',
      refresh_ok: 1,
      refresh_failed: 0,
      reauths: 0,
    };
    let grants = [
      {
        user_id: 'u1',
        connector_id: 'github',
        status: 'authorized',
        scopes: ['repo'],
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/connectors`, () => {
        connectorsListCount += 1;
        return HttpResponse.json([connector]);
      }),
      http.get(`${API_BASE_URL}/admin/connectors/github/lifecycle`, () => HttpResponse.json(lifecycle)),
      http.get(`${API_BASE_URL}/admin/connectors/github/bindings/agents`, () =>
        HttpResponse.json({ service_id: 'github', agent_ids: [7, 9] })
      ),
      http.get(`${API_BASE_URL}/admin/connectors/grants`, () => {
        grantsListCount += 1;
        return HttpResponse.json({
          grants,
          consent_hint: 'first consent must be completed in the browser',
        });
      }),
      http.get(`${API_BASE_URL}/admin/connectors/offboarding/u1`, () =>
        HttpResponse.json({ user_id: 'u1', revoked: ['github'], failed: [] })
      ),
      http.get(`${API_BASE_URL}/admin/connectors/authorize/github`, () =>
        HttpResponse.json({
          authorize_url:
            'https://github.com/login/oauth/authorize?client_id=cid&state=test-state',
        })
      ),
      http.post(`${API_BASE_URL}/admin/connectors`, async ({ request }) => {
        calls.push('create-connector');
        expect(await request.json()).toEqual({
          display_name: 'GitHub',
          enabled: true,
          id: 'github',
          oauth_config: {
            authorize: 'https://github.com/login/oauth/authorize',
            client_id: 'cid',
            client_secret: 'super-secret',
          },
          protocol: 'oauth2',
        });
        connector = {
          ...connector,
          oauth_config: {
            authorize: 'https://github.com/login/oauth/authorize',
            client_id: 'cid',
          },
        };
        return HttpResponse.json(connector, { status: 201 });
      }),
      http.put(`${API_BASE_URL}/admin/connectors/github`, async ({ request }) => {
        calls.push('update-connector');
        expect(await request.json()).toEqual({ display_name: 'GitHub Enterprise', enabled: false });
        connector = {
          ...connector,
          display_name: 'GitHub Enterprise',
          enabled: false,
        };
        return HttpResponse.json(connector);
      }),
      http.delete(`${API_BASE_URL}/admin/connectors/github`, () => {
        calls.push('delete-connector');
        connector = {
          ...connector,
          display_name: 'GitHub',
          enabled: true,
        };
        return HttpResponse.json({ connector_id: 'github', success: true });
      }),
      http.post(`${API_BASE_URL}/admin/connectors/github/test`, () => {
        calls.push('test-connector');
        return HttpResponse.json({
          success: true,
          connector_id: 'github',
          enabled: true,
          token_valid: true,
          active_grants: 2,
          display_name: 'GitHub',
        });
      }),
      http.post(`${API_BASE_URL}/admin/connectors/grants/u1/github/revoke`, ({ request }) => {
        calls.push('revoke-grant');
        expect(request.headers.get('x-confirm')).toBe('true');
        grants = [];
        return HttpResponse.json({ revoked: true, user_id: 'u1', connector_id: 'github' });
      }),
      http.post(`${API_BASE_URL}/admin/connectors/github/credentials`, async ({ request }) => {
        calls.push('submit-credentials');
        expect(await request.json()).toEqual({ api_key: 'token-123' });
        return HttpResponse.json({ submitted: true, service_id: 'github' });
      })
    );

    const wrapper = createWrapper();
    const connectorsQuery = renderHook(() => useConnectorsQuery(), { wrapper });
    const lifecycleQuery = renderHook(() => useConnectorLifecycleQuery('github'), { wrapper });
    const bindingsQuery = renderHook(() => useConnectorAgentBindingsQuery('github'), { wrapper });
    const grantsQuery = renderHook(() => useConnectorGrantsQuery(), { wrapper });
    const offboardingQuery = renderHook(() => useOffboardingQuery('u1'), { wrapper });
    const authorizeQuery = renderHook(() => useConnectorAuthorizeQuery('github'), { wrapper });

    await waitFor(() => {
      expect(connectorsQuery.result.current.data?.[0]?.display_name).toBe('GitHub');
    });
    await waitFor(() => {
      expect(lifecycleQuery.result.current.data?.refresh_ok).toBe(1);
      expect(bindingsQuery.result.current.data?.agent_ids).toEqual([7, 9]);
      expect(grantsQuery.result.current.data?.grants[0]?.status).toBe('authorized');
      expect(offboardingQuery.result.current.data?.revoked).toEqual(['github']);
      expect(authorizeQuery.result.current.data?.authorize_url).toContain('state=test-state');
    });

    const createConnector = renderHook(() => useCreateConnectorMutation(), { wrapper });
    const updateConnector = renderHook(() => useUpdateConnectorMutation('github'), { wrapper });
    const deleteConnector = renderHook(() => useDeleteConnectorMutation('github'), { wrapper });
    const testConnector = renderHook(() => useConnectorTestMutation('github'), { wrapper });
    const revokeGrant = renderHook(() => useRevokeConnectorGrantMutation('u1', 'github'), { wrapper });
    const submitCredentials = renderHook(() => useConnectorCredentialsMutation('github'), {
      wrapper,
    });

    let previousConnectorListCount = connectorsListCount;
    let previousGrantListCount = grantsListCount;

    await createConnector.result.current.mutateAsync({
      display_name: 'GitHub',
      enabled: true,
      id: 'github',
      oauth_config: {
        authorize: 'https://github.com/login/oauth/authorize',
        client_id: 'cid',
        client_secret: 'super-secret',
      },
      protocol: 'oauth2',
    });
    await waitFor(() => {
      expect(connectorsListCount).toBeGreaterThan(previousConnectorListCount);
    });
    previousConnectorListCount = connectorsListCount;

    await updateConnector.result.current.mutateAsync({
      display_name: 'GitHub Enterprise',
      enabled: false,
    });
    await waitFor(() => {
      expect(connectorsListCount).toBeGreaterThan(previousConnectorListCount);
      expect(connectorsQuery.result.current.data?.[0]?.display_name).toBe('GitHub Enterprise');
    });
    previousConnectorListCount = connectorsListCount;

    const testResult = await testConnector.result.current.mutateAsync();
    expect(testResult.success).toBe(true);
    expect(testResult.active_grants).toBe(2);

    await revokeGrant.result.current.mutateAsync();
    await waitFor(() => {
      expect(grantsListCount).toBeGreaterThan(previousGrantListCount);
      expect(grantsQuery.result.current.data?.grants).toEqual([]);
    });
    previousGrantListCount = grantsListCount;

    const credentialsResult = await submitCredentials.result.current.mutateAsync({ api_key: 'token-123' });
    expect(credentialsResult).toEqual({ service_id: 'github', submitted: true });

    await deleteConnector.result.current.mutateAsync();
    await waitFor(() => {
      expect(connectorsListCount).toBeGreaterThan(previousConnectorListCount);
    });

    expect(calls).toEqual([
      'create-connector',
      'update-connector',
      'test-connector',
      'revoke-grant',
      'submit-credentials',
      'delete-connector',
    ]);
  });

  it('loads mcp resources and refreshes the mcp list after create, update, reconnect, test, and delete', async () => {
    let mcpListCount = 0;
    const calls: string[] = [];
    let servers = [
      {
        id: 'filesystem',
        transport: 'stdio',
        command: 'uvx',
        args: ['mcp-filesystem'],
        enabled: true,
        status: 'connected',
        tool_count: 2,
        agent_id: null,
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers`, () => {
        mcpListCount += 1;
        return HttpResponse.json(servers);
      }),
      http.get(`${API_BASE_URL}/admin/mcp/servers/filesystem/tools`, () =>
        HttpResponse.json({
          connected: true,
          tools: [{ name: 'read_file', description: 'Read a file' }],
        })
      ),
      http.get(`${API_BASE_URL}/admin/mcp/doctor`, () =>
        HttpResponse.json({
          checks: [{ name: 'filesystem', level: 'green', detail: 'reachable' }],
        })
      ),
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        calls.push('create-mcp');
        expect(await request.json()).toEqual({
          args: ['mcp-filesystem'],
          command: 'uvx',
          id: 'filesystem',
          transport: 'stdio',
        });
        return HttpResponse.json({ server_id: 'filesystem', success: true }, { status: 201 });
      }),
      http.put(`${API_BASE_URL}/admin/mcp/servers/filesystem`, async ({ request }) => {
        calls.push('update-mcp');
        expect(await request.json()).toEqual({ enabled: false, transport: 'websocket', url: 'wss://mcp.test' });
        servers = [
          {
            ...servers[0],
            enabled: false,
            status: 'disabled',
            transport: 'websocket',
            url: 'wss://mcp.test',
          },
        ];
        return HttpResponse.json({ server_id: 'filesystem', success: true });
      }),
      http.post(`${API_BASE_URL}/admin/mcp/servers/filesystem/reconnect`, () => {
        calls.push('reconnect-mcp');
        return HttpResponse.json({ reconnected: true, server_id: 'filesystem' });
      }),
      http.post(`${API_BASE_URL}/admin/mcp/servers/filesystem/test`, () => {
        calls.push('test-mcp');
        return HttpResponse.json({
          success: true,
          server_id: 'filesystem',
          connected: true,
          tools_count: 3,
          tools: ['read_file', 'write_file', 'stat'],
        });
      }),
      http.delete(`${API_BASE_URL}/admin/mcp/servers/filesystem`, () => {
        calls.push('delete-mcp');
        servers = [];
        return HttpResponse.json({ server_id: 'filesystem', success: true });
      })
    );

    const wrapper = createWrapper();
    const mcpServersQuery = renderHook(() => useMcpServersQuery(), { wrapper });
    const toolsQuery = renderHook(() => useMcpServerToolsQuery('filesystem'), { wrapper });
    const doctorQuery = renderHook(() => useMcpDoctorQuery(), { wrapper });

    await waitFor(() => {
      expect(mcpServersQuery.result.current.data?.[0]?.id).toBe('filesystem');
      expect(toolsQuery.result.current.data?.tools[0]?.name).toBe('read_file');
      expect(doctorQuery.result.current.data?.checks[0]?.level).toBe('green');
    });

    const createMcp = renderHook(() => useCreateMcpServerMutation(), { wrapper });
    const updateMcp = renderHook(() => useUpdateMcpServerMutation('filesystem'), { wrapper });
    const reconnectMcp = renderHook(() => useMcpReconnectMutation('filesystem'), { wrapper });
    const testMcp = renderHook(() => useMcpServerTestMutation('filesystem'), { wrapper });
    const deleteMcp = renderHook(() => useDeleteMcpServerMutation('filesystem'), { wrapper });

    let previousMcpListCount = mcpListCount;

    await createMcp.result.current.mutateAsync({
      args: ['mcp-filesystem'],
      command: 'uvx',
      id: 'filesystem',
      transport: 'stdio',
    });
    await waitFor(() => {
      expect(mcpListCount).toBeGreaterThan(previousMcpListCount);
    });
    previousMcpListCount = mcpListCount;

    await updateMcp.result.current.mutateAsync({
      enabled: false,
      transport: 'websocket',
      url: 'wss://mcp.test',
    });
    await waitFor(() => {
      expect(mcpListCount).toBeGreaterThan(previousMcpListCount);
      expect(mcpServersQuery.result.current.data?.[0]?.transport).toBe('websocket');
    });
    previousMcpListCount = mcpListCount;

    const reconnectResult = await reconnectMcp.result.current.mutateAsync();
    expect(reconnectResult).toEqual({ reconnected: true, server_id: 'filesystem' });

    const testResult = await testMcp.result.current.mutateAsync();
    expect(testResult.tools_count).toBe(3);

    await deleteMcp.result.current.mutateAsync();
    await waitFor(() => {
      expect(mcpListCount).toBeGreaterThan(previousMcpListCount);
      expect(mcpServersQuery.result.current.data).toEqual([]);
    });

    expect(calls).toEqual(['create-mcp', 'update-mcp', 'reconnect-mcp', 'test-mcp', 'delete-mcp']);
  });
});

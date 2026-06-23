import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { ConnectorsPage } from '@/features/connectors/page';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

function renderPage(): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken="session-token"
    >
      <AppQueryProvider>
        <ConnectorsPage />
      </AppQueryProvider>
    </AuthProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('connectors page', () => {
  it('supports oauth connector create, edit, delete, test, authorize, revoke, and keeps credentials write-only', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    let connectors = [
      {
        id: 'github',
        display_name: 'GitHub',
        protocol: 'oauth2',
        enabled: true,
        oauth_config: {
          authorize: 'https://github.com/login/oauth/authorize',
          client_id: 'cid',
        },
      },
    ];
    let grants = [
      {
        user_id: 'u1',
        connector_id: 'github',
        status: 'authorized',
        scopes: ['repo'],
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/connectors`, () => HttpResponse.json(connectors)),
      http.get(`${API_BASE_URL}/admin/connectors/github/lifecycle`, () =>
        HttpResponse.json({
          connector_id: 'github',
          refresh_ok: 2,
          refresh_failed: 0,
          reauths: 0,
        })
      ),
      http.get(`${API_BASE_URL}/admin/connectors/github/bindings/agents`, () =>
        HttpResponse.json({ service_id: 'github', agent_ids: [7, 9] })
      ),
      http.get(`${API_BASE_URL}/admin/connectors/:connectorId/lifecycle`, ({ params }) =>
        HttpResponse.json({
          connector_id: String(params.connectorId),
          refresh_ok: 0,
          refresh_failed: 0,
          reauths: 0,
        })
      ),
      http.get(`${API_BASE_URL}/admin/connectors/:connectorId/bindings/agents`, ({ params }) =>
        HttpResponse.json({ service_id: String(params.connectorId), agent_ids: [] })
      ),
      http.get(`${API_BASE_URL}/admin/connectors/grants`, () =>
        HttpResponse.json({
          grants,
          consent_hint: 'first consent must be completed in the browser',
        })
      ),
      http.get(`${API_BASE_URL}/admin/connectors/authorize/github`, () =>
        HttpResponse.json({
          authorize_url: 'https://github.com/login/oauth/authorize?client_id=cid&state=test-state',
        })
      ),
      http.get(`${API_BASE_URL}/admin/connectors/offboarding/u1`, () =>
        HttpResponse.json({ user_id: 'u1', revoked: ['github'], failed: [] })
      ),
      http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/mcp/doctor`, () => HttpResponse.json({ checks: [] })),
      http.post(`${API_BASE_URL}/admin/connectors`, async ({ request }) => {
        const body = (await request.json()) as {
          display_name: string;
          enabled: boolean;
          id: string;
          protocol: string;
        };
        connectors = [...connectors, { ...body, oauth_config: undefined }];
        const created = connectors[connectors.length - 1];
        return HttpResponse.json(created, { status: 201 });
      }),
      http.put(`${API_BASE_URL}/admin/connectors/github`, async ({ request }) => {
        const body = (await request.json()) as { display_name?: string; enabled?: boolean };
        connectors = connectors.map((connector) =>
          connector.id === 'github' ? { ...connector, ...body } : connector
        );
        return HttpResponse.json(connectors[0]);
      }),
      http.delete(`${API_BASE_URL}/admin/connectors/github`, () => {
        connectors = connectors.filter((connector) => connector.id !== 'github');
        return HttpResponse.json({ success: true, connector_id: 'github' });
      }),
      http.post(`${API_BASE_URL}/admin/connectors/github/test`, () =>
        HttpResponse.json({
          success: true,
          connector_id: 'github',
          enabled: true,
          token_valid: true,
          active_grants: 3,
          display_name: 'GitHub',
        })
      ),
      http.post(`${API_BASE_URL}/admin/connectors/grants/u1/github/revoke`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        grants = [];
        return HttpResponse.json({ revoked: true, user_id: 'u1', connector_id: 'github' });
      }),
      http.post(`${API_BASE_URL}/admin/connectors/github/credentials`, async ({ request }) => {
        expect(await request.json()).toEqual({ api_key: 'secret-token' });
        return HttpResponse.json({ submitted: true, service_id: 'github' });
      })
    );

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Connectors' })).toBeInTheDocument();
    expect(await screen.findByText('GitHub')).toBeInTheDocument();
    expect(screen.getByText('authorized')).toBeInTheDocument();
    expect(await screen.findByText('Agents: 7, 9')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Connector ID'), 'slack');
    await user.type(screen.getByLabelText('Display name'), 'Slack');
    await user.selectOptions(screen.getByLabelText('Protocol'), 'apikey');
    await user.click(screen.getByRole('button', { name: 'Create connector' }));
    expect(await screen.findByText('Slack')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit GitHub' }));
    expect(screen.getByDisplayValue('github')).toBeDisabled();
    await user.clear(screen.getByLabelText('Display name'));
    await user.type(screen.getByLabelText('Display name'), 'GitHub Enterprise');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText('GitHub Enterprise')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Test GitHub Enterprise' }));
    expect(await screen.findByText('Token valid; 3 active grants')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Load authorize link for GitHub Enterprise' }));
    const authorizeLink = await screen.findByRole('link', { name: 'Open browser authorize flow' });
    expect(authorizeLink).toHaveAttribute(
      'href',
      'https://github.com/login/oauth/authorize?client_id=cid&state=test-state'
    );

    const githubCard = screen.getByRole('heading', { name: 'GitHub Enterprise' }).closest('article') as HTMLElement;
    await user.clear(within(githubCard).getByLabelText('API key'));
    await user.type(within(githubCard).getByLabelText('API key'), 'secret-token');
    await user.click(screen.getByRole('button', { name: 'Save GitHub Enterprise credentials' }));
    await waitFor(() => {
      expect(screen.getByText('Credentials saved for GitHub Enterprise')).toBeInTheDocument();
    });
    expect(screen.queryByDisplayValue('secret-token')).not.toBeInTheDocument();
    expect(screen.queryByText('secret-token')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Revoke github for u1' }));
    await waitFor(() => {
      expect(screen.queryByText('authorized')).not.toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText('Offboarding user ID'));
    await user.type(screen.getByLabelText('Offboarding user ID'), 'u1');
    await user.click(screen.getByRole('button', { name: 'Load offboarding summary' }));
    expect(await screen.findByText('Revoked: github')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete GitHub Enterprise' }));
    await waitFor(() => {
      expect(screen.queryByText('GitHub Enterprise')).not.toBeInTheDocument();
    });
  });

  it('supports mcp server create, edit, delete, test, reconnect, tools, and doctor views', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

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
      http.get(`${API_BASE_URL}/admin/connectors`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/connectors/grants`, () =>
        HttpResponse.json({ grants: [], consent_hint: 'browser flow required' })
      ),
      http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json(servers)),
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
        const body = (await request.json()) as {
          command?: string;
          id: string;
          transport: string;
          url?: string;
        };
        servers = [
          ...servers,
          {
            ...body,
            enabled: true,
            status: 'configured',
            tool_count: 0,
            agent_id: null,
          },
        ];
        return HttpResponse.json({ success: true, server_id: body.id }, { status: 201 });
      }),
      http.put(`${API_BASE_URL}/admin/mcp/servers/filesystem`, async ({ request }) => {
        const body = (await request.json()) as {
          enabled?: boolean;
          transport?: string;
          url?: string;
        };
        servers = servers.map((server) =>
          server.id === 'filesystem'
            ? {
                ...server,
                enabled: body.enabled ?? server.enabled,
                status: body.enabled === false ? 'disabled' : server.status,
                transport: body.transport ?? server.transport,
                url: body.url,
              }
            : server
        );
        return HttpResponse.json({ success: true, server_id: 'filesystem' });
      }),
      http.post(`${API_BASE_URL}/admin/mcp/servers/filesystem/reconnect`, () =>
        HttpResponse.json({ reconnected: true, server_id: 'filesystem' })
      ),
      http.post(`${API_BASE_URL}/admin/mcp/servers/filesystem/test`, () =>
        HttpResponse.json({
          success: true,
          server_id: 'filesystem',
          connected: true,
          tools_count: 3,
          tools: ['read_file', 'write_file', 'stat'],
        })
      ),
      http.delete(`${API_BASE_URL}/admin/mcp/servers/filesystem`, () => {
        servers = servers.filter((server) => server.id !== 'filesystem');
        return HttpResponse.json({ success: true, server_id: 'filesystem' });
      })
    );

    renderPage();

    expect(await screen.findByText('filesystem')).toBeInTheDocument();
    expect(screen.getByText('connected')).toBeInTheDocument();

    await user.type(screen.getByLabelText('MCP server ID'), 'github');
    await user.selectOptions(screen.getByLabelText('MCP transport'), 'http');
    await user.type(screen.getByLabelText('Command'), 'npx');
    await user.type(screen.getByLabelText('URL'), 'https://mcp.example.com');
    await user.click(screen.getByRole('button', { name: 'Create MCP server' }));
    expect(await screen.findByText('github')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit filesystem' }));
    expect(screen.getByDisplayValue('filesystem')).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('MCP transport'), 'websocket');
    await user.clear(screen.getByLabelText('URL'));
    await user.type(screen.getByLabelText('URL'), 'wss://mcp.example.com');
    await user.click(screen.getByLabelText('Enabled'));
    await user.click(screen.getByRole('button', { name: 'Save MCP changes' }));
    expect(await screen.findByText('disabled')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reconnect filesystem' }));
    expect(await screen.findByText('Reconnect requested for filesystem')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Test filesystem' }));
    expect(await screen.findByText('Connected; 3 tools')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Load tools for filesystem' }));
    expect(await screen.findByText('read_file')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Load doctor checks' }));
    const doctor = await screen.findByTestId('mcp-doctor');
    expect(within(doctor).getByText('filesystem')).toBeInTheDocument();
    expect(within(doctor).getByText('green')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete filesystem' }));
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Delete filesystem' })).not.toBeInTheDocument();
    });
  });
});

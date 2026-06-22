import { MemoryRouter } from 'react-router-dom';
import { render, screen, within } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { AdminRoutes } from '@/app/routes';
import { server } from '@/test/msw/server';

function renderRoutes(route: string, token?: string): void {
  render(
    <AuthProvider
      baseUrl="http://fleetent.test"
      initialToken={token ?? null}
    >
      <AppQueryProvider>
        <MemoryRouter initialEntries={[route]}>
          <AdminRoutes />
        </MemoryRouter>
      </AppQueryProvider>
    </AuthProvider>
  );
}

describe('admin routes', () => {
  it('redirects unauthenticated users to the login page', async () => {
    renderRoutes('/agents');

    expect(await screen.findByRole('heading', { name: 'Admin Login' })).toBeInTheDocument();
  });

  it('renders the agents page with native navigation links', async () => {
    server.use(http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])));

    renderRoutes('/agents', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Agents' })).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Agents' })).toHaveAttribute('href', '/agents');
    expect(nav.getByRole('link', { name: 'Sessions' })).toHaveAttribute('href', '/sessions');
    expect(nav.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users');
    expect(nav.getByRole('link', { name: 'Providers' })).toHaveAttribute(
      'href',
      '/providers'
    );
    expect(nav.getAllByRole('link', { name: 'Skills' })[0]).toHaveAttribute('href', '/skills');
    expect(nav.getAllByRole('link', { name: 'Knowledge Base' })[0]).toHaveAttribute('href', '/kb');
  });

  it('keeps migrated domains on native routes without duplicate legacy deep links', async () => {
    server.use(http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])));

    renderRoutes('/agents', 'session-token');

    await screen.findByRole('heading', { name: 'Agents' });
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getAllByRole('link', { name: 'Skills' })).toHaveLength(1);
    expect(nav.getAllByRole('link', { name: 'Knowledge Base' })).toHaveLength(1);
    expect(nav.getAllByRole('link', { name: 'Statistics' })).toHaveLength(1);
  });

  it('renders statistics as a native route instead of a legacy deep link', async () => {
    server.use(
      http.get('http://fleetent.test/admin/agents', () =>
        HttpResponse.json([
          {
            agent_name: 'alpha',
            provenance: 'adhoc',
            status: 'enabled',
            system_prompt: 'Alpha prompt',
          },
        ])
      ),
      http.get('http://fleetent.test/admin/stats/agents/alpha/overview', () =>
        HttpResponse.json({
          agent_id: 'alpha',
          approvals: { approved: 2 },
          cost: { total: 1.1 },
          performance: { p95_ms: 700 },
          usage: { calls: 9, total_tokens: 600 },
        })
      ),
      http.get('http://fleetent.test/admin/stats/compare', () =>
        HttpResponse.json([{ agent_id: 'alpha', value: 9 }])
      ),
      http.get('http://fleetent.test/admin/stats/agents/alpha/tools', () =>
        HttpResponse.json({
          coverage: { allowed: 2, used: 1 },
          top_tools: { top: [['read_file', 9]] },
        })
      ),
      http.get('http://fleetent.test/admin/stats/per-user', () =>
        HttpResponse.json([{ user_id: 'u1', calls: 9, total_tokens: 600 }])
      )
    );

    renderRoutes('/stats', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Statistics' })).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Statistics' })).toHaveAttribute('href', '/stats');
  });

  it('renders providers as a native route instead of a legacy deep link', async () => {
    server.use(http.get('http://fleetent.test/admin/providers', () => HttpResponse.json([])));

    renderRoutes('/providers', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Providers' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Providers' })).toHaveAttribute('href', '/providers');
  });

  it('renders skills as a native route instead of a legacy deep link', async () => {
    server.use(
      http.get('http://fleetent.test/admin/skills', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/skills/proposals', () => HttpResponse.json([]))
    );

    renderRoutes('/skills', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Skills' })).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getAllByRole('link', { name: 'Skills' })[0]).toHaveAttribute('href', '/skills');
  });

  it('renders sessions as a native route in the SPA', async () => {
    server.use(
      http.get('http://fleetent.test/admin/me', () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get('http://fleetent.test/admin/sessions', () => HttpResponse.json([]))
    );

    renderRoutes('/sessions', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Sessions' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Sessions' })).toHaveAttribute('href', '/sessions');
  });

  it('renders knowledge base as a native route instead of a legacy deep link', async () => {
    server.use(
      http.get('http://fleetent.test/admin/kb', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/kb/connectors', () => HttpResponse.json([]))
    );

    renderRoutes('/kb', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Knowledge Base' })).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    const knowledgeBaseLinks = nav.getAllByRole('link', { name: 'Knowledge Base' });
    expect(knowledgeBaseLinks[0]).toHaveAttribute('href', '/kb');
  });

  it('renders the users page as a native route', async () => {
    server.use(
      http.get('http://fleetent.test/admin/users', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/im-users', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/users/u1/keys', () => HttpResponse.json([]))
    );

    renderRoutes('/users', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users');
  });

  it('renders connectors as a native route and removes the legacy connectors link', async () => {
    server.use(
      http.get('http://fleetent.test/admin/connectors', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/connectors/grants', () =>
        HttpResponse.json({ grants: [], consent_hint: 'browser flow required' })
      ),
      http.get('http://fleetent.test/admin/mcp/servers', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/mcp/doctor', () => HttpResponse.json({ checks: [] }))
    );

    renderRoutes('/connectors', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Connectors' })).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    const connectorLinks = nav.getAllByRole('link', { name: 'Connectors' });
    expect(connectorLinks).toHaveLength(1);
    expect(connectorLinks[0]).toHaveAttribute('href', '/connectors');
    expect(nav.getAllByRole('link', { name: 'Skills' })).toHaveLength(1);
  });

  it('renders chat as a native route in the SPA', async () => {
    server.use(http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])));

    renderRoutes('/chat', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Chat Console' })).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Chat' })).toHaveAttribute('href', '/chat');
  });

  it('renders tenancy as a native route in the SPA', async () => {
    server.use(
      http.get('http://fleetent.test/admin/me', () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get('http://fleetent.test/admin/tenancy/tenants', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/tenancy/teams', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/users', () => HttpResponse.json([]))
    );

    renderRoutes('/tenancy', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Tenancy' })).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Tenancy' })).toHaveAttribute('href', '/tenancy');
  });

  it('renders nodes as a native route in the SPA', async () => {
    server.use(
      http.get('http://fleetent.test/admin/nodes', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/agents', ({ request }) => {
        expect(new URL(request.url).searchParams.get('include_archived')).toBe('true');
        return HttpResponse.json([]);
      })
    );

    renderRoutes('/nodes', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Nodes' })).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Nodes' })).toHaveAttribute('href', '/nodes');
  });
});

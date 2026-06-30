import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, delay, http } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { AdminRoutes } from '@/app/routes';
import { ThemeProvider } from '@/app/theme';
import { I18nProvider } from '@/i18n';
import { server } from '@/test/msw/server';

beforeEach(() => {
  server.use(
    http.get('http://fleetent.test/admin/oidc/config', () =>
      HttpResponse.json({ enabled: false, label: '' })
    )
  );
});

function renderRoutes(route: string, token?: string, mustReset?: boolean): void {
  render(
    <I18nProvider>
      <ThemeProvider>
        <AuthProvider
          baseUrl="http://fleetent.test"
          initialToken={token ?? null}
          initialMustReset={mustReset ?? false}
        >
          <AppQueryProvider>
            <MemoryRouter initialEntries={[route]}>
              <AdminRoutes />
            </MemoryRouter>
          </AppQueryProvider>
        </AuthProvider>
      </ThemeProvider>
    </I18nProvider>
  );
}

describe('admin routes', () => {
  it('redirects unauthenticated users to the login page', async () => {
    renderRoutes('/agents');

    expect(await screen.findByRole('heading', { name: 'Admin Login' })).toBeInTheDocument();
  });

  it('forces a password change when the session requires a reset', async () => {
    server.use(http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])));

    renderRoutes('/agents', 'session-token', true);

    expect(await screen.findByRole('heading', { name: 'Set a new password' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Agents' })).not.toBeInTheDocument();
  });

  it('lets the admin complete the forced password change and enter the app', async () => {
    server.use(
      http.post('http://fleetent.test/admin/change-password', async ({ request }) => {
        const body = (await request.json()) as { new_password: string };
        expect(body.new_password).toBe('s3cret-new');
        return HttpResponse.json({ status: 'password_changed' });
      }),
      http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([]))
    );

    renderRoutes('/agents', 'session-token', true);

    const field = await screen.findByLabelText('New password');
    await userEvent.type(field, 's3cret-new');
    // The gate now also requires a matching confirmation before the submit enables.
    await userEvent.type(screen.getByLabelText('Confirm new password'), 's3cret-new');
    await userEvent.click(screen.getByRole('button', { name: 'Set password & continue' }));

    expect((await screen.findAllByRole('heading', { name: 'Agents' }))[0]).toBeInTheDocument();
  });

  it('hides the SSO entry point when OIDC is disabled', async () => {
    server.use(
      http.get('http://fleetent.test/admin/oidc/config', () =>
        HttpResponse.json({ enabled: false, label: '' })
      )
    );

    renderRoutes('/login');

    expect(await screen.findByRole('heading', { name: 'Admin Login' })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Sign in with SSO' })).not.toBeInTheDocument();
    });
  });

  it('hides the SSO entry point while config is loading or failed', async () => {
    server.use(
      http.get('http://fleetent.test/admin/oidc/config', async () => {
        await delay('infinite');
        return HttpResponse.json({ enabled: true, label: 'Sign in with Google' });
      })
    );

    renderRoutes('/login');

    expect(await screen.findByRole('heading', { name: 'Admin Login' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign in with Google' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign in with SSO' })).not.toBeInTheDocument();

    server.resetHandlers(
      http.get('http://fleetent.test/admin/oidc/config', () => HttpResponse.error())
    );
    renderRoutes('/login');

    expect(await screen.findAllByRole('heading', { name: 'Admin Login' })).toHaveLength(2);
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Sign in with Google' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Sign in with SSO' })).not.toBeInTheDocument();
    });
  });

  it('shows the configured SSO label when OIDC is enabled', async () => {
    server.use(
      http.get('http://fleetent.test/admin/oidc/config', () =>
        HttpResponse.json({ enabled: true, label: 'Sign in with Google' })
      )
    );

    renderRoutes('/login');

    expect(await screen.findByRole('button', { name: 'Sign in with Google' })).toBeInTheDocument();
  });

  it('falls back to the default SSO label when OIDC is enabled without a label', async () => {
    server.use(
      http.get('http://fleetent.test/admin/oidc/config', () =>
        HttpResponse.json({ enabled: true, label: '' })
      )
    );

    renderRoutes('/login');

    expect(await screen.findByRole('button', { name: 'Sign in with SSO' })).toBeInTheDocument();
  });

  it('consumes an OIDC callback token from the login route query string', async () => {
    server.use(
      http.get('http://fleetent.test/admin/agents', ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Session oidc-session');
        return HttpResponse.json([]);
      })
    );

    renderRoutes('/login?token=oidc-session');

    expect((await screen.findAllByRole('heading', { name: 'Agents' }))[0]).toBeInTheDocument();
  });

  it('renders the agents page with native navigation links', async () => {
    server.use(http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])));

    renderRoutes('/agents', 'session-token');

    expect((await screen.findAllByRole('heading', { name: 'Agents' }))[0]).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Agents' })).toHaveAttribute('href', '/agents');
    expect(nav.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users');
    expect(nav.getByRole('link', { name: 'Providers' })).toHaveAttribute(
      'href',
      '/providers'
    );
    expect(nav.getAllByRole('link', { name: 'Skills' })[0]).toHaveAttribute('href', '/skills');
    expect(nav.getAllByRole('link', { name: 'Knowledge Base' })[0]).toHaveAttribute('href', '/kb');
  });

  it('signs out by notifying the backend and returning to the login page', async () => {
    let logoutAuth: string | null = 'never-called';
    server.use(
      http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])),
      http.post('http://fleetent.test/admin/logout', ({ request }) => {
        logoutAuth = request.headers.get('authorization');
        return HttpResponse.json({ status: 'logged_out' });
      })
    );

    renderRoutes('/agents', 'session-token');
    await screen.findAllByRole('heading', { name: 'Agents' });

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    // The backend session is torn down with the current token, then the UI
    // drops the local session and redirects to the login page.
    expect(await screen.findByRole('heading', { name: 'Admin Login' })).toBeInTheDocument();
    expect(logoutAuth).toBe('Session session-token');
  });

  it('keeps migrated domains on native routes without duplicate legacy deep links', async () => {
    server.use(http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])));

    renderRoutes('/agents', 'session-token');

    await screen.findAllByRole('heading', { name: 'Agents' });
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

    expect((await screen.findAllByRole('heading', { name: 'Statistics' }))[0]).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Statistics' })).toHaveAttribute('href', '/stats');
  });

  it('renders audit as a native route in the SPA', async () => {
    renderRoutes('/audit', 'session-token');

    expect((await screen.findAllByRole('heading', { name: 'Audit' }))[0]).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Audit' })).toHaveAttribute('href', '/audit');
  });

  it('renders providers as a native route instead of a legacy deep link', async () => {
    server.use(http.get('http://fleetent.test/admin/providers', () => HttpResponse.json([])));

    renderRoutes('/providers', 'session-token');

    expect((await screen.findAllByRole('heading', { name: 'Providers' }))[0]).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Providers' })).toHaveAttribute('href', '/providers');
  });

  it('renders skills as a native route instead of a legacy deep link', async () => {
    server.use(
      http.get('http://fleetent.test/admin/skills', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/skills/proposals', () => HttpResponse.json([]))
    );

    renderRoutes('/skills', 'session-token');

    expect((await screen.findAllByRole('heading', { name: 'Skills' }))[0]).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getAllByRole('link', { name: 'Skills' })[0]).toHaveAttribute('href', '/skills');
  });

  it('renders knowledge base as a native route instead of a legacy deep link', async () => {
    server.use(
      http.get('http://fleetent.test/admin/kb', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/kb/connectors', () => HttpResponse.json([]))
    );

    renderRoutes('/kb', 'session-token');

    expect((await screen.findAllByRole('heading', { name: 'Knowledge Base' }))[0]).toBeInTheDocument();
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

    expect((await screen.findAllByRole('heading', { name: 'Users' }))[0]).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users');
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

    expect((await screen.findAllByRole('heading', { name: 'Tenancy' }))[0]).toBeInTheDocument();
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

    expect((await screen.findAllByRole('heading', { name: 'Nodes' }))[0]).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Nodes' })).toHaveAttribute('href', '/nodes');
  });

  it('removes the standalone user-IM identities route and navigation item', async () => {
    server.use(http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])));

    renderRoutes('/im-identities', 'session-token');

    expect((await screen.findAllByRole('heading', { name: 'Agents' }))[0]).toBeInTheDocument();
    const nav = within(screen.getByRole('navigation'));
    expect(nav.queryByRole('link', { name: 'IM Identities' })).not.toBeInTheDocument();
  });
});

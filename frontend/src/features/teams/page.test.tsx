import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { TeamsPage } from '@/features/teams/page';
import { I18nProvider } from '@/i18n';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

type TeamRecord = {
  approver_user_id: string | null;
  created_at: string;
  id: string;
  name: string;
  tenant_id: string;
};

function renderTeamsPage(): void {
  render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <AppQueryProvider>
          <TeamsPage />
        </AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

describe('teams page', () => {
  it('lets admins list and create teams, and set a team approver', async () => {
    const user = userEvent.setup({ delay: null });
    let teams: TeamRecord[] = [
      {
        approver_user_id: null,
        created_at: '2026-06-21T10:05:00Z',
        id: 'team-a',
        name: 'Team A',
        tenant_id: 'tenant-a',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/tenancy/tenants`, () =>
        HttpResponse.json([
          {
            approver_user_id: null,
            created_at: '2026-06-21T10:00:00Z',
            id: 'tenant-a',
            name: 'Tenant A',
            status: 'active',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/tenancy/teams`, () => HttpResponse.json(teams)),
      http.get(`${API_BASE_URL}/admin/users`, () =>
        HttpResponse.json([
          {
            email: 'bob@fleetent.test',
            id: 'user-2',
            must_reset: false,
            name: 'Bob',
            role: 'admin',
            status: 'active',
            tenant_id: null,
          },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/tenancy/teams`, async ({ request }) => {
        const body = (await request.json()) as { name: string; tenant_id: string };
        const created = {
          approver_user_id: null,
          created_at: '2026-06-21T10:11:00Z',
          id: 'team-b',
          name: body.name,
          tenant_id: body.tenant_id,
        };
        teams = [...teams, created];
        return HttpResponse.json(created, { status: 201 });
      }),
      http.patch(`${API_BASE_URL}/admin/tenancy/approvers/team-a`, async ({ request }) => {
        expect(await request.json()).toEqual({ approver_user_id: 'user-2', entity_type: 'team' });
        teams = teams.map((team) =>
          team.id === 'team-a' ? { ...team, approver_user_id: 'user-2' } : team
        );
        return HttpResponse.json({ entity_type: 'team', id: 'team-a', status: 'ok' });
      })
    );

    renderTeamsPage();

    expect(await screen.findByRole('heading', { name: 'Teams' })).toBeInTheDocument();
    expect(await screen.findByText('Team A')).toBeInTheDocument();

    // Create a team via the dialog.
    await user.click(screen.getByRole('button', { name: 'Create team' }));
    await user.type(screen.getByLabelText('Name'), 'Team B');
    await user.click(screen.getByRole('button', { name: 'Create team' }));
    expect(await screen.findByText('Team B')).toBeInTheDocument();

    // Set the approver for Team A via the row action menu + dialog.
    await user.click(screen.getByRole('button', { name: 'Actions for Team A' }));
    await user.click(await screen.findByText('Set approver'));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('combobox'));
    await user.click(await screen.findByText('Bob (bob@fleetent.test)'));
    await user.click(within(dialog).getByRole('button', { name: 'Save approver' }));

    await waitFor(() => {
      expect(screen.getByRole('row', { name: /Team A/ })).toHaveTextContent('Bob');
    });
  });

  it('keeps viewers in read-only mode', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'viewer@fleetent.test', id: 'viewer-1', role: 'viewer' })
      ),
      http.get(`${API_BASE_URL}/admin/tenancy/tenants`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/tenancy/teams`, () =>
        HttpResponse.json([
          {
            approver_user_id: null,
            created_at: '2026-06-21T10:05:00Z',
            id: 'team-a',
            name: 'Team A',
            tenant_id: 'tenant-a',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json([]))
    );

    renderTeamsPage();

    expect(await screen.findByRole('heading', { name: 'Teams' })).toBeInTheDocument();
    expect(await screen.findByText('Team A')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create team' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Actions for Team A' })).not.toBeInTheDocument();
  });
});

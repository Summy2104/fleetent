import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { TenancyPage } from '@/features/tenancy/page';
import { I18nProvider } from '@/i18n';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

type TenantRecord = {
  approver_user_id: string | null;
  created_at: string;
  id: string;
  name: string;
  status: string;
};

type TeamRecord = {
  approver_user_id: string | null;
  created_at: string;
  id: string;
  name: string;
  tenant_id: string;
};

type UserRecord = {
  email: string | null;
  id: string;
  must_reset: boolean;
  name: string;
  role: string;
  status: string;
  tenant_id?: string | null;
};

function renderTenancyPage(): void {
  render(
    <I18nProvider>
      <AuthProvider
        baseUrl={API_BASE_URL}
        initialToken="session-token"
      >
        <AppQueryProvider>
          <TenancyPage />
        </AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

describe('tenancy page', () => {
  it('lets admins list and create tenants, assign user tenancy, and set tenant approvers', async () => {
    const user = userEvent.setup();
    let tenants: TenantRecord[] = [
      {
        approver_user_id: null,
        created_at: '2026-06-21T10:00:00Z',
        id: 'tenant-a',
        name: 'Tenant A',
        status: 'active',
      },
    ];
    let teams: TeamRecord[] = [
      {
        approver_user_id: null,
        created_at: '2026-06-21T10:05:00Z',
        id: 'team-a',
        name: 'Team A',
        tenant_id: 'tenant-a',
      },
    ];
    let users: UserRecord[] = [
      {
        email: 'alice@fleetent.test',
        id: 'user-1',
        must_reset: false,
        name: 'Alice',
        role: 'viewer',
        status: 'active',
        tenant_id: null,
      },
      {
        email: 'bob@fleetent.test',
        id: 'user-2',
        must_reset: false,
        name: 'Bob',
        role: 'admin',
        status: 'active',
        tenant_id: null,
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/tenancy/tenants`, () => HttpResponse.json(tenants)),
      http.get(`${API_BASE_URL}/admin/tenancy/teams`, () => HttpResponse.json(teams)),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(users)),
      http.post(`${API_BASE_URL}/admin/tenancy/tenants`, async ({ request }) => {
        const body = (await request.json()) as { name: string; status: string };
        const created = {
          approver_user_id: null,
          created_at: '2026-06-21T10:10:00Z',
          id: 'tenant-b',
          name: body.name,
          status: body.status,
        };
        tenants = [...tenants, created];
        return HttpResponse.json(created, { status: 201 });
      }),
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
      http.post(`${API_BASE_URL}/admin/tenancy/users/user-1/tenant`, async ({ request }) => {
        expect(await request.json()).toEqual({ tenant_id: 'tenant-b' });
        users = users.map((item) => (item.id === 'user-1' ? { ...item, tenant_id: 'tenant-b' } : item));
        return HttpResponse.json({ status: 'ok', tenant_id: 'tenant-b', user_id: 'user-1' });
      }),
      http.patch(`${API_BASE_URL}/admin/tenancy/approvers/tenant-b`, async ({ request }) => {
        expect(await request.json()).toEqual({
          approver_user_id: 'user-2',
          entity_type: 'tenant',
        });
        tenants = tenants.map((tenant) =>
          tenant.id === 'tenant-b' ? { ...tenant, approver_user_id: 'user-2' } : tenant
        );
        return HttpResponse.json({ entity_type: 'tenant', id: 'tenant-b', status: 'ok' });
      }),
      http.patch(`${API_BASE_URL}/admin/tenancy/approvers/team-b`, async ({ request }) => {
        expect(await request.json()).toEqual({
          approver_user_id: 'user-2',
          entity_type: 'team',
        });
        teams = teams.map((team) =>
          team.id === 'team-b' ? { ...team, approver_user_id: 'user-2' } : team
        );
        return HttpResponse.json({ entity_type: 'team', id: 'team-b', status: 'ok' });
      }),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json([]))
    );

    renderTenancyPage();

    expect(await screen.findByRole('heading', { name: 'Tenancy' })).toBeInTheDocument();
    expect(await screen.findByTestId('tenant-card-tenant-a')).toHaveTextContent('Tenant A');
    await user.type(screen.getByLabelText('Tenant name'), 'Tenant B');
    await user.click(screen.getByRole('button', { name: 'Create tenant' }));
    expect(await screen.findByTestId('tenant-card-tenant-b')).toHaveTextContent('Tenant B');

    await user.selectOptions(screen.getByLabelText('Assign tenant for Alice'), 'tenant-b');
    await user.click(screen.getByRole('button', { name: 'Assign tenant for Alice' }));
    await waitFor(() => {
      expect(screen.getByText('Alice -> tenant-b')).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText('Tenant approver for tenant-b'), 'user-2');
    await user.click(screen.getByRole('button', { name: 'Save tenant approver for tenant-b' }));
    await waitFor(() => {
      const tenantCard = screen.getByTestId('tenant-card-tenant-b');
      expect(within(tenantCard).getByText('Approver: user-2')).toBeInTheDocument();
    });
  });

  it('keeps viewers in read-only mode', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'viewer@fleetent.test', id: 'viewer-1', role: 'viewer' })
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
      http.get(`${API_BASE_URL}/admin/users`, () =>
        HttpResponse.json([
          {
            email: 'alice@fleetent.test',
            id: 'user-1',
            must_reset: false,
            name: 'Alice',
            role: 'viewer',
            status: 'active',
            tenant_id: 'tenant-a',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json([]))
    );

    renderTenancyPage();

    expect(await screen.findByRole('heading', { name: 'Tenancy' })).toBeInTheDocument();
    expect(await screen.findByText('Viewer access is read-only.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create tenant' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Assign tenant for Alice' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save tenant approver for tenant-a' })).not.toBeInTheDocument();
  });
});

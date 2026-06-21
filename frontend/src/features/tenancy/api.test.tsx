import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import {
  useAssignUserTenantMutation,
  useCreateTeamMutation,
  useCreateTenantMutation,
  useSetApproverMutation,
  useTeamsQuery,
  useTenantsQuery,
} from '@/features/tenancy/api';
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

describe('tenancy api', () => {
  it('loads tenant and team lists and refreshes both after create, assign, and approver mutations', async () => {
    let tenantListRequests = 0;
    let teamListRequests = 0;
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

    server.use(
      http.get(`${API_BASE_URL}/admin/tenancy/tenants`, ({ request }) => {
        tenantListRequests += 1;
        expect(request.headers.get('authorization')).toBe('Session session-token');
        return HttpResponse.json(tenants);
      }),
      http.get(`${API_BASE_URL}/admin/tenancy/teams`, ({ request }) => {
        teamListRequests += 1;
        expect(request.headers.get('authorization')).toBe('Session session-token');
        return HttpResponse.json(teams);
      }),
      http.post(`${API_BASE_URL}/admin/tenancy/tenants`, async ({ request }) => {
        const body = (await request.json()) as {
          id?: string;
          name: string;
          status: string;
        };
        const created = {
          approver_user_id: null,
          created_at: '2026-06-21T10:10:00Z',
          id: body.id ?? 'tenant-b',
          name: body.name,
          status: body.status,
        };
        tenants = [...tenants, created];
        return HttpResponse.json(created, { status: 201 });
      }),
      http.post(`${API_BASE_URL}/admin/tenancy/teams`, async ({ request }) => {
        const body = (await request.json()) as {
          id?: string;
          name: string;
          tenant_id: string;
        };
        const created = {
          approver_user_id: null,
          created_at: '2026-06-21T10:11:00Z',
          id: body.id ?? 'team-b',
          name: body.name,
          tenant_id: body.tenant_id,
        };
        teams = [...teams, created];
        return HttpResponse.json(created, { status: 201 });
      }),
      http.post(`${API_BASE_URL}/admin/tenancy/users/user-1/tenant`, async ({ request }) => {
        expect(await request.json()).toEqual({ tenant_id: 'tenant-b' });
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
          approver_user_id: 'user-3',
          entity_type: 'team',
        });
        teams = teams.map((team) =>
          team.id === 'team-b' ? { ...team, approver_user_id: 'user-3' } : team
        );
        return HttpResponse.json({ entity_type: 'team', id: 'team-b', status: 'ok' });
      })
    );

    const wrapper = createWrapper();
    renderHook(() => useTenantsQuery(), { wrapper });
    renderHook(() => useTeamsQuery(), { wrapper });

    await waitFor(() => {
      expect(tenantListRequests).toBe(1);
      expect(teamListRequests).toBe(1);
    });

    const createTenant = renderHook(() => useCreateTenantMutation(), { wrapper });
    const createTeam = renderHook(() => useCreateTeamMutation(), { wrapper });
    const assignUserTenant = renderHook(() => useAssignUserTenantMutation(), { wrapper });
    const setTenantApprover = renderHook(() => useSetApproverMutation('tenant-b'), { wrapper });
    const setTeamApprover = renderHook(() => useSetApproverMutation('team-b'), { wrapper });

    let previousTenantListRequests = tenantListRequests;
    await createTenant.result.current.mutateAsync({ name: 'Tenant B', status: 'active' });
    await waitFor(() => {
      expect(tenantListRequests).toBeGreaterThan(previousTenantListRequests);
    });

    let previousTeamListRequests = teamListRequests;
    await createTeam.result.current.mutateAsync({ name: 'Team B', tenant_id: 'tenant-b' });
    await waitFor(() => {
      expect(teamListRequests).toBeGreaterThan(previousTeamListRequests);
    });

    previousTenantListRequests = tenantListRequests;
    previousTeamListRequests = teamListRequests;
    await assignUserTenant.result.current.mutateAsync({ tenant_id: 'tenant-b', user_id: 'user-1' });
    await waitFor(() => {
      expect(tenantListRequests).toBeGreaterThan(previousTenantListRequests);
      expect(teamListRequests).toBeGreaterThan(previousTeamListRequests);
    });

    previousTenantListRequests = tenantListRequests;
    await setTenantApprover.result.current.mutateAsync({
      approver_user_id: 'user-2',
      entity_type: 'tenant',
    });
    await waitFor(() => {
      expect(tenantListRequests).toBeGreaterThan(previousTenantListRequests);
    });

    previousTeamListRequests = teamListRequests;
    await setTeamApprover.result.current.mutateAsync({
      approver_user_id: 'user-3',
      entity_type: 'team',
    });
    await waitFor(() => {
      expect(teamListRequests).toBeGreaterThan(previousTeamListRequests);
    });
  });
});

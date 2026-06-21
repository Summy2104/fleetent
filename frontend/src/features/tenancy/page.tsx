import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  type TeamListItem,
  type TenantListItem,
  useAssignUserTenantMutation,
  useCreateTeamMutation,
  useCreateTenantMutation,
  useSetApproverMutation,
  useTeamsQuery,
  useTenantsQuery,
} from '@/features/tenancy/api';
import { useAdminApi } from '@/lib/api-client';

type AdminMe = {
  email: string;
  id: string;
  role: string;
};

type TenancyUser = {
  email: string | null;
  id: string;
  must_reset: boolean;
  name: string;
  role: string;
  status: string;
  tenant_id?: string | null;
};

function useAdminMeQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['admin-me'],
    queryFn: () => api.get<AdminMe>('/admin/me'),
  });
}

function useTenancyUsersQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['users'],
    queryFn: () => api.get<TenancyUser[]>('/admin/users'),
  });
}

function TenantCard({
  tenant,
  canWrite,
  onApproverChange,
  onSaveApprover,
  selectedApprover,
  users,
}: {
  tenant: TenantListItem;
  canWrite: boolean;
  onApproverChange: (value: string) => void;
  onSaveApprover: () => void;
  selectedApprover: string;
  users: TenancyUser[];
}): JSX.Element {
  return (
    <article
      className="rounded-2xl border bg-white/75 p-5"
      data-testid={`tenant-card-${tenant.id}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold">{tenant.name}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{tenant.id}</p>
          <p className="mt-1 text-sm text-muted-foreground">{tenant.status}</p>
          <p className="mt-2 text-sm">{`Approver: ${tenant.approver_user_id ?? 'Unassigned'}`}</p>
        </div>
        {canWrite ? (
          <div className="grid gap-2">
            <label className="grid gap-2 text-sm font-medium">
              {`Tenant approver for ${tenant.id}`}
              <select
                aria-label={`Tenant approver for ${tenant.id}`}
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => onApproverChange(event.target.value)}
                value={selectedApprover}
              >
                <option value="">None</option>
                {users.map((user) => (
                  <option
                    key={user.id}
                    value={user.id}
                  >
                    {user.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
              onClick={onSaveApprover}
              type="button"
            >
              {`Save tenant approver for ${tenant.id}`}
            </button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function TeamCard({
  canWrite,
  onApproverChange,
  onSaveApprover,
  selectedApprover,
  team,
  users,
}: {
  canWrite: boolean;
  onApproverChange: (value: string) => void;
  onSaveApprover: () => void;
  selectedApprover: string;
  team: TeamListItem;
  users: TenancyUser[];
}): JSX.Element {
  return (
    <article
      className="rounded-2xl border bg-white/75 p-5"
      data-testid={`team-card-${team.id}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold">{team.name}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{team.id}</p>
          <p className="mt-1 text-sm text-muted-foreground">{`Tenant: ${team.tenant_id}`}</p>
          <p className="mt-2 text-sm">{`Approver: ${team.approver_user_id ?? 'Unassigned'}`}</p>
        </div>
        {canWrite ? (
          <div className="grid gap-2">
            <label className="grid gap-2 text-sm font-medium">
              {`Team approver for ${team.id}`}
              <select
                aria-label={`Team approver for ${team.id}`}
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => onApproverChange(event.target.value)}
                value={selectedApprover}
              >
                <option value="">None</option>
                {users.map((user) => (
                  <option
                    key={user.id}
                    value={user.id}
                  >
                    {user.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
              onClick={onSaveApprover}
              type="button"
            >
              {`Save team approver for ${team.id}`}
            </button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function TenancyPage(): JSX.Element {
  const me = useAdminMeQuery();
  const users = useTenancyUsersQuery();
  const tenants = useTenantsQuery();
  const teams = useTeamsQuery();
  const createTenant = useCreateTenantMutation();
  const createTeam = useCreateTeamMutation();
  const assignUserTenant = useAssignUserTenantMutation();
  const [tenantName, setTenantName] = useState('');
  const [teamName, setTeamName] = useState('');
  const [teamTenantId, setTeamTenantId] = useState('');
  const [tenantAssignments, setTenantAssignments] = useState<Record<string, string>>({});
  const [tenantApprovers, setTenantApprovers] = useState<Record<string, string>>({});
  const [teamApprovers, setTeamApprovers] = useState<Record<string, string>>({});

  const canWrite = me.data ? me.data.role !== 'viewer' : false;
  const isViewer = me.data?.role === 'viewer';

  useEffect(() => {
    if (!tenants.data?.length) {
      setTeamTenantId('');
      return;
    }
    setTeamTenantId((current) => current || tenants.data[0].id);
  }, [tenants.data]);

  useEffect(() => {
    if (!users.data) {
      return;
    }
    setTenantAssignments((current) => {
      const next = { ...current };
      for (const user of users.data) {
        next[user.id] = current[user.id] ?? user.tenant_id ?? '';
      }
      return next;
    });
  }, [users.data]);

  useEffect(() => {
    if (!tenants.data) {
      return;
    }
    setTenantApprovers((current) => {
      const next = { ...current };
      for (const tenant of tenants.data) {
        next[tenant.id] = current[tenant.id] ?? tenant.approver_user_id ?? '';
      }
      return next;
    });
  }, [tenants.data]);

  useEffect(() => {
    if (!teams.data) {
      return;
    }
    setTeamApprovers((current) => {
      const next = { ...current };
      for (const team of teams.data) {
        next[team.id] = current[team.id] ?? team.approver_user_id ?? '';
      }
      return next;
    });
  }, [teams.data]);

  const createTenantDraft = async (): Promise<void> => {
    await createTenant.mutateAsync({ name: tenantName, status: 'active' });
    setTenantName('');
  };

  const createTeamDraft = async (): Promise<void> => {
    await createTeam.mutateAsync({ name: teamName, tenant_id: teamTenantId });
    setTeamName('');
  };

  return (
    <section className="grid gap-6">
      <header className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
          Native SPA
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Tenancy</h1>
        <p className="text-sm text-muted-foreground">
          Manage tenants, teams, user tenancy assignment, and approval ownership in the native
          React admin surface.
        </p>
        {isViewer ? <p className="text-sm text-muted-foreground">Viewer access is read-only.</p> : null}
      </header>

      {canWrite ? (
        <section className="grid gap-6 xl:grid-cols-2">
          <div className="rounded-2xl border bg-white/75 p-5">
            <h2 className="text-lg font-semibold">Create tenant</h2>
            <div className="mt-4 grid gap-4">
              <label className="grid gap-2 text-sm font-medium">
                Tenant name
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) => setTenantName(event.target.value)}
                  value={tenantName}
                />
              </label>
              <button
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
                onClick={() => void createTenantDraft()}
                type="button"
              >
                Create tenant
              </button>
            </div>
          </div>

          <div className="rounded-2xl border bg-white/75 p-5">
            <h2 className="text-lg font-semibold">Create team</h2>
            <div className="mt-4 grid gap-4">
              <label className="grid gap-2 text-sm font-medium">
                Team name
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) => setTeamName(event.target.value)}
                  value={teamName}
                />
              </label>
              <label className="grid gap-2 text-sm font-medium">
                Team tenant
                <select
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) => setTeamTenantId(event.target.value)}
                  value={teamTenantId}
                >
                  {tenants.data?.map((tenant) => (
                    <option
                      key={tenant.id}
                      value={tenant.id}
                    >
                      {tenant.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
                onClick={() => void createTeamDraft()}
                type="button"
              >
                Create team
              </button>
            </div>
          </div>
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Tenants</h2>
          {tenants.data?.map((tenant) => (
            <TenantActions
              canWrite={canWrite}
              key={tenant.id}
              tenant={tenant}
              tenantApprovers={tenantApprovers}
              users={users.data ?? []}
            />
          ))}
        </div>
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Teams</h2>
          {teams.data?.map((team) => (
            <TeamActions
              canWrite={canWrite}
              key={team.id}
              team={team}
              teamApprovers={teamApprovers}
              users={users.data ?? []}
            />
          ))}
        </div>
      </section>

      <section className="rounded-2xl border bg-white/75 p-5">
        <h2 className="text-xl font-semibold">User tenancy assignment</h2>
        <div className="mt-4 grid gap-4">
          {users.data?.map((user) => (
            <div
              className="rounded-xl border bg-white p-4"
              key={user.id}
            >
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="font-medium">{user.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {tenantAssignments[user.id] || user.tenant_id
                      ? `${user.name} -> ${tenantAssignments[user.id] || user.tenant_id}`
                      : 'Unassigned'}
                  </p>
                </div>
                {canWrite ? (
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="grid gap-2 text-sm font-medium">
                      {`Assign tenant for ${user.name}`}
                      <select
                        aria-label={`Assign tenant for ${user.name}`}
                        className="rounded-md border bg-white px-3 py-2"
                        onChange={(event) =>
                          setTenantAssignments((current) => ({
                            ...current,
                            [user.id]: event.target.value,
                          }))
                        }
                        value={tenantAssignments[user.id] ?? user.tenant_id ?? ''}
                      >
                        <option value="">None</option>
                        {tenants.data?.map((tenant) => (
                          <option
                            key={tenant.id}
                            value={tenant.id}
                          >
                            {tenant.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                      onClick={() =>
                        void assignUserTenant
                          .mutateAsync({
                            tenant_id: tenantAssignments[user.id] ?? '',
                            user_id: user.id,
                          })
                          .then(() => {
                            setTenantAssignments((current) => ({
                              ...current,
                              [user.id]: tenantAssignments[user.id] ?? '',
                            }));
                          })
                      }
                      type="button"
                    >
                      {`Assign tenant for ${user.name}`}
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </section>
    </section>
  );

  function TenantActions({
    canWrite,
    tenant,
    tenantApprovers,
    users,
  }: {
    canWrite: boolean;
    tenant: TenantListItem;
    tenantApprovers: Record<string, string>;
    users: TenancyUser[];
  }): JSX.Element {
    const setApprover = useSetApproverMutation(tenant.id);

    return (
      <TenantCard
        canWrite={canWrite}
        onApproverChange={(value) =>
          setTenantApprovers((current) => ({
            ...current,
            [tenant.id]: value,
          }))
        }
        onSaveApprover={() =>
          void setApprover.mutateAsync({
            approver_user_id: tenantApprovers[tenant.id] || null,
            entity_type: 'tenant',
          })
        }
        selectedApprover={tenantApprovers[tenant.id] ?? tenant.approver_user_id ?? ''}
        tenant={tenant}
        users={users}
      />
    );
  }

  function TeamActions({
    canWrite,
    team,
    teamApprovers,
    users,
  }: {
    canWrite: boolean;
    team: TeamListItem;
    teamApprovers: Record<string, string>;
    users: TenancyUser[];
  }): JSX.Element {
    const setApprover = useSetApproverMutation(team.id);

    return (
      <TeamCard
        canWrite={canWrite}
        onApproverChange={(value) =>
          setTeamApprovers((current) => ({
            ...current,
            [team.id]: value,
          }))
        }
        onSaveApprover={() =>
          void setApprover.mutateAsync({
            approver_user_id: teamApprovers[team.id] || null,
            entity_type: 'team',
          })
        }
        selectedApprover={teamApprovers[team.id] ?? team.approver_user_id ?? ''}
        team={team}
        users={users}
      />
    );
  }
}

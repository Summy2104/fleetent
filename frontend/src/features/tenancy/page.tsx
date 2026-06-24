import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Building2, Users } from 'lucide-react';

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
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';

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

const SELECT_CLASS = cn(
  'flex h-9 w-full appearance-none rounded-md border border-input bg-background/60 px-3 py-1 text-sm shadow-sm transition-colors',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50'
);

// ─────────────────────────── Tenant / Team cards ───────────────────────────

function TenantCard({
  tenant,
  canWrite,
  onApproverChange,
  onSaveApprover,
  selectedApprover,
  saving,
  users,
}: {
  tenant: TenantListItem;
  canWrite: boolean;
  onApproverChange: (value: string) => void;
  onSaveApprover: () => void;
  selectedApprover: string;
  saving: boolean;
  users: TenancyUser[];
}): JSX.Element {
  return (
    <Card data-testid={`tenant-card-${tenant.id}`}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <Building2 className="size-4 text-primary" /> {tenant.name}
          </span>
          <Badge variant={tenant.status === 'active' ? 'success' : 'secondary'}>{tenant.status}</Badge>
        </CardTitle>
        <CardDescription className="font-mono text-xs">{tenant.id}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {`Approver: ${tenant.approver_user_id ?? 'Unassigned'}`}
        </p>
        {canWrite ? (
          <>
            <Separator />
            <div className="grid gap-2">
              <Label htmlFor={`tenant-approver-${tenant.id}`} className="text-xs text-muted-foreground">
                {`Tenant approver for ${tenant.id}`}
              </Label>
              <select
                id={`tenant-approver-${tenant.id}`}
                aria-label={`Tenant approver for ${tenant.id}`}
                className={SELECT_CLASS}
                onChange={(event) => onApproverChange(event.target.value)}
                value={selectedApprover}
              >
                <option value="">None</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name}
                  </option>
                ))}
              </select>
              <Button variant="outline" disabled={saving} onClick={onSaveApprover}>
                {`Save tenant approver for ${tenant.id}`}
              </Button>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function TeamCard({
  team,
  canWrite,
  onApproverChange,
  onSaveApprover,
  selectedApprover,
  saving,
  users,
}: {
  team: TeamListItem;
  canWrite: boolean;
  onApproverChange: (value: string) => void;
  onSaveApprover: () => void;
  selectedApprover: string;
  saving: boolean;
  users: TenancyUser[];
}): JSX.Element {
  return (
    <Card data-testid={`team-card-${team.id}`}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="size-4 text-primary" /> {team.name}
        </CardTitle>
        <CardDescription className="space-y-0.5">
          <span className="block font-mono text-xs">{team.id}</span>
          <span className="block text-xs">{`Tenant: ${team.tenant_id}`}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {`Approver: ${team.approver_user_id ?? 'Unassigned'}`}
        </p>
        {canWrite ? (
          <>
            <Separator />
            <div className="grid gap-2">
              <Label htmlFor={`team-approver-${team.id}`} className="text-xs text-muted-foreground">
                {`Team approver for ${team.id}`}
              </Label>
              <select
                id={`team-approver-${team.id}`}
                aria-label={`Team approver for ${team.id}`}
                className={SELECT_CLASS}
                onChange={(event) => onApproverChange(event.target.value)}
                value={selectedApprover}
              >
                <option value="">None</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name}
                  </option>
                ))}
              </select>
              <Button variant="outline" disabled={saving} onClick={onSaveApprover}>
                {`Save team approver for ${team.id}`}
              </Button>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

// ─────────────────────────── Page ───────────────────────────

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

  const userList = users.data ?? [];
  const tenantList = tenants.data ?? [];

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Tenancy</h1>
        <p className="text-sm text-muted-foreground">
          Manage tenants, teams, user tenancy assignment, and approval ownership.
        </p>
        {isViewer ? (
          <p className="text-xs text-muted-foreground">Viewer access is read-only.</p>
        ) : null}
      </header>

      {canWrite ? (
        <section className="grid gap-6 xl:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Create tenant</CardTitle>
              <CardDescription>Tenants own teams, users, and approval routing.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="tenant-name">Tenant name</Label>
                <Input
                  id="tenant-name"
                  onChange={(event) => setTenantName(event.target.value)}
                  value={tenantName}
                />
              </div>
              <Button disabled={createTenant.isPending || !tenantName} onClick={() => void createTenantDraft()}>
                Create tenant
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Create team</CardTitle>
              <CardDescription>Teams group users within a tenant.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="team-name">Team name</Label>
                <Input
                  id="team-name"
                  onChange={(event) => setTeamName(event.target.value)}
                  value={teamName}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="team-tenant">Team tenant</Label>
                <select
                  id="team-tenant"
                  aria-label="Team tenant"
                  className={SELECT_CLASS}
                  onChange={(event) => setTeamTenantId(event.target.value)}
                  value={teamTenantId}
                >
                  {tenantList.map((tenant) => (
                    <option key={tenant.id} value={tenant.id}>
                      {tenant.name}
                    </option>
                  ))}
                </select>
              </div>
              <Button
                disabled={createTeam.isPending || !teamName || !teamTenantId}
                onClick={() => void createTeamDraft()}
              >
                Create team
              </Button>
            </CardContent>
          </Card>
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-foreground">Tenants</h2>
            <Badge variant="secondary">{tenantList.length}</Badge>
          </div>
          {tenantList.map((tenant) => (
            <TenantActions
              canWrite={canWrite}
              key={tenant.id}
              tenant={tenant}
              tenantApprovers={tenantApprovers}
              users={userList}
            />
          ))}
          {!tenantList.length ? (
            <div className="rounded-lg border border-dashed border-border py-10 text-center text-sm text-muted-foreground">
              No tenants yet.
            </div>
          ) : null}
        </div>
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-foreground">Teams</h2>
            <Badge variant="secondary">{teams.data?.length ?? 0}</Badge>
          </div>
          {teams.data?.map((team) => (
            <TeamActions
              canWrite={canWrite}
              key={team.id}
              team={team}
              teamApprovers={teamApprovers}
              users={userList}
            />
          ))}
          {teams.data && teams.data.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border py-10 text-center text-sm text-muted-foreground">
              No teams yet.
            </div>
          ) : null}
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>User tenancy assignment</CardTitle>
          <CardDescription>Assign each user to a tenant.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {userList.map((user) => (
            <div
              key={user.id}
              className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border bg-card px-4 py-3"
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">{user.name}</p>
                <p className="text-sm text-muted-foreground">
                  {tenantAssignments[user.id] || user.tenant_id
                    ? `${user.name} -> ${tenantAssignments[user.id] || user.tenant_id}`
                    : 'Unassigned'}
                </p>
              </div>
              {canWrite ? (
                <div className="flex flex-wrap items-end gap-3">
                  <div className="grid w-56 gap-1.5">
                    <Label
                      htmlFor={`assign-tenant-${user.id}`}
                      className="text-xs text-muted-foreground"
                    >
                      {`Assign tenant for ${user.name}`}
                    </Label>
                    <select
                      id={`assign-tenant-${user.id}`}
                      aria-label={`Assign tenant for ${user.name}`}
                      className={SELECT_CLASS}
                      onChange={(event) =>
                        setTenantAssignments((current) => ({
                          ...current,
                          [user.id]: event.target.value,
                        }))
                      }
                      value={tenantAssignments[user.id] ?? user.tenant_id ?? ''}
                    >
                      <option value="">None</option>
                      {tenantList.map((tenant) => (
                        <option key={tenant.id} value={tenant.id}>
                          {tenant.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    variant="outline"
                    disabled={assignUserTenant.isPending}
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
                  >
                    {`Assign tenant for ${user.name}`}
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
          {!userList.length ? (
            <p className="text-sm text-muted-foreground">No users to assign.</p>
          ) : null}
        </CardContent>
      </Card>
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
        saving={setApprover.isPending}
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
        saving={setApprover.isPending}
        selectedApprover={teamApprovers[team.id] ?? team.approver_user_id ?? ''}
        team={team}
        users={users}
      />
    );
  }
}

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Building2 } from 'lucide-react';

import {
  type TenantListItem,
  useAssignUserTenantMutation,
  useCreateTenantMutation,
  useSetApproverMutation,
  useTenantsQuery,
} from '@/features/tenancy/api';
import { useAdminApi } from '@/lib/api-client';
import { useT } from '@/i18n';
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
  const t = useT();
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
          {t('tenancy.approverLine', { value: tenant.approver_user_id ?? t('tenancy.unassigned') })}
        </p>
        {canWrite ? (
          <>
            <Separator />
            <div className="grid gap-2">
              <Label htmlFor={`tenant-approver-${tenant.id}`} className="text-xs text-muted-foreground">
                {t('tenancy.tenantApproverFor', { id: tenant.id })}
              </Label>
              <select
                id={`tenant-approver-${tenant.id}`}
                aria-label={t('tenancy.tenantApproverFor', { id: tenant.id })}
                className={SELECT_CLASS}
                onChange={(event) => onApproverChange(event.target.value)}
                value={selectedApprover}
              >
                <option value="">{t('tenancy.none')}</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name}
                  </option>
                ))}
              </select>
              <Button variant="outline" disabled={saving} onClick={onSaveApprover}>
                {t('tenancy.saveTenantApproverFor', { id: tenant.id })}
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
  const t = useT();
  const me = useAdminMeQuery();
  const users = useTenancyUsersQuery();
  const tenants = useTenantsQuery();
  const createTenant = useCreateTenantMutation();
  const assignUserTenant = useAssignUserTenantMutation();
  const [tenantName, setTenantName] = useState('');
  const [tenantAssignments, setTenantAssignments] = useState<Record<string, string>>({});
  const [tenantApprovers, setTenantApprovers] = useState<Record<string, string>>({});

  const canWrite = me.data ? me.data.role !== 'viewer' : false;
  const isViewer = me.data?.role === 'viewer';

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

  const createTenantDraft = async (): Promise<void> => {
    await createTenant.mutateAsync({ name: tenantName, status: 'active' });
    setTenantName('');
  };

  const userList = users.data ?? [];
  const tenantList = tenants.data ?? [];

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">{t('tenancy.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('tenancy.subtitle')}</p>
        {isViewer ? (
          <p className="text-xs text-muted-foreground">{t('tenancy.viewerReadOnly')}</p>
        ) : null}
      </header>

      {canWrite ? (
        <section className="grid gap-6">
          <Card>
            <CardHeader>
              <CardTitle>{t('tenancy.createTenant')}</CardTitle>
              <CardDescription>{t('tenancy.createTenantDesc')}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="tenant-name">{t('tenancy.tenantName')}</Label>
                <Input
                  id="tenant-name"
                  onChange={(event) => setTenantName(event.target.value)}
                  value={tenantName}
                />
              </div>
              <Button disabled={createTenant.isPending || !tenantName} onClick={() => void createTenantDraft()}>
                {t('tenancy.createTenant')}
              </Button>
            </CardContent>
          </Card>
        </section>
      ) : null}

      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-foreground">{t('tenancy.tenants')}</h2>
          <Badge variant="secondary">{tenantList.length}</Badge>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {tenantList.map((tenant, index) => (
            <div key={tenant.id} className={index < 2 ? 'xl:col-span-2' : undefined}>
              <TenantActions
                canWrite={canWrite}
                tenant={tenant}
                tenantApprovers={tenantApprovers}
                users={userList}
              />
            </div>
          ))}
        </div>
        {!tenantList.length ? (
          <div className="rounded-lg border border-dashed border-border py-10 text-center text-sm text-muted-foreground">
            {t('tenancy.noTenants')}
          </div>
        ) : null}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>{t('tenancy.userAssignment')}</CardTitle>
          <CardDescription>{t('tenancy.userAssignmentDesc')}</CardDescription>
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
                    ? t('tenancy.assignmentLine', {
                        name: user.name,
                        tenant: tenantAssignments[user.id] || user.tenant_id || '',
                      })
                    : t('tenancy.unassigned')}
                </p>
              </div>
              {canWrite ? (
                <div className="flex flex-wrap items-end gap-3">
                  <div className="grid w-56 gap-1.5">
                    <Label
                      htmlFor={`assign-tenant-${user.id}`}
                      className="text-xs text-muted-foreground"
                    >
                      {t('tenancy.assignTenantFor', { name: user.name })}
                    </Label>
                    <select
                      id={`assign-tenant-${user.id}`}
                      aria-label={t('tenancy.assignTenantFor', { name: user.name })}
                      className={SELECT_CLASS}
                      onChange={(event) =>
                        setTenantAssignments((current) => ({
                          ...current,
                          [user.id]: event.target.value,
                        }))
                      }
                      value={tenantAssignments[user.id] ?? user.tenant_id ?? ''}
                    >
                      <option value="">{t('tenancy.none')}</option>
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
                    {t('tenancy.assignTenantFor', { name: user.name })}
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
          {!userList.length ? (
            <p className="text-sm text-muted-foreground">{t('tenancy.noUsers')}</p>
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
}

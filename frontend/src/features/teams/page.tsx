import { type ReactNode, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Inbox, Plus } from 'lucide-react';

import {
  type TeamListItem,
  useCreateTeamMutation,
  useSetApproverMutation,
  useTeamsQuery,
  useTenantsQuery,
} from '@/features/tenancy/api';
import { useAdminApi } from '@/lib/api-client';
import { useT } from '@/i18n';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const APPROVER_NONE = '__none__';

type AdminMe = { email: string; id: string; role: string };
type TeamUser = { email: string | null; id: string; name: string };

function useAdminMeQuery() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

function useTeamUsersQuery() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['users'], queryFn: () => api.get<TeamUser[]>('/admin/users') });
}

function Th({ children, className }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <th className={cn('px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground', className)}>
      {children}
    </th>
  );
}

// ─────────────────────────── Create team dialog ───────────────────────────

function CreateTeamDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const t = useT();
  const create = useCreateTeamMutation();
  const tenants = useTenantsQuery();
  const [name, setName] = useState('');
  const [tenantId, setTenantId] = useState('');

  useEffect(() => {
    if (open && !tenantId && tenants.data?.length) {
      setTenantId(tenants.data[0].id);
    }
  }, [open, tenantId, tenants.data]);

  const submit = async (): Promise<void> => {
    await create.mutateAsync({ name: name.trim(), tenant_id: tenantId });
    setName('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('teams.createTeam')}</DialogTitle>
          <DialogDescription>{t('teams.createTeamDesc')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="team-name">{t('teams.name')}</Label>
            <Input id="team-name" value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label>{t('teams.tenant')}</Label>
            <Select value={tenantId || undefined} onValueChange={setTenantId}>
              <SelectTrigger>
                <SelectValue placeholder={t('teams.selectTenant')} />
              </SelectTrigger>
              <SelectContent>
                {(tenants.data ?? []).map((tenant) => (
                  <SelectItem key={tenant.id} value={tenant.id}>
                    {tenant.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('teams.cancel')}
          </Button>
          <Button disabled={!name.trim() || !tenantId || create.isPending} onClick={() => void submit()}>
            {t('teams.createTeam')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Set approver dialog ───────────────────────────

function SetApproverDialog({
  team,
  users,
  onOpenChange,
}: {
  team: TeamListItem | null;
  users: TeamUser[];
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const t = useT();
  const setApprover = useSetApproverMutation(team?.id ?? '');
  const [value, setValue] = useState(APPROVER_NONE);

  // Reset the picker to the team's current approver whenever the dialog opens for a team.
  useEffect(() => {
    setValue(team?.approver_user_id ?? APPROVER_NONE);
  }, [team]);

  const submit = async (): Promise<void> => {
    await setApprover.mutateAsync({
      approver_user_id: value === APPROVER_NONE ? null : value,
      entity_type: 'team',
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={Boolean(team)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('teams.approverTitle', { name: team?.name ?? '' })}</DialogTitle>
          <DialogDescription>{t('teams.approverDesc')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label>{t('teams.approver')}</Label>
          <Select value={value} onValueChange={setValue}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={APPROVER_NONE}>{t('teams.none')}</SelectItem>
              {users.map((user) => (
                <SelectItem key={user.id} value={user.id}>
                  {user.email
                    ? t('teams.userWithEmail', { name: user.name, email: user.email })
                    : user.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('teams.cancel')}
          </Button>
          <Button disabled={setApprover.isPending} onClick={() => void submit()}>
            {t('teams.saveApprover')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Row ───────────────────────────

function TeamRow({
  team,
  userName,
  canWrite,
  onSetApprover,
}: {
  team: TeamListItem;
  userName: (id: string | null) => string;
  canWrite: boolean;
  onSetApprover: (team: TeamListItem) => void;
}): JSX.Element {
  const t = useT();
  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3">
        <div className="text-sm font-semibold text-foreground">{team.name}</div>
        <div className="font-mono text-xs text-muted-foreground">{team.id}</div>
      </td>
      <td className="px-4 py-3 font-mono text-sm text-muted-foreground">{team.tenant_id}</td>
      <td className="px-4 py-3 text-sm text-foreground">{userName(team.approver_user_id)}</td>
      <td className="px-4 py-3 text-right">
        {canWrite ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary" size="sm" aria-label={t('teams.actionsFor', { name: team.name })}>
                {t('teams.actions')}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setTimeout(() => onSetApprover(team), 0)}>
                {t('teams.setApprover')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </td>
    </tr>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function TeamsPage(): JSX.Element {
  const t = useT();
  const me = useAdminMeQuery();
  const teams = useTeamsQuery();
  const users = useTeamUsersQuery();
  const [creating, setCreating] = useState(false);
  const [approverTeam, setApproverTeam] = useState<TeamListItem | null>(null);

  const canWrite = me.data?.role !== 'viewer';
  const list = teams.data ?? [];
  const userList = users.data ?? [];

  const userName = (id: string | null): string => {
    if (!id) return t('teams.unassigned');
    return userList.find((user) => user.id === id)?.name ?? id;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">{t('teams.title')}</h2>
          <Badge variant="secondary">{list.length}</Badge>
        </div>
        {canWrite ? (
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" /> {t('teams.createTeam')}
          </Button>
        ) : null}
      </div>

      <p className="text-sm text-muted-foreground">{t('teams.subtitle')}</p>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <Th>{t('teams.colTeam')}</Th>
              <Th>{t('teams.colTenant')}</Th>
              <Th>{t('teams.colApprover')}</Th>
              <Th className="text-right">{t('teams.colActions')}</Th>
            </tr>
          </thead>
          <tbody>
            {list.map((team) => (
              <TeamRow
                key={team.id}
                team={team}
                userName={userName}
                canWrite={canWrite}
                onSetApprover={setApproverTeam}
              />
            ))}
            {teams.data && list.length === 0 ? (
              <tr>
                <td colSpan={4}>
                  <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
                    <Inbox className="size-6 opacity-50" />
                    <span className="text-sm">{t('teams.noTeams')}</span>
                  </div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <CreateTeamDialog open={creating} onOpenChange={setCreating} />
      <SetApproverDialog
        team={approverTeam}
        users={userList}
        onOpenChange={(open) => !open && setApproverTeam(null)}
      />
    </div>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Copy, KeyRound, MoreVertical, Plus, RefreshCw, Trash2, UserPlus } from 'lucide-react';

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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  type ImUser,
  type UserListItem,
  useBindImUserMutation,
  useBlockImUserMutation,
  useBlockUserMutation,
  useCreateKeyMutation,
  useCreateUserMutation,
  useDeleteUserMutation,
  useImUsersQuery,
  useResetPasswordMutation,
  useRestoreImUserMutation,
  useRevokeKeyMutation,
  useRotateKeyMutation,
  useSetRoleMutation,
  useUnblockUserMutation,
  useUpdateUserMutation,
  useUserKeysQuery,
  useUsersQuery,
} from '@/features/users/api';

type AdminMe = { email: string; id: string; role: string };

const ROLES = ['viewer', 'admin', 'built_in_admin'];

function useAdminMeQuery() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

function parseScopes(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function initials(name: string): string {
  const parts = name.replace(/[-_]/g, ' ').split(' ').filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function statusVariant(status: string): 'success' | 'destructive' | 'secondary' {
  if (status === 'blocked') return 'destructive';
  if (status === 'active') return 'success';
  return 'secondary';
}

// ─────────────────────────── One-time secret dialog ───────────────────────────

function SecretDialog({
  secret,
  onDismiss,
}: {
  secret: string | null;
  onDismiss: () => void;
}): JSX.Element {
  const t = useT();
  return (
    <Dialog open={Boolean(secret)} onOpenChange={(open) => !open && onDismiss()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.newApiKey')}</DialogTitle>
          <DialogDescription>{t('users.newApiKeyDescription')}</DialogDescription>
        </DialogHeader>
        <div className="rounded-md border border-warning/40 bg-warning/10 p-4">
          <p className="break-all font-mono text-sm text-foreground">{secret}</p>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => secret && void navigator.clipboard?.writeText(secret)}
          >
            <Copy className="size-4" /> {t('users.copy')}
          </Button>
          <Button onClick={onDismiss}>{t('users.dismissNewSecret')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── User form dialog ───────────────────────────

type UserFormState = {
  email: string;
  name: string;
  password: string;
  resetPassword: string;
  role: string;
  mustReset: boolean;
};

function UserFormDialog({
  mode,
  open,
  onOpenChange,
  user,
  busy,
  onSubmit,
}: {
  mode: 'create' | 'edit';
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: UserListItem | null;
  busy: boolean;
  onSubmit: (state: UserFormState) => Promise<void>;
}): JSX.Element {
  const t = useT();
  const [state, setState] = useState<UserFormState>({
    email: '',
    name: '',
    password: '',
    resetPassword: '',
    role: 'viewer',
    mustReset: false,
  });

  useEffect(() => {
    if (!open) return;
    if (mode === 'edit' && user) {
      setState({
        email: user.email ?? '',
        name: user.name,
        password: '',
        resetPassword: '',
        role: user.role,
        mustReset: user.must_reset,
      });
    } else {
      setState({ email: '', name: '', password: '', resetPassword: '', role: 'viewer', mustReset: false });
    }
  }, [open, mode, user]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === 'create' ? t('users.createUser') : t('users.editUser', { name: user?.name ?? t('users.userFallback') })}</DialogTitle>
          <DialogDescription>
            {mode === 'create'
              ? t('users.createUserDescription')
              : t('users.editUserDescription')}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="user-name">{t('users.userName')}</Label>
            <Input
              id="user-name"
              value={state.name}
              onChange={(event) => setState((current) => ({ ...current, name: event.target.value }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="user-email">{t('users.email')}</Label>
            <Input
              id="user-email"
              value={state.email}
              onChange={(event) => setState((current) => ({ ...current, email: event.target.value }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="user-role">{t('users.role')}</Label>
            <Select
              value={state.role}
              onValueChange={(value) => setState((current) => ({ ...current, role: value }))}
            >
              <SelectTrigger id="user-role" aria-label={t('users.role')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((role) => (
                  <SelectItem key={role} value={role}>
                    {role}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <label className="flex items-center justify-between gap-3 text-sm font-medium">
            {t('users.mustResetPassword')}
            <Switch
              checked={state.mustReset}
              aria-label={t('users.mustResetPassword')}
              onCheckedChange={(checked) => setState((current) => ({ ...current, mustReset: checked }))}
            />
          </label>
          {mode === 'create' ? (
            <div className="grid gap-2">
              <Label htmlFor="user-password">{t('users.password')}</Label>
              <Input
                id="user-password"
                type="password"
                value={state.password}
                onChange={(event) => setState((current) => ({ ...current, password: event.target.value }))}
              />
            </div>
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="user-reset-password">{t('users.resetPassword')}</Label>
              <Input
                id="user-reset-password"
                type="password"
                value={state.resetPassword}
                onChange={(event) =>
                  setState((current) => ({ ...current, resetPassword: event.target.value }))
                }
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('users.cancel')}
          </Button>
          <Button disabled={busy || !state.name} onClick={() => void onSubmit(state)}>
            {mode === 'create' ? t('users.createUser') : t('users.saveChanges')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Block user dialog ───────────────────────────

function BlockUserDialog({
  user,
  open,
  onOpenChange,
}: {
  user: UserListItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const t = useT();
  const blockUser = useBlockUserMutation(user.id);
  const [reason, setReason] = useState('');

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setReason('');
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.blockUser', { name: user.name })}</DialogTitle>
          <DialogDescription>{t('users.blockUserDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="block-reason">{t('users.blockReason')}</Label>
          <Input id="block-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('users.cancel')}
          </Button>
          <Button
            variant="destructive"
            onClick={() =>
              void blockUser.mutateAsync({ reason }).then(() => {
                setReason('');
                onOpenChange(false);
              })
            }
          >
            {t('users.block')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── User row ───────────────────────────

function UserRow({
  user,
  selected,
  canWrite,
  onSelect,
  onEdit,
  onManageKeys,
}: {
  user: UserListItem;
  selected: boolean;
  canWrite: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onManageKeys: () => void;
}): JSX.Element {
  const t = useT();
  const unblockUser = useUnblockUserMutation(user.id);
  const deleteUser = useDeleteUserMutation(user.id);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [blockOpen, setBlockOpen] = useState(false);

  return (
    <div
      data-testid={`user-card-${user.id}`}
      className={cn(
        'group flex items-center gap-4 rounded-lg border px-4 py-3 transition-colors',
        selected ? 'border-primary/40 bg-primary/[0.04]' : 'border-border bg-card hover:bg-accent/40'
      )}
    >
      <button type="button" className="flex min-w-0 flex-1 items-center gap-4 text-left" onClick={onSelect}>
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-secondary text-xs font-semibold text-foreground">
          {initials(user.name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold text-foreground">{user.name}</span>
            <Badge variant="outline">{user.role}</Badge>
            <Badge variant={statusVariant(user.status)}>{user.status}</Badge>
          </span>
          <span className="mt-0.5 block truncate text-sm text-muted-foreground">
            {user.email ?? t('users.noEmail')}
          </span>
        </span>
      </button>

      {canWrite ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={t('users.actionsFor', { name: user.name })}>
              <MoreVertical className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={onEdit}>{t('users.edit')}</DropdownMenuItem>
            {user.status === 'blocked' ? (
              <DropdownMenuItem onSelect={() => void unblockUser.mutateAsync()}>{t('users.unblock')}</DropdownMenuItem>
            ) : (
              <DropdownMenuItem onSelect={() => setBlockOpen(true)}>{t('users.block')}</DropdownMenuItem>
            )}
            <DropdownMenuItem onSelect={() => setTimeout(onManageKeys, 0)}>{t('users.apiKeys')}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={() => setConfirmDelete(true)}>
              <Trash2 /> {t('users.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}

      <BlockUserDialog user={user} open={blockOpen} onOpenChange={setBlockOpen} />

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.deleteUserConfirmTitle', { name: user.name })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('users.deleteUserConfirmDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('users.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void deleteUser.mutateAsync()}>{t('users.delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ─────────────────────────── Issue key dialog ───────────────────────────

function IssueKeyDialog({
  userId,
  userName,
  open,
  onOpenChange,
  onSecret,
}: {
  userId: string;
  userName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSecret: (secret: string) => void;
}): JSX.Element {
  const t = useT();
  const createKey = useCreateKeyMutation(userId);
  const [note, setNote] = useState('');
  const [scope, setScope] = useState('*');

  const reset = (): void => {
    setNote('');
    setScope('*');
  };

  const onIssue = async (): Promise<void> => {
    const result = await createKey.mutateAsync({
      note: note || undefined,
      scope: parseScopes(scope),
    });
    onSecret(result.plaintext);
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.issueKeyFor', { name: userName })}</DialogTitle>
          <DialogDescription>{t('users.issueKeyDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="key-note">{t('users.keyNote')}</Label>
            <Input id="key-note" value={note} onChange={(event) => setNote(event.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="key-scope">{t('users.keyScope')}</Label>
            <Input id="key-scope" value={scope} onChange={(event) => setScope(event.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('users.cancel')}
          </Button>
          <Button disabled={createKey.isPending} onClick={() => void onIssue()}>
            {t('users.issueKey')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── API keys dialog ───────────────────────────

function KeysDialog({
  user,
  open,
  onOpenChange,
  canWrite,
  onSecret,
}: {
  user: UserListItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canWrite: boolean;
  onSecret: (secret: string) => void;
}): JSX.Element {
  const t = useT();
  const userKeys = useUserKeysQuery(user.id);
  const rotateKey = useRotateKeyMutation(user.id);
  const revokeKey = useRevokeKeyMutation(user.id);
  const [issueOpen, setIssueOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<{ id: number; masked: string } | null>(null);

  const onRotate = async (): Promise<void> => {
    const result = await rotateKey.mutateAsync();
    onSecret(result.api_key_plaintext_once);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="size-4 text-primary" /> {t('users.apiKeysFor', { name: user.name })}
          </DialogTitle>
          <DialogDescription>{t('users.apiKeysDescription')}</DialogDescription>
        </DialogHeader>
        {canWrite ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setIssueOpen(true)}>
              <KeyRound className="size-4" /> {t('users.issueKey')}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => void onRotate()}>
              <RefreshCw className="size-4" /> {t('users.rotateKey')}
            </Button>
          </div>
        ) : null}

      <div className="space-y-2">
        {(userKeys.data ?? []).map((key) => (
          <div
            key={key.id}
            className="flex items-center justify-between gap-4 rounded-md border border-border bg-secondary/40 px-4 py-3"
          >
            <div className="flex min-w-0 items-center gap-3">
              <span className={`truncate font-mono text-sm ${key.revoked_at ? 'text-muted-foreground' : ''}`}>
                {key.masked}
              </span>
              <span className="shrink-0 font-mono text-xs text-muted-foreground">{key.prefix}</span>
              {key.revoked_at ? <Badge variant="secondary">{t('users.revoked')}</Badge> : null}
            </div>
            {canWrite && !key.revoked_at ? (
              <Button
                size="sm"
                variant="ghost"
                aria-label={t('users.revokeKeyAria', { id: key.id })}
                onClick={() => setRevokeTarget({ id: key.id, masked: key.masked })}
              >
                <Trash2 className="size-4" /> {t('users.revoke')}
              </Button>
            ) : null}
          </div>
        ))}
        {userKeys.data && userKeys.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('users.noApiKeys')}</p>
        ) : null}
      </div>

      {canWrite ? (
        <IssueKeyDialog
          userId={user.id}
          userName={user.name}
          open={issueOpen}
          onOpenChange={setIssueOpen}
          onSecret={onSecret}
        />
      ) : null}

      <AlertDialog open={Boolean(revokeTarget)} onOpenChange={(open) => !open && setRevokeTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.revokeKeyConfirmTitle', { masked: revokeTarget?.masked ?? '' })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('users.revokeKeyConfirmDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('users.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (revokeTarget) void revokeKey.mutateAsync(revokeTarget.id);
                setRevokeTarget(null);
              }}
            >
              {revokeTarget ? t('users.revokeKeyAria', { id: revokeTarget.id }) : t('users.revoke')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── IM identity row ───────────────────────────

function ImUserRow({
  imUser,
  users,
  canWrite,
}: {
  imUser: ImUser;
  users: UserListItem[];
  canWrite: boolean;
}): JSX.Element {
  const t = useT();
  const bindImUser = useBindImUserMutation(imUser.id);
  const blockImUser = useBlockImUserMutation(imUser.id);
  const restoreImUser = useRestoreImUserMutation(imUser.id);

  const [boundUser, setBoundUser] = useState(imUser.user_id);
  const [reason, setReason] = useState('');

  return (
    <div
      data-testid={`im-user-${imUser.id}`}
      className="space-y-4 rounded-lg border border-border bg-card p-4"
    >
      <div className="space-y-2">
        <p className="font-medium text-foreground">{imUser.platform_user_id}</p>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="secondary">{imUser.user_id}</Badge>
          <Badge variant={statusVariant(imUser.status)}>{imUser.status}</Badge>
          <Badge variant={imUser.allowed ? 'success' : 'destructive'}>
            {imUser.allowed ? t('users.allowed') : t('users.notAllowed')}
          </Badge>
        </div>
      </div>

      {canWrite ? (
        <div className="grid gap-3">
          <div className="grid gap-2">
            <Label htmlFor={`im-bind-${imUser.id}`}>{t('users.bindToUser')}</Label>
            <Select
              value={boundUser}
              onValueChange={(value) => {
                setBoundUser(value);
                void bindImUser.mutateAsync({ user_id: value });
              }}
            >
              <SelectTrigger id={`im-bind-${imUser.id}`} aria-label={t('users.bindToUser')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {users.map((user) => (
                  <SelectItem key={user.id} value={user.id}>
                    {user.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor={`im-reason-${imUser.id}`}>{t('users.imReason')}</Label>
            <Input
              id={`im-reason-${imUser.id}`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant={imUser.allowed ? 'destructive' : 'secondary'}
              onClick={() =>
                void (imUser.allowed
                  ? blockImUser.mutateAsync({ reason })
                  : restoreImUser.mutateAsync({ reason }))
              }
            >
              {imUser.allowed ? t('users.blockIdentity') : t('users.restoreIdentity')}
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">{t('users.viewerReadOnly')}</p>
      )}
    </div>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function UsersPage(): JSX.Element {
  const t = useT();
  const me = useAdminMeQuery();
  const users = useUsersQuery();
  const imUsers = useImUsersQuery();

  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create');
  const [formOpen, setFormOpen] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [keysForUserId, setKeysForUserId] = useState<string | null>(null);

  const canWrite = me.data?.role !== 'viewer';

  useEffect(() => {
    if (!users.data?.length) {
      setSelectedUserId(null);
      return;
    }
    if (!selectedUserId || !users.data.some((item) => item.id === selectedUserId)) {
      setSelectedUserId(users.data[0].id);
    }
  }, [selectedUserId, users.data]);

  const selectedUser = useMemo(
    () => users.data?.find((item) => item.id === selectedUserId) ?? null,
    [users.data, selectedUserId]
  );

  const updateUser = useUpdateUserMutation(selectedUserId ?? '');
  const setRole = useSetRoleMutation(selectedUserId ?? '');
  const resetPassword = useResetPasswordMutation(selectedUserId ?? '');
  const createUser = useCreateUserMutation();

  const submitForm = async (state: {
    email: string;
    name: string;
    password: string;
    resetPassword: string;
    role: string;
    mustReset: boolean;
  }): Promise<void> => {
    if (formMode === 'create') {
      await createUser.mutateAsync({
        email: state.email,
        must_reset: state.mustReset,
        name: state.name,
        password: state.password,
        role: state.role,
      });
      setFormOpen(false);
      return;
    }
    if (!selectedUser) return;

    if (selectedUser.name !== state.name || (selectedUser.email ?? '') !== state.email) {
      await updateUser.mutateAsync({ email: state.email, name: state.name });
    }
    if (selectedUser.role !== state.role) {
      await setRole.mutateAsync({ role: state.role });
    }
    if (state.resetPassword.trim()) {
      await resetPassword.mutateAsync({ new_password: state.resetPassword });
    }
    setFormOpen(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">{t('users.title')}</h2>
          <Badge variant="secondary">{users.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <Button
            onClick={() => {
              setFormMode('create');
              setFormOpen(true);
            }}
          >
            <UserPlus className="size-4" /> {t('users.createUser')}
          </Button>
        ) : null}
      </div>

      <p className="max-w-2xl text-sm text-muted-foreground">
        {t('users.pageDescription')}
      </p>

      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users">{t('users.tabUsers')}</TabsTrigger>
          <TabsTrigger value="im">{t('users.tabImIdentities')}</TabsTrigger>
        </TabsList>

        <TabsContent value="users">
          <div className="space-y-2">
            {users.data?.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                selected={selectedUserId === user.id}
                canWrite={canWrite}
                onSelect={() => setSelectedUserId(user.id)}
                onEdit={() => {
                  setSelectedUserId(user.id);
                  setFormMode('edit');
                  setFormOpen(true);
                }}
                onManageKeys={() => setKeysForUserId(user.id)}
              />
            ))}
            {users.data && users.data.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
                {t('users.emptyUsers')}
              </div>
            ) : null}
          </div>
        </TabsContent>

        <TabsContent value="im">
          <div className="space-y-4">
            {imUsers.data?.map((imUser) => (
              <ImUserRow
                key={imUser.id}
                imUser={imUser}
                users={users.data ?? []}
                canWrite={canWrite}
              />
            ))}
            {imUsers.data && imUsers.data.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
                {t('users.emptyImIdentities')}
              </div>
            ) : null}
          </div>
        </TabsContent>
      </Tabs>

      {canWrite ? (
        <UserFormDialog
          mode={formMode}
          open={formOpen}
          onOpenChange={setFormOpen}
          user={formMode === 'edit' ? selectedUser : null}
          busy={createUser.isPending || updateUser.isPending}
          onSubmit={submitForm}
        />
      ) : null}

      {keysForUserId
        ? (() => {
            const keysUser = users.data?.find((item) => item.id === keysForUserId);
            return keysUser ? (
              <KeysDialog
                user={keysUser}
                open
                onOpenChange={(open) => !open && setKeysForUserId(null)}
                canWrite={canWrite}
                onSecret={setSecret}
              />
            ) : null;
          })()
        : null}

      <SecretDialog secret={secret} onDismiss={() => setSecret(null)} />
    </div>
  );
}

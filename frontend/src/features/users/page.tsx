import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Copy, KeyRound, MoreVertical, Plus, RefreshCw, Trash2, UserPlus } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import { SimpleSelect } from '@/components/base/simple-select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import {
  type ImUser,
  type UserListItem,
  useBindImUserMutation,
  useBlockImUserMutation,
  useBlockUserMutation,
  useCreateImMappingMutation,
  useCreateKeyMutation,
  useCreateServicePrincipalMutation,
  useCreateUserMutation,
  useDeleteImUserMutation,
  useDeleteUserMutation,
  useImIdentityFieldsQuery,
  useImUsersQuery,
  useInitiateLinkMutation,
  useResetPasswordMutation,
  useRestoreImUserMutation,
  useRevokeKeyMutation,
  useRotateKeyMutation,
  useSetRoleMutation,
  useUnblockUserMutation,
  useUnlinkIdentityMutation,
  useUpdateImUserMutation,
  useUpdateUserMutation,
  useUserKeysQuery,
  useUsersQuery,
} from '@/features/users/api'
import { useT } from '@/i18n'
import { describeApiError, useAdminApi } from '@/lib/api-client'
import { cn } from '@/lib/utils'

type AdminMe = { email: string; id: string; role: string }

const ROLES = ['viewer', 'admin', 'built_in_admin']
const IM_PLATFORMS = ['slack', 'telegram', 'whatsapp']

function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

function parseScopes(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function initials(name: string): string {
  const parts = name.replace(/[-_]/g, ' ').split(' ').filter(Boolean)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
}

function statusVariant(status: string): 'success' | 'destructive' | 'secondary' {
  if (status === 'blocked') return 'destructive'
  if (status === 'active') return 'success'
  return 'secondary'
}

// ─────────────────────────── One-time secret dialog ───────────────────────────

function SecretDialog({ secret, onDismiss }: { secret: string | null; onDismiss: () => void }): JSX.Element {
  const t = useT()
  return (
    <Dialog onOpenChange={(open) => !open && onDismiss()} open={Boolean(secret)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.newApiKey')}</DialogTitle>
          <DialogDescription>{t('users.newApiKeyDescription')}</DialogDescription>
        </DialogHeader>
        <div className="rounded-md border border-warning/40 bg-warning/10 p-4">
          <p className="break-all font-mono text-foreground text-sm">{secret}</p>
        </div>
        <DialogFooter>
          <Button onClick={() => secret && void navigator.clipboard?.writeText(secret)} variant="outline">
            <Copy className="size-4" /> {t('users.copy')}
          </Button>
          <Button onClick={onDismiss}>{t('users.dismissNewSecret')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── User form dialog ───────────────────────────

type UserFormState = {
  email: string
  name: string
  password: string
  resetPassword: string
  role: string
  mustReset: boolean
}

function UserFormDialog({
  mode,
  open,
  onOpenChange,
  user,
  busy,
  onSubmit,
}: {
  mode: 'create' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  user: UserListItem | null
  busy: boolean
  onSubmit: (state: UserFormState) => Promise<void>
}): JSX.Element {
  const t = useT()
  const [state, setState] = useState<UserFormState>({
    email: '',
    name: '',
    password: '',
    resetPassword: '',
    role: 'viewer',
    mustReset: false,
  })

  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && user) {
      setState({
        email: user.email ?? '',
        name: user.name,
        password: '',
        resetPassword: '',
        role: user.role,
        mustReset: user.must_reset,
      })
    } else {
      setState({ email: '', name: '', password: '', resetPassword: '', role: 'viewer', mustReset: false })
    }
  }, [open, mode, user])

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {mode === 'create'
              ? t('users.createUser')
              : t('users.editUser', { name: user?.name ?? t('users.userFallback') })}
          </DialogTitle>
          <DialogDescription>
            {mode === 'create' ? t('users.createUserDescription') : t('users.editUserDescription')}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="user-name">{t('users.userName')}</Label>
            <Input
              id="user-name"
              onChange={(event) => setState((current) => ({ ...current, name: event.target.value }))}
              value={state.name}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="user-email">{t('users.email')}</Label>
            <Input
              id="user-email"
              onChange={(event) => setState((current) => ({ ...current, email: event.target.value }))}
              value={state.email}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="user-role">{t('users.role')}</Label>
            <SimpleSelect
              onValueChange={(value) => setState((current) => ({ ...current, role: value ?? '' }))}
              options={ROLES.map((role) => ({ value: role, label: role }))}
              triggerAriaLabel={t('users.role')}
              triggerId="user-role"
              value={state.role}
            />
          </div>
          <div className="flex items-center justify-between gap-3 font-medium text-sm">
            <Label htmlFor="user-must-reset">{t('users.mustResetPassword')}</Label>
            <Switch
              checked={state.mustReset}
              id="user-must-reset"
              onCheckedChange={(checked) => setState((current) => ({ ...current, mustReset: checked }))}
            />
          </div>
          {mode === 'create' ? (
            <div className="grid gap-2">
              <Label htmlFor="user-password">{t('users.password')}</Label>
              <Input
                id="user-password"
                onChange={(event) => setState((current) => ({ ...current, password: event.target.value }))}
                type="password"
                value={state.password}
              />
            </div>
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="user-reset-password">{t('users.resetPassword')}</Label>
              <Input
                id="user-reset-password"
                onChange={(event) => setState((current) => ({ ...current, resetPassword: event.target.value }))}
                type="password"
                value={state.resetPassword}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button
            disabled={
              busy ||
              !state.name ||
              // A platform user logs in by email + password; without both, the
              // created account can never sign in. Edit mode keeps its own rules.
              (mode === 'create' && (!state.email.trim() || !state.password))
            }
            onClick={() => void onSubmit(state)}
          >
            {mode === 'create' ? t('users.createUser') : t('users.saveChanges')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CreateServicePrincipalDialog({
  open,
  onOpenChange,
  onSecret,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSecret: (secret: string) => void
}): JSX.Element {
  const t = useT()
  const createServicePrincipal = useCreateServicePrincipalMutation()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const reset = (): void => {
    setName('')
    setError(null)
  }

  const submit = async (): Promise<void> => {
    setError(null)
    try {
      const result = await createServicePrincipal.mutateAsync({ name: name.trim() })
      onSecret(result.api_key_plaintext_once)
      reset()
      onOpenChange(false)
    } catch (exc) {
      setError(describeApiError(exc))
    }
  }

  return (
    <Dialog
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
      open={open}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.createServicePrincipal')}</DialogTitle>
          <DialogDescription>{t('users.createServicePrincipalDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="service-principal-name">{t('users.servicePrincipalName')}</Label>
          <Input id="service-principal-name" onChange={(event) => setName(event.target.value)} value={name} />
        </div>
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button disabled={!name.trim() || createServicePrincipal.isPending} onClick={() => void submit()}>
            {t('users.createServicePrincipal')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Block user dialog ───────────────────────────

function BlockUserDialog({
  user,
  open,
  onOpenChange,
}: {
  user: UserListItem
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const blockUser = useBlockUserMutation(user.id)
  const [reason, setReason] = useState('')

  return (
    <Dialog
      onOpenChange={(next) => {
        if (!next) setReason('')
        onOpenChange(next)
      }}
      open={open}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.blockUser', { name: user.name })}</DialogTitle>
          <DialogDescription>{t('users.blockUserDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="block-reason">{t('users.blockReason')}</Label>
          <Input id="block-reason" onChange={(event) => setReason(event.target.value)} value={reason} />
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button
            onClick={() =>
              void blockUser.mutateAsync({ reason }).then(() => {
                setReason('')
                onOpenChange(false)
              })
            }
            variant="destructive"
          >
            {t('users.block')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── User row ───────────────────────────

function UserRow({
  user,
  selected,
  canWrite,
  onClick,
  onEdit,
  onManageKeys,
}: {
  user: UserListItem
  selected: boolean
  canWrite: boolean
  onClick: () => void
  onEdit: () => void
  onManageKeys: () => void
}): JSX.Element {
  const t = useT()
  const unblockUser = useUnblockUserMutation(user.id)
  const deleteUser = useDeleteUserMutation(user.id)
  const initiateLink = useInitiateLinkMutation()
  const unlinkIdentity = useUnlinkIdentityMutation()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [blockOpen, setBlockOpen] = useState(false)
  const [linkCode, setLinkCode] = useState<{ code: string; expires_at: string } | null>(null)
  const [unlinkOpen, setUnlinkOpen] = useState(false)
  const [unlinkPlatform, setUnlinkPlatform] = useState('')
  const [unlinkExternalId, setUnlinkExternalId] = useState('')

  const resetUnlink = (): void => {
    setUnlinkPlatform('')
    setUnlinkExternalId('')
  }

  const submitUnlink = async (): Promise<void> => {
    await unlinkIdentity.mutateAsync({
      platform: unlinkPlatform.trim(),
      platform_user_id: unlinkExternalId.trim(),
    })
    resetUnlink()
    setUnlinkOpen(false)
  }

  return (
    <div
      className={cn(
        'group flex items-center gap-4 rounded-lg border px-4 py-3 transition-colors',
        selected ? 'border-primary/40 bg-primary/4' : 'border-border bg-card hover:bg-accent/40'
      )}
      data-testid={`user-card-${user.id}`}
    >
      <button className="flex min-w-0 flex-1 items-center gap-4 text-left" onClick={onClick} type="button">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-secondary font-semibold text-foreground text-xs">
          {initials(user.name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="truncate font-semibold text-foreground text-sm">{user.name}</span>
            <Badge variant="outline">{user.role}</Badge>
            <Badge variant={statusVariant(user.status)}>{user.status}</Badge>
          </span>
          <span className="mt-0.5 block truncate text-muted-foreground text-sm">
            {user.email ?? t('users.noEmail')}
          </span>
        </span>
      </button>

      {canWrite ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button aria-label={t('users.actionsFor', { name: user.name })} size="icon" variant="ghost">
                <MoreVertical className="size-4" />
              </Button>
            }
          />
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onEdit}>{t('users.edit')}</DropdownMenuItem>
            {user.status === 'blocked' ? (
              <DropdownMenuItem onClick={() => void unblockUser.mutateAsync()}>{t('users.unblock')}</DropdownMenuItem>
            ) : (
              <DropdownMenuItem onClick={() => setBlockOpen(true)}>{t('users.block')}</DropdownMenuItem>
            )}
            <DropdownMenuItem
              onClick={() => {
                void initiateLink.mutateAsync().then(setLinkCode)
              }}
            >
              {t('users.initiateChannelLink')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(() => setUnlinkOpen(true), 0)}>
              {t('users.unlinkChannelIdentity')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(onManageKeys, 0)}>{t('users.apiKeys')}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setConfirmDelete(true)} variant="destructive">
              <Trash2 /> {t('users.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}

      <BlockUserDialog onOpenChange={setBlockOpen} open={blockOpen} user={user} />

      <Dialog onOpenChange={(open) => !open && setLinkCode(null)} open={Boolean(linkCode)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('users.channelLinkCode')}</DialogTitle>
            <DialogDescription>{t('users.channelLinkCodeDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 rounded-md border border-warning/40 bg-warning/10 p-4">
            <p className="break-all font-mono text-foreground text-sm">{linkCode?.code}</p>
            <p className="text-muted-foreground text-sm">
              {t('users.channelLinkExpiresAt')}: {linkCode?.expires_at}
            </p>
          </div>
          <DialogFooter>
            <Button onClick={() => setLinkCode(null)}>{t('users.dismiss')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        onOpenChange={(next) => {
          if (!next) resetUnlink()
          setUnlinkOpen(next)
        }}
        open={unlinkOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('users.unlinkChannelIdentity')}</DialogTitle>
            <DialogDescription>{t('users.unlinkChannelIdentityDescription')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor={`unlink-platform-${user.id}`}>{t('users.imPlatform')}</Label>
              <Input
                id={`unlink-platform-${user.id}`}
                onChange={(event) => setUnlinkPlatform(event.target.value)}
                value={unlinkPlatform}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor={`unlink-external-id-${user.id}`}>{t('users.imExternalId')}</Label>
              <Input
                id={`unlink-external-id-${user.id}`}
                onChange={(event) => setUnlinkExternalId(event.target.value)}
                value={unlinkExternalId}
              />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setUnlinkOpen(false)} variant="outline">
              {t('users.cancel')}
            </Button>
            <Button
              disabled={!unlinkPlatform.trim() || !unlinkExternalId.trim() || unlinkIdentity.isPending}
              onClick={() => void submitUnlink()}
              variant="destructive"
            >
              {t('users.unlinkChannelIdentity')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.deleteUserConfirmTitle', { name: user.name })}</AlertDialogTitle>
            <AlertDialogDescription>{t('users.deleteUserConfirmDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('users.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void deleteUser.mutateAsync()}>{t('users.delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

// ─────────────────────────── Issue key dialog ───────────────────────────

function IssueKeyDialog({
  userId,
  userName,
  open,
  onOpenChange,
  onSecret,
}: {
  userId: string
  userName: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onSecret: (secret: string) => void
}): JSX.Element {
  const t = useT()
  const createKey = useCreateKeyMutation(userId)
  const [note, setNote] = useState('')
  const [scope, setScope] = useState('*')

  const reset = (): void => {
    setNote('')
    setScope('*')
  }

  const onIssue = async (): Promise<void> => {
    const result = await createKey.mutateAsync({
      note: note || undefined,
      scope: parseScopes(scope),
    })
    onSecret(result.plaintext)
    reset()
    onOpenChange(false)
  }

  return (
    <Dialog
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
      open={open}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.issueKeyFor', { name: userName })}</DialogTitle>
          <DialogDescription>{t('users.issueKeyDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="key-note">{t('users.keyNote')}</Label>
            <Input id="key-note" onChange={(event) => setNote(event.target.value)} value={note} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="key-scope">{t('users.keyScope')}</Label>
            <Input id="key-scope" onChange={(event) => setScope(event.target.value)} value={scope} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button disabled={createKey.isPending} onClick={() => void onIssue()}>
            {t('users.issueKey')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── API keys dialog ───────────────────────────

function KeysDialog({
  user,
  open,
  onOpenChange,
  canWrite,
  onSecret,
}: {
  user: UserListItem
  open: boolean
  onOpenChange: (open: boolean) => void
  canWrite: boolean
  onSecret: (secret: string) => void
}): JSX.Element {
  const t = useT()
  const userKeys = useUserKeysQuery(user.id)
  const rotateKey = useRotateKeyMutation(user.id)
  const revokeKey = useRevokeKeyMutation(user.id)
  const [issueOpen, setIssueOpen] = useState(false)
  const [revokeTarget, setRevokeTarget] = useState<{ id: number; masked: string } | null>(null)

  const onRotate = async (): Promise<void> => {
    const result = await rotateKey.mutateAsync()
    onSecret(result.api_key_plaintext_once)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="size-4 text-primary" /> {t('users.apiKeysFor', { name: user.name })}
          </DialogTitle>
          <DialogDescription>{t('users.apiKeysDescription')}</DialogDescription>
        </DialogHeader>
        {canWrite ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setIssueOpen(true)} size="sm">
              <KeyRound className="size-4" /> {t('users.issueKey')}
            </Button>
            <Button onClick={() => void onRotate()} size="sm" variant="secondary">
              <RefreshCw className="size-4" /> {t('users.rotateKey')}
            </Button>
          </div>
        ) : null}

        <div className="space-y-2">
          {(userKeys.data ?? []).map((key) => (
            <div
              className="flex items-center justify-between gap-4 rounded-md border border-border bg-secondary/40 px-4 py-3"
              key={key.id}
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className={`truncate font-mono text-sm ${key.revoked_at ? 'text-muted-foreground' : ''}`}>
                  {key.masked}
                </span>
                <span className="shrink-0 font-mono text-muted-foreground text-xs">{key.prefix}</span>
                {key.revoked_at ? <Badge variant="secondary">{t('users.revoked')}</Badge> : null}
              </div>
              {canWrite && !key.revoked_at ? (
                <Button
                  aria-label={t('users.revokeKeyAria', { id: key.id })}
                  onClick={() => setRevokeTarget({ id: key.id, masked: key.masked })}
                  size="sm"
                  variant="ghost"
                >
                  <Trash2 className="size-4" /> {t('users.revoke')}
                </Button>
              ) : null}
            </div>
          ))}
          {userKeys.data && userKeys.data.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t('users.noApiKeys')}</p>
          ) : null}
        </div>

        {canWrite ? (
          <IssueKeyDialog
            onOpenChange={setIssueOpen}
            onSecret={onSecret}
            open={issueOpen}
            userId={user.id}
            userName={user.name}
          />
        ) : null}

        <AlertDialog onOpenChange={(open) => !open && setRevokeTarget(null)} open={Boolean(revokeTarget)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {t('users.revokeKeyConfirmTitle', { masked: revokeTarget?.masked ?? '' })}
              </AlertDialogTitle>
              <AlertDialogDescription>{t('users.revokeKeyConfirmDescription')}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('users.cancel')}</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  if (revokeTarget) void revokeKey.mutateAsync(revokeTarget.id)
                  setRevokeTarget(null)
                }}
              >
                {revokeTarget ? t('users.revokeKeyAria', { id: revokeTarget.id }) : t('users.revoke')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── IM identity row ───────────────────────────

function AddImMappingDialog({
  open,
  onOpenChange,
  users,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  users: UserListItem[]
}): JSX.Element {
  const t = useT()
  const createMapping = useCreateImMappingMutation()
  const [platform, setPlatform] = useState<string | null>(IM_PLATFORMS[0])
  const [platformUserId, setPlatformUserId] = useState('')
  const [userId, setUserId] = useState<string | null>('')

  const reset = (): void => {
    setPlatform(IM_PLATFORMS[0])
    setPlatformUserId('')
    setUserId('')
  }

  const submit = async (): Promise<void> => {
    await createMapping.mutateAsync({
      platform: platform ?? '',
      platform_user_id: platformUserId.trim(),
      user_id: userId ?? '',
    })
    reset()
    onOpenChange(false)
  }

  return (
    <Dialog
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
      open={open}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.addImMapping')}</DialogTitle>
          <DialogDescription>{t('users.addImMappingDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="im-mapping-platform">{t('users.imPlatform')}</Label>
            <SimpleSelect
              onValueChange={setPlatform}
              options={IM_PLATFORMS.map((option) => ({ value: option, label: option }))}
              triggerAriaLabel={t('users.imPlatform')}
              triggerId="im-mapping-platform"
              value={platform}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="im-mapping-external-id">{t('users.imExternalId')}</Label>
            <Input
              id="im-mapping-external-id"
              onChange={(event) => setPlatformUserId(event.target.value)}
              placeholder={t('users.imExternalIdPlaceholder')}
              value={platformUserId}
            />
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor="im-mapping-user">{t('users.imInternalUser')}</Label>
            <SimpleSelect
              onValueChange={setUserId}
              options={users.map((user) => ({
                value: user.id,
                label: user.email ? `${user.name} (${user.email})` : user.name,
              }))}
              placeholder={t('users.selectUser')}
              triggerAriaLabel={t('users.imInternalUser')}
              triggerId="im-mapping-user"
              value={userId}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button disabled={!platformUserId.trim() || !userId || createMapping.isPending} onClick={() => void submit()}>
            {t('users.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function EditImIdentityDialog({
  imUser,
  open,
  onOpenChange,
}: {
  imUser: ImUser
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const fields = useImIdentityFieldsQuery(open)
  const updateImUser = useUpdateImUserMutation(imUser.id)
  const [platformUserId, setPlatformUserId] = useState(imUser.platform_user_id)
  const [metadata, setMetadata] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!open) return
    setPlatformUserId(imUser.platform_user_id)
    setMetadata(
      Object.fromEntries(
        Object.entries(imUser.metadata ?? {}).map(([key, value]) => [key, metadataValueToString(value)])
      )
    )
  }, [imUser, open])

  const platformFields = fields.data?.[imUser.platform] ?? []

  const submit = async (): Promise<void> => {
    await updateImUser.mutateAsync({
      metadata: Object.fromEntries(platformFields.map((field) => [field.key, metadata[field.key]?.trim() ?? ''])),
      platform_user_id: platformUserId.trim(),
    })
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.editImIdentity')}</DialogTitle>
          <DialogDescription>{t('users.editImIdentityDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor={`im-user-platform-id-${imUser.id}`}>{t('users.imExternalId')}</Label>
            <Input
              id={`im-user-platform-id-${imUser.id}`}
              onChange={(event) => setPlatformUserId(event.target.value)}
              value={platformUserId}
            />
          </div>
          {platformFields.map((field) => (
            <div className="grid gap-2" key={field.key}>
              <Label htmlFor={`im-user-${imUser.id}-${field.key}`}>{field.label}</Label>
              {field.multiline ? (
                <Textarea
                  id={`im-user-${imUser.id}-${field.key}`}
                  onChange={(event) => setMetadata((current) => ({ ...current, [field.key]: event.target.value }))}
                  value={metadata[field.key] ?? ''}
                />
              ) : (
                <Input
                  id={`im-user-${imUser.id}-${field.key}`}
                  onChange={(event) => setMetadata((current) => ({ ...current, [field.key]: event.target.value }))}
                  value={metadata[field.key] ?? ''}
                />
              )}
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button disabled={!platformUserId.trim() || updateImUser.isPending} onClick={() => void submit()}>
            {t('users.saveChanges')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function metadataValueToString(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value) ?? ''
}

function ImUserRow({
  imUser,
  users,
  canWrite,
}: {
  imUser: ImUser
  users: UserListItem[]
  canWrite: boolean
}): JSX.Element {
  const t = useT()
  const bindImUser = useBindImUserMutation(imUser.id)
  const blockImUser = useBlockImUserMutation(imUser.id)
  const restoreImUser = useRestoreImUserMutation(imUser.id)
  const deleteImUser = useDeleteImUserMutation(imUser.id)

  const [boundUser, setBoundUser] = useState(imUser.user_id)
  const [reason, setReason] = useState('')
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4" data-testid={`im-user-${imUser.id}`}>
      <div className="space-y-2">
        <p className="font-medium text-foreground">{imUser.platform_user_id}</p>
        {imUser.user_email ? <p className="text-muted-foreground text-sm">{imUser.user_email}</p> : null}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="outline">{imUser.platform}</Badge>
          <Badge variant="secondary">{imUser.user_name || imUser.user_id}</Badge>
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
            <SimpleSelect
              onValueChange={(value) => {
                if (!value) return
                setBoundUser(value)
                void bindImUser.mutateAsync({ user_id: value })
              }}
              options={users.map((user) => ({ value: user.id, label: user.name }))}
              triggerAriaLabel={t('users.bindToUser')}
              triggerId={`im-bind-${imUser.id}`}
              value={boundUser}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor={`im-reason-${imUser.id}`}>{t('users.imReason')}</Label>
            <Input id={`im-reason-${imUser.id}`} onChange={(event) => setReason(event.target.value)} value={reason} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() =>
                void (imUser.allowed ? blockImUser.mutateAsync({ reason }) : restoreImUser.mutateAsync({ reason }))
              }
              size="sm"
              variant={imUser.allowed ? 'destructive' : 'secondary'}
            >
              {imUser.allowed ? t('users.blockIdentity') : t('users.restoreIdentity')}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    aria-label={t('users.imIdentityActionsFor', {
                      platform: imUser.platform,
                      id: imUser.platform_user_id,
                    })}
                    size="sm"
                    variant="secondary"
                  >
                    <MoreVertical className="size-4" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setTimeout(() => setEditOpen(true), 0)}>
                  {t('users.editImMetadata')}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setConfirmDelete(true)} variant="destructive">
                  <Trash2 /> {t('users.deleteIdentity')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      ) : (
        <p className="text-muted-foreground text-xs">{t('users.viewerReadOnly')}</p>
      )}

      <EditImIdentityDialog imUser={imUser} onOpenChange={setEditOpen} open={editOpen} />

      <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.deleteIdentityTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('users.deleteIdentityDescription', {
                platform: imUser.platform,
                id: imUser.platform_user_id,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('users.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void deleteImUser.mutateAsync()}>
              {t('users.deleteIdentity')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

// ─────────────────────────── Page ───────────────────────────

export function UsersPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const users = useUsersQuery()
  const imUsers = useImUsersQuery()

  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create')
  const [formOpen, setFormOpen] = useState(false)
  const [servicePrincipalOpen, setServicePrincipalOpen] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const [keysForUserId, setKeysForUserId] = useState<string | null>(null)
  const [addImMappingOpen, setAddImMappingOpen] = useState(false)

  const canWrite = me.data?.role !== 'viewer'

  useEffect(() => {
    if (!users.data?.length) {
      setSelectedUserId(null)
      return
    }
    if (!selectedUserId || !users.data.some((item) => item.id === selectedUserId)) {
      setSelectedUserId(users.data[0].id)
    }
  }, [selectedUserId, users.data])

  const selectedUser = useMemo(
    () => users.data?.find((item) => item.id === selectedUserId) ?? null,
    [users.data, selectedUserId]
  )

  const updateUser = useUpdateUserMutation(selectedUserId ?? '')
  const setRole = useSetRoleMutation(selectedUserId ?? '')
  const resetPassword = useResetPasswordMutation(selectedUserId ?? '')
  const createUser = useCreateUserMutation()

  const submitForm = async (state: {
    email: string
    name: string
    password: string
    resetPassword: string
    role: string
    mustReset: boolean
  }): Promise<void> => {
    if (formMode === 'create') {
      await createUser.mutateAsync({
        email: state.email,
        must_reset: state.mustReset,
        name: state.name,
        password: state.password,
        role: state.role,
      })
      setFormOpen(false)
      return
    }
    if (!selectedUser) return

    if (selectedUser.name !== state.name || (selectedUser.email ?? '') !== state.email) {
      await updateUser.mutateAsync({ email: state.email, name: state.name })
    }
    if (selectedUser.role !== state.role) {
      await setRole.mutateAsync({ role: state.role })
    }
    if (state.resetPassword.trim()) {
      await resetPassword.mutateAsync({ new_password: state.resetPassword })
    }
    setFormOpen(false)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-xl tracking-tight">{t('users.title')}</h2>
          <Badge variant="secondary">{users.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setServicePrincipalOpen(true)} variant="secondary">
              <KeyRound className="size-4" /> {t('users.createServicePrincipal')}
            </Button>
            <Button
              onClick={() => {
                setFormMode('create')
                setFormOpen(true)
              }}
            >
              <UserPlus className="size-4" /> {t('users.createUser')}
            </Button>
          </div>
        ) : null}
      </div>

      <p className="max-w-2xl text-muted-foreground text-sm">{t('users.pageDescription')}</p>

      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users">{t('users.tabUsers')}</TabsTrigger>
          <TabsTrigger value="im">{t('users.tabImIdentities')}</TabsTrigger>
        </TabsList>

        <TabsContent value="users">
          <div className="space-y-2">
            {users.data?.map((user) => (
              <UserRow
                canWrite={canWrite}
                key={user.id}
                onClick={() => setSelectedUserId(user.id)}
                onEdit={() => {
                  setSelectedUserId(user.id)
                  setFormMode('edit')
                  setFormOpen(true)
                }}
                onManageKeys={() => setKeysForUserId(user.id)}
                selected={selectedUserId === user.id}
                user={user}
              />
            ))}
            {users.data && users.data.length === 0 ? (
              <div className="rounded-lg border border-border border-dashed py-12 text-center text-muted-foreground text-sm">
                {t('users.emptyUsers')}
              </div>
            ) : null}
          </div>
        </TabsContent>

        <TabsContent value="im">
          <div className="space-y-4">
            {canWrite ? (
              <div className="flex justify-end">
                <Button onClick={() => setAddImMappingOpen(true)}>
                  <Plus className="size-4" /> {t('users.addImMapping')}
                </Button>
              </div>
            ) : null}
            {imUsers.data?.map((imUser) => (
              <ImUserRow canWrite={canWrite} imUser={imUser} key={imUser.id} users={users.data ?? []} />
            ))}
            {imUsers.data && imUsers.data.length === 0 ? (
              <div className="rounded-lg border border-border border-dashed py-12 text-center text-muted-foreground text-sm">
                {t('users.emptyImIdentities')}
              </div>
            ) : null}
          </div>
        </TabsContent>
      </Tabs>

      {canWrite ? (
        <UserFormDialog
          busy={createUser.isPending || updateUser.isPending}
          mode={formMode}
          onOpenChange={setFormOpen}
          onSubmit={submitForm}
          open={formOpen}
          user={formMode === 'edit' ? selectedUser : null}
        />
      ) : null}

      {canWrite ? (
        <CreateServicePrincipalDialog
          onOpenChange={setServicePrincipalOpen}
          onSecret={setSecret}
          open={servicePrincipalOpen}
        />
      ) : null}

      {keysForUserId
        ? (() => {
            const keysUser = users.data?.find((item) => item.id === keysForUserId)
            return keysUser ? (
              <KeysDialog
                canWrite={canWrite}
                onOpenChange={(open) => !open && setKeysForUserId(null)}
                onSecret={setSecret}
                open
                user={keysUser}
              />
            ) : null
          })()
        : null}

      {canWrite ? (
        <AddImMappingDialog onOpenChange={setAddImMappingOpen} open={addImMappingOpen} users={users.data ?? []} />
      ) : null}

      <SecretDialog onDismiss={() => setSecret(null)} secret={secret} />
    </div>
  )
}

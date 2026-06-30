import { useEffect, useMemo, useState } from 'react'
import { MoreVertical, Plus, Trash2, UserPlus, KeyRound } from 'lucide-react'

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  type ImUser,
  type UserListItem,
  useBindImUserMutation,
  useBlockImUserMutation,
  useCreateUserMutation,
  useDeleteImUserMutation,
  useDeleteUserMutation,
  useImUsersQuery,
  useInitiateLinkMutation,
  useResetPasswordMutation,
  useRestoreImUserMutation,
  useSetRoleMutation,
  useUnblockUserMutation,
  useUnlinkIdentityMutation,
  useUpdateUserMutation,
  useUsersQuery,
} from '@/features/users/api'
import {
  initials,
  statusVariant,
  useAdminMeQuery,
} from '@/features/users/shared'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'
import { BlockUserDialog } from '@/features/users/dialogs/block-user-dialog'
import { CreateServicePrincipalDialog } from '@/features/users/dialogs/create-service-principal-dialog'
import { KeysDialog } from '@/features/users/dialogs/keys-dialog'
import { SecretDialog } from '@/features/users/dialogs/secret-dialog'
import { type UserFormState, UserFormDialog } from '@/features/users/dialogs/user-form-dialog'
import { AddImMappingDialog } from '@/features/users/dialogs/add-im-mapping-dialog'
import { EditImIdentityDialog } from '@/features/users/dialogs/edit-im-identity-dialog'

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

// ─────────────────────────── IM identity row ───────────────────────────

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

  const submitForm = async (state: UserFormState): Promise<void> => {
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

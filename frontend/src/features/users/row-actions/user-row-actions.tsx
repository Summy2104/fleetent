import { useState } from 'react'
import { MoreVertical, Trash2 } from 'lucide-react'

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
import {
  type UserListItem,
  useDeleteUserMutation,
  useInitiateLinkMutation,
  useUnblockUserMutation,
  useUnlinkIdentityMutation,
} from '@/features/users/api'
import { BlockUserDialog } from '@/features/users/dialogs/block-user-dialog'
import { useT } from '@/i18n'

export function UserRowActions({
  user,
  canWrite,
  onEdit,
  onManageKeys,
}: {
  user: UserListItem
  canWrite: boolean
  onEdit: (user: UserListItem) => void
  onManageKeys: (user: UserListItem) => void
}): JSX.Element | null {
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

  if (!canWrite) return null

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
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button aria-label={t('users.actionsFor', { name: user.name })} size="icon" variant="ghost">
              <MoreVertical className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => onEdit(user)}>{t('users.edit')}</DropdownMenuItem>
          {user.status === 'blocked' ? (
            <DropdownMenuItem onClick={() => void unblockUser.mutateAsync()}>{t('users.unblock')}</DropdownMenuItem>
          ) : (
            <DropdownMenuItem onClick={() => setBlockOpen(true)}>{t('users.block')}</DropdownMenuItem>
          )}
          <DropdownMenuItem onClick={() => void initiateLink.mutateAsync().then(setLinkCode)}>
            {t('users.initiateChannelLink')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTimeout(() => setUnlinkOpen(true), 0)}>
            {t('users.unlinkChannelIdentity')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTimeout(() => onManageKeys(user), 0)}>
            {t('users.apiKeys')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setConfirmDelete(true)} variant="destructive">
            <Trash2 /> {t('users.delete')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

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
    </>
  )
}

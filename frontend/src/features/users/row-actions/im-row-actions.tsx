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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { type ImUser, type UserListItem, useDeleteImUserMutation } from '@/features/users/api'
import { BindImUserDialog } from '@/features/users/dialogs/bind-im-user-dialog'
import { BlockImIdentityDialog } from '@/features/users/dialogs/block-im-identity-dialog'
import { EditImIdentityDialog } from '@/features/users/dialogs/edit-im-identity-dialog'
import { useT } from '@/i18n'

export function ImRowActions({
  imUser,
  users,
  canWrite,
}: {
  imUser: ImUser
  users: UserListItem[]
  canWrite: boolean
}): JSX.Element | null {
  const t = useT()
  const deleteImUser = useDeleteImUserMutation(imUser.id)
  const [bindOpen, setBindOpen] = useState(false)
  const [blockOpen, setBlockOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (!canWrite) return null

  return (
    <div className="flex justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              aria-label={t('users.imIdentityActionsFor', {
                platform: imUser.platform,
                id: imUser.platform_user_id,
              })}
              size="icon"
              variant="ghost"
            >
              <MoreVertical className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setTimeout(() => setBindOpen(true), 0)}>
            {t('users.bindToUser')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setBlockOpen(true)}>
            {imUser.allowed ? t('users.blockIdentity') : t('users.restoreIdentity')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTimeout(() => setEditOpen(true), 0)}>
            {t('users.editImMetadata')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setConfirmDelete(true)} variant="destructive">
            <Trash2 /> {t('users.deleteIdentity')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <BindImUserDialog imUser={imUser} onOpenChange={setBindOpen} open={bindOpen} users={users} />
      <BlockImIdentityDialog imUser={imUser} onOpenChange={setBlockOpen} open={blockOpen} />
      <EditImIdentityDialog imUser={imUser} onOpenChange={setEditOpen} open={editOpen} />

      <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.deleteIdentityTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('users.deleteIdentityDescription', { platform: imUser.platform, id: imUser.platform_user_id })}
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

import { useEffect, useState } from 'react'

import { SimpleSelect } from '@/components/base/simple-select'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { type ImUser, type UserListItem, useBindImUserMutation } from '@/features/users/api'
import { useT } from '@/i18n'

export function BindImUserDialog({
  imUser,
  users,
  open,
  onOpenChange,
}: {
  imUser: ImUser
  users: UserListItem[]
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const bindImUser = useBindImUserMutation(imUser.id)
  const [userId, setUserId] = useState<string | null>(imUser.user_id)

  useEffect(() => {
    if (open) setUserId(imUser.user_id)
  }, [open, imUser.user_id])

  const submit = async (): Promise<void> => {
    if (!userId) return
    await bindImUser.mutateAsync({ user_id: userId })
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.bindToUser')}</DialogTitle>
          <DialogDescription>{t('users.addImMappingDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor={`im-bind-${imUser.id}`}>{t('users.bindToUser')}</Label>
          <SimpleSelect
            onValueChange={setUserId}
            options={users.map((u) => ({ value: u.id, label: u.email ? `${u.name} (${u.email})` : u.name }))}
            placeholder={t('users.selectUser')}
            triggerAriaLabel={t('users.bindToUser')}
            triggerId={`im-bind-${imUser.id}`}
            value={userId}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button disabled={!userId || bindImUser.isPending} onClick={() => void submit()}>
            {t('users.saveChanges')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

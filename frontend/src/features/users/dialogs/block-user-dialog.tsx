import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { type UserListItem, useBlockUserMutation } from '@/features/users/api'
import { useT } from '@/i18n'

export function BlockUserDialog({
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

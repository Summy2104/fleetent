import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { type ImUser, useBlockImUserMutation, useRestoreImUserMutation } from '@/features/users/api'
import { useT } from '@/i18n'

export function BlockImIdentityDialog({
  imUser,
  open,
  onOpenChange,
}: {
  imUser: ImUser
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const blockImUser = useBlockImUserMutation(imUser.id)
  const restoreImUser = useRestoreImUserMutation(imUser.id)
  const [reason, setReason] = useState('')
  const isBlocking = imUser.allowed
  const title = isBlocking ? t('users.blockIdentity') : t('users.restoreIdentity')

  const submit = async (): Promise<void> => {
    const action = isBlocking ? blockImUser : restoreImUser
    await action.mutateAsync({ reason })
    setReason('')
    onOpenChange(false)
  }

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
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{t('users.blockUserDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor={`im-reason-${imUser.id}`}>{t('users.imReason')}</Label>
          <Input id={`im-reason-${imUser.id}`} onChange={(event) => setReason(event.target.value)} value={reason} />
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button
            disabled={blockImUser.isPending || restoreImUser.isPending}
            onClick={() => void submit()}
            variant={isBlocking ? 'destructive' : 'secondary'}
          >
            {title}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

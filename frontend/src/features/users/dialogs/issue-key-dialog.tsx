import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCreateKeyMutation } from '@/features/users/api'
import { parseScopes } from '@/features/users/shared'
import { useT } from '@/i18n'

export function IssueKeyDialog({
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

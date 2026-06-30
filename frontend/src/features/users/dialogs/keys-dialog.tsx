import { useState } from 'react'

import { KeyRound, RefreshCw, Trash2 } from 'lucide-react'

import { Badge } from '@/components/base/badge'
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
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { type UserListItem, useRevokeKeyMutation, useRotateKeyMutation, useUserKeysQuery } from '@/features/users/api'
import { useT } from '@/i18n'
import { IssueKeyDialog } from '@/features/users/dialogs/issue-key-dialog'

export function KeysDialog({
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

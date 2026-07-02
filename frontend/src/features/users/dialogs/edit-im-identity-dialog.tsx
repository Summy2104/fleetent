import { useEffect, useState } from 'react'

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
import { Textarea } from '@/components/ui/textarea'
import { type ImUser, useImIdentityFieldsQuery, useUpdateImUserMutation } from '@/features/users/api'
import { metadataValueToString } from '@/features/users/shared'
import { useT } from '@/i18n'

export function EditImIdentityDialog({
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

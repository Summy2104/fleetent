import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCreateServicePrincipalMutation } from '@/features/users/api'
import { useT } from '@/i18n'
import { describeApiError } from '@/lib/api-client'

export function CreateServicePrincipalDialog({
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

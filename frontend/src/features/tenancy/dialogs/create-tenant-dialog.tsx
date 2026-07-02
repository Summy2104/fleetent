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
import { useCreateTenantMutation } from '@/features/tenancy/api'
import { useT } from '@/i18n'

export function CreateTenantDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const createTenant = useCreateTenantMutation()
  const [tenantName, setTenantName] = useState('')

  useEffect(() => {
    if (open) setTenantName('')
  }, [open])

  const submit = async (): Promise<void> => {
    await createTenant.mutateAsync({ name: tenantName, status: 'active' })
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('tenancy.createTenant')}</DialogTitle>
          <DialogDescription>{t('tenancy.createTenantDesc')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="tenant-name">{t('tenancy.tenantName')}</Label>
          <Input id="tenant-name" onChange={(event) => setTenantName(event.target.value)} value={tenantName} />
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('common.cancel')}
          </Button>
          <Button disabled={createTenant.isPending || !tenantName} onClick={() => void submit()}>
            {t('tenancy.createTenant')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

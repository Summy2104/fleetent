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
import { type TenantListItem, useAssignUserTenantMutation } from '@/features/tenancy/api'
import type { TenancyUser } from '@/features/tenancy/shared'
import { useT } from '@/i18n'

export function AssignTenantDialog({
  user,
  tenants,
  open,
  onOpenChange,
}: {
  user: TenancyUser
  tenants: TenantListItem[]
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const assignUserTenant = useAssignUserTenantMutation()
  const [selected, setSelected] = useState(user.tenant_id ?? '')

  useEffect(() => {
    if (open) setSelected(user.tenant_id ?? '')
  }, [open, user.tenant_id])

  const submit = async (): Promise<void> => {
    await assignUserTenant.mutateAsync({ tenant_id: selected, user_id: user.id })
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('tenancy.assignTenant')}</DialogTitle>
          <DialogDescription>{t('tenancy.assignTenantFor', { name: user.name })}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor={`assign-tenant-${user.id}`}>{t('tenancy.colTenant')}</Label>
          <SimpleSelect
            onValueChange={setSelected}
            options={[
              { label: t('tenancy.none'), value: '' },
              ...tenants.map((tenant) => ({ label: tenant.name, value: tenant.id })),
            ]}
            placeholder={t('tenancy.selectTenant')}
            triggerAriaLabel={t('tenancy.assignTenantFor', { name: user.name })}
            triggerId={`assign-tenant-${user.id}`}
            value={selected}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('common.cancel')}
          </Button>
          <Button disabled={assignUserTenant.isPending} onClick={() => void submit()}>
            {t('tenancy.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

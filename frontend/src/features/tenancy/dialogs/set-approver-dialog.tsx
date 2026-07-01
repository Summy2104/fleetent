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
import { type TenantListItem, useSetApproverMutation } from '@/features/tenancy/api'
import type { TenancyUser } from '@/features/tenancy/shared'
import { useT } from '@/i18n'

export function SetApproverDialog({
  tenant,
  users,
  open,
  onOpenChange,
}: {
  tenant: TenantListItem
  users: TenancyUser[]
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const setApprover = useSetApproverMutation(tenant.id)
  const [selected, setSelected] = useState(tenant.approver_user_id ?? '')

  useEffect(() => {
    if (open) setSelected(tenant.approver_user_id ?? '')
  }, [open, tenant.approver_user_id])

  const submit = async (): Promise<void> => {
    await setApprover.mutateAsync({ approver_user_id: selected || null, entity_type: 'tenant' })
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('tenancy.setApprover')}</DialogTitle>
          <DialogDescription>{t('tenancy.tenantApproverFor', { id: tenant.id })}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor={`tenant-approver-${tenant.id}`}>{t('tenancy.colApprover')}</Label>
          <SimpleSelect
            onValueChange={setSelected}
            options={[
              { label: t('tenancy.none'), value: '' },
              ...users.map((user) => ({ label: user.name, value: user.id })),
            ]}
            placeholder={t('tenancy.selectApprover')}
            triggerAriaLabel={t('tenancy.tenantApproverFor', { id: tenant.id })}
            triggerId={`tenant-approver-${tenant.id}`}
            value={selected}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('common.cancel')}
          </Button>
          <Button disabled={setApprover.isPending} onClick={() => void submit()}>
            {t('tenancy.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { type TenantListItem, useSetApproverMutation } from '@/features/tenancy/api'
import { SELECT_CLASS, type TenancyUser } from '@/features/tenancy/shared'
import { useT } from '@/i18n'

export function TenantApproverCell({
  tenant,
  users,
  canWrite,
}: {
  tenant: TenantListItem
  users: TenancyUser[]
  canWrite: boolean
}): JSX.Element {
  const t = useT()
  const setApprover = useSetApproverMutation(tenant.id)
  const [selected, setSelected] = useState(tenant.approver_user_id ?? '')

  return (
    <div className="flex flex-col gap-2">
      <span className="text-muted-foreground text-sm">
        {t('tenancy.approverLine', { value: tenant.approver_user_id ?? t('tenancy.unassigned') })}
      </span>
      {canWrite ? (
        <div className="flex items-center gap-2">
          <select
            aria-label={t('tenancy.tenantApproverFor', { id: tenant.id })}
            className={SELECT_CLASS}
            onChange={(event) => setSelected(event.target.value)}
            value={selected}
          >
            <option value="">{t('tenancy.none')}</option>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
          <Button
            className="shrink-0"
            disabled={setApprover.isPending}
            onClick={() => void setApprover.mutateAsync({ approver_user_id: selected || null, entity_type: 'tenant' })}
            variant="outline"
          >
            {t('tenancy.saveTenantApproverFor', { id: tenant.id })}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

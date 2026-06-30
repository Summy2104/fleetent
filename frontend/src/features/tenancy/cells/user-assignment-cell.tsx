import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { type TenantListItem, useAssignUserTenantMutation } from '@/features/tenancy/api'
import { SELECT_CLASS, type TenancyUser } from '@/features/tenancy/shared'
import { useT } from '@/i18n'

export function UserAssignmentCell({
  user,
  tenants,
  canWrite,
}: {
  user: TenancyUser
  tenants: TenantListItem[]
  canWrite: boolean
}): JSX.Element | null {
  const t = useT()
  const assignUserTenant = useAssignUserTenantMutation()
  const [selected, setSelected] = useState(user.tenant_id ?? '')

  if (!canWrite) return null

  return (
    <div className="flex items-center justify-end gap-2">
      <select
        aria-label={t('tenancy.assignTenantFor', { name: user.name })}
        className={`${SELECT_CLASS} w-48`}
        onChange={(event) => setSelected(event.target.value)}
        value={selected}
      >
        <option value="">{t('tenancy.none')}</option>
        {tenants.map((tenant) => (
          <option key={tenant.id} value={tenant.id}>
            {tenant.name}
          </option>
        ))}
      </select>
      <Button
        className="shrink-0"
        disabled={assignUserTenant.isPending}
        onClick={() => void assignUserTenant.mutateAsync({ tenant_id: selected, user_id: user.id })}
        variant="outline"
      >
        {t('tenancy.assignTenantFor', { name: user.name })}
      </Button>
    </div>
  )
}

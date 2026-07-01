import { useState } from 'react'
import { MoreVertical } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import type { TenantListItem } from '@/features/tenancy/api'
import { SetApproverDialog } from '@/features/tenancy/dialogs/set-approver-dialog'
import type { TenancyUser } from '@/features/tenancy/shared'
import { useT } from '@/i18n'

export function TenantRowActions({
  tenant,
  users,
  canWrite,
}: {
  tenant: TenantListItem
  users: TenancyUser[]
  canWrite: boolean
}): JSX.Element | null {
  const t = useT()
  const [approverOpen, setApproverOpen] = useState(false)

  if (!canWrite) return null

  return (
    <div className="flex justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button aria-label={t('tenancy.tenantActionsFor', { id: tenant.id })} size="icon" variant="ghost">
              <MoreVertical className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setTimeout(() => setApproverOpen(true), 0)}>
            {t('tenancy.setApprover')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <SetApproverDialog onOpenChange={setApproverOpen} open={approverOpen} tenant={tenant} users={users} />
    </div>
  )
}

import { useState } from 'react'
import { MoreVertical } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import type { TenantListItem } from '@/features/tenancy/api'
import { AssignTenantDialog } from '@/features/tenancy/dialogs/assign-tenant-dialog'
import type { TenancyUser } from '@/features/tenancy/shared'
import { useT } from '@/i18n'

export function AssignmentRowActions({
  user,
  tenants,
  canWrite,
}: {
  user: TenancyUser
  tenants: TenantListItem[]
  canWrite: boolean
}): JSX.Element | null {
  const t = useT()
  const [assignOpen, setAssignOpen] = useState(false)

  if (!canWrite) return null

  return (
    <div className="flex justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button aria-label={t('tenancy.assignmentActionsFor', { name: user.name })} size="icon" variant="ghost">
              <MoreVertical className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setTimeout(() => setAssignOpen(true), 0)}>
            {t('tenancy.assignTenant')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <AssignTenantDialog onOpenChange={setAssignOpen} open={assignOpen} tenants={tenants} user={user} />
    </div>
  )
}

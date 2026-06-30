import type { ColumnDef } from '@tanstack/react-table'

import type { TenantListItem } from '@/features/tenancy/api'
import { UserAssignmentCell } from '@/features/tenancy/cells/user-assignment-cell'
import type { TenancyUser } from '@/features/tenancy/shared'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

export function buildAssignmentColumns({
  t,
  canWrite,
  tenants,
}: {
  t: Translate
  canWrite: boolean
  tenants: TenantListItem[]
}): ColumnDef<TenancyUser, unknown>[] {
  return [
    {
      accessorKey: 'name',
      header: t('tenancy.colUser'),
      meta: { title: t('tenancy.colUser') },
      cell: ({ row }) => <span className="font-medium text-foreground text-sm">{row.original.name}</span>,
    },
    {
      accessorKey: 'tenant_id',
      header: t('tenancy.colTenant'),
      meta: { title: t('tenancy.colTenant') },
      cell: ({ row }) =>
        row.original.tenant_id
          ? t('tenancy.assignmentLine', { name: row.original.name, tenant: row.original.tenant_id })
          : t('tenancy.unassigned'),
    },
    {
      id: 'assign',
      header: '',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => <UserAssignmentCell canWrite={canWrite} tenants={tenants} user={row.original} />,
    },
  ]
}

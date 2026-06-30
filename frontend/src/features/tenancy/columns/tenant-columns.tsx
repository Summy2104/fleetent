import type { ColumnDef } from '@tanstack/react-table'
import { Building2 } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import type { TenantListItem } from '@/features/tenancy/api'
import { TenantApproverCell } from '@/features/tenancy/cells/tenant-approver-cell'
import type { TenancyUser } from '@/features/tenancy/shared'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

export function buildTenantColumns({
  t,
  canWrite,
  users,
}: {
  t: Translate
  canWrite: boolean
  users: TenancyUser[]
}): ColumnDef<TenantListItem, unknown>[] {
  return [
    {
      accessorKey: 'name',
      header: t('tenancy.tenantName'),
      meta: { title: t('tenancy.tenantName') },
      cell: ({ row }) => (
        <span className="flex items-center gap-2 font-medium text-foreground text-sm">
          <Building2 className="size-4 text-primary" /> {row.original.name}
        </span>
      ),
    },
    {
      accessorKey: 'id',
      header: t('tenancy.colId'),
      meta: { title: t('tenancy.colId') },
      cell: ({ row }) => <span className="font-mono text-muted-foreground text-xs">{row.original.id}</span>,
    },
    {
      accessorKey: 'status',
      header: t('tenancy.colStatus'),
      meta: { title: t('tenancy.colStatus') },
      cell: ({ row }) => (
        <Badge variant={row.original.status === 'active' ? 'success' : 'secondary'}>{row.original.status}</Badge>
      ),
    },
    {
      id: 'approver',
      header: t('tenancy.colApprover'),
      enableSorting: false,
      meta: { title: t('tenancy.colApprover') },
      cell: ({ row }) => <TenantApproverCell canWrite={canWrite} tenant={row.original} users={users} />,
    },
  ]
}

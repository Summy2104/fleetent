import type { ColumnDef } from '@tanstack/react-table'
import { Building2 } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import type { TenantListItem } from '@/features/tenancy/api'
import { TenantRowActions } from '@/features/tenancy/row-actions/tenant-row-actions'
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
      filterFn: 'equals',
      meta: {
        title: t('tenancy.colStatus'),
        filter: {
          type: 'select',
          options: [
            { label: t('tenancy.statusActive'), value: 'active' },
            { label: t('tenancy.statusInactive'), value: 'inactive' },
          ],
        },
      },
      cell: ({ row }) => (
        <Badge variant={row.original.status === 'active' ? 'success' : 'secondary'}>{row.original.status}</Badge>
      ),
    },
    {
      id: 'approver',
      header: t('tenancy.colApprover'),
      enableSorting: false,
      meta: { title: t('tenancy.colApprover') },
      cell: ({ row }) => (
        <span className="text-muted-foreground text-sm">
          {t('tenancy.approverLine', { value: row.original.approver_user_id ?? t('tenancy.unassigned') })}
        </span>
      ),
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => <TenantRowActions canWrite={canWrite} tenant={row.original} users={users} />,
    },
  ]
}

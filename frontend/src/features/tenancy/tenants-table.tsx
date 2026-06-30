import type * as React from 'react'
import { useMemo } from 'react'

import { DataTable } from '@/components/base/data-table'
import type { TenantListItem } from '@/features/tenancy/api'
import { buildTenantColumns } from '@/features/tenancy/columns/tenant-columns'
import type { TenancyUser } from '@/features/tenancy/shared'
import { useT } from '@/i18n'

export function TenantsTable({
  tenants,
  users,
  canWrite,
  isLoading,
  actions,
  title,
}: {
  tenants: TenantListItem[]
  users: TenancyUser[]
  canWrite: boolean
  isLoading: boolean
  actions?: React.ReactNode
  title?: React.ReactNode
}): JSX.Element {
  const t = useT()
  const columns = useMemo(() => buildTenantColumns({ canWrite, t, users }), [canWrite, t, users])

  return (
    <DataTable
      actions={actions}
      columns={columns}
      data={tenants}
      emptyState={<div className="py-12 text-center text-muted-foreground text-sm">{t('tenancy.noTenants')}</div>}
      enableColumnVisibility
      enableGlobalFilter
      getRowId={(row) => row.id}
      isLoading={isLoading}
      title={title}
    />
  )
}

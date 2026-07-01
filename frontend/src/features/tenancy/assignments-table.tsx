import type * as React from 'react'
import { useMemo } from 'react'

import { DataTable } from '@/components/base/data-table'
import type { TenantListItem } from '@/features/tenancy/api'
import { buildAssignmentColumns } from '@/features/tenancy/columns/assignment-columns'
import type { TenancyUser } from '@/features/tenancy/shared'
import { useT } from '@/i18n'

export function AssignmentsTable({
  users,
  tenants,
  canWrite,
  isLoading,
  title,
}: {
  users: TenancyUser[]
  tenants: TenantListItem[]
  canWrite: boolean
  isLoading: boolean
  title?: React.ReactNode
}): JSX.Element {
  const t = useT()
  const columns = useMemo(() => buildAssignmentColumns({ canWrite, t, tenants }), [canWrite, t, tenants])

  return (
    <DataTable
      columns={columns}
      data={users}
      emptyState={<div className="py-12 text-center text-muted-foreground text-sm">{t('tenancy.noUsers')}</div>}
      enableColumnVisibility
      enableGlobalFilter
      getRowId={(row) => row.id}
      isLoading={isLoading}
      title={title}
    />
  )
}

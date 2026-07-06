import type * as React from 'react'
import { useMemo } from 'react'

import { DataTable } from '@/components/base/data-table'
import { type UserListItem, useUsersQuery } from '@/features/users/api'
import { buildUserColumns } from '@/features/users/columns/user-columns'
import { useT } from '@/i18n'

export function UsersTable({
  canWrite,
  onEdit,
  onManageKeys,
  actions,
  title,
}: {
  canWrite: boolean
  onEdit: (user: UserListItem) => void
  onManageKeys: (user: UserListItem) => void
  actions?: React.ReactNode
  title?: React.ReactNode
}): JSX.Element {
  const t = useT()
  const users = useUsersQuery()
  const columns = useMemo(
    () => buildUserColumns({ canWrite, onEdit, onManageKeys, t }),
    [canWrite, onEdit, onManageKeys, t]
  )

  return (
    <DataTable
      actions={actions}
      columns={columns}
      data={users.data ?? []}
      emptyState={<div className="py-12 text-center text-muted-foreground text-sm">{t('users.emptyUsers')}</div>}
      enableColumnVisibility
      enableGlobalFilter
      getRowId={(row) => row.id}
      isLoading={users.isPending}
      title={title}
    />
  )
}

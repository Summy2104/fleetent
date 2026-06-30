import { useMemo } from 'react'

import { DataTable } from '@/components/base/data-table'
import { type UserListItem, useImUsersQuery } from '@/features/users/api'
import { buildImColumns } from '@/features/users/columns/im-columns'
import { useT } from '@/i18n'

export function ImIdentitiesTable({ canWrite, users }: { canWrite: boolean; users: UserListItem[] }): JSX.Element {
  const t = useT()
  const imUsers = useImUsersQuery()
  const columns = useMemo(() => buildImColumns({ canWrite, t, users }), [canWrite, t, users])

  return (
    <DataTable
      columns={columns}
      data={imUsers.data ?? []}
      emptyState={<div className="py-12 text-center text-muted-foreground text-sm">{t('users.emptyImIdentities')}</div>}
      enableGlobalFilter
      getRowId={(row) => String(row.id)}
      isLoading={imUsers.isPending}
    />
  )
}

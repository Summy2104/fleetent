import type { ColumnDef } from '@tanstack/react-table'

import { Badge } from '@/components/base/badge'
import type { UserListItem } from '@/features/users/api'
import { UserRowActions } from '@/features/users/row-actions/user-row-actions'
import { initials, ROLES, statusVariant } from '@/features/users/shared'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

const STATUS_VALUES = ['active', 'blocked']

export function buildUserColumns({
  t,
  canWrite,
  onEdit,
  onManageKeys,
}: {
  t: Translate
  canWrite: boolean
  onEdit: (user: UserListItem) => void
  onManageKeys: (user: UserListItem) => void
}): ColumnDef<UserListItem, unknown>[] {
  return [
    {
      accessorKey: 'name',
      header: t('users.userName'),
      meta: { title: t('users.userName') },
      cell: ({ row }) => (
        <div className="flex items-center gap-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-secondary font-semibold text-foreground text-xs">
            {initials(row.original.name)}
          </span>
          <span className="truncate font-medium text-foreground text-sm">{row.original.name}</span>
        </div>
      ),
    },
    {
      accessorKey: 'role',
      header: t('users.role'),
      filterFn: 'equals',
      meta: {
        title: t('users.role'),
        filter: { type: 'select', options: ROLES.map((role) => ({ label: role, value: role })) },
      },
      cell: ({ row }) => <Badge variant="outline">{row.original.role}</Badge>,
    },
    {
      accessorKey: 'status',
      header: t('users.status'),
      filterFn: 'equals',
      meta: {
        title: t('users.status'),
        filter: { type: 'select', options: STATUS_VALUES.map((s) => ({ label: s, value: s })) },
      },
      cell: ({ row }) => <Badge variant={statusVariant(row.original.status)}>{row.original.status}</Badge>,
    },
    {
      accessorKey: 'email',
      header: t('users.email'),
      meta: { title: t('users.email') },
      cell: ({ row }) => (
        <span className="text-muted-foreground text-sm">{row.original.email ?? t('users.noEmail')}</span>
      ),
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <UserRowActions canWrite={canWrite} onEdit={onEdit} onManageKeys={onManageKeys} user={row.original} />
        </div>
      ),
    },
  ]
}

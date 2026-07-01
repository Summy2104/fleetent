import type { ColumnDef } from '@tanstack/react-table'

import { Badge } from '@/components/base/badge'
import type { ImUser, UserListItem } from '@/features/users/api'
import { ImRowActions } from '@/features/users/row-actions/im-row-actions'
import { IM_PLATFORMS, statusVariant } from '@/features/users/shared'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

export function buildImColumns({
  t,
  canWrite,
  users,
}: {
  t: Translate
  canWrite: boolean
  users: UserListItem[]
}): ColumnDef<ImUser, unknown>[] {
  return [
    {
      accessorKey: 'platform',
      header: t('users.imPlatform'),
      filterFn: 'equals',
      meta: {
        title: t('users.imPlatform'),
        filter: { type: 'select', options: IM_PLATFORMS.map((p) => ({ label: p, value: p })) },
      },
      cell: ({ row }) => <Badge variant="outline">{row.original.platform}</Badge>,
    },
    {
      accessorKey: 'platform_user_id',
      header: t('users.imExternalId'),
      meta: { title: t('users.imExternalId') },
      cell: ({ row }) => <span className="font-mono text-sm">{row.original.platform_user_id}</span>,
    },
    {
      accessorKey: 'user_name',
      header: t('users.imInternalUser'),
      meta: { title: t('users.imInternalUser') },
      cell: ({ row }) => (
        <div className="min-w-0">
          <span className="block truncate text-sm">{row.original.user_name || row.original.user_id}</span>
          {row.original.user_email ? (
            <span className="block truncate text-muted-foreground text-xs">{row.original.user_email}</span>
          ) : null}
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: t('users.status'),
      filterFn: 'equals',
      meta: {
        title: t('users.status'),
        filter: { type: 'select', options: ['active', 'blocked'].map((s) => ({ label: s, value: s })) },
      },
      cell: ({ row }) => <Badge variant={statusVariant(row.original.status)}>{row.original.status}</Badge>,
    },
    {
      accessorKey: 'allowed',
      header: t('users.allowed'),
      enableSorting: false,
      meta: { title: t('users.allowed') },
      cell: ({ row }) => (
        <Badge variant={row.original.allowed ? 'success' : 'destructive'}>
          {row.original.allowed ? t('users.allowed') : t('users.notAllowed')}
        </Badge>
      ),
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      cell: ({ row }) => <ImRowActions canWrite={canWrite} imUser={row.original} users={users} />,
    },
  ]
}

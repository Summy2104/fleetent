import type { ColumnDef } from '@tanstack/react-table'

import type { AuditLogRow } from '@/features/audit/api'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

export function buildAuditColumns({ t }: { t: Translate }): ColumnDef<AuditLogRow, unknown>[] {
  return [
    {
      accessorKey: 'created_at',
      header: t('audit.when'),
      meta: { title: t('audit.when'), filter: { type: 'date-range', placeholder: t('audit.dateRange') } },
      cell: ({ row }) => <span className="font-mono text-sm">{row.original.created_at}</span>,
    },
    {
      accessorKey: 'actor_user_id',
      header: t('audit.actor'),
      meta: { title: t('audit.actor'), filter: { type: 'text', placeholder: t('audit.actor') } },
      cell: ({ row }) => <span className="text-sm">{row.original.actor_user_id ?? '-'}</span>,
    },
    {
      accessorKey: 'action',
      header: t('audit.action'),
      meta: { title: t('audit.action'), filter: { type: 'text', placeholder: t('audit.action') } },
      cell: ({ row }) => <span className="text-sm">{row.original.action}</span>,
    },
    {
      id: 'resource',
      // Accessor on target_id so the column is filterable (TanStack requires an
      // accessorFn for getCanFilter); the cell still shows type:id.
      accessorFn: (row) => row.target_id ?? '',
      header: t('audit.resource'),
      enableSorting: false,
      meta: { title: t('audit.resource'), filter: { type: 'text', placeholder: t('audit.target') } },
      cell: ({ row }) => `${row.original.target_type ?? '-'}:${row.original.target_id ?? '-'}`,
    },
  ]
}

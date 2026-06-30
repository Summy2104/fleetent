import type { ColumnDef } from '@tanstack/react-table'

import type { AuditLogRow } from '@/features/audit/api'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

export function buildAuditColumns({ t }: { t: Translate }): ColumnDef<AuditLogRow, unknown>[] {
  return [
    {
      accessorKey: 'created_at',
      header: t('audit.when'),
      meta: { title: t('audit.when') },
      cell: ({ row }) => <span className="font-mono text-sm">{row.original.created_at}</span>,
    },
    {
      accessorKey: 'actor_user_id',
      header: t('audit.actor'),
      meta: { title: t('audit.actor') },
      cell: ({ row }) => <span className="text-sm">{row.original.actor_user_id ?? '-'}</span>,
    },
    {
      accessorKey: 'action',
      header: t('audit.action'),
      meta: { title: t('audit.action') },
      cell: ({ row }) => <span className="text-sm">{row.original.action}</span>,
    },
    {
      id: 'resource',
      header: t('audit.resource'),
      enableSorting: false,
      meta: { title: t('audit.resource') },
      cell: ({ row }) => `${row.original.target_type ?? '-'}:${row.original.target_id ?? '-'}`,
    },
  ]
}

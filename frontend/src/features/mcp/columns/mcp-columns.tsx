import type { ColumnDef } from '@tanstack/react-table'

import { Badge } from '@/components/base/badge'
import type { McpServerRecord } from '@/features/connectors/api'
import { McpRowActions } from '@/features/mcp/row-actions/mcp-row-actions'
import { statusVariant, TRANSPORTS } from '@/features/mcp/shared'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

export function buildMcpColumns({
  t,
  canWrite,
  scopeLabel,
  statusOptions,
  onEdit,
  onViewTools,
}: {
  t: Translate
  canWrite: boolean
  scopeLabel: (server: McpServerRecord) => string
  statusOptions: string[]
  onEdit: (server: McpServerRecord) => void
  onViewTools: (server: McpServerRecord) => void
}): ColumnDef<McpServerRecord, unknown>[] {
  return [
    {
      accessorKey: 'id',
      header: t('mcp.columnId'),
      meta: { title: t('mcp.columnId') },
      cell: ({ row }) => <span className="font-mono text-foreground text-sm">{row.original.id}</span>,
    },
    {
      id: 'scope',
      header: t('mcp.columnScope'),
      accessorFn: (server) => scopeLabel(server),
      meta: { title: t('mcp.columnScope') },
      cell: ({ row }) => <span className="text-muted-foreground text-sm">{scopeLabel(row.original)}</span>,
    },
    {
      accessorKey: 'transport',
      header: t('mcp.columnTransport'),
      filterFn: 'equals',
      meta: {
        title: t('mcp.columnTransport'),
        filter: { type: 'select', options: TRANSPORTS.map((transport) => ({ label: transport, value: transport })) },
      },
      cell: ({ row }) => <span className="text-muted-foreground text-sm">{row.original.transport}</span>,
    },
    {
      accessorKey: 'status',
      header: t('mcp.columnStatus'),
      filterFn: 'equals',
      meta: {
        title: t('mcp.columnStatus'),
        filter: { type: 'select', options: statusOptions.map((status) => ({ label: status, value: status })) },
      },
      cell: ({ row }) => <Badge variant={statusVariant(row.original.status)}>{row.original.status}</Badge>,
    },
    {
      accessorKey: 'enabled',
      header: t('mcp.columnEnabled'),
      filterFn: 'equalsString',
      meta: {
        title: t('mcp.columnEnabled'),
        filter: {
          type: 'select',
          options: [
            { label: t('mcp.enabled'), value: 'true' },
            { label: t('mcp.disabled'), value: 'false' },
          ],
        },
      },
      cell: ({ row }) => (
        <Badge variant={row.original.enabled ? 'success' : 'secondary'}>
          {row.original.enabled ? t('mcp.enabled') : t('mcp.disabled')}
        </Badge>
      ),
    },
    {
      accessorKey: 'tool_count',
      header: t('mcp.columnTools'),
      meta: { title: t('mcp.columnTools') },
      cell: ({ row }) => <span className="text-muted-foreground text-sm">{row.original.tool_count}</span>,
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => (
        <McpRowActions canWrite={canWrite} onEdit={onEdit} onViewTools={onViewTools} server={row.original} />
      ),
    },
  ]
}

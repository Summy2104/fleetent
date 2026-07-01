import type { ColumnDef } from '@tanstack/react-table'

import { Badge } from '@/components/base/badge'
import { Switch } from '@/components/ui/switch'
import type { AgentSkillBinding } from '@/features/agents/api'
import type { McpServerRecord } from '@/features/connectors/api'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

// An MCP server row carries whether it is bound to the current agent, so the toggle column
// can render checked state without a second lookup per cell.
export type McpServerRow = McpServerRecord & { bound: boolean }

export function buildMcpColumns({
  t,
  canWrite,
  onToggle,
}: {
  t: Translate
  canWrite: boolean
  onToggle: (serverId: string, bound: boolean) => void
}): ColumnDef<McpServerRow, unknown>[] {
  return [
    {
      accessorKey: 'id',
      header: t('agents.colName'),
      meta: { title: t('agents.colName') },
      cell: ({ row }) => <span className="font-mono text-foreground text-sm">{row.original.id}</span>,
    },
    {
      accessorKey: 'transport',
      header: t('agents.colTransport'),
      meta: { title: t('agents.colTransport') },
      cell: ({ row }) => <span className="text-muted-foreground text-sm">{row.original.transport}</span>,
    },
    {
      accessorKey: 'status',
      header: t('agents.colStatus'),
      meta: { title: t('agents.colStatus') },
      cell: ({ row }) => (
        <Badge variant={row.original.status === 'connected' ? 'success' : 'outline'}>{row.original.status}</Badge>
      ),
    },
    {
      accessorKey: 'tool_count',
      header: () => <span className="block text-right">{t('agents.colTools')}</span>,
      meta: { title: t('agents.colTools') },
      cell: ({ row }) => (
        <span className="block text-right text-muted-foreground text-sm tabular-nums">{row.original.tool_count}</span>
      ),
    },
    {
      id: 'toggle',
      header: '',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <Switch
            aria-label={t(row.original.bound ? 'agents.unbindMcp' : 'agents.bindMcp', { name: row.original.id })}
            checked={row.original.bound}
            disabled={!canWrite}
            onCheckedChange={(checked) => onToggle(row.original.id, checked)}
          />
        </div>
      ),
    },
  ]
}

export function buildSkillColumns({
  t,
  canWrite,
  onToggle,
}: {
  t: Translate
  canWrite: boolean
  onToggle: (skillName: string, enabled: boolean) => void
}): ColumnDef<AgentSkillBinding, unknown>[] {
  return [
    {
      accessorKey: 'skill_name',
      header: t('agents.colName'),
      meta: { title: t('agents.colName') },
      cell: ({ row }) => <span className="text-foreground text-sm">{row.original.skill_name}</span>,
    },
    {
      id: 'toggle',
      header: '',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <Switch
            aria-label={t(row.original.enabled ? 'agents.disableSkill' : 'agents.enableSkill', {
              name: row.original.skill_name,
            })}
            checked={row.original.enabled}
            disabled={!canWrite}
            onCheckedChange={(checked) => onToggle(row.original.skill_name, checked)}
          />
        </div>
      ),
    },
  ]
}

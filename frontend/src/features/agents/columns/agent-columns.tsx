import type { ColumnDef } from '@tanstack/react-table'

import { Badge } from '@/components/base/badge'
import type { AgentListItem } from '@/features/agents/api'
import { AgentRowActions } from '@/features/agents/row-actions/agent-row-actions'
import { AGENT_STATUSES, initials, statusVariant } from '@/features/agents/shared'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

export function buildAgentColumns({
  t,
  canWrite,
  onConfigure,
}: {
  t: Translate
  canWrite: boolean
  onConfigure: (agent: AgentListItem) => void
}): ColumnDef<AgentListItem, unknown>[] {
  return [
    {
      accessorKey: 'agent_name',
      header: t('agents.nameFieldLabel'),
      meta: { title: t('agents.nameFieldLabel') },
      cell: ({ row }) => {
        const agent = row.original
        return (
          <div className="flex items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-secondary font-semibold text-foreground text-xs">
              {initials(agent.agent_name)}
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <button
                  className="truncate font-semibold text-foreground text-sm hover:underline"
                  onClick={() => onConfigure(agent)}
                  type="button"
                >
                  {agent.agent_name}
                </button>
                {agent.is_default ? <Badge variant="default">{t('agents.defaultBadge')}</Badge> : null}
              </div>
              {agent.system_prompt ? (
                <span className="mt-0.5 line-clamp-1 block text-muted-foreground text-sm">{agent.system_prompt}</span>
              ) : null}
            </div>
          </div>
        )
      },
    },
    {
      accessorKey: 'status',
      header: t('agents.statusColumn'),
      filterFn: 'equals',
      meta: {
        title: t('agents.statusColumn'),
        filter: { type: 'select', options: AGENT_STATUSES.map((status) => ({ label: status, value: status })) },
      },
      cell: ({ row }) => <Badge variant={statusVariant(row.original.status)}>{row.original.status}</Badge>,
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => <AgentRowActions agent={row.original} canWrite={canWrite} onConfigure={onConfigure} />,
    },
  ]
}

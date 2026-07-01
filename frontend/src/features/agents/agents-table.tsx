import type * as React from 'react'
import { useMemo } from 'react'

import { DataTable } from '@/components/base/data-table'
import { type AgentListItem, useAgentsQuery } from '@/features/agents/api'
import { buildAgentColumns } from '@/features/agents/columns/agent-columns'
import { useT } from '@/i18n'

export function AgentsTable({
  canWrite,
  onConfigure,
  actions,
  title,
}: {
  canWrite: boolean
  onConfigure: (agent: AgentListItem) => void
  actions?: React.ReactNode
  title?: React.ReactNode
}): JSX.Element {
  const t = useT()
  const agents = useAgentsQuery()
  const columns = useMemo(() => buildAgentColumns({ canWrite, onConfigure, t }), [canWrite, onConfigure, t])

  return (
    <DataTable
      actions={actions}
      columns={columns}
      data={agents.data ?? []}
      emptyState={<div className="py-12 text-center text-muted-foreground text-sm">{t('agents.emptyState')}</div>}
      enableColumnVisibility
      enableGlobalFilter
      getRowId={(row) => row.agent_name}
      isLoading={agents.isPending}
      title={title}
    />
  )
}

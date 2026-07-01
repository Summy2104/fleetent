import { useCallback, useMemo } from 'react'

import { DataTable } from '@/components/base/data-table'
import { useAgentMcpQuery, useBindAgentMcpMutation, useUnbindAgentMcpMutation } from '@/features/agents/api'
import { buildMcpColumns, type McpServerRow } from '@/features/agents/columns/capability-columns'
import { useMcpServersQuery } from '@/features/connectors/api'
import { useT } from '@/i18n'

// The MCP catalog is the full server list; each row's toggle reflects whether it is bound to
// this agent (bind/unbind are the two backend calls). Kept as its own tab from skills because
// binding an MCP server and enabling a skill are different mechanisms.
export function McpServersTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT()

  const servers = useMcpServersQuery()
  const boundMcp = useAgentMcpQuery(agentName)
  const bindMcp = useBindAgentMcpMutation(agentName).mutateAsync
  const unbindMcp = useUnbindAgentMcpMutation(agentName).mutateAsync

  const boundSet = useMemo(() => new Set(boundMcp.data ?? []), [boundMcp.data])
  const rows = useMemo<McpServerRow[]>(
    () => (servers.data ?? []).map((server) => ({ ...server, bound: boundSet.has(server.id) })),
    [servers.data, boundSet]
  )
  const onToggle = useCallback(
    (serverId: string, bound: boolean) => {
      void (bound ? bindMcp(serverId) : unbindMcp(serverId))
    },
    [bindMcp, unbindMcp]
  )
  const columns = useMemo(() => buildMcpColumns({ t, canWrite, onToggle }), [t, canWrite, onToggle])

  return (
    <DataTable
      columns={columns}
      data={rows}
      emptyState={<div className="py-10 text-center text-muted-foreground text-sm">{t('agents.noMcpServers')}</div>}
      enableColumnVisibility
      enableGlobalFilter
      getRowId={(row) => row.id}
      isLoading={servers.isPending}
      title={t('agents.mcpServers')}
    />
  )
}

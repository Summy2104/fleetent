import type * as React from 'react'
import { useMemo, useState } from 'react'

import { DataTable } from '@/components/base/data-table'
import { useAgentsQuery } from '@/features/agents/api'
import { type McpServerRecord, useMcpServersQuery } from '@/features/connectors/api'
import { buildMcpColumns } from '@/features/mcp/columns/mcp-columns'
import { ServerDialog } from '@/features/mcp/dialogs/server-dialog'
import { ToolsDialog } from '@/features/mcp/dialogs/tools-dialog'
import { useT } from '@/i18n'

export function McpTable({
  canWrite,
  actions,
  title,
}: {
  canWrite: boolean
  actions?: React.ReactNode
  title?: React.ReactNode
}): JSX.Element {
  const t = useT()
  const servers = useMcpServersQuery()
  const agents = useAgentsQuery()
  const [editing, setEditing] = useState<McpServerRecord | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [toolsFor, setToolsFor] = useState<string | null>(null)

  const agentNameById = useMemo(
    () =>
      Object.fromEntries(
        (agents.data ?? []).flatMap((agent) => (agent.agent_id == null ? [] : [[agent.agent_id, agent.agent_name]]))
      ),
    [agents.data]
  )

  const scopeLabel = useMemo(
    () =>
      (server: McpServerRecord): string =>
        server.agent_id == null
          ? t('mcp.scopeGlobalOption')
          : (agentNameById[server.agent_id] ?? t('mcp.scopeAgentFallback', { id: server.agent_id })),
    [agentNameById, t]
  )

  const openEdit = useMemo(
    () =>
      (server: McpServerRecord): void => {
        setEditing(server)
        setEditOpen(true)
      },
    []
  )
  const openTools = useMemo(
    () =>
      (server: McpServerRecord): void => {
        setToolsFor(server.id)
      },
    []
  )

  const statusOptions = useMemo(
    () => Array.from(new Set((servers.data ?? []).map((server) => server.status))),
    [servers.data]
  )

  const columns = useMemo(
    () => buildMcpColumns({ canWrite, onEdit: openEdit, onViewTools: openTools, scopeLabel, statusOptions, t }),
    [canWrite, openEdit, openTools, scopeLabel, statusOptions, t]
  )

  return (
    <>
      <DataTable
        actions={actions}
        columns={columns}
        data={servers.data ?? []}
        emptyState={<div className="py-12 text-center text-muted-foreground text-sm">{t('mcp.emptyState')}</div>}
        enableColumnVisibility
        enableGlobalFilter
        getRowId={(row) => row.id}
        isLoading={servers.isPending}
        title={title}
      />

      {canWrite ? (
        <ServerDialog agents={agents.data ?? []} editing={editing} onOpenChange={setEditOpen} open={editOpen} />
      ) : null}
      <ToolsDialog onOpenChange={(open) => !open && setToolsFor(null)} serverId={toolsFor} />
    </>
  )
}

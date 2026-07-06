import { useState } from 'react'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useAgentsQuery } from '@/features/agents/api'
import { ServerDialog } from '@/features/mcp/dialogs/server-dialog'
import { McpTable } from '@/features/mcp/mcp-table'
import { useAdminMeQuery } from '@/features/mcp/shared'
import { useT } from '@/i18n'

export function McpPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const agents = useAgentsQuery()
  const [createOpen, setCreateOpen] = useState(false)

  const canWrite = me.data?.role !== 'viewer'

  const actions = canWrite ? (
    <Button onClick={() => setCreateOpen(true)}>
      <Plus className="size-4" /> {t('mcp.addServer')}
    </Button>
  ) : undefined

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-semibold text-xl tracking-tight">{t('mcp.pageTitle')}</h2>
        <p className="mt-1 text-muted-foreground text-sm">{t('mcp.pageDescription')}</p>
      </div>

      <McpTable actions={actions} canWrite={canWrite} title={t('mcp.title')} />

      {canWrite ? (
        <ServerDialog agents={agents.data ?? []} editing={null} onOpenChange={setCreateOpen} open={createOpen} />
      ) : null}
    </div>
  )
}

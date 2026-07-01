import { useState } from 'react'
import { Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { AgentsTable } from '@/features/agents/agents-table'
import type { AgentListItem } from '@/features/agents/api'
import { CreateAgentDialog } from '@/features/agents/dialogs/create-agent-dialog'
import { useAdminMeQuery } from '@/features/agents/shared'
import { useT } from '@/i18n'

export function AgentsPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const navigate = useNavigate()
  const [createOpen, setCreateOpen] = useState(false)

  const canWrite = me.data?.role !== 'viewer'

  const actions = canWrite ? (
    <Button onClick={() => setCreateOpen(true)}>
      <Plus className="size-4" /> {t('agents.newAgent')}
    </Button>
  ) : undefined

  return (
    <div className="space-y-6">
      <AgentsTable
        actions={actions}
        canWrite={canWrite}
        onConfigure={(agent: AgentListItem) => navigate(`/agents/${agent.agent_name}/configure`)}
        title={t('agents.title')}
      />

      {canWrite ? <CreateAgentDialog onOpenChange={setCreateOpen} open={createOpen} /> : null}
    </div>
  )
}

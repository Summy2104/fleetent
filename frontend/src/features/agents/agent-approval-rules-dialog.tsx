import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  useAgentMcpApprovalRulesQuery,
  useSetAgentMcpApprovalRulesMutation,
} from '@/features/agents/api'
import { useMcpServerToolsQuery } from '@/features/connectors/api'
import {
  type ApprovalRuleForm,
  approvalRulesComplete,
  formToRules,
  rulesToForm,
} from '@/features/mcp/approval-rules'
import { ApprovalRulesEditor } from '@/features/mcp/dialogs/approval-rules-editor'
import { useT } from '@/i18n'

// Per-(agent, server) approval-rules editor. Tool names are seeded from the server's live tool
// list (probed on open); saving writes the binding's approval_rules via the agent API.
export function AgentApprovalRulesDialog({
  agentName,
  serverId,
  onOpenChange,
}: {
  agentName: string
  serverId: string | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const open = serverId !== null
  const rulesQuery = useAgentMcpApprovalRulesQuery(agentName, serverId)
  const toolsQuery = useMcpServerToolsQuery(serverId)
  const save = useSetAgentMcpApprovalRulesMutation(agentName, serverId ?? '')
  const [form, setForm] = useState<ApprovalRuleForm[]>([])

  // Rehydrate the editor from the stored rules each time a server's dialog opens.
  useEffect(() => {
    if (open && rulesQuery.data) setForm(rulesToForm(rulesQuery.data))
  }, [open, rulesQuery.data])

  const toolOptions = (toolsQuery.data?.tools ?? []).map((tool) => tool.name)

  const submit = async (): Promise<void> => {
    await save.mutateAsync(formToRules(form))
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className="grid max-h-[90vh] grid-rows-[auto_minmax(0,1fr)_auto]">
        <DialogHeader>
          <DialogTitle>{t('agents.approvalRulesTitle', { name: serverId ?? '' })}</DialogTitle>
          <DialogDescription>{t('agents.approvalRulesDescription')}</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 overflow-y-auto pr-1">
          <ApprovalRulesEditor onChange={setForm} toolOptions={toolOptions} value={form} />
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('agents.approvalCancel')}
          </Button>
          <Button
            disabled={!approvalRulesComplete(form) || save.isPending}
            onClick={() => void submit()}
          >
            {t('agents.approvalSave')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

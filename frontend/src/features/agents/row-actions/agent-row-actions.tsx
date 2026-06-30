import { useState } from 'react'
import { MoreVertical, Trash2 } from 'lucide-react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  type AgentListItem,
  useAgentLifecycleMutation,
  useClearDefaultAgentMutation,
  useCloneAgentMutation,
  useDeleteAgentMutation,
  useSetDefaultAgentMutation,
} from '@/features/agents/api'
import { useT } from '@/i18n'

export function AgentRowActions({
  agent,
  canWrite,
  onConfigure,
}: {
  agent: AgentListItem
  canWrite: boolean
  onConfigure: (agent: AgentListItem) => void
}): JSX.Element {
  const t = useT()
  const disable = useAgentLifecycleMutation(agent.agent_name, 'disable')
  const enable = useAgentLifecycleMutation(agent.agent_name, 'enable')
  const archive = useAgentLifecycleMutation(agent.agent_name, 'archive', { 'X-Confirm': 'true' })
  const restore = useAgentLifecycleMutation(agent.agent_name, 'restore')
  const clone = useCloneAgentMutation(agent.agent_name)
  const remove = useDeleteAgentMutation(agent.agent_name)
  const setDefault = useSetDefaultAgentMutation(agent.agent_name)
  const clearDefault = useClearDefaultAgentMutation()
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <div className="flex justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button aria-label={t('agents.actionsFor', { name: agent.agent_name })} size="icon" variant="ghost">
              <MoreVertical className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => onConfigure(agent)}>{t('agents.configure')}</DropdownMenuItem>
          {canWrite ? (
            <>
              <DropdownMenuItem
                onClick={() => (agent.status === 'disabled' ? void enable.mutateAsync() : void disable.mutateAsync())}
              >
                {agent.status === 'disabled' ? t('agents.enable') : t('agents.disable')}
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => (agent.status === 'archived' ? void restore.mutateAsync() : void archive.mutateAsync())}
              >
                {agent.status === 'archived' ? t('agents.restore') : t('agents.archive')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => void clone.mutateAsync(`${agent.agent_name}-copy`)}>
                {t('agents.clone')}
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => (agent.is_default ? void clearDefault.mutateAsync() : void setDefault.mutateAsync())}
              >
                {agent.is_default ? t('agents.clearDefault') : t('agents.setAsDefault')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setTimeout(() => setConfirmDelete(true), 0)} variant="destructive">
                <Trash2 /> {t('agents.delete')}
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('agents.deleteTitle', { name: agent.agent_name })}</AlertDialogTitle>
            <AlertDialogDescription>{t('agents.deleteDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void remove.mutateAsync()}>{t('agents.delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

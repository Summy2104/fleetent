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

// A pending confirmation captured when a state-changing action is picked from the
// menu. Rendered by a single AlertDialog so every toggle shares one confirm surface.
type PendingConfirm = {
  title: string
  description: string
  confirmLabel: string
  run: () => void
}

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
  const [pending, setPending] = useState<PendingConfirm | null>(null)

  // Defer opening the dialog to the next tick so the dropdown finishes closing
  // and does not fight the dialog for focus.
  const askConfirm = (confirm: PendingConfirm) => setTimeout(() => setPending(confirm), 0)

  const name = agent.agent_name
  const enableToggle: PendingConfirm =
    agent.status === 'disabled'
      ? {
          title: t('agents.enableTitle', { name }),
          description: t('agents.enableDescription'),
          confirmLabel: t('agents.enable'),
          run: () => void enable.mutateAsync(),
        }
      : {
          title: t('agents.disableTitle', { name }),
          description: t('agents.disableDescription'),
          confirmLabel: t('agents.disable'),
          run: () => void disable.mutateAsync(),
        }
  const archiveToggle: PendingConfirm =
    agent.status === 'archived'
      ? {
          title: t('agents.restoreTitle', { name }),
          description: t('agents.restoreDescription'),
          confirmLabel: t('agents.restore'),
          run: () => void restore.mutateAsync(),
        }
      : {
          title: t('agents.archiveTitle', { name }),
          description: t('agents.archiveDescription'),
          confirmLabel: t('agents.archive'),
          run: () => void archive.mutateAsync(),
        }
  const defaultToggle: PendingConfirm = agent.is_default
    ? {
        title: t('agents.clearDefaultTitle'),
        description: t('agents.clearDefaultDescription'),
        confirmLabel: t('agents.clearDefault'),
        run: () => void clearDefault.mutateAsync(),
      }
    : {
        title: t('agents.setDefaultTitle', { name }),
        description: t('agents.setDefaultDescription'),
        confirmLabel: t('agents.setAsDefault'),
        run: () => void setDefault.mutateAsync(),
      }

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
              <DropdownMenuItem onClick={() => askConfirm(enableToggle)}>{enableToggle.confirmLabel}</DropdownMenuItem>
              <DropdownMenuItem onClick={() => askConfirm(archiveToggle)}>
                {archiveToggle.confirmLabel}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => void clone.mutateAsync(`${agent.agent_name}-copy`)}>
                {t('agents.clone')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => askConfirm(defaultToggle)}>
                {defaultToggle.confirmLabel}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() =>
                  askConfirm({
                    title: t('agents.deleteTitle', { name }),
                    description: t('agents.deleteDescription'),
                    confirmLabel: t('agents.delete'),
                    run: () => void remove.mutateAsync(),
                  })
                }
                variant="destructive"
              >
                <Trash2 /> {t('agents.delete')}
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog onOpenChange={(open) => (open ? undefined : setPending(null))} open={pending !== null}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{pending?.title}</AlertDialogTitle>
            <AlertDialogDescription>{pending?.description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                pending?.run()
                setPending(null)
              }}
            >
              {pending?.confirmLabel}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

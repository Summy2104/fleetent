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
import { type SkillListItem, useForcePublishSkillMutation, useSkillLifecycleMutation } from '@/features/skills/api'
import { useT } from '@/i18n'

export function SkillRowActions({
  skill,
  canWrite,
  proposalCount,
  backflowCount,
  onViewContent,
  onVersions,
  onBindings,
  onProposals,
  onBackflow,
}: {
  skill: SkillListItem
  canWrite: boolean
  proposalCount: number
  backflowCount: number
  onViewContent: () => void
  onVersions: () => void
  onBindings: () => void
  onProposals: () => void
  onBackflow: () => void
}): JSX.Element {
  const t = useT()
  const toggle = useSkillLifecycleMutation(skill.name, skill.global_enabled ? 'disable' : 'enable')
  const restore = useSkillLifecycleMutation(skill.name, 'restore')
  const archive = useSkillLifecycleMutation(skill.name, 'delete')
  const forcePublish = useForcePublishSkillMutation(skill.name)
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [confirmForcePublish, setConfirmForcePublish] = useState(false)
  const [confirmDisable, setConfirmDisable] = useState(false)
  const canForcePublish = skill.audit_verdict === 'rejected' || skill.status === 'quarantined'

  const runArchive = async (): Promise<void> => {
    await archive.mutateAsync()
    setConfirmArchive(false)
  }

  const runForcePublish = async (): Promise<void> => {
    await forcePublish.mutateAsync()
    setConfirmForcePublish(false)
  }

  const runDisable = async (): Promise<void> => {
    await toggle.mutateAsync()
    setConfirmDisable(false)
  }

  return (
    <div className="flex justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button aria-label={t('skills.actionsFor', { name: skill.name })} size="icon" variant="ghost">
              <MoreVertical className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setTimeout(onViewContent, 0)}>{t('skills.viewContent')}</DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTimeout(onVersions, 0)}>{t('skills.versions')}</DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTimeout(onBindings, 0)}>{t('skills.agentBindings')}</DropdownMenuItem>
          <DropdownMenuItem disabled={proposalCount === 0} onClick={() => setTimeout(onProposals, 0)}>
            {t('skills.proposals')}
            {proposalCount > 0 ? ` (${proposalCount})` : ''}
          </DropdownMenuItem>
          <DropdownMenuItem disabled={backflowCount === 0} onClick={() => setTimeout(onBackflow, 0)}>
            {t('skills.backflow')}
            {backflowCount > 0 ? ` (${backflowCount})` : ''}
          </DropdownMenuItem>
          {canWrite ? (
            <>
              <DropdownMenuSeparator />
              {skill.global_enabled ? (
                <DropdownMenuItem onClick={() => setTimeout(() => setConfirmDisable(true), 0)} variant="destructive">
                  {t('skills.disable')}
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem onClick={() => void toggle.mutateAsync()}>{t('skills.enable')}</DropdownMenuItem>
              )}
              {skill.status === 'archived' ? (
                <DropdownMenuItem onClick={() => void restore.mutateAsync()}>{t('skills.restore')}</DropdownMenuItem>
              ) : (
                <DropdownMenuItem onClick={() => setTimeout(() => setConfirmArchive(true), 0)} variant="destructive">
                  <Trash2 /> {t('skills.archive')}
                </DropdownMenuItem>
              )}
              {canForcePublish ? (
                <DropdownMenuItem
                  onClick={() => setTimeout(() => setConfirmForcePublish(true), 0)}
                  variant="destructive"
                >
                  {t('skills.forcePublish')}
                </DropdownMenuItem>
              ) : null}
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog onOpenChange={setConfirmDisable} open={confirmDisable}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('skills.disableConfirmTitle', { name: skill.name })}</AlertDialogTitle>
            <AlertDialogDescription>{t('skills.disableConfirmDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('skills.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runDisable()}>{t('skills.disable')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog onOpenChange={setConfirmArchive} open={confirmArchive}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('skills.archiveConfirmTitle', { name: skill.name })}</AlertDialogTitle>
            <AlertDialogDescription>{t('skills.archiveConfirmDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('skills.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runArchive()}>{t('skills.archive')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog onOpenChange={setConfirmForcePublish} open={confirmForcePublish}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('skills.forcePublishConfirmTitle', { name: skill.name })}</AlertDialogTitle>
            <AlertDialogDescription>{t('skills.forcePublishConfirmDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('skills.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runForcePublish()}>{t('skills.forcePublish')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

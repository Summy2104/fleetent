import { useEffect, useState } from 'react'
import { GitCompare, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  type BackflowProposal,
  type SkillProposal,
  useBackflowAcceptMutation,
  useBackflowForkMutation,
  useBackflowRejectMutation,
  useOpenBackflowPrMutation,
  useSetSkillAgentBindingMutation,
  useSkillAgentBindingsQuery,
  useSkillContentQuery,
  useSkillDiffQuery,
  useSkillProposalDiffQuery,
  useSkillVersionsQuery,
  useSyncBackflowMutation,
} from '@/features/skills/api'
import { useT } from '@/i18n'

export function CodeBlock({ children }: { children: string }): JSX.Element {
  return (
    <pre className="max-h-80 overflow-auto rounded-md border border-border bg-secondary/50 p-4 font-mono text-foreground text-sm">
      {children}
    </pre>
  )
}

// ─────────────────────────── Content dialog ───────────────────────────

export function ContentDialog({
  skillName,
  onOpenChange,
}: {
  skillName: string | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const content = useSkillContentQuery(skillName)
  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(skillName)}>
      <DialogContent className="sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>{t('skills.contentTitle', { name: skillName ?? '' })}</DialogTitle>
          <DialogDescription>{t('skills.contentDescription')}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[70vh] overflow-auto">
          <CodeBlock>{content.data?.content ?? ''}</CodeBlock>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Versions dialog ───────────────────────────

export function VersionsDialog({
  skillName,
  onOpenChange,
}: {
  skillName: string | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const [selectedRef, setSelectedRef] = useState<string | null>(null)
  const versions = useSkillVersionsQuery(skillName, Boolean(skillName))
  const diff = useSkillDiffQuery(skillName, selectedRef, Boolean(selectedRef))

  useEffect(() => {
    if (!skillName) setSelectedRef(null)
  }, [skillName])

  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(skillName)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('skills.versionsTitle', { name: skillName ?? '' })}</DialogTitle>
          <DialogDescription>{t('skills.versionsDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          {(versions.data ?? []).map((version) => (
            <div
              className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
              key={version.sha}
            >
              <div className="min-w-0">
                <p className="font-mono text-foreground text-sm">{version.sha.slice(0, 10)}</p>
                <p className="truncate text-muted-foreground text-sm">{version.message}</p>
              </div>
              <Button
                onClick={() => setSelectedRef(version.sha)}
                size="sm"
                variant={selectedRef === version.sha ? 'secondary' : 'outline'}
              >
                <GitCompare className="size-4" /> {t('skills.diff')}
              </Button>
            </div>
          ))}
          {versions.data && versions.data.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t('skills.noVersionHistory')}</p>
          ) : null}
        </div>
        {diff.data?.diff ? <CodeBlock>{diff.data.diff}</CodeBlock> : null}
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Agent bindings dialog ───────────────────────────

function BindingToggle({
  agentId,
  label,
  enabled,
  skillName,
  canWrite,
}: {
  agentId: number
  label: string
  enabled: boolean
  skillName: string
  canWrite: boolean
}): JSX.Element {
  const t = useT()
  const update = useSetSkillAgentBindingMutation(skillName, agentId)
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
      <Label className="font-medium text-foreground text-sm" htmlFor={`binding-${agentId}`}>
        {label}
      </Label>
      {canWrite ? (
        <Switch
          checked={enabled}
          id={`binding-${agentId}`}
          onCheckedChange={(checked) => update.mutate({ enabled: checked })}
        />
      ) : (
        <span className="text-muted-foreground text-xs">{enabled ? t('skills.enabled') : t('skills.disabled')}</span>
      )}
    </div>
  )
}

export function BindingsDialog({
  skillName,
  canWrite,
  onOpenChange,
}: {
  skillName: string | null
  canWrite: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const bindings = useSkillAgentBindingsQuery(skillName)
  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(skillName)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('skills.bindingsTitle', { name: skillName ?? '' })}</DialogTitle>
          <DialogDescription>{t('skills.bindingsDescription')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {(bindings.data ?? []).map((binding) => (
            <BindingToggle
              agentId={binding.agent_id}
              canWrite={canWrite}
              enabled={binding.enabled}
              key={binding.agent_id}
              label={binding.name ?? String(binding.agent_id)}
              skillName={skillName ?? ''}
            />
          ))}
          {bindings.data && bindings.data.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t('skills.noAgentsBound')}</p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Proposal diff dialog ───────────────────────────

export function ProposalDiffDialog({
  proposalId,
  onOpenChange,
}: {
  proposalId: string | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const diff = useSkillProposalDiffQuery(proposalId, Boolean(proposalId))
  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(proposalId)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('skills.proposalDiffTitle')}</DialogTitle>
          <DialogDescription>{t('skills.proposalDiffDescription')}</DialogDescription>
        </DialogHeader>
        {diff.data?.diff ? (
          <CodeBlock>{diff.data.diff}</CodeBlock>
        ) : (
          <p className="text-muted-foreground text-sm">{t('skills.noProposalDiff')}</p>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Proposals dialog (per skill) ───────────────────────────

export function ProposalsDialog({
  skillName,
  proposals,
  onDiff,
  onOpenChange,
}: {
  skillName: string | null
  proposals: SkillProposal[]
  onDiff: (id: string) => void
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(skillName)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('skills.proposalsTitle', { name: skillName ?? '' })}</DialogTitle>
          <DialogDescription>{t('skills.proposalsDescription')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {proposals.map((proposal) => (
            <div
              className="flex items-start justify-between gap-3 rounded-md border border-border px-3 py-2"
              key={proposal.id}
            >
              <div className="min-w-0 space-y-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-foreground text-sm">{proposal.type}</span>
                  <Badge variant={proposal.risk_level === 'high' ? 'destructive' : 'outline'}>
                    {proposal.risk_level}
                  </Badge>
                </span>
                <p className="text-muted-foreground text-sm">{proposal.reason}</p>
              </div>
              {proposal.has_diff ? (
                <Button onClick={() => onDiff(proposal.id)} size="sm" variant="outline">
                  <GitCompare className="size-4" /> {t('skills.diff')}
                </Button>
              ) : null}
            </div>
          ))}
          {proposals.length === 0 ? <p className="text-muted-foreground text-sm">{t('skills.noProposals')}</p> : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Backflow proposal card + dialog ───────────────────────────

function BackflowProposalCard({
  onViewDiff,
  proposal,
  gitopsEnabled = false,
}: {
  onViewDiff: (id: number) => void
  proposal: BackflowProposal
  gitopsEnabled?: boolean
}): JSX.Element {
  const accept = useBackflowAcceptMutation(proposal.id)
  const reject = useBackflowRejectMutation(proposal.id)
  const fork = useBackflowForkMutation(proposal.id)
  const openPr = useOpenBackflowPrMutation(proposal.id)
  // A PR can still be opened while the proposal is only backed up (or a prior attempt
  // deferred); once it is open/merged there is nothing to open.
  const canOpenPr = gitopsEnabled && (!proposal.pr_state || ['backed_up', 'deferred'].includes(proposal.pr_state))

  const onAccept = async (): Promise<void> => {
    if (proposal.conflict) {
      // Pool advanced past the proposal's base — require an explicit override decision.
      if (!window.confirm(`Pool advanced for ${proposal.skill_name}. Override pool head?`)) {
        return
      }
      await accept.mutateAsync({ confirm: true })
      return
    }
    await accept.mutateAsync({})
  }

  const onFork = async (): Promise<void> => {
    const forkName = window.prompt(`New skill name to fork ${proposal.skill_name} as`, `${proposal.skill_name}-fork`)
    if (!forkName) {
      return
    }
    await fork.mutateAsync({ fork_name: forkName })
  }

  return (
    <article className="rounded-xl border bg-white p-4" key={proposal.id}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold text-sm">{proposal.skill_name}</p>
          <p className="text-muted-foreground text-sm">
            {`from ${proposal.agent_name ?? `agent ${proposal.agent_id}`}${proposal.conflict ? ' · conflict' : ''}`}
          </p>
          {proposal.pr_state ? (
            <span className="mt-1 flex items-center gap-2">
              <Badge variant="secondary">{proposal.pr_state}</Badge>
              {proposal.pr_url ? (
                <a className="text-primary text-sm underline" href={proposal.pr_url} rel="noreferrer" target="_blank">
                  {proposal.pr_branch ?? 'PR'}
                </a>
              ) : proposal.pr_branch ? (
                <span className="font-mono text-muted-foreground text-xs">{proposal.pr_branch}</span>
              ) : null}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <button
            className="rounded-md bg-secondary px-3 py-2 font-medium text-sm"
            onClick={() => onViewDiff(proposal.id)}
            type="button"
          >
            {`View backflow diff for ${proposal.id}`}
          </button>
          {canOpenPr ? (
            <button
              className="rounded-md bg-secondary px-3 py-2 font-medium text-sm"
              onClick={() => void openPr.mutateAsync()}
              type="button"
            >
              {`Open PR ${proposal.id}`}
            </button>
          ) : null}
          <button
            className="rounded-md bg-primary px-3 py-2 font-medium text-primary-foreground text-sm"
            onClick={() => void onAccept()}
            type="button"
          >
            {`Accept backflow ${proposal.id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 font-medium text-sm"
            onClick={() => void reject.mutateAsync()}
            type="button"
          >
            {`Reject backflow ${proposal.id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 font-medium text-sm"
            onClick={() => void onFork()}
            type="button"
          >
            {`Fork backflow ${proposal.id}`}
          </button>
        </div>
      </div>
    </article>
  )
}

export function BackflowDialog({
  skillName,
  proposals,
  onViewDiff,
  diffText,
  onOpenChange,
  gitopsEnabled = false,
}: {
  skillName: string | null
  proposals: BackflowProposal[]
  onViewDiff: (id: number) => void
  diffText: string | null
  onOpenChange: (open: boolean) => void
  gitopsEnabled?: boolean
}): JSX.Element {
  const t = useT()
  const syncBackflow = useSyncBackflowMutation()
  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(skillName)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('skills.backflowTitle', { name: skillName ?? '' })}</DialogTitle>
          <DialogDescription>{t('skills.backflowDescription')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {gitopsEnabled ? (
            <div className="flex justify-end">
              <Button
                disabled={syncBackflow.isPending}
                onClick={() => void syncBackflow.mutateAsync()}
                size="sm"
                variant="outline"
              >
                <RefreshCw className="size-4" /> Sync backflow
              </Button>
            </div>
          ) : null}
          {proposals.map((proposal) => (
            <BackflowProposalCard
              gitopsEnabled={gitopsEnabled}
              key={proposal.id}
              onViewDiff={onViewDiff}
              proposal={proposal}
            />
          ))}
          {proposals.length === 0 ? <p className="text-muted-foreground text-sm">{t('skills.noBackflow')}</p> : null}
          {diffText ? (
            <pre className="mt-2 max-h-72 overflow-auto rounded-xl bg-slate-950 p-4 text-slate-50 text-sm">
              {diffText}
            </pre>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}

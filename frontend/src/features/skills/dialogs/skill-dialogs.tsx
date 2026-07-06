import { useEffect, useState } from 'react'
import { GitCompare, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  type BackflowDiff,
  type BackflowProposal,
  bitbucketPrCreateUrl,
  type SkillGitStatus,
  type SkillProposal,
  useBackflowDiffQuery,
  useSetSkillAgentBindingMutation,
  useSkillAgentBindingsQuery,
  useSkillContentQuery,
  useSkillDiffQuery,
  useSkillProposalDiffQuery,
  useSkillVersionsQuery,
  useSyncBackflowMutation,
} from '@/features/skills/api'
import { useTransientFlag } from '@/features/skills/shared'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'

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

// Read-only: the platform does not accept/reject/fork backflow. It records the agent's edit,
// pushes it to a backup branch, and shows the diff; adoption is a human PR in the git host.
function BackflowProposalCard({
  onViewDiff,
  proposal,
}: {
  onViewDiff: (id: number) => void
  proposal: BackflowProposal
}): JSX.Element {
  return (
    <article className="rounded-lg border border-border p-4" key={proposal.id}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold text-sm">{proposal.skill_name}</p>
          <p className="text-muted-foreground text-sm">
            {`from ${proposal.agent_name ?? `agent ${proposal.agent_id}`}${proposal.conflict ? ' · conflict' : ''}`}
          </p>
          {proposal.pr_branch ? (
            <span className="mt-1 flex items-center gap-2">
              {proposal.pr_state ? <Badge variant="secondary">{proposal.pr_state}</Badge> : null}
              <span className="font-mono text-muted-foreground text-xs">{proposal.pr_branch}</span>
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
        </div>
      </div>
    </article>
  )
}

function DiffPre({ children }: { children: string }): JSX.Element {
  return (
    <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-border bg-secondary/50 p-4 font-mono text-foreground text-sm">
      {children}
    </pre>
  )
}

export function BackflowDialog({
  skillName,
  proposals,
  onViewDiff,
  diff,
  diffLoading = false,
  onOpenChange,
  gitopsEnabled = false,
}: {
  skillName: string | null
  proposals: BackflowProposal[]
  onViewDiff: (id: number) => void
  diff: BackflowDiff | null
  diffLoading?: boolean
  onOpenChange: (open: boolean) => void
  gitopsEnabled?: boolean
}): JSX.Element {
  const t = useT()
  const syncBackflow = useSyncBackflowMutation()
  const pushed = useTransientFlag(syncBackflow.isSuccess)
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
                <RefreshCw className={cn('size-4', syncBackflow.isPending && 'animate-spin')} />
                {syncBackflow.isPending
                  ? t('skills.backflowSyncing')
                  : pushed
                    ? t('skills.backflowSynced')
                    : t('skills.backflowSyncNow')}
              </Button>
            </div>
          ) : null}
          {proposals.map((proposal) => (
            <BackflowProposalCard key={proposal.id} onViewDiff={onViewDiff} proposal={proposal} />
          ))}
          {proposals.length === 0 ? <p className="text-muted-foreground text-sm">{t('skills.noBackflow')}</p> : null}
          <BackflowDiffView diff={diff} loading={diffLoading} />
        </div>
      </DialogContent>
    </Dialog>
  )
}

// Dual diff (vs the base the agent started from / vs the current pool). diff_vs_head can be
// empty when the pool already matches the edit, so diff_vs_base usually carries the content.
export function BackflowDiffView({
  diff,
  loading = false,
}: {
  diff: BackflowDiff | null
  loading?: boolean
}): JSX.Element | null {
  const t = useT()
  if (loading) {
    return <p className="mt-2 text-muted-foreground text-sm">{t('skills.diffLoading')}</p>
  }
  if (!diff) {
    return null
  }
  return (
    <div className="mt-2 space-y-2">
      {diff.conflict ? (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-amber-900 text-sm dark:bg-amber-950/30 dark:text-amber-200">
          {t('skills.backflowConflict')}
        </p>
      ) : null}
      {diff.diff_vs_base ? (
        <div>
          <p className="font-medium text-muted-foreground text-xs">{t('skills.diffVsBase')}</p>
          <DiffPre>{diff.diff_vs_base}</DiffPre>
        </div>
      ) : null}
      {diff.diff_vs_head ? (
        <div>
          <p className="font-medium text-muted-foreground text-xs">{t('skills.diffVsHead')}</p>
          <DiffPre>{diff.diff_vs_head}</DiffPre>
        </div>
      ) : null}
      {!diff.diff_vs_base && !diff.diff_vs_head ? (
        <p className="text-muted-foreground text-sm">{t('skills.diffNone')}</p>
      ) : null}
    </div>
  )
}

// ─────────────────────────── Aggregate backflow worklist ───────────────────────────

// One row per (agent, skill), grouped by agent, with a one-click "create PR" link per agent
// (source = that agent's aggregate backup branch -> the authority branch). Read-only: adoption
// is a human PR in the git host. Landed proposals (already merged + synced back) are hidden.
export function BackflowWorklist({
  proposals,
  gitStatus,
}: {
  proposals: BackflowProposal[]
  gitStatus: SkillGitStatus | undefined
}): JSX.Element | null {
  const t = useT()
  const syncBackflow = useSyncBackflowMutation()
  const pushed = useTransientFlag(syncBackflow.isSuccess)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const diff = useBackflowDiffQuery(selectedId, selectedId !== null)

  const active = proposals.filter((p) => p.pr_state !== 'merged' && p.pr_state !== 'closed')
  if (active.length === 0) {
    return null
  }

  const groups = new Map<number, { branch: string | null; items: BackflowProposal[]; name: string }>()
  for (const proposal of active) {
    const group = groups.get(proposal.agent_id) ?? {
      branch: null,
      items: [],
      name: proposal.agent_name ?? `agent ${proposal.agent_id}`,
    }
    group.items.push(proposal)
    if (proposal.pr_branch) {
      group.branch = proposal.pr_branch
    }
    groups.set(proposal.agent_id, group)
  }
  const dest = gitStatus?.branch ?? 'main'

  return (
    <section className="mb-4 space-y-3 rounded-lg border border-border p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold text-foreground text-sm">{t('skills.backflowWorklistTitle')}</h3>
          <p className="text-muted-foreground text-sm">{t('skills.backflowWorklistDescription')}</p>
        </div>
        <Button
          disabled={syncBackflow.isPending}
          onClick={() => void syncBackflow.mutateAsync()}
          size="sm"
          variant="outline"
        >
          <RefreshCw className={cn('size-4', syncBackflow.isPending && 'animate-spin')} />
          {syncBackflow.isPending
            ? t('skills.backflowSyncing')
            : pushed
              ? t('skills.backflowSynced')
              : t('skills.backflowSyncNow')}
        </Button>
      </div>
      <div className="space-y-3">
        {[...groups.entries()].map(([agentId, group]) => {
          const prUrl = group.branch ? bitbucketPrCreateUrl(gitStatus?.remote_url, group.branch, dest) : null
          return (
            <div className="rounded-md border border-border p-3" key={agentId}>
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium text-foreground text-sm">{group.name}</span>
                {prUrl ? (
                  <a className="text-primary text-sm underline" href={prUrl} rel="noreferrer" target="_blank">
                    {t('skills.backflowCreatePr')}
                  </a>
                ) : group.branch ? (
                  <span className="font-mono text-muted-foreground text-xs">{group.branch}</span>
                ) : null}
              </div>
              <ul className="mt-2 space-y-1">
                {group.items.map((proposal) => (
                  <li className="flex items-center gap-2 text-sm" key={proposal.id}>
                    <span>{proposal.skill_name}</span>
                    <Badge variant="secondary">{proposal.pr_state ?? 'pending'}</Badge>
                    {proposal.conflict ? (
                      <span className="text-amber-600 text-xs dark:text-amber-400">conflict</span>
                    ) : null}
                    <button
                      className="ml-auto text-muted-foreground text-xs underline"
                      onClick={() => setSelectedId(proposal.id)}
                      type="button"
                    >
                      {t('skills.diff')}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>
      {selectedId === null ? null : <BackflowDiffView diff={diff.data ?? null} loading={diff.isPending} />}
    </section>
  )
}

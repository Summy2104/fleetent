import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { GitCompare, Inbox, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/base/badge'
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
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  type BackflowProposal,
  type SkillListItem,
  type SkillProposal,
  useBackflowAcceptMutation,
  useBackflowDiffQuery,
  useBackflowForkMutation,
  useBackflowProposalsQuery,
  useBackflowRejectMutation,
  useForcePublishSkillMutation,
  useReloadSkillsMutation,
  useSetSkillAgentBindingMutation,
  useSkillAgentBindingsQuery,
  useSkillContentQuery,
  useSkillDiffQuery,
  useSkillLifecycleMutation,
  useSkillProposalDiffQuery,
  useSkillProposalsQuery,
  useSkillsQuery,
  useSkillVersionsQuery,
} from '@/features/skills/api'
import { useT } from '@/i18n'
import { useAdminApi } from '@/lib/api-client'
import { cn } from '@/lib/utils'

type AdminMe = { email: string; id: string; role: string }

function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

function auditVariant(verdict: string): 'success' | 'warning' | 'destructive' | 'secondary' {
  if (verdict === 'approved' || verdict === 'passed') return 'success'
  if (verdict === 'rejected') return 'destructive'
  if (verdict === 'pending') return 'warning'
  return 'secondary'
}

function statusVariant(status: string): 'success' | 'warning' | 'secondary' {
  if (status === 'archived' || status === 'quarantined') return 'warning'
  if (status === 'disabled') return 'secondary'
  return 'success'
}

function Th({ children, className }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <th
      className={cn(
        'px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide',
        className
      )}
    >
      {children}
    </th>
  )
}

function CodeBlock({ children }: { children: string }): JSX.Element {
  return (
    <pre className="max-h-80 overflow-auto rounded-md border border-border bg-secondary/50 p-4 font-mono text-foreground text-sm">
      {children}
    </pre>
  )
}

// ─────────────────────────── Content dialog ───────────────────────────

function ContentDialog({
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
      <DialogContent className="max-w-4xl">
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

function VersionsDialog({
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

function BindingsDialog({
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

function ProposalDiffDialog({
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

function ProposalsDialog({
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

function BackflowDialog({
  skillName,
  proposals,
  onViewDiff,
  diffText,
  onOpenChange,
}: {
  skillName: string | null
  proposals: BackflowProposal[]
  onViewDiff: (id: number) => void
  diffText: string | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(skillName)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('skills.backflowTitle', { name: skillName ?? '' })}</DialogTitle>
          <DialogDescription>{t('skills.backflowDescription')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {proposals.map((proposal) => (
            <BackflowProposalCard key={proposal.id} onViewDiff={onViewDiff} proposal={proposal} />
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

// ─────────────────────────── Skill row ───────────────────────────

function SkillRow({
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
  const canForcePublish = skill.audit_verdict === 'rejected' || skill.status === 'quarantined'

  const runArchive = async (): Promise<void> => {
    await archive.mutateAsync()
    setConfirmArchive(false)
  }

  return (
    <tr className="border-border border-b last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3">
        <span className="font-semibold text-foreground text-sm">{skill.name}</span>
        {skill.description ? (
          <span className="mt-0.5 line-clamp-1 block text-muted-foreground text-sm">{skill.description}</span>
        ) : null}
      </td>
      <td className="px-4 py-3">
        <Badge variant={statusVariant(skill.status)}>{skill.status}</Badge>
      </td>
      <td className="px-4 py-3">
        <Badge variant={skill.global_enabled ? 'success' : 'secondary'}>
          {skill.global_enabled ? t('skills.enabled') : t('skills.disabled')}
        </Badge>
      </td>
      <td className="px-4 py-3">
        {skill.audit_verdict ? (
          <Badge variant={auditVariant(skill.audit_verdict)}>{skill.audit_verdict}</Badge>
        ) : (
          <span className="text-muted-foreground text-sm">-</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button aria-label={t('skills.actionsFor', { name: skill.name })} size="sm" variant="secondary">
                {t('skills.actions')}
              </Button>
            }
          />
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setTimeout(onViewContent, 0)}>{t('skills.viewContent')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(onVersions, 0)}>{t('skills.versions')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(onBindings, 0)}>{t('skills.agentBindings')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(onProposals, 0)}>
              {t('skills.proposals')}
              {proposalCount > 0 ? ` (${proposalCount})` : ''}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(onBackflow, 0)}>
              {t('skills.backflow')}
              {backflowCount > 0 ? ` (${backflowCount})` : ''}
            </DropdownMenuItem>
            {canWrite ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => void toggle.mutateAsync()}>
                  {skill.global_enabled ? t('skills.disable') : t('skills.enable')}
                </DropdownMenuItem>
                {skill.status === 'archived' ? (
                  <DropdownMenuItem onClick={() => void restore.mutateAsync()}>{t('skills.restore')}</DropdownMenuItem>
                ) : (
                  <DropdownMenuItem onClick={() => setTimeout(() => setConfirmArchive(true), 0)}>
                    {t('skills.archive')}
                  </DropdownMenuItem>
                )}
                {canForcePublish ? (
                  <DropdownMenuItem onClick={() => void forcePublish.mutateAsync()}>
                    {t('skills.forcePublish')}
                  </DropdownMenuItem>
                ) : null}
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>

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
      </td>
    </tr>
  )
}

function BackflowProposalCard({
  onViewDiff,
  proposal,
}: {
  onViewDiff: (id: number) => void
  proposal: BackflowProposal
}): JSX.Element {
  const accept = useBackflowAcceptMutation(proposal.id)
  const reject = useBackflowRejectMutation(proposal.id)
  const fork = useBackflowForkMutation(proposal.id)

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
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <button
            className="rounded-md bg-secondary px-3 py-2 font-medium text-sm"
            onClick={() => onViewDiff(proposal.id)}
            type="button"
          >
            {`View backflow diff for ${proposal.id}`}
          </button>
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
// ─────────────────────────── Page ───────────────────────────

export function SkillsPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const skills = useSkillsQuery()
  const proposals = useSkillProposalsQuery()
  const backflow = useBackflowProposalsQuery()
  const reload = useReloadSkillsMutation()

  const [query, setQuery] = useState('')
  const [contentFor, setContentFor] = useState<string | null>(null)
  const [versionsFor, setVersionsFor] = useState<string | null>(null)
  const [bindingsFor, setBindingsFor] = useState<string | null>(null)
  const [proposalsFor, setProposalsFor] = useState<string | null>(null)
  const [proposalDiffId, setProposalDiffId] = useState<string | null>(null)
  const [backflowFor, setBackflowFor] = useState<string | null>(null)
  const [selectedBackflowId, setSelectedBackflowId] = useState<number | null>(null)

  const canWrite = me.data?.role !== 'viewer'
  const backflowDiff = useBackflowDiffQuery(selectedBackflowId, selectedBackflowId !== null)

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase()
    const list = skills.data ?? []
    if (!term) return list
    return list.filter((skill) => skill.name.toLowerCase().includes(term))
  }, [skills.data, query])

  const proposalsBySkill = useMemo(() => {
    const map = new Map<string, SkillProposal[]>()
    ;(proposals.data ?? []).forEach((proposal) => {
      const list = map.get(proposal.target_skill) ?? []
      list.push(proposal)
      map.set(proposal.target_skill, list)
    })
    return map
  }, [proposals.data])

  const backflowBySkill = useMemo(() => {
    const map = new Map<string, BackflowProposal[]>()
    ;(backflow.data ?? []).forEach((proposal) => {
      const list = map.get(proposal.skill_name) ?? []
      list.push(proposal)
      map.set(proposal.skill_name, list)
    })
    return map
  }, [backflow.data])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-xl tracking-tight">{t('skills.title')}</h2>
          <Badge variant="secondary">{skills.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <Button onClick={() => void reload.mutateAsync()} variant="outline">
            <RefreshCw className="size-4" /> {t('skills.reloadIndex')}
          </Button>
        ) : null}
      </div>

      <Input
        className="max-w-xs"
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t('skills.searchPlaceholder')}
        value={query}
      />

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <Th>{t('skills.colSkill')}</Th>
              <Th>{t('skills.colStatus')}</Th>
              <Th>{t('skills.colEnabled')}</Th>
              <Th>{t('skills.colAudit')}</Th>
              <Th className="text-right">{t('skills.colActions')}</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((skill) => (
              <SkillRow
                backflowCount={backflowBySkill.get(skill.name)?.length ?? 0}
                canWrite={canWrite}
                key={skill.name}
                onBackflow={() => setBackflowFor(skill.name)}
                onBindings={() => setBindingsFor(skill.name)}
                onProposals={() => setProposalsFor(skill.name)}
                onVersions={() => setVersionsFor(skill.name)}
                onViewContent={() => setContentFor(skill.name)}
                proposalCount={proposalsBySkill.get(skill.name)?.length ?? 0}
                skill={skill}
              />
            ))}
            {skills.data && filtered.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
                    <Inbox className="size-6 opacity-50" />
                    <span className="text-sm">{query ? t('skills.noMatching') : t('skills.empty')}</span>
                  </div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <ContentDialog onOpenChange={(open) => !open && setContentFor(null)} skillName={contentFor} />
      <VersionsDialog onOpenChange={(open) => !open && setVersionsFor(null)} skillName={versionsFor} />
      <BindingsDialog
        canWrite={canWrite}
        onOpenChange={(open) => !open && setBindingsFor(null)}
        skillName={bindingsFor}
      />
      <ProposalsDialog
        onDiff={(id) => setProposalDiffId(id)}
        onOpenChange={(open) => !open && setProposalsFor(null)}
        proposals={proposalsFor ? (proposalsBySkill.get(proposalsFor) ?? []) : []}
        skillName={proposalsFor}
      />
      <ProposalDiffDialog onOpenChange={(open) => !open && setProposalDiffId(null)} proposalId={proposalDiffId} />
      <BackflowDialog
        diffText={backflowDiff.data?.diff_vs_head ?? null}
        onOpenChange={(open) => {
          if (!open) {
            setBackflowFor(null)
            setSelectedBackflowId(null)
          }
        }}
        onViewDiff={setSelectedBackflowId}
        proposals={backflowFor ? (backflowBySkill.get(backflowFor) ?? []) : []}
        skillName={backflowFor}
      />
    </div>
  )
}

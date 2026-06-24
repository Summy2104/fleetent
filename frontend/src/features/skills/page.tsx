import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { GitCompare, Inbox, RefreshCw } from 'lucide-react';

import { useAdminApi } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  type SkillListItem,
  type SkillProposal,
  useForcePublishSkillMutation,
  useReloadSkillsMutation,
  useSetSkillAgentBindingMutation,
  useSkillAgentBindingsQuery,
  useSkillContentQuery,
  useSkillDiffQuery,
  useSkillLifecycleMutation,
  useSkillProposalDiffQuery,
  useSkillProposalsQuery,
  useSkillVersionsQuery,
  useSkillsQuery,
} from '@/features/skills/api';

type AdminMe = { email: string; id: string; role: string };

function useAdminMeQuery() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

function auditVariant(verdict: string): 'success' | 'warning' | 'destructive' | 'secondary' {
  if (verdict === 'approved' || verdict === 'passed') return 'success';
  if (verdict === 'rejected') return 'destructive';
  if (verdict === 'pending') return 'warning';
  return 'secondary';
}

function statusVariant(status: string): 'success' | 'warning' | 'secondary' {
  if (status === 'archived' || status === 'quarantined') return 'warning';
  if (status === 'disabled') return 'secondary';
  return 'success';
}

function Th({ children, className }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <th className={cn('px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground', className)}>
      {children}
    </th>
  );
}

function CodeBlock({ children }: { children: string }): JSX.Element {
  return (
    <pre className="max-h-80 overflow-auto rounded-md border border-border bg-secondary/50 p-4 font-mono text-sm text-foreground">
      {children}
    </pre>
  );
}

// ─────────────────────────── Content dialog ───────────────────────────

function ContentDialog({
  skillName,
  onOpenChange,
}: {
  skillName: string | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const content = useSkillContentQuery(skillName);
  return (
    <Dialog open={Boolean(skillName)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Content · {skillName}</DialogTitle>
          <DialogDescription>Read-only view of the published skill definition.</DialogDescription>
        </DialogHeader>
        <CodeBlock>{content.data?.content ?? ''}</CodeBlock>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Versions dialog ───────────────────────────

function VersionsDialog({
  skillName,
  onOpenChange,
}: {
  skillName: string | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const [selectedRef, setSelectedRef] = useState<string | null>(null);
  const versions = useSkillVersionsQuery(skillName, Boolean(skillName));
  const diff = useSkillDiffQuery(skillName, selectedRef, Boolean(selectedRef));

  useEffect(() => {
    if (!skillName) setSelectedRef(null);
  }, [skillName]);

  return (
    <Dialog open={Boolean(skillName)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Versions · {skillName}</DialogTitle>
          <DialogDescription>Browse commit history and inspect the diff for any revision.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          {(versions.data ?? []).map((version) => (
            <div
              key={version.sha}
              className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
            >
              <div className="min-w-0">
                <p className="font-mono text-sm text-foreground">{version.sha.slice(0, 10)}</p>
                <p className="truncate text-sm text-muted-foreground">{version.message}</p>
              </div>
              <Button
                size="sm"
                variant={selectedRef === version.sha ? 'secondary' : 'outline'}
                onClick={() => setSelectedRef(version.sha)}
              >
                <GitCompare className="size-4" /> Diff
              </Button>
            </div>
          ))}
          {versions.data && versions.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">No version history.</p>
          ) : null}
        </div>
        {diff.data?.diff ? <CodeBlock>{diff.data.diff}</CodeBlock> : null}
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Agent bindings dialog ───────────────────────────

function BindingToggle({
  agentId,
  label,
  enabled,
  skillName,
  canWrite,
}: {
  agentId: number;
  label: string;
  enabled: boolean;
  skillName: string;
  canWrite: boolean;
}): JSX.Element {
  const update = useSetSkillAgentBindingMutation(skillName, agentId);
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
      <span className="text-sm font-medium text-foreground">{label}</span>
      {canWrite ? (
        <Switch aria-label={label} checked={enabled} onCheckedChange={(checked) => update.mutate({ enabled: checked })} />
      ) : (
        <span className="text-xs text-muted-foreground">{enabled ? 'enabled' : 'disabled'}</span>
      )}
    </div>
  );
}

function BindingsDialog({
  skillName,
  canWrite,
  onOpenChange,
}: {
  skillName: string | null;
  canWrite: boolean;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const bindings = useSkillAgentBindingsQuery(skillName);
  return (
    <Dialog open={Boolean(skillName)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Agent bindings · {skillName}</DialogTitle>
          <DialogDescription>Toggle which agents this skill is enabled for.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {(bindings.data ?? []).map((binding) => (
            <BindingToggle
              key={binding.agent_id}
              agentId={binding.agent_id}
              label={binding.name ?? String(binding.agent_id)}
              enabled={binding.enabled}
              skillName={skillName ?? ''}
              canWrite={canWrite}
            />
          ))}
          {bindings.data && bindings.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">No agents bound.</p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Proposal diff dialog ───────────────────────────

function ProposalDiffDialog({
  proposalId,
  onOpenChange,
}: {
  proposalId: string | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const diff = useSkillProposalDiffQuery(proposalId, Boolean(proposalId));
  return (
    <Dialog open={Boolean(proposalId)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Proposal diff</DialogTitle>
          <DialogDescription>Read-only reflection proposal. Apply it from the agent workflow.</DialogDescription>
        </DialogHeader>
        {diff.data?.diff ? (
          <CodeBlock>{diff.data.diff}</CodeBlock>
        ) : (
          <p className="text-sm text-muted-foreground">No diff available for this proposal.</p>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Proposals dialog (per skill) ───────────────────────────

function ProposalsDialog({
  skillName,
  proposals,
  onDiff,
  onOpenChange,
}: {
  skillName: string | null;
  proposals: SkillProposal[];
  onDiff: (id: string) => void;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  return (
    <Dialog open={Boolean(skillName)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Proposals · {skillName}</DialogTitle>
          <DialogDescription>Reflection-generated change proposals targeting this skill.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {proposals.map((proposal) => (
            <div
              key={proposal.id}
              className="flex items-start justify-between gap-3 rounded-md border border-border px-3 py-2"
            >
              <div className="min-w-0 space-y-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-foreground">{proposal.type}</span>
                  <Badge variant={proposal.risk_level === 'high' ? 'destructive' : 'outline'}>
                    {proposal.risk_level}
                  </Badge>
                </span>
                <p className="text-sm text-muted-foreground">{proposal.reason}</p>
              </div>
              {proposal.has_diff ? (
                <Button size="sm" variant="outline" onClick={() => onDiff(proposal.id)}>
                  <GitCompare className="size-4" /> Diff
                </Button>
              ) : null}
            </div>
          ))}
          {proposals.length === 0 ? (
            <p className="text-sm text-muted-foreground">No proposals for this skill.</p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Skill row ───────────────────────────

function SkillRow({
  skill,
  canWrite,
  proposalCount,
  onViewContent,
  onVersions,
  onBindings,
  onProposals,
}: {
  skill: SkillListItem;
  canWrite: boolean;
  proposalCount: number;
  onViewContent: () => void;
  onVersions: () => void;
  onBindings: () => void;
  onProposals: () => void;
}): JSX.Element {
  const toggle = useSkillLifecycleMutation(skill.name, skill.global_enabled ? 'disable' : 'enable');
  const restore = useSkillLifecycleMutation(skill.name, 'restore');
  const archive = useSkillLifecycleMutation(skill.name, 'delete');
  const forcePublish = useForcePublishSkillMutation(skill.name);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const canForcePublish = skill.audit_verdict === 'rejected' || skill.status === 'quarantined';

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3">
        <span className="text-sm font-semibold text-foreground">{skill.name}</span>
        {skill.description ? (
          <span className="mt-0.5 line-clamp-1 block text-sm text-muted-foreground">{skill.description}</span>
        ) : null}
      </td>
      <td className="px-4 py-3">
        <Badge variant={statusVariant(skill.status)}>{skill.status}</Badge>
      </td>
      <td className="px-4 py-3">
        <Badge variant={skill.global_enabled ? 'success' : 'secondary'}>
          {skill.global_enabled ? 'enabled' : 'disabled'}
        </Badge>
      </td>
      <td className="px-4 py-3">
        {skill.audit_verdict ? (
          <Badge variant={auditVariant(skill.audit_verdict)}>{skill.audit_verdict}</Badge>
        ) : (
          <span className="text-sm text-muted-foreground">-</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" aria-label={`Actions for ${skill.name}`}>
              Actions
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setTimeout(onViewContent, 0)}>View content</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setTimeout(onVersions, 0)}>Versions</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setTimeout(onBindings, 0)}>Agent bindings</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setTimeout(onProposals, 0)}>
              Proposals{proposalCount > 0 ? ` (${proposalCount})` : ''}
            </DropdownMenuItem>
            {canWrite ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => void toggle.mutateAsync()}>
                  {skill.global_enabled ? 'Disable' : 'Enable'}
                </DropdownMenuItem>
                {skill.status === 'archived' ? (
                  <DropdownMenuItem onSelect={() => void restore.mutateAsync()}>Restore</DropdownMenuItem>
                ) : (
                  <DropdownMenuItem onSelect={() => setTimeout(() => setConfirmArchive(true), 0)}>
                    Archive
                  </DropdownMenuItem>
                )}
                {canForcePublish ? (
                  <DropdownMenuItem onSelect={() => void forcePublish.mutateAsync()}>Force publish</DropdownMenuItem>
                ) : null}
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>

        <AlertDialog open={confirmArchive} onOpenChange={setConfirmArchive}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Archive {skill.name}?</AlertDialogTitle>
              <AlertDialogDescription>
                Archiving removes the skill from active rollout. You can restore it later.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => void archive.mutateAsync()}>Archive</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </td>
    </tr>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function SkillsPage(): JSX.Element {
  const me = useAdminMeQuery();
  const skills = useSkillsQuery();
  const proposals = useSkillProposalsQuery();
  const reload = useReloadSkillsMutation();

  const [query, setQuery] = useState('');
  const [contentFor, setContentFor] = useState<string | null>(null);
  const [versionsFor, setVersionsFor] = useState<string | null>(null);
  const [bindingsFor, setBindingsFor] = useState<string | null>(null);
  const [proposalsFor, setProposalsFor] = useState<string | null>(null);
  const [proposalDiffId, setProposalDiffId] = useState<string | null>(null);

  const canWrite = me.data?.role !== 'viewer';

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const list = skills.data ?? [];
    if (!term) return list;
    return list.filter((skill) => skill.name.toLowerCase().includes(term));
  }, [skills.data, query]);

  const proposalsBySkill = useMemo(() => {
    const map = new Map<string, SkillProposal[]>();
    (proposals.data ?? []).forEach((proposal) => {
      const list = map.get(proposal.target_skill) ?? [];
      list.push(proposal);
      map.set(proposal.target_skill, list);
    });
    return map;
  }, [proposals.data]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">Skills</h2>
          <Badge variant="secondary">{skills.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <Button variant="outline" onClick={() => void reload.mutateAsync()}>
            <RefreshCw className="size-4" /> Reload index
          </Button>
        ) : null}
      </div>

      <Input
        className="max-w-xs"
        placeholder="Search skills…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <Th>Skill</Th>
              <Th>Status</Th>
              <Th>Enabled</Th>
              <Th>Audit</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((skill) => (
              <SkillRow
                key={skill.name}
                skill={skill}
                canWrite={canWrite}
                proposalCount={proposalsBySkill.get(skill.name)?.length ?? 0}
                onViewContent={() => setContentFor(skill.name)}
                onVersions={() => setVersionsFor(skill.name)}
                onBindings={() => setBindingsFor(skill.name)}
                onProposals={() => setProposalsFor(skill.name)}
              />
            ))}
            {skills.data && filtered.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
                    <Inbox className="size-6 opacity-50" />
                    <span className="text-sm">{query ? 'No matching skills.' : 'No skills registered yet.'}</span>
                  </div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <ContentDialog skillName={contentFor} onOpenChange={(open) => !open && setContentFor(null)} />
      <VersionsDialog skillName={versionsFor} onOpenChange={(open) => !open && setVersionsFor(null)} />
      <BindingsDialog
        skillName={bindingsFor}
        canWrite={canWrite}
        onOpenChange={(open) => !open && setBindingsFor(null)}
      />
      <ProposalsDialog
        skillName={proposalsFor}
        proposals={proposalsFor ? proposalsBySkill.get(proposalsFor) ?? [] : []}
        onDiff={(id) => setProposalDiffId(id)}
        onOpenChange={(open) => !open && setProposalsFor(null)}
      />
      <ProposalDiffDialog proposalId={proposalDiffId} onOpenChange={(open) => !open && setProposalDiffId(null)} />
    </div>
  );
}

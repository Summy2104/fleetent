import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { MoreVertical, Plus, Trash2 } from 'lucide-react';

import { useAdminApi } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  type AgentListItem,
  useAgentsQuery,
  useClearDefaultAgentMutation,
  useCloneAgentMutation,
  useCreateAgentMutation,
  useDeleteAgentMutation,
  useSetDefaultAgentMutation,
  useAgentLifecycleMutation,
} from '@/features/agents/api';

type AdminMe = { email: string; id: string; role: string };

function useAdminMeQuery() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

function parseAllowedTools(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function initials(name: string): string {
  const parts = name.replace(/[-_]/g, ' ').split(' ').filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function statusVariant(status: string): 'success' | 'warning' | 'secondary' {
  if (status === 'archived') return 'warning';
  if (status === 'disabled') return 'secondary';
  return 'success';
}

function statusDot(status: string): string {
  if (status === 'archived') return 'bg-warning';
  if (status === 'disabled') return 'bg-muted-foreground';
  return 'bg-success';
}

// ─────────────────────────── Create dialog ───────────────────────────

function CreateAgentDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const create = useCreateAgentMutation();
  const [name, setName] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [allowedTools, setAllowedTools] = useState('');

  // Reset fields whenever the dialog re-opens.
  useEffect(() => {
    if (open) {
      setName('');
      setSystemPrompt('');
      setAllowedTools('');
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Agent</DialogTitle>
          <DialogDescription>Create an adhoc agent. It starts enabled with no bindings.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="new-name">Agent name</Label>
            <Input id="new-name" value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="new-prompt">System prompt</Label>
            <Textarea
              id="new-prompt"
              className="min-h-32"
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="new-tools">Allowed tools (comma-separated)</Label>
            <Input
              id="new-tools"
              placeholder="tool_a, tool_b"
              value={allowedTools}
              onChange={(event) => setAllowedTools(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={create.isPending || !name}
            onClick={async () => {
              await create.mutateAsync({
                name,
                system_prompt: systemPrompt,
                allowed_tools: parseAllowedTools(allowedTools),
              });
              onOpenChange(false);
            }}
          >
            Create agent
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Row ───────────────────────────

function AgentRow({
  agent,
  canWrite,
  onConfigure,
}: {
  agent: AgentListItem;
  canWrite: boolean;
  onConfigure: () => void;
}): JSX.Element {
  const disable = useAgentLifecycleMutation(agent.agent_name, 'disable');
  const enable = useAgentLifecycleMutation(agent.agent_name, 'enable');
  const archive = useAgentLifecycleMutation(agent.agent_name, 'archive', { 'X-Confirm': 'true' });
  const restore = useAgentLifecycleMutation(agent.agent_name, 'restore');
  const clone = useCloneAgentMutation(agent.agent_name);
  const remove = useDeleteAgentMutation(agent.agent_name);
  const setDefault = useSetDefaultAgentMutation(agent.agent_name);
  const clearDefault = useClearDefaultAgentMutation();
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div className="flex items-center gap-4 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:bg-accent/40">
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-4 text-left"
        onClick={onConfigure}
      >
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-secondary text-xs font-semibold text-foreground">
          {initials(agent.agent_name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-foreground">{agent.agent_name}</span>
            <span className={cn('size-1.5 rounded-full', statusDot(agent.status))} />
            {agent.is_default ? <Badge variant="default">default</Badge> : null}
            <Badge variant={statusVariant(agent.status)}>{agent.status}</Badge>
          </span>
          {agent.system_prompt ? (
            <span className="mt-0.5 line-clamp-1 block text-sm text-muted-foreground">{agent.system_prompt}</span>
          ) : null}
        </span>
      </button>
      <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">{agent.provenance}</span>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="secondary" size="sm" aria-label={`Actions for ${agent.agent_name}`}>
            Actions <MoreVertical className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={onConfigure}>Configure</DropdownMenuItem>
          {canWrite ? (
            <>
              <DropdownMenuItem
                onSelect={() =>
                  agent.status === 'disabled' ? void enable.mutateAsync() : void disable.mutateAsync()
                }
              >
                {agent.status === 'disabled' ? 'Enable' : 'Disable'}
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() =>
                  agent.status === 'archived' ? void restore.mutateAsync() : void archive.mutateAsync()
                }
              >
                {agent.status === 'archived' ? 'Restore' : 'Archive'}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void clone.mutateAsync(`${agent.agent_name}-copy`)}>
                Clone
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => (agent.is_default ? void clearDefault.mutateAsync() : void setDefault.mutateAsync())}
              >
                {agent.is_default ? 'Clear default' : 'Set as default'}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onSelect={() => setTimeout(() => setConfirmDelete(true), 0)}>
                <Trash2 /> Delete
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {agent.agent_name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the agent definition. Agents with active bindings cannot be deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void remove.mutateAsync()}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function AgentsPage(): JSX.Element {
  const me = useAdminMeQuery();
  const agents = useAgentsQuery();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [createOpen, setCreateOpen] = useState(false);

  const canWrite = me.data?.role !== 'viewer';

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const list = agents.data ?? [];
    if (!term) return list;
    return list.filter((agent) => agent.agent_name.toLowerCase().includes(term));
  }, [agents.data, query]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">Agents</h2>
          <Badge variant="secondary">{agents.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" /> New Agent
          </Button>
        ) : null}
      </div>

      <Input placeholder="Search agents…" value={query} onChange={(event) => setQuery(event.target.value)} />

      <div className="space-y-2">
        {filtered.map((agent) => (
          <AgentRow
            key={agent.agent_name}
            agent={agent}
            canWrite={canWrite}
            onConfigure={() => navigate(`/agents/${agent.agent_name}/configure`)}
          />
        ))}
        {agents.data && filtered.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
            {query ? 'No agents match your search.' : 'No agents yet. Create one to get started.'}
          </div>
        ) : null}
      </div>

      <CreateAgentDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

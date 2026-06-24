import { useEffect, useMemo, useState } from 'react';
import { Inbox, Plus, Trash2, X } from 'lucide-react';

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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  type McpServerInput,
  type McpServerRecord,
  useCreateMcpServerMutation,
  useDeleteMcpServerMutation,
  useMcpReconnectMutation,
  useMcpServerTestMutation,
  useMcpServerToolsQuery,
  useMcpServersQuery,
  useUpdateMcpServerMutation,
} from '@/features/connectors/api';

const TRANSPORTS = ['stdio', 'http', 'websocket'] as const;

function statusVariant(status: string): 'success' | 'secondary' | 'warning' {
  if (status === 'connected' || status === 'configured') return 'success';
  if (status === 'disabled') return 'secondary';
  return 'warning';
}

type EnvPair = { key: string; value: string };

// ─────────────────────────── Add / Edit dialog ───────────────────────────

function ServerDialog({
  open,
  editing,
  onOpenChange,
}: {
  open: boolean;
  editing: McpServerRecord | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const create = useCreateMcpServerMutation();
  const update = useUpdateMcpServerMutation(editing?.id ?? '');
  const isEdit = editing !== null;

  const [id, setId] = useState('');
  const [transport, setTransport] = useState<string>('stdio');
  const [command, setCommand] = useState('');
  const [url, setUrl] = useState('');
  const [env, setEnv] = useState<EnvPair[]>([]);

  useEffect(() => {
    if (open) {
      setId(editing?.id ?? '');
      setTransport(editing?.transport ?? 'stdio');
      setCommand(editing?.command ?? '');
      setUrl(editing?.url ?? '');
      setEnv([]);
    }
  }, [open, editing]);

  const submit = async (): Promise<void> => {
    const payload: McpServerInput = { id: id.trim(), transport, enabled: editing?.enabled ?? true };
    if (transport === 'stdio') {
      payload.command = command.trim() || undefined;
    } else {
      payload.url = url.trim() || undefined;
    }
    const envMap: Record<string, string> = {};
    env.forEach((pair) => {
      if (pair.key.trim()) envMap[pair.key.trim()] = pair.value;
    });
    if (Object.keys(envMap).length > 0) payload.env = envMap;

    if (isEdit) {
      const { id: _omit, ...editPayload } = payload;
      await update.mutateAsync(editPayload);
    } else {
      await create.mutateAsync(payload);
    }
    onOpenChange(false);
  };

  const canSubmit =
    id.trim().length > 0 && (transport === 'stdio' ? command.trim().length > 0 : url.trim().length > 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${editing?.id}` : 'Add MCP Server'}</DialogTitle>
          <DialogDescription>Register an MCP server the platform can connect agents to.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="mcp-id">
              ID <span className="text-destructive">*</span>
            </Label>
            <Input
              id="mcp-id"
              placeholder="e.g. filesystem"
              disabled={isEdit}
              value={id}
              onChange={(event) => setId(event.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Transport</Label>
            <Select value={transport} onValueChange={setTransport}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TRANSPORTS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {transport === 'stdio' ? (
            <div className="grid gap-2">
              <Label htmlFor="mcp-command">
                Command <span className="text-destructive">*</span>
              </Label>
              <Input
                id="mcp-command"
                placeholder="e.g. npx -y @modelcontextprotocol/server-filesystem"
                value={command}
                onChange={(event) => setCommand(event.target.value)}
              />
            </div>
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="mcp-url">
                Server URL <span className="text-destructive">*</span>
              </Label>
              <Input
                id="mcp-url"
                placeholder="https://mcp-server.example.com/mcp"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
              />
            </div>
          )}

          <div className="grid gap-2">
            <Label>Env (optional)</Label>
            <div className="space-y-2">
              {env.map((pair, index) => (
                <div key={index} className="flex items-center gap-2">
                  <Input
                    className="flex-1"
                    placeholder="KEY"
                    value={pair.key}
                    onChange={(event) =>
                      setEnv((current) => current.map((p, i) => (i === index ? { ...p, key: event.target.value } : p)))
                    }
                  />
                  <Input
                    className="flex-1"
                    placeholder="value"
                    value={pair.value}
                    onChange={(event) =>
                      setEnv((current) => current.map((p, i) => (i === index ? { ...p, value: event.target.value } : p)))
                    }
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Remove env var"
                    onClick={() => setEnv((current) => current.filter((_, i) => i !== index))}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                className="w-full border-dashed"
                onClick={() => setEnv((current) => [...current, { key: '', value: '' }])}
              >
                <Plus className="size-4" /> Add
              </Button>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!canSubmit || create.isPending || update.isPending} onClick={() => void submit()}>
            {isEdit ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Server row ───────────────────────────

function ServerRow({
  server,
  onEdit,
  onViewTools,
}: {
  server: McpServerRecord;
  onEdit: () => void;
  onViewTools: () => void;
}): JSX.Element {
  const test = useMcpServerTestMutation(server.id);
  const reconnect = useMcpReconnectMutation(server.id);
  const remove = useDeleteMcpServerMutation(server.id);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3 font-mono text-sm text-foreground">{server.id}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{server.transport}</td>
      <td className="px-4 py-3">
        <Badge variant={statusVariant(server.status)}>{server.status}</Badge>
        {test.data ? (
          <span className="ml-2 text-xs text-muted-foreground">
            {test.data.connected ? `connected · ${test.data.tools_count ?? 0} tools` : test.data.error ?? 'failed'}
          </span>
        ) : null}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{server.tool_count}</td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" aria-label={`Actions for ${server.id}`}>
              Actions
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setTimeout(onEdit, 0)}>Edit</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void test.mutateAsync()}>Test connection</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void reconnect.mutateAsync()}>Reconnect</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setTimeout(onViewTools, 0)}>View tools</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={() => setTimeout(() => setConfirmDelete(true), 0)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete {server.id}?</AlertDialogTitle>
              <AlertDialogDescription>This removes the MCP server registration.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => void remove.mutateAsync()}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </td>
    </tr>
  );
}

// ─────────────────────────── Tools dialog ───────────────────────────

function ToolsDialog({
  serverId,
  onOpenChange,
}: {
  serverId: string | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const tools = useMcpServerToolsQuery(serverId);

  return (
    <Dialog open={Boolean(serverId)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tools · {serverId}</DialogTitle>
          <DialogDescription>Live tools/list from a real handshake with the server.</DialogDescription>
        </DialogHeader>
        {tools.data?.error ? (
          <p className="text-sm text-destructive">{tools.data.error}</p>
        ) : tools.data?.tools.length ? (
          <div className="space-y-2">
            {tools.data.tools.map((tool) => (
              <div key={tool.name} className="rounded-md border border-border px-3 py-2">
                <p className="font-mono text-sm text-foreground">{tool.name}</p>
                {tool.description ? <p className="text-sm text-muted-foreground">{tool.description}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{tools.isLoading ? 'Connecting…' : 'No tools reported.'}</p>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function McpPage(): JSX.Element {
  const servers = useMcpServersQuery();
  const [query, setQuery] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<McpServerRecord | null>(null);
  const [toolsFor, setToolsFor] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const list = servers.data ?? [];
    if (!term) return list;
    return list.filter((server) => server.id.toLowerCase().includes(term));
  }, [servers.data, query]);

  const openCreate = (): void => {
    setEditing(null);
    setDialogOpen(true);
  };
  const openEdit = (server: McpServerRecord): void => {
    setEditing(server);
    setDialogOpen(true);
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">MCP Servers</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Inspect MCP servers, probe their tools, run connectivity tests, and trigger reconnects.
        </p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <Input
          className="max-w-xs"
          placeholder="Search servers…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button onClick={openCreate}>
          <Plus className="size-4" /> Add MCP Server
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">ID</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Transport</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Tools</th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((server) => (
              <ServerRow
                key={server.id}
                server={server}
                onEdit={() => openEdit(server)}
                onViewTools={() => setToolsFor(server.id)}
              />
            ))}
            {servers.data && filtered.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
                    <Inbox className="size-6 opacity-50" />
                    <span className="text-sm">{query ? 'No matching servers.' : 'No MCP servers'}</span>
                  </div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <ServerDialog open={dialogOpen} editing={editing} onOpenChange={setDialogOpen} />
      <ToolsDialog serverId={toolsFor} onOpenChange={(open) => !open && setToolsFor(null)} />
    </div>
  );
}

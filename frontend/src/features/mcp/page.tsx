import { useEffect, useMemo, useState } from 'react';
import { Inbox, Plus, Trash2, X } from 'lucide-react';

import { useT } from '@/i18n';
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

const toPairs = (map?: Record<string, string>): EnvPair[] =>
  Object.entries(map ?? {}).map(([key, value]) => ({ key, value }));

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
  const t = useT();
  const create = useCreateMcpServerMutation();
  const update = useUpdateMcpServerMutation(editing?.id ?? '');
  const isEdit = editing !== null;

  const [id, setId] = useState('');
  const [transport, setTransport] = useState<string>('stdio');
  const [command, setCommand] = useState('');
  const [url, setUrl] = useState('');
  const [env, setEnv] = useState<EnvPair[]>([]);
  const [args, setArgs] = useState<string[]>([]);
  const [headers, setHeaders] = useState<EnvPair[]>([]);

  useEffect(() => {
    if (open) {
      setId(editing?.id ?? '');
      setTransport(editing?.transport ?? 'stdio');
      setCommand(editing?.command ?? '');
      setUrl(editing?.url ?? '');
      setEnv(toPairs(editing?.env));
      setArgs(editing?.args ?? []);
      setHeaders(toPairs(editing?.headers));
    }
  }, [open, editing]);

  const submit = async (): Promise<void> => {
    const payload: McpServerInput = { id: id.trim(), transport, enabled: editing?.enabled ?? true };
    if (transport === 'stdio') {
      payload.command = command.trim() || undefined;
      const cleanArgs = args.map((arg) => arg.trim()).filter(Boolean);
      if (cleanArgs.length > 0) payload.args = cleanArgs;
    } else {
      payload.url = url.trim() || undefined;
      const headerMap: Record<string, string> = {};
      headers.forEach((pair) => {
        if (pair.key.trim()) headerMap[pair.key.trim()] = pair.value;
      });
      if (Object.keys(headerMap).length > 0) payload.headers = headerMap;
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
          <DialogTitle>{isEdit ? t('mcp.editTitle', { name: editing?.id ?? '' }) : t('mcp.addTitle')}</DialogTitle>
          <DialogDescription>{t('mcp.dialogDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="mcp-id">
              {t('mcp.idLabel')} <span className="text-destructive">*</span>
            </Label>
            <Input
              id="mcp-id"
              placeholder={t('mcp.idPlaceholder')}
              disabled={isEdit}
              value={id}
              onChange={(event) => setId(event.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>{t('mcp.transportLabel')}</Label>
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
                {t('mcp.commandLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="mcp-command"
                placeholder={t('mcp.commandPlaceholder')}
                value={command}
                onChange={(event) => setCommand(event.target.value)}
              />
            </div>
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="mcp-url">
                {t('mcp.serverUrlLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="mcp-url"
                placeholder="https://mcp-server.example.com/mcp"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
              />
            </div>
          )}

          {transport === 'stdio' ? (
            <div className="grid gap-2">
              <Label>{t('mcp.argsLabel')}</Label>
              <div className="space-y-2">
                {args.map((arg, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      className="flex-1"
                      placeholder={t('mcp.argPlaceholder')}
                      value={arg}
                      onChange={(event) =>
                        setArgs((current) => current.map((a, i) => (i === index ? event.target.value : a)))
                      }
                    />
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={t('mcp.removeArg')}
                      onClick={() => setArgs((current) => current.filter((_, i) => i !== index))}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  className="w-full border-dashed"
                  onClick={() => setArgs((current) => [...current, ''])}
                >
                  <Plus className="size-4" /> {t('mcp.addArg')}
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid gap-2">
              <Label>{t('mcp.headersLabel')}</Label>
              <div className="space-y-2">
                {headers.map((pair, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      className="flex-1"
                      placeholder={t('mcp.headerKeyPlaceholder')}
                      value={pair.key}
                      onChange={(event) =>
                        setHeaders((current) =>
                          current.map((p, i) => (i === index ? { ...p, key: event.target.value } : p))
                        )
                      }
                    />
                    <Input
                      className="flex-1"
                      placeholder={t('mcp.headerValuePlaceholder')}
                      value={pair.value}
                      onChange={(event) =>
                        setHeaders((current) =>
                          current.map((p, i) => (i === index ? { ...p, value: event.target.value } : p))
                        )
                      }
                    />
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={t('mcp.removeHeader')}
                      onClick={() => setHeaders((current) => current.filter((_, i) => i !== index))}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  className="w-full border-dashed"
                  onClick={() => setHeaders((current) => [...current, { key: '', value: '' }])}
                >
                  <Plus className="size-4" /> {t('mcp.addHeader')}
                </Button>
              </div>
            </div>
          )}

          <div className="grid gap-2">
            <Label>{t('mcp.envLabel')}</Label>
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
                    placeholder={t('mcp.envValuePlaceholder')}
                    value={pair.value}
                    onChange={(event) =>
                      setEnv((current) => current.map((p, i) => (i === index ? { ...p, value: event.target.value } : p)))
                    }
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={t('mcp.removeEnvVar')}
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
                <Plus className="size-4" /> {t('mcp.addEnvVar')}
              </Button>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('mcp.cancel')}
          </Button>
          <Button disabled={!canSubmit || create.isPending || update.isPending} onClick={() => void submit()}>
            {isEdit ? t('mcp.save') : t('mcp.create')}
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
  const t = useT();
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
            {test.data.connected
              ? t('mcp.connectedTools', { count: test.data.tools_count ?? 0 })
              : test.data.error ?? t('mcp.testFailed')}
          </span>
        ) : null}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{server.tool_count}</td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" aria-label={t('mcp.actionsFor', { name: server.id })}>
              {t('mcp.actions')}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setTimeout(onEdit, 0)}>{t('mcp.edit')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void test.mutateAsync()}>{t('mcp.testConnection')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void reconnect.mutateAsync()}>{t('mcp.reconnect')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setTimeout(onViewTools, 0)}>{t('mcp.viewTools')}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={() => setTimeout(() => setConfirmDelete(true), 0)}>
              <Trash2 /> {t('mcp.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('mcp.deleteConfirmTitle', { name: server.id })}</AlertDialogTitle>
              <AlertDialogDescription>{t('mcp.deleteConfirmDescription')}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('mcp.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={() => void remove.mutateAsync()}>{t('mcp.delete')}</AlertDialogAction>
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
  const t = useT();
  const tools = useMcpServerToolsQuery(serverId);

  return (
    <Dialog open={Boolean(serverId)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('mcp.toolsTitle', { name: serverId ?? '' })}</DialogTitle>
          <DialogDescription>{t('mcp.toolsDescription')}</DialogDescription>
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
          <p className="text-sm text-muted-foreground">
            {tools.isLoading ? t('mcp.connecting') : t('mcp.noToolsReported')}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function McpPage(): JSX.Element {
  const t = useT();
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
        <h2 className="text-xl font-semibold tracking-tight">{t('mcp.pageTitle')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('mcp.pageDescription')}</p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <Input
          className="max-w-xs"
          placeholder={t('mcp.searchPlaceholder')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button onClick={openCreate}>
          <Plus className="size-4" /> {t('mcp.addServer')}
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnId')}</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnTransport')}</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnStatus')}</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnTools')}</th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnActions')}</th>
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
                    <span className="text-sm">{query ? t('mcp.noMatching') : t('mcp.empty')}</span>
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

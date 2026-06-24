import { type ReactNode, useEffect, useState } from 'react';
import { Inbox, Plus, Trash2 } from 'lucide-react';

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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  type CreateConnectorInput,
  type KbConnector,
  type KnowledgeBase,
  useConnectorCheckMutation,
  useConnectorStatusQuery,
  useConnectorSyncMutation,
  useCreateConnectorMutation,
  useCreateKbMutation,
  useDeleteConnectorMutation,
  useDeleteDocumentMutation,
  useDeleteKbMutation,
  useDocumentsQuery,
  useIngestDocumentMutation,
  useKbsQuery,
  useKbConnectorsQuery,
  useSyncDocumentsMutation,
  useUpdateConnectorMutation,
  useUpdateKbMutation,
} from '@/features/kb/api';

const TENANT = 'default';
const DOC_FORMATS = ['markdown', 'text', 'html'] as const;
const CONNECTOR_KINDS = ['google_drive', 'confluence'] as const;

function Th({ children, className }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <th className={cn('px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground', className)}>
      {children}
    </th>
  );
}

function EmptyRow({ colSpan, label }: { colSpan: number; label: string }): JSX.Element {
  return (
    <tr>
      <td colSpan={colSpan}>
        <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
          <Inbox className="size-6 opacity-50" />
          <span className="text-sm">{label}</span>
        </div>
      </td>
    </tr>
  );
}

// ─────────────────────────── KB create / edit dialog ───────────────────────────

function KbDialog({
  open,
  editing,
  onOpenChange,
}: {
  open: boolean;
  editing: KnowledgeBase | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const create = useCreateKbMutation();
  const update = useUpdateKbMutation(editing?.kb_id ?? '');
  const isEdit = editing !== null;
  const [kbId, setKbId] = useState('');
  const [description, setDescription] = useState('');

  useEffect(() => {
    if (open) {
      setKbId(editing?.kb_id ?? '');
      setDescription(editing?.description ?? '');
    }
  }, [open, editing]);

  const submit = async (): Promise<void> => {
    if (isEdit) {
      await update.mutateAsync({ description });
    } else {
      await create.mutateAsync({ kb_id: kbId.trim(), description, tenant_id: TENANT });
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${editing?.kb_id}` : 'Add knowledge base'}</DialogTitle>
          <DialogDescription>A knowledge base holds documents the agents can retrieve.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="kb-id">
              Knowledge base ID <span className="text-destructive">*</span>
            </Label>
            <Input id="kb-id" disabled={isEdit} value={kbId} onChange={(event) => setKbId(event.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="kb-description">Description</Label>
            <Input
              id="kb-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={(!isEdit && !kbId.trim()) || create.isPending || update.isPending}
            onClick={() => void submit()}
          >
            {isEdit ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Documents dialog ───────────────────────────

function DocumentsDialog({
  kbId,
  onOpenChange,
}: {
  kbId: string | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const documents = useDocumentsQuery(kbId);
  const ingest = useIngestDocumentMutation(kbId ?? '');
  const deleteDocument = useDeleteDocumentMutation(kbId ?? '');

  const [source, setSource] = useState('');
  const [format, setFormat] = useState('markdown');
  const [content, setContent] = useState('');

  useEffect(() => {
    if (kbId) {
      setSource(`${kbId}.md`);
      setFormat('markdown');
      setContent('');
    }
  }, [kbId]);

  const submit = async (): Promise<void> => {
    await ingest.mutateAsync({ source, content, document_format: format, tenant_id: TENANT });
    setContent('');
  };

  return (
    <Dialog open={Boolean(kbId)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Documents · {kbId}</DialogTitle>
          <DialogDescription>Paste content to ingest, or remove existing documents.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="doc-source">Source</Label>
              <Input id="doc-source" value={source} onChange={(event) => setSource(event.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>Format</Label>
              <Select value={format} onValueChange={setFormat}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOC_FORMATS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="doc-content">Content</Label>
            <Textarea
              id="doc-content"
              className="min-h-28"
              value={content}
              onChange={(event) => setContent(event.target.value)}
            />
          </div>
          <Button className="justify-self-start" disabled={!content || ingest.isPending} onClick={() => void submit()}>
            <Plus className="size-4" /> Ingest document
          </Button>
        </div>

        <div className="max-h-60 space-y-2 overflow-y-auto">
          {(documents.data ?? []).map((document) => (
            <div
              key={document.document_id}
              className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{document.filename}</p>
                <p className="text-xs text-muted-foreground">{document.chunks} chunks</p>
              </div>
              <Button
                size="icon"
                variant="ghost"
                aria-label={`Delete ${document.filename}`}
                onClick={() =>
                  void deleteDocument.mutateAsync({ document_id: document.document_id, tenant_id: TENANT })
                }
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
          {documents.data && documents.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">No documents yet.</p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Sync dialog ───────────────────────────

function SyncDialog({
  kbId,
  onOpenChange,
}: {
  kbId: string | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const sync = useSyncDocumentsMutation(kbId ?? '');
  const [path, setPath] = useState('');

  useEffect(() => {
    if (kbId) setPath(`/data/${kbId}`);
  }, [kbId]);

  return (
    <Dialog open={Boolean(kbId)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Sync · {kbId}</DialogTitle>
          <DialogDescription>Ingest every supported file under a local directory.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="sync-path">Directory path</Label>
          <Input id="sync-path" value={path} onChange={(event) => setPath(event.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!path || sync.isPending}
            onClick={async () => {
              await sync.mutateAsync({ path, tenant_id: TENANT });
              onOpenChange(false);
            }}
          >
            Sync
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── KB row ───────────────────────────

function KbRow({
  kb,
  onEdit,
  onDocuments,
  onSync,
}: {
  kb: KnowledgeBase;
  onEdit: () => void;
  onDocuments: () => void;
  onSync: () => void;
}): JSX.Element {
  const remove = useDeleteKbMutation(kb.kb_id);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3">
        <p className="text-sm font-semibold text-foreground">{kb.kb_id}</p>
        {kb.description ? <p className="line-clamp-1 text-sm text-muted-foreground">{kb.description}</p> : null}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{kb.doc_count}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{kb.chunk_count}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {kb.bound_agents.length ? kb.bound_agents.join(', ') : '-'}
      </td>
      <td className="px-4 py-3">
        <Badge variant={kb.archived ? 'warning' : 'success'}>{kb.archived ? 'archived' : 'active'}</Badge>
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" aria-label={`Actions for ${kb.kb_id}`}>
              Actions
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setTimeout(onEdit, 0)}>Edit</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setTimeout(onDocuments, 0)}>Documents</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setTimeout(onSync, 0)}>Sync</DropdownMenuItem>
            {!kb.archived ? (
              <>
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
              <AlertDialogTitle>Delete {kb.kb_id}?</AlertDialogTitle>
              <AlertDialogDescription>
                Archives the knowledge base. KBs still bound to agents cannot be archived.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => void remove.mutateAsync({ tenant_id: TENANT })}>
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </td>
    </tr>
  );
}

// ─────────────────────────── Connector dialog ───────────────────────────

function ConnectorDialog({
  open,
  editing,
  onOpenChange,
}: {
  open: boolean;
  editing: KbConnector | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const create = useCreateConnectorMutation();
  const update = useUpdateConnectorMutation(editing?.connector_id ?? '');
  const isEdit = editing !== null;

  const [connectorId, setConnectorId] = useState('');
  const [kind, setKind] = useState('google_drive');
  const [kbId, setKbId] = useState('global');
  const [description, setDescription] = useState('');
  const [configJson, setConfigJson] = useState('{}');
  const [customYaml, setCustomYaml] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setConnectorId(editing?.connector_id ?? '');
      setKind(editing?.kind ?? 'google_drive');
      setKbId(editing?.kb_id ?? 'global');
      setDescription(editing?.description ?? '');
      setConfigJson(editing?.config ? JSON.stringify(editing.config, null, 2) : '{}');
      setCustomYaml(editing?.custom_yaml ?? '');
      setEnabled(editing?.enabled ?? true);
      setError(null);
    }
  }, [open, editing]);

  const submit = async (): Promise<void> => {
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(configJson || '{}') as Record<string, unknown>;
    } catch {
      setError('config is not valid JSON.');
      return;
    }
    if (isEdit) {
      await update.mutateAsync({ config, custom_yaml: customYaml, description, enabled, kb_id: kbId, tenant_id: TENANT });
    } else {
      const input: CreateConnectorInput = {
        config,
        connector_id: connectorId.trim(),
        custom_yaml: customYaml,
        description,
        enabled,
        kb_id: kbId,
        kind,
        tenant_id: TENANT,
      };
      await create.mutateAsync(input);
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${editing?.connector_id}` : 'Add connector'}</DialogTitle>
          <DialogDescription>Google Drive / Confluence ingestion source for a knowledge base.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="conn-id">
                Connector ID <span className="text-destructive">*</span>
              </Label>
              <Input
                id="conn-id"
                disabled={isEdit}
                value={connectorId}
                onChange={(event) => setConnectorId(event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Kind</Label>
              <Select value={kind} onValueChange={setKind} disabled={isEdit}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONNECTOR_KINDS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="conn-kb">Knowledge base ID</Label>
              <Input id="conn-kb" value={kbId} onChange={(event) => setKbId(event.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="conn-desc">Description</Label>
              <Input id="conn-desc" value={description} onChange={(event) => setDescription(event.target.value)} />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="conn-config">Config (JSON)</Label>
            <Textarea
              id="conn-config"
              className="min-h-24 font-mono text-xs"
              value={configJson}
              onChange={(event) => setConfigJson(event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="conn-yaml">Custom YAML (optional)</Label>
            <Textarea
              id="conn-yaml"
              className="min-h-20 font-mono text-xs"
              value={customYaml}
              onChange={(event) => setCustomYaml(event.target.value)}
            />
          </div>
          <label className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
            Enabled
            <Switch checked={enabled} aria-label="Enabled" onCheckedChange={setEnabled} />
          </label>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={(!isEdit && !connectorId.trim()) || create.isPending || update.isPending}
            onClick={() => void submit()}
          >
            {isEdit ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Connector row ───────────────────────────

function ConnectorRow({
  connector,
  onEdit,
}: {
  connector: KbConnector;
  onEdit: () => void;
}): JSX.Element {
  const status = useConnectorStatusQuery(connector.connector_id);
  const check = useConnectorCheckMutation(connector.connector_id);
  const sync = useConnectorSyncMutation(connector.connector_id);
  const remove = useDeleteConnectorMutation(connector.connector_id);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3 font-mono text-sm text-foreground">{connector.connector_id}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{connector.kind}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{connector.kb_id}</td>
      <td className="px-4 py-3">
        <Badge variant={connector.enabled ? 'success' : 'secondary'}>
          {connector.enabled ? 'enabled' : 'disabled'}
        </Badge>
        <span className="ml-2 text-xs text-muted-foreground">
          {check.data ? check.data.status : status.data?.status ?? ''}
        </span>
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" aria-label={`Actions for ${connector.connector_id}`}>
              Actions
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setTimeout(onEdit, 0)}>Edit</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void check.mutateAsync()}>Check</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void sync.mutateAsync({ dry_run: true })}>
              Sync (dry-run)
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={() => setTimeout(() => setConfirmDelete(true), 0)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete {connector.connector_id}?</AlertDialogTitle>
              <AlertDialogDescription>This removes the connector configuration.</AlertDialogDescription>
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

// ─────────────────────────── Page ───────────────────────────

export function KnowledgeBasePage(): JSX.Element {
  const kbs = useKbsQuery();
  const connectors = useKbConnectorsQuery();

  const [kbDialogOpen, setKbDialogOpen] = useState(false);
  const [editingKb, setEditingKb] = useState<KnowledgeBase | null>(null);
  const [documentsFor, setDocumentsFor] = useState<string | null>(null);
  const [syncFor, setSyncFor] = useState<string | null>(null);

  const [connectorDialogOpen, setConnectorDialogOpen] = useState(false);
  const [editingConnector, setEditingConnector] = useState<KbConnector | null>(null);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Knowledge Base</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Libraries, documents, syncs, and ingestion connectors.
        </p>
      </div>

      <Tabs defaultValue="kbs">
        <TabsList>
          <TabsTrigger value="kbs">Knowledge bases</TabsTrigger>
          <TabsTrigger value="connectors">Connectors</TabsTrigger>
        </TabsList>

        <TabsContent value="kbs" className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <Badge variant="secondary">{kbs.data?.length ?? 0} bases</Badge>
            <Button
              onClick={() => {
                setEditingKb(null);
                setKbDialogOpen(true);
              }}
            >
              <Plus className="size-4" /> Add knowledge base
            </Button>
          </div>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full">
              <thead className="bg-secondary/50">
                <tr>
                  <Th>Knowledge base</Th>
                  <Th>Docs</Th>
                  <Th>Chunks</Th>
                  <Th>Bound agents</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {(kbs.data ?? []).map((kb) => (
                  <KbRow
                    key={kb.kb_id}
                    kb={kb}
                    onEdit={() => {
                      setEditingKb(kb);
                      setKbDialogOpen(true);
                    }}
                    onDocuments={() => setDocumentsFor(kb.kb_id)}
                    onSync={() => setSyncFor(kb.kb_id)}
                  />
                ))}
                {kbs.data && kbs.data.length === 0 ? (
                  <EmptyRow colSpan={6} label="No knowledge bases yet." />
                ) : null}
              </tbody>
            </table>
          </div>
        </TabsContent>

        <TabsContent value="connectors" className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <Badge variant="secondary">{connectors.data?.length ?? 0} connectors</Badge>
            <Button
              onClick={() => {
                setEditingConnector(null);
                setConnectorDialogOpen(true);
              }}
            >
              <Plus className="size-4" /> Add connector
            </Button>
          </div>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full">
              <thead className="bg-secondary/50">
                <tr>
                  <Th>Connector</Th>
                  <Th>Kind</Th>
                  <Th>KB</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {(connectors.data ?? []).map((connector) => (
                  <ConnectorRow
                    key={connector.connector_id}
                    connector={connector}
                    onEdit={() => {
                      setEditingConnector(connector);
                      setConnectorDialogOpen(true);
                    }}
                  />
                ))}
                {connectors.data && connectors.data.length === 0 ? (
                  <EmptyRow colSpan={5} label="No connectors yet." />
                ) : null}
              </tbody>
            </table>
          </div>
        </TabsContent>
      </Tabs>

      <KbDialog open={kbDialogOpen} editing={editingKb} onOpenChange={setKbDialogOpen} />
      <DocumentsDialog kbId={documentsFor} onOpenChange={(open) => !open && setDocumentsFor(null)} />
      <SyncDialog kbId={syncFor} onOpenChange={(open) => !open && setSyncFor(null)} />
      <ConnectorDialog open={connectorDialogOpen} editing={editingConnector} onOpenChange={setConnectorDialogOpen} />
    </div>
  );
}

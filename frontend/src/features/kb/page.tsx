import { type ReactNode, useEffect, useState } from 'react'
import { Inbox, Plus, Trash2 } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import { SimpleSelect } from '@/components/base/simple-select'
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
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
  useKbConnectorsQuery,
  useKbsQuery,
  useSyncDocumentsMutation,
  useUpdateConnectorMutation,
  useUpdateKbMutation,
} from '@/features/kb/api'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'

const TENANT = 'default'
const DOC_FORMATS = ['markdown', 'text', 'html'] as const
const CONNECTOR_KINDS = ['google_drive', 'confluence'] as const

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
  )
}

// ─────────────────────────── KB create / edit dialog ───────────────────────────

function KbDialog({
  open,
  editing,
  onOpenChange,
}: {
  open: boolean
  editing: KnowledgeBase | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const create = useCreateKbMutation()
  const update = useUpdateKbMutation(editing?.kb_id ?? '')
  const isEdit = editing !== null
  const [kbId, setKbId] = useState('')
  const [description, setDescription] = useState('')

  useEffect(() => {
    if (open) {
      setKbId(editing?.kb_id ?? '')
      setDescription(editing?.description ?? '')
    }
  }, [open, editing])

  const submit = async (): Promise<void> => {
    if (isEdit) {
      await update.mutateAsync({ description })
    } else {
      await create.mutateAsync({ kb_id: kbId.trim(), description, tenant_id: TENANT })
    }
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? t('kb.editKbTitle', { name: editing?.kb_id ?? '' }) : t('kb.addKbTitle')}</DialogTitle>
          <DialogDescription>{t('kb.kbDialogDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="kb-id">
              {t('kb.kbIdLabel')} <span className="text-destructive">*</span>
            </Label>
            <Input disabled={isEdit} id="kb-id" onChange={(event) => setKbId(event.target.value)} value={kbId} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="kb-description">{t('kb.descriptionLabel')}</Label>
            <Input id="kb-description" onChange={(event) => setDescription(event.target.value)} value={description} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('kb.cancel')}
          </Button>
          <Button
            disabled={(!isEdit && !kbId.trim()) || create.isPending || update.isPending}
            onClick={() => void submit()}
          >
            {isEdit ? t('kb.save') : t('kb.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Documents dialog ───────────────────────────

function DocumentsDialog({
  kbId,
  onOpenChange,
}: {
  kbId: string | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const documents = useDocumentsQuery(kbId)
  const ingest = useIngestDocumentMutation(kbId ?? '')
  const deleteDocument = useDeleteDocumentMutation(kbId ?? '')

  const [source, setSource] = useState('')
  const [format, setFormat] = useState<string | null>('markdown')
  const [content, setContent] = useState('')

  useEffect(() => {
    if (kbId) {
      setSource(`${kbId}.md`)
      setFormat('markdown')
      setContent('')
    }
  }, [kbId])

  const submit = async (): Promise<void> => {
    await ingest.mutateAsync({ source, content, document_format: format ?? '', tenant_id: TENANT })
    setContent('')
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(kbId)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('kb.documentsTitle', { name: kbId ?? '' })}</DialogTitle>
          <DialogDescription>{t('kb.documentsDescription')}</DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="doc-source">{t('kb.sourceLabel')}</Label>
              <Input id="doc-source" onChange={(event) => setSource(event.target.value)} value={source} />
            </div>
            <div className="grid gap-2">
              <Label>{t('kb.formatLabel')}</Label>
              <SimpleSelect
                onValueChange={setFormat}
                options={DOC_FORMATS.map((option) => ({ value: option, label: option }))}
                value={format}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="doc-content">{t('kb.contentLabel')}</Label>
            <Textarea
              className="min-h-28"
              id="doc-content"
              onChange={(event) => setContent(event.target.value)}
              value={content}
            />
          </div>
          <Button className="justify-self-start" disabled={!content || ingest.isPending} onClick={() => void submit()}>
            <Plus className="size-4" /> {t('kb.ingestDocument')}
          </Button>
        </div>

        <div className="max-h-60 space-y-2 overflow-y-auto">
          {(documents.data ?? []).map((document) => (
            <div
              className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
              key={document.document_id}
            >
              <div className="min-w-0">
                <p className="truncate font-medium text-foreground text-sm">{document.filename}</p>
                <p className="text-muted-foreground text-xs">{t('kb.chunksCount', { count: document.chunks })}</p>
              </div>
              <Button
                aria-label={t('kb.deleteDocument', { name: document.filename })}
                onClick={() =>
                  void deleteDocument.mutateAsync({ document_id: document.document_id, tenant_id: TENANT })
                }
                size="icon"
                variant="ghost"
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
          {documents.data && documents.data.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t('kb.noDocuments')}</p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Sync dialog ───────────────────────────

function SyncDialog({
  kbId,
  onOpenChange,
}: {
  kbId: string | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const sync = useSyncDocumentsMutation(kbId ?? '')
  const [path, setPath] = useState('')

  useEffect(() => {
    if (kbId) setPath(`/data/${kbId}`)
  }, [kbId])

  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(kbId)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('kb.syncTitle', { name: kbId ?? '' })}</DialogTitle>
          <DialogDescription>{t('kb.syncDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="sync-path">{t('kb.directoryPathLabel')}</Label>
          <Input id="sync-path" onChange={(event) => setPath(event.target.value)} value={path} />
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('kb.cancel')}
          </Button>
          <Button
            disabled={!path || sync.isPending}
            onClick={() => void sync.mutateAsync({ path, tenant_id: TENANT }).then(() => onOpenChange(false))}
          >
            {t('kb.sync')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── KB row ───────────────────────────

function KbRow({
  kb,
  onEdit,
  onDocuments,
  onSync,
}: {
  kb: KnowledgeBase
  onEdit: () => void
  onDocuments: () => void
  onSync: () => void
}): JSX.Element {
  const t = useT()
  const remove = useDeleteKbMutation(kb.kb_id)
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <tr className="border-border border-b last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3">
        <p className="font-semibold text-foreground text-sm">{kb.kb_id}</p>
        {kb.description ? <p className="line-clamp-1 text-muted-foreground text-sm">{kb.description}</p> : null}
      </td>
      <td className="px-4 py-3 text-muted-foreground text-sm">{kb.doc_count}</td>
      <td className="px-4 py-3 text-muted-foreground text-sm">{kb.chunk_count}</td>
      <td className="px-4 py-3 text-muted-foreground text-sm">
        {kb.bound_agents.length ? kb.bound_agents.join(', ') : '-'}
      </td>
      <td className="px-4 py-3">
        <Badge variant={kb.archived ? 'warning' : 'success'}>{kb.archived ? t('kb.archived') : t('kb.active')}</Badge>
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button aria-label={t('kb.actionsFor', { name: kb.kb_id })} size="sm" variant="secondary">
                {t('kb.actions')}
              </Button>
            }
          />
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setTimeout(onEdit, 0)}>{t('kb.edit')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(onDocuments, 0)}>{t('kb.documents')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(onSync, 0)}>{t('kb.syncAction')}</DropdownMenuItem>
            {!kb.archived ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setTimeout(() => setConfirmDelete(true), 0)} variant="destructive">
                  <Trash2 /> {t('kb.delete')}
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>

        <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('kb.deleteKbConfirmTitle', { name: kb.kb_id })}</AlertDialogTitle>
              <AlertDialogDescription>{t('kb.deleteKbConfirmDescription')}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('kb.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={() => void remove.mutateAsync({ tenant_id: TENANT })}>
                {t('kb.delete')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </td>
    </tr>
  )
}

// ─────────────────────────── Connector dialog ───────────────────────────

function ConnectorDialog({
  open,
  editing,
  onOpenChange,
}: {
  open: boolean
  editing: KbConnector | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const create = useCreateConnectorMutation()
  const update = useUpdateConnectorMutation(editing?.connector_id ?? '')
  const isEdit = editing !== null

  const [connectorId, setConnectorId] = useState('')
  const [kind, setKind] = useState<string | null>('google_drive')
  const [kbId, setKbId] = useState('global')
  const [description, setDescription] = useState('')
  const [configJson, setConfigJson] = useState('{}')
  const [customYaml, setCustomYaml] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setConnectorId(editing?.connector_id ?? '')
      setKind(editing?.kind ?? 'google_drive')
      setKbId(editing?.kb_id ?? 'global')
      setDescription(editing?.description ?? '')
      setConfigJson(editing?.config ? JSON.stringify(editing.config, null, 2) : '{}')
      setCustomYaml(editing?.custom_yaml ?? '')
      setEnabled(editing?.enabled ?? true)
      setError(null)
    }
  }, [open, editing])

  const submit = async (): Promise<void> => {
    let config: Record<string, unknown>
    try {
      config = JSON.parse(configJson || '{}') as Record<string, unknown>
    } catch {
      setError(t('kb.invalidConfigJson'))
      return
    }
    if (isEdit) {
      await update.mutateAsync({
        config,
        custom_yaml: customYaml,
        description,
        enabled,
        kb_id: kbId,
        tenant_id: TENANT,
      })
    } else {
      const input: CreateConnectorInput = {
        config,
        connector_id: connectorId.trim(),
        custom_yaml: customYaml,
        description,
        enabled,
        kb_id: kbId,
        kind: kind ?? '',
        tenant_id: TENANT,
      }
      await create.mutateAsync(input)
    }
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? t('kb.editConnectorTitle', { name: editing?.connector_id ?? '' }) : t('kb.addConnectorTitle')}
          </DialogTitle>
          <DialogDescription>{t('kb.connectorDialogDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="conn-id">
                {t('kb.connectorIdLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input
                disabled={isEdit}
                id="conn-id"
                onChange={(event) => setConnectorId(event.target.value)}
                value={connectorId}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t('kb.kindLabel')}</Label>
              <SimpleSelect
                disabled={isEdit}
                onValueChange={setKind}
                options={CONNECTOR_KINDS.map((option) => ({ value: option, label: option }))}
                value={kind}
              />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="conn-kb">{t('kb.kbIdLabel')}</Label>
              <Input id="conn-kb" onChange={(event) => setKbId(event.target.value)} value={kbId} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="conn-desc">{t('kb.descriptionLabel')}</Label>
              <Input id="conn-desc" onChange={(event) => setDescription(event.target.value)} value={description} />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="conn-config">{t('kb.configJsonLabel')}</Label>
            <Textarea
              className="min-h-24 font-mono text-xs"
              id="conn-config"
              onChange={(event) => setConfigJson(event.target.value)}
              value={configJson}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="conn-yaml">{t('kb.customYamlLabel')}</Label>
            <Textarea
              className="min-h-20 font-mono text-xs"
              id="conn-yaml"
              onChange={(event) => setCustomYaml(event.target.value)}
              value={customYaml}
            />
          </div>
          <div className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
            {t('kb.enabledLabel')}
            <Switch aria-label={t('kb.enabledLabel')} checked={enabled} onCheckedChange={setEnabled} />
          </div>
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('kb.cancel')}
          </Button>
          <Button
            disabled={(!isEdit && !connectorId.trim()) || create.isPending || update.isPending}
            onClick={() => void submit()}
          >
            {isEdit ? t('kb.save') : t('kb.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Connector row ───────────────────────────

function ConnectorRow({ connector, onEdit }: { connector: KbConnector; onEdit: () => void }): JSX.Element {
  const t = useT()
  const status = useConnectorStatusQuery(connector.connector_id)
  const check = useConnectorCheckMutation(connector.connector_id)
  const sync = useConnectorSyncMutation(connector.connector_id)
  const remove = useDeleteConnectorMutation(connector.connector_id)
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <tr className="border-border border-b last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3 font-mono text-foreground text-sm">{connector.connector_id}</td>
      <td className="px-4 py-3 text-muted-foreground text-sm">{connector.kind}</td>
      <td className="px-4 py-3 text-muted-foreground text-sm">{connector.kb_id}</td>
      <td className="px-4 py-3">
        <Badge variant={connector.enabled ? 'success' : 'secondary'}>
          {connector.enabled ? t('kb.enabled') : t('kb.disabled')}
        </Badge>
        <span className="ml-2 text-muted-foreground text-xs">
          {check.data ? check.data.status : (status.data?.status ?? '')}
        </span>
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button aria-label={t('kb.actionsFor', { name: connector.connector_id })} size="sm" variant="secondary">
                {t('kb.actions')}
              </Button>
            }
          />
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setTimeout(onEdit, 0)}>{t('kb.edit')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => void check.mutateAsync()}>{t('kb.check')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => void sync.mutateAsync({ dry_run: true })}>
              {t('kb.syncDryRun')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setTimeout(() => setConfirmDelete(true), 0)} variant="destructive">
              <Trash2 /> {t('kb.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {t('kb.deleteConnectorConfirmTitle', { name: connector.connector_id })}
              </AlertDialogTitle>
              <AlertDialogDescription>{t('kb.deleteConnectorConfirmDescription')}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('kb.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={() => void remove.mutateAsync()}>{t('kb.delete')}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </td>
    </tr>
  )
}

// ─────────────────────────── Page ───────────────────────────

export function KnowledgeBasePage(): JSX.Element {
  const t = useT()
  const kbs = useKbsQuery()
  const connectors = useKbConnectorsQuery()

  const [kbDialogOpen, setKbDialogOpen] = useState(false)
  const [editingKb, setEditingKb] = useState<KnowledgeBase | null>(null)
  const [documentsFor, setDocumentsFor] = useState<string | null>(null)
  const [syncFor, setSyncFor] = useState<string | null>(null)

  const [connectorDialogOpen, setConnectorDialogOpen] = useState(false)
  const [editingConnector, setEditingConnector] = useState<KbConnector | null>(null)

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-semibold text-xl tracking-tight">{t('kb.title')}</h2>
        <p className="mt-1 text-muted-foreground text-sm">{t('kb.subtitle')}</p>
      </div>

      <Tabs defaultValue="kbs">
        <TabsList>
          <TabsTrigger value="kbs">{t('kb.tabKbs')}</TabsTrigger>
          <TabsTrigger value="connectors">{t('kb.tabConnectors')}</TabsTrigger>
        </TabsList>

        <TabsContent className="space-y-4" value="kbs">
          <div className="flex items-center justify-between gap-3">
            <Badge variant="secondary">{t('kb.basesCount', { count: kbs.data?.length ?? 0 })}</Badge>
            <Button
              onClick={() => {
                setEditingKb(null)
                setKbDialogOpen(true)
              }}
            >
              <Plus className="size-4" /> {t('kb.addKb')}
            </Button>
          </div>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full">
              <thead className="bg-secondary/50">
                <tr>
                  <Th>{t('kb.colKb')}</Th>
                  <Th>{t('kb.colDocs')}</Th>
                  <Th>{t('kb.colChunks')}</Th>
                  <Th>{t('kb.colBoundAgents')}</Th>
                  <Th>{t('kb.colStatus')}</Th>
                  <Th className="text-right">{t('kb.colActions')}</Th>
                </tr>
              </thead>
              <tbody>
                {(kbs.data ?? []).map((kb) => (
                  <KbRow
                    kb={kb}
                    key={kb.kb_id}
                    onDocuments={() => setDocumentsFor(kb.kb_id)}
                    onEdit={() => {
                      setEditingKb(kb)
                      setKbDialogOpen(true)
                    }}
                    onSync={() => setSyncFor(kb.kb_id)}
                  />
                ))}
                {kbs.data && kbs.data.length === 0 ? <EmptyRow colSpan={6} label={t('kb.noKbs')} /> : null}
              </tbody>
            </table>
          </div>
        </TabsContent>

        <TabsContent className="space-y-4" value="connectors">
          <div className="flex items-center justify-between gap-3">
            <Badge variant="secondary">{t('kb.connectorsCount', { count: connectors.data?.length ?? 0 })}</Badge>
            <Button
              onClick={() => {
                setEditingConnector(null)
                setConnectorDialogOpen(true)
              }}
            >
              <Plus className="size-4" /> {t('kb.addConnector')}
            </Button>
          </div>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full">
              <thead className="bg-secondary/50">
                <tr>
                  <Th>{t('kb.colConnector')}</Th>
                  <Th>{t('kb.colKind')}</Th>
                  <Th>{t('kb.colConnectorKb')}</Th>
                  <Th>{t('kb.colStatus')}</Th>
                  <Th className="text-right">{t('kb.colActions')}</Th>
                </tr>
              </thead>
              <tbody>
                {(connectors.data ?? []).map((connector) => (
                  <ConnectorRow
                    connector={connector}
                    key={connector.connector_id}
                    onEdit={() => {
                      setEditingConnector(connector)
                      setConnectorDialogOpen(true)
                    }}
                  />
                ))}
                {connectors.data && connectors.data.length === 0 ? (
                  <EmptyRow colSpan={5} label={t('kb.noConnectors')} />
                ) : null}
              </tbody>
            </table>
          </div>
        </TabsContent>
      </Tabs>

      <KbDialog editing={editingKb} onOpenChange={setKbDialogOpen} open={kbDialogOpen} />
      <DocumentsDialog kbId={documentsFor} onOpenChange={(open) => !open && setDocumentsFor(null)} />
      <SyncDialog kbId={syncFor} onOpenChange={(open) => !open && setSyncFor(null)} />
      <ConnectorDialog editing={editingConnector} onOpenChange={setConnectorDialogOpen} open={connectorDialogOpen} />
    </div>
  )
}

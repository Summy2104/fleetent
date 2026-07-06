import { type ReactNode, useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, Inbox, Plus, RefreshCcw, Trash2 } from 'lucide-react'

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  type DocumentChunk,
  type KnowledgeBase,
  useCreateKbMutation,
  useBindAgentMutation,
  useDeleteDocumentMutation,
  useDeleteKbMutation,
  useDocumentChunksQuery,
  useDocumentsQuery,
  useKbAgentsQuery,
  useKbsQuery,
  useSearchKbMutation,
  useUnbindAgentMutation,
  useUploadDocumentMutation,
  useUpdateKbMutation,
} from '@/features/kb/api'
import { useAgentsQuery } from '@/features/agents/api'
import { useT } from '@/i18n'
import { describeApiError } from '@/lib/api-client'
import { toast } from '@/lib/toast'
import { cn } from '@/lib/utils'

const TENANT = 'default'

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

function ChunkPreview({ chunk }: { chunk: DocumentChunk }): JSX.Element {
  const t = useT()

  return (
    <div className="space-y-2 rounded-md border border-border border-dashed bg-muted/20 p-3">
      <div className="grid gap-1 text-sm">
        <span className="font-medium text-foreground">{t('kb.chunkSection')}</span>
        <span className="text-muted-foreground">{chunk.section || '-'}</span>
      </div>
      <div className="grid gap-1 text-sm">
        <span className="font-medium text-foreground">{t('kb.chunkContent')}</span>
        <p className="whitespace-pre-wrap text-foreground">{chunk.content}</p>
      </div>
    </div>
  )
}

function DocumentsSection({ kbId }: { kbId: string }): JSX.Element {
  const t = useT()
  const documents = useDocumentsQuery(kbId)
  const deleteDocument = useDeleteDocumentMutation(kbId)
  const uploadDocument = useUploadDocumentMutation(kbId)
  const [expandedDocumentId, setExpandedDocumentId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const chunks = useDocumentChunksQuery(kbId, expandedDocumentId)

  useEffect(() => {
    if (expandedDocumentId && !(documents.data ?? []).some((document) => document.document_id === expandedDocumentId)) {
      setExpandedDocumentId(null)
    }
  }, [documents.data, expandedDocumentId])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold text-lg">{t('kb.documentsTitle', { name: kbId })}</h3>
          <p className="text-muted-foreground text-sm">{t('kb.documentsDescription')}</p>
        </div>
        <Button onClick={() => void documents.refetch()} size="sm" variant="outline">
          <RefreshCcw className="size-4" /> {t('kb.refresh')}
        </Button>
      </div>

      <div className="grid gap-3 rounded-lg border border-border p-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
        <div className="grid gap-2">
          <Label htmlFor="kb-upload-file">{t('kb.uploadDocument')}</Label>
          <input
            accept="*/*"
            className="h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-2.5 py-1 text-base shadow-xs outline-none transition-[color,box-shadow] file:inline-flex file:h-7 file:border-0 file:bg-transparent file:font-medium file:text-foreground file:text-sm placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40"
            id="kb-upload-file"
            ref={fileInputRef}
            type="file"
          />
        </div>
        <Button
          disabled={uploadDocument.isPending}
          onClick={() => {
            const file = fileInputRef.current?.files?.[0]
            if (!file) {
              return
            }

            void uploadDocument
              .mutateAsync({ file })
              .then((result) => {
                toast.success(`已入队（job ${result.job_id}）`)
                if (fileInputRef.current) {
                  fileInputRef.current.value = ''
                }
              })
              .catch((error) => {
                toast.error(describeApiError(error))
              })
          }}
        >
          {t('kb.uploadDocument')}
        </Button>
      </div>

      <div className="space-y-3">
        {(documents.data ?? []).map((document) => {
          const expanded = expandedDocumentId === document.document_id
          return (
            <div className="space-y-3 rounded-lg border border-border p-4" key={document.document_id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <p className="truncate font-medium text-foreground text-sm">{document.filename}</p>
                  <p className="text-muted-foreground text-xs">{t('kb.chunksCount', { count: document.chunks })}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    aria-label={
                      expanded ? t('kb.hideChunksFor', { name: document.filename }) : t('kb.previewChunksFor', { name: document.filename })
                    }
                    onClick={() =>
                      setExpandedDocumentId((current) => (current === document.document_id ? null : document.document_id))
                    }
                    size="sm"
                    variant="outline"
                  >
                    {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
                    {expanded ? t('kb.hideChunks') : t('kb.previewChunks')}
                  </Button>
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
              </div>

              {expanded ? (
                <div className="space-y-3">
                  {chunks.isPending ? <p className="text-muted-foreground text-sm">{t('kb.loadingChunks')}</p> : null}
                  {(chunks.data ?? []).map((chunk) => (
                    <ChunkPreview chunk={chunk} key={chunk.chunk_id} />
                  ))}
                  {chunks.data && chunks.data.length === 0 ? (
                    <p className="text-muted-foreground text-sm">{t('kb.noChunks')}</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          )
        })}
        {documents.data && documents.data.length === 0 ? <p className="text-muted-foreground text-sm">{t('kb.noDocuments')}</p> : null}
      </div>
    </div>
  )
}

function AgentsSection({ kbId }: { kbId: string }): JSX.Element {
  const t = useT()
  const agents = useAgentsQuery()
  const bindings = useKbAgentsQuery(kbId)
  const bindAgent = useBindAgentMutation(kbId)
  const unbindAgent = useUnbindAgentMutation(kbId)
  const [selectedAgentId, setSelectedAgentId] = useState('')

  const boundAgentIds = bindings.data?.agents ?? []
  const candidateOptions = (agents.data ?? [])
    .filter((agent) => agent.agent_id !== undefined && !boundAgentIds.includes(agent.agent_id))
    .map((agent) => ({
      label: agent.agent_name,
      value: String(agent.agent_id),
    }))

  useEffect(() => {
    if (selectedAgentId && !candidateOptions.some((option) => option.value === selectedAgentId)) {
      setSelectedAgentId('')
    }
  }, [candidateOptions, selectedAgentId])

  const agentNameById = new Map(
    (agents.data ?? [])
      .filter((agent) => agent.agent_id !== undefined)
      .map((agent) => [agent.agent_id as number, agent.agent_name])
  )

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
        <div className="grid gap-2">
          <Label htmlFor="kb-agent-select">{t('kb.agentLabel')}</Label>
          <SimpleSelect
            options={candidateOptions}
            onValueChange={setSelectedAgentId}
            placeholder={t('kb.agentPlaceholder')}
            triggerAriaLabel={t('kb.agentLabel')}
            triggerId="kb-agent-select"
            value={selectedAgentId}
          />
        </div>
        <Button
          disabled={!selectedAgentId || bindAgent.isPending}
          onClick={() =>
            void bindAgent.mutateAsync({ agent_id: Number(selectedAgentId), tenant_id: TENANT }).then(() => {
              setSelectedAgentId('')
            })
          }
        >
          {t('kb.bindAgent')}
        </Button>
      </div>

      <div className="space-y-3">
        {boundAgentIds.map((agentId) => (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-border p-3" key={agentId}>
            <div>
              <p className="font-medium text-foreground text-sm">{agentNameById.get(agentId) ?? agentId}</p>
              <p className="text-muted-foreground text-xs">{agentId}</p>
            </div>
            <Button
              aria-label={t('kb.unbindAgentFor', { id: agentId })}
              onClick={() => void unbindAgent.mutateAsync({ agent_id: agentId, tenant_id: TENANT })}
              size="sm"
              variant="outline"
            >
              {t('kb.unbindAgent')}
            </Button>
          </div>
        ))}
        {bindings.data && bindings.data.agents.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t('kb.noBoundAgents')}</p>
        ) : null}
      </div>
    </div>
  )
}

function PlaygroundSection({ kbId }: { kbId: string }): JSX.Element {
  const t = useT()
  const searchKb = useSearchKbMutation()
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState('5')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const results = searchKb.data?.results ?? []

  const submit = async (): Promise<void> => {
    setErrorMessage(null)
    try {
      await searchKb.mutateAsync({
        kb_id: kbId,
        query,
        tenant_id: TENANT,
        top_k: topK.trim() === '' ? undefined : Number(topK),
      })
    } catch (error) {
      setErrorMessage(describeApiError(error))
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_140px_auto] md:items-end">
        <div className="grid gap-2">
          <Label htmlFor="kb-playground-query">{t('kb.playgroundQueryLabel')}</Label>
          <Input id="kb-playground-query" onChange={(event) => setQuery(event.target.value)} value={query} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="kb-playground-topk">{t('kb.playgroundTopKLabel')}</Label>
          <Input id="kb-playground-topk" onChange={(event) => setTopK(event.target.value)} value={topK} />
        </div>
        <Button disabled={!query.trim() || searchKb.isPending} onClick={() => void submit()}>
          {t('kb.runSearch')}
        </Button>
      </div>

      {errorMessage ? <p className="text-destructive text-sm">{errorMessage}</p> : null}
      {!errorMessage && searchKb.data && results.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t('kb.noSearchResults')}</p>
      ) : null}

      <div className="space-y-3">
        {results.map((result) => (
          <div className="space-y-2 rounded-lg border border-border p-4" key={result.chunk_id}>
            <div className="flex flex-wrap items-center gap-2 text-muted-foreground text-xs">
              <span>{result.filename}</span>
              <span>{result.score?.toFixed(2) ?? '-'}</span>
            </div>
            <p className="font-medium text-foreground text-sm">{result.section || '-'}</p>
            <p className="whitespace-pre-wrap text-foreground text-sm">{result.content}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function KbDetailPanel({
  activeTab,
  kb,
  onTabChange,
}: {
  activeTab: 'documents' | 'agents' | 'playground'
  kb: KnowledgeBase | null
  onTabChange: (value: 'documents' | 'agents' | 'playground') => void
}): JSX.Element {
  const t = useT()

  if (!kb) {
    return (
      <div className="rounded-xl border border-border border-dashed bg-muted/10 p-6 text-muted-foreground text-sm">
        {t('kb.selectKbPrompt')}
      </div>
    )
  }

  return (
    <section className="space-y-4 rounded-xl border border-border bg-card p-5">
      <div className="space-y-1">
        <h3 className="font-semibold text-lg">{t('kb.detailTitle', { name: kb.kb_id })}</h3>
        <p className="text-muted-foreground text-sm">{t('kb.detailDescription')}</p>
      </div>

      <Tabs onValueChange={(value) => onTabChange(value as 'documents' | 'agents' | 'playground')} value={activeTab}>
        <TabsList>
          <TabsTrigger value="documents">{t('kb.documents')}</TabsTrigger>
          <TabsTrigger value="agents">{t('kb.tabAgents')}</TabsTrigger>
          <TabsTrigger value="playground">{t('kb.tabPlayground')}</TabsTrigger>
        </TabsList>
        <TabsContent value="documents">
          <DocumentsSection kbId={kb.kb_id} />
        </TabsContent>
        <TabsContent value="agents">
          <AgentsSection kbId={kb.kb_id} />
        </TabsContent>
        <TabsContent value="playground">
          <PlaygroundSection kbId={kb.kb_id} />
        </TabsContent>
      </Tabs>
    </section>
  )
}

function KbRow({
  kb,
  onEdit,
  onOpenDetails,
}: {
  kb: KnowledgeBase
  onEdit: () => void
  onOpenDetails: (tab: 'documents' | 'agents' | 'playground') => void
}): JSX.Element {
  const t = useT()
  const remove = useDeleteKbMutation(kb.kb_id)
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <tr className="border-border border-b last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3">
        <button className="text-left" onClick={() => onOpenDetails('documents')} type="button">
          <p className="font-semibold text-foreground text-sm">{kb.kb_id}</p>
          {kb.description ? <p className="line-clamp-1 text-muted-foreground text-sm">{kb.description}</p> : null}
        </button>
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
            <DropdownMenuItem onClick={() => setTimeout(() => onOpenDetails('documents'), 0)}>
              {t('kb.documents')}
            </DropdownMenuItem>
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

export function KnowledgeBasePage(): JSX.Element {
  const t = useT()
  const kbs = useKbsQuery()

  const [kbDialogOpen, setKbDialogOpen] = useState(false)
  const [editingKb, setEditingKb] = useState<KnowledgeBase | null>(null)
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'documents' | 'agents' | 'playground'>('documents')

  useEffect(() => {
    if (selectedKbId && !(kbs.data ?? []).some((kb) => kb.kb_id === selectedKbId)) {
      setSelectedKbId(null)
    }
  }, [kbs.data, selectedKbId])

  const selectedKb = (kbs.data ?? []).find((kb) => kb.kb_id === selectedKbId) ?? null

  const openDetails = (kbId: string, tab: 'documents' | 'agents' | 'playground'): void => {
    setSelectedKbId(kbId)
    setActiveTab(tab)
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-semibold text-xl tracking-tight">{t('kb.title')}</h2>
        <p className="mt-1 text-muted-foreground text-sm">{t('kb.subtitle')}</p>
      </div>

      <div className="space-y-4">
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
                  onEdit={() => {
                    setEditingKb(kb)
                    setKbDialogOpen(true)
                  }}
                  onOpenDetails={(tab) => openDetails(kb.kb_id, tab)}
                />
              ))}
              {kbs.data && kbs.data.length === 0 ? <EmptyRow colSpan={6} label={t('kb.noKbs')} /> : null}
            </tbody>
          </table>
        </div>
      </div>

      <KbDetailPanel activeTab={activeTab} kb={selectedKb} onTabChange={setActiveTab} />
      <KbDialog editing={editingKb} onOpenChange={setKbDialogOpen} open={kbDialogOpen} />
    </div>
  )
}

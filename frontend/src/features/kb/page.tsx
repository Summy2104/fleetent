import { type ReactNode, useEffect, useState } from 'react'
import { Inbox, Plus, Trash2 } from 'lucide-react'

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
import {
  type KnowledgeBase,
  useCreateKbMutation,
  useDeleteDocumentMutation,
  useDeleteKbMutation,
  useDocumentsQuery,
  useKbsQuery,
  useUpdateKbMutation,
} from '@/features/kb/api'
import { useT } from '@/i18n'
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

function DocumentsDialog({
  kbId,
  onOpenChange,
}: {
  kbId: string | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const documents = useDocumentsQuery(kbId)
  const deleteDocument = useDeleteDocumentMutation(kbId ?? '')

  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(kbId)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('kb.documentsTitle', { name: kbId ?? '' })}</DialogTitle>
          <DialogDescription>{t('kb.documentsDescription')}</DialogDescription>
        </DialogHeader>

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

function KbRow({
  kb,
  onEdit,
  onDocuments,
}: {
  kb: KnowledgeBase
  onEdit: () => void
  onDocuments: () => void
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
  const [documentsFor, setDocumentsFor] = useState<string | null>(null)

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
                  onDocuments={() => setDocumentsFor(kb.kb_id)}
                  onEdit={() => {
                    setEditingKb(kb)
                    setKbDialogOpen(true)
                  }}
                />
              ))}
              {kbs.data && kbs.data.length === 0 ? <EmptyRow colSpan={6} label={t('kb.noKbs')} /> : null}
            </tbody>
          </table>
        </div>
      </div>

      <KbDialog editing={editingKb} onOpenChange={setKbDialogOpen} open={kbDialogOpen} />
      <DocumentsDialog kbId={documentsFor} onOpenChange={(open) => !open && setDocumentsFor(null)} />
    </div>
  )
}

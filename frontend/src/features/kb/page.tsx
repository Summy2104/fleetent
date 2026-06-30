import { type ReactNode, useEffect, useState } from 'react';
import { Inbox, Plus, Trash2 } from 'lucide-react';

import { useT } from '@/i18n';
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
import {
  type KnowledgeBase,
  useCreateKbMutation,
  useDeleteDocumentMutation,
  useDeleteKbMutation,
  useDocumentsQuery,
  useKbsQuery,
  useUpdateKbMutation,
} from '@/features/kb/api';

const TENANT = 'default';

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

function KbDialog({
  open,
  editing,
  onOpenChange,
}: {
  open: boolean;
  editing: KnowledgeBase | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const t = useT();
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
          <DialogTitle>
            {isEdit ? t('kb.editKbTitle', { name: editing?.kb_id ?? '' }) : t('kb.addKbTitle')}
          </DialogTitle>
          <DialogDescription>{t('kb.kbDialogDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="kb-id">
              {t('kb.kbIdLabel')} <span className="text-destructive">*</span>
            </Label>
            <Input id="kb-id" disabled={isEdit} value={kbId} onChange={(event) => setKbId(event.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="kb-description">{t('kb.descriptionLabel')}</Label>
            <Input
              id="kb-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
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
  );
}

function DocumentsDialog({
  kbId,
  onOpenChange,
}: {
  kbId: string | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const t = useT();
  const documents = useDocumentsQuery(kbId);
  const deleteDocument = useDeleteDocumentMutation(kbId ?? '');

  return (
    <Dialog open={Boolean(kbId)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('kb.documentsTitle', { name: kbId ?? '' })}</DialogTitle>
          <DialogDescription>{t('kb.documentsDescription')}</DialogDescription>
        </DialogHeader>

        <div className="max-h-60 space-y-2 overflow-y-auto">
          {(documents.data ?? []).map((document) => (
            <div
              key={document.document_id}
              className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{document.filename}</p>
                <p className="text-xs text-muted-foreground">
                  {t('kb.chunksCount', { count: document.chunks })}
                </p>
              </div>
              <Button
                size="icon"
                variant="ghost"
                aria-label={t('kb.deleteDocument', { name: document.filename })}
                onClick={() =>
                  void deleteDocument.mutateAsync({ document_id: document.document_id, tenant_id: TENANT })
                }
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
          {documents.data && documents.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('kb.noDocuments')}</p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function KbRow({
  kb,
  onEdit,
  onDocuments,
}: {
  kb: KnowledgeBase;
  onEdit: () => void;
  onDocuments: () => void;
}): JSX.Element {
  const t = useT();
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
        <Badge variant={kb.archived ? 'warning' : 'success'}>
          {kb.archived ? t('kb.archived') : t('kb.active')}
        </Badge>
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" aria-label={t('kb.actionsFor', { name: kb.kb_id })}>
              {t('kb.actions')}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setTimeout(onEdit, 0)}>{t('kb.edit')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setTimeout(onDocuments, 0)}>{t('kb.documents')}</DropdownMenuItem>
            {!kb.archived ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem destructive onSelect={() => setTimeout(() => setConfirmDelete(true), 0)}>
                  <Trash2 /> {t('kb.delete')}
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>

        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
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
  );
}

export function KnowledgeBasePage(): JSX.Element {
  const t = useT();
  const kbs = useKbsQuery();
  const [kbDialogOpen, setKbDialogOpen] = useState(false);
  const [editingKb, setEditingKb] = useState<KnowledgeBase | null>(null);
  const [documentsFor, setDocumentsFor] = useState<string | null>(null);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">{t('kb.title')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('kb.subtitle')}</p>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Badge variant="secondary">{t('kb.basesCount', { count: kbs.data?.length ?? 0 })}</Badge>
          <Button
            onClick={() => {
              setEditingKb(null);
              setKbDialogOpen(true);
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
                  key={kb.kb_id}
                  kb={kb}
                  onEdit={() => {
                    setEditingKb(kb);
                    setKbDialogOpen(true);
                  }}
                  onDocuments={() => setDocumentsFor(kb.kb_id)}
                />
              ))}
              {kbs.data && kbs.data.length === 0 ? <EmptyRow colSpan={6} label={t('kb.noKbs')} /> : null}
            </tbody>
          </table>
        </div>
      </div>

      <KbDialog open={kbDialogOpen} editing={editingKb} onOpenChange={setKbDialogOpen} />
      <DocumentsDialog kbId={documentsFor} onOpenChange={(open) => !open && setDocumentsFor(null)} />
    </div>
  );
}

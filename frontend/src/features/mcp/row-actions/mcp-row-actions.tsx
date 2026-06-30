import { useState } from 'react'
import { MoreVertical, Trash2 } from 'lucide-react'

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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  type McpServerRecord,
  useDeleteMcpServerMutation,
  useMcpReconnectMutation,
  useMcpServerTestMutation,
} from '@/features/connectors/api'
import { useT } from '@/i18n'

export function McpRowActions({
  server,
  canWrite,
  onEdit,
  onViewTools,
}: {
  server: McpServerRecord
  canWrite: boolean
  onEdit: (server: McpServerRecord) => void
  onViewTools: (server: McpServerRecord) => void
}): JSX.Element {
  const t = useT()
  const test = useMcpServerTestMutation(server.id)
  const reconnect = useMcpReconnectMutation(server.id)
  const remove = useDeleteMcpServerMutation(server.id)
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <div className="flex items-center justify-end gap-2">
      {test.data ? (
        <span className="text-muted-foreground text-xs">
          {test.data.connected
            ? t('mcp.connectedTools', { count: test.data.tools_count ?? 0 })
            : (test.data.error ?? t('mcp.testFailed'))}
        </span>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button aria-label={t('mcp.actionsFor', { name: server.id })} size="icon" variant="ghost">
              <MoreVertical className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setTimeout(() => onViewTools(server), 0)}>
            {t('mcp.viewTools')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void test.mutateAsync()}>{t('mcp.testConnection')}</DropdownMenuItem>
          {canWrite ? (
            <>
              <DropdownMenuItem onClick={() => void reconnect.mutateAsync()}>{t('mcp.reconnect')}</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setTimeout(() => onEdit(server), 0)}>{t('mcp.edit')}</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setTimeout(() => setConfirmDelete(true), 0)} variant="destructive">
                <Trash2 /> {t('mcp.delete')}
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
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
    </div>
  )
}

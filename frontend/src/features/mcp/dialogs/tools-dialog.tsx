import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useMcpServerToolsQuery } from '@/features/connectors/api'
import { useT } from '@/i18n'

export function ToolsDialog({
  serverId,
  onOpenChange,
}: {
  serverId: string | null
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const tools = useMcpServerToolsQuery(serverId)

  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(serverId)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('mcp.toolsTitle', { name: serverId ?? '' })}</DialogTitle>
          <DialogDescription>{t('mcp.toolsDescription')}</DialogDescription>
        </DialogHeader>
        {tools.data?.error ? (
          <p className="text-destructive text-sm">{tools.data.error}</p>
        ) : tools.data?.tools.length ? (
          <div className="space-y-2">
            {tools.data.tools.map((tool) => (
              <div className="rounded-md border border-border px-3 py-2" key={tool.name}>
                <p className="font-mono text-foreground text-sm">{tool.name}</p>
                {tool.description ? <p className="text-muted-foreground text-sm">{tool.description}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            {tools.isLoading ? t('mcp.connecting') : t('mcp.noToolsReported')}
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}

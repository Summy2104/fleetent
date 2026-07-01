import { Copy } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useT } from '@/i18n'

export function SecretDialog({ secret, onDismiss }: { secret: string | null; onDismiss: () => void }): JSX.Element {
  const t = useT()
  return (
    <Dialog onOpenChange={(open) => !open && onDismiss()} open={Boolean(secret)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.newApiKey')}</DialogTitle>
          <DialogDescription>{t('users.newApiKeyDescription')}</DialogDescription>
        </DialogHeader>
        <div className="rounded-md border border-warning/40 bg-warning/10 p-4">
          <p className="break-all font-mono text-foreground text-sm">{secret}</p>
        </div>
        <DialogFooter>
          <Button onClick={() => secret && void navigator.clipboard?.writeText(secret)} variant="outline">
            <Copy className="size-4" /> {t('users.copy')}
          </Button>
          <Button onClick={onDismiss}>{t('users.dismissNewSecret')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

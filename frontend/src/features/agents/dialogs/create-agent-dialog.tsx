import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useCreateAgentMutation } from '@/features/agents/api'
import { useT } from '@/i18n'

function parseAllowedTools(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function CreateAgentDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const create = useCreateAgentMutation()
  const [name, setName] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [allowedTools, setAllowedTools] = useState('')

  // Reset fields whenever the dialog re-opens.
  useEffect(() => {
    if (open) {
      setName('')
      setSystemPrompt('')
      setAllowedTools('')
    }
  }, [open])

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('agents.newAgent')}</DialogTitle>
          <DialogDescription>{t('agents.createDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="new-name">{t('agents.nameLabel')}</Label>
            <Input id="new-name" onChange={(event) => setName(event.target.value)} value={name} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="new-prompt">{t('agents.systemPromptLabel')}</Label>
            <Textarea
              className="min-h-32"
              id="new-prompt"
              onChange={(event) => setSystemPrompt(event.target.value)}
              value={systemPrompt}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="new-tools">{t('agents.allowedToolsLabel')}</Label>
            <Input
              id="new-tools"
              onChange={(event) => setAllowedTools(event.target.value)}
              placeholder="tool_a, tool_b"
              value={allowedTools}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('common.cancel')}
          </Button>
          <Button
            disabled={create.isPending || !name}
            onClick={() => {
              void (async () => {
                await create.mutateAsync({
                  name,
                  system_prompt: systemPrompt,
                  allowed_tools: parseAllowedTools(allowedTools),
                })
                onOpenChange(false)
              })()
            }}
          >
            {t('agents.createButton')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

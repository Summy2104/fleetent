import { useMemo, useState } from 'react'
import { Copy, Eye, Inbox, Pencil, Plus, Trash2 } from 'lucide-react'

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
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { type AgentListItem, useAgentsQuery } from '@/features/agents/api'
import { type UserListItem, useUsersQuery } from '@/features/users/api'
import {
  useCreateWebhookSourceMutation,
  useDeleteWebhookSourceMutation,
  useUpdateWebhookSourceMutation,
  useWebhookSourcesQuery,
  type WebhookSecretAction,
  type WebhookSourceInput,
  type WebhookSourceRecord,
  type WebhookSourceUpdateInput,
} from '@/features/webhooks/api'
import { useT } from '@/i18n'
import { labelWithId } from '@/lib/labels'

const NO_REPLY_TARGET = 'none'

// Resolve a bound user_id to "name (id)" for read-back, falling back to the id.
function userLabel(users: UserListItem[], id: string): string {
  return labelWithId(users.find((u) => u.id === id)?.name, id)
}

function generateSecret(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

// ─────────────────────────── Add dialog ───────────────────────────

function CreateWebhookDialog({
  open,
  agents,
  users,
  onOpenChange,
}: {
  open: boolean
  agents: AgentListItem[]
  users: UserListItem[]
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const create = useCreateWebhookSourceMutation()

  const [id, setId] = useState('')
  const [agentId, setAgentId] = useState('')
  const [userId, setUserId] = useState('')
  const [replyTarget, setReplyTarget] = useState(NO_REPLY_TARGET)
  const [messageTemplate, setMessageTemplate] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [secret, setSecret] = useState('')
  const [createdUrl, setCreatedUrl] = useState<string | null>(null)

  const reset = (): void => {
    setId('')
    setAgentId('')
    setUserId('')
    setReplyTarget(NO_REPLY_TARGET)
    setMessageTemplate('')
    setEnabled(true)
    setSecret('')
  }

  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      setCreatedUrl(null)
      reset()
    }
    onOpenChange(next)
  }

  const submit = async (): Promise<void> => {
    const payload: WebhookSourceInput = {
      id: id.trim(),
      agent_id: Number(agentId),
      user_id: userId,
      message_template: messageTemplate.trim() || null,
      reply_target: replyTarget === NO_REPLY_TARGET ? null : replyTarget,
      enabled,
      secret: secret.trim() || null,
    }
    await create.mutateAsync(payload)
    setCreatedUrl(`${window.location.origin}/webhook/${payload.id}`)
  }

  const canSubmit = id.trim().length > 0 && agentId.length > 0 && userId.length > 0

  return (
    <Dialog onOpenChange={handleOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{createdUrl ? t('webhooks.urlShownTitle') : t('webhooks.addTitle')}</DialogTitle>
          {createdUrl ? null : <DialogDescription>{t('webhooks.dialogDescription')}</DialogDescription>}
        </DialogHeader>

        {createdUrl ? (
          <div className="space-y-3 rounded-md border border-warning/40 bg-warning/10 p-4">
            <code className="block max-h-40 overflow-y-auto break-all rounded-md border border-border bg-background/60 p-3 font-mono text-foreground text-xs">
              {createdUrl}
            </code>
            <p className="text-muted-foreground text-xs">{t('webhooks.urlCopyHint')}</p>
            <div className="flex gap-2">
              <Button onClick={() => void navigator.clipboard?.writeText(createdUrl)} size="sm" variant="outline">
                <Copy className="size-4" /> {t('webhooks.copyUrl')}
              </Button>
              <Button onClick={() => handleOpenChange(false)} size="sm" variant="secondary">
                {t('webhooks.done')}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="webhook-id">
                  {t('webhooks.idLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="webhook-id"
                  onChange={(event) => setId(event.target.value)}
                  placeholder={t('webhooks.idPlaceholder')}
                  value={id}
                />
              </div>

              <div className="grid gap-2">
                <Label>
                  {t('webhooks.agentLabel')} <span className="text-destructive">*</span>
                </Label>
                <Select onValueChange={(value) => setAgentId(value ?? '')} value={agentId}>
                  <SelectTrigger aria-label={t('webhooks.agentLabel')}>
                    <SelectValue placeholder={t('webhooks.agentPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agent) => (
                      <SelectItem key={agent.agent_name} value={String(agent.agent_id ?? '')}>
                        {agent.agent_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label>
                  {t('webhooks.userLabel')} <span className="text-destructive">*</span>
                </Label>
                <Select onValueChange={(value) => setUserId(value ?? '')} value={userId}>
                  <SelectTrigger aria-label={t('webhooks.userLabel')}>
                    <SelectValue placeholder={t('webhooks.userPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    {users.map((user) => (
                      <SelectItem key={user.id} value={user.id}>
                        {user.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label>{t('webhooks.replyTargetLabel')}</Label>
                <Select onValueChange={(value) => setReplyTarget(value ?? NO_REPLY_TARGET)} value={replyTarget}>
                  <SelectTrigger aria-label={t('webhooks.replyTargetLabel')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_REPLY_TARGET}>{t('webhooks.replyTargetNone')}</SelectItem>
                    {users.map((user) => (
                      <SelectItem key={user.id} value={user.id}>
                        {user.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label htmlFor="webhook-message-template">{t('webhooks.messageTemplateLabel')}</Label>
                <Input
                  id="webhook-message-template"
                  onChange={(event) => setMessageTemplate(event.target.value)}
                  value={messageTemplate}
                />
                <p className="text-muted-foreground text-xs">{t('webhooks.messageTemplateHint')}</p>
              </div>

              <div className="flex items-center justify-between">
                <Label htmlFor="webhook-enabled">{t('webhooks.enabledLabel')}</Label>
                <Switch checked={enabled} id="webhook-enabled" onCheckedChange={setEnabled} />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="webhook-secret">{t('webhooks.secretLabel')}</Label>
                <div className="flex items-center gap-2">
                  <Input
                    className="flex-1"
                    id="webhook-secret"
                    onChange={(event) => setSecret(event.target.value)}
                    value={secret}
                  />
                  <Button onClick={() => setSecret(generateSecret())} type="button" variant="outline">
                    {t('webhooks.generateSecret')}
                  </Button>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={() => handleOpenChange(false)} variant="outline">
                {t('webhooks.cancel')}
              </Button>
              <Button disabled={!canSubmit || create.isPending} onClick={() => void submit()}>
                {t('webhooks.create')}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── View / edit dialog ───────────────────────────

function ReadonlyField({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="grid gap-1">
      <span className="font-medium text-muted-foreground text-xs uppercase tracking-wide">{label}</span>
      <span className="break-words text-foreground text-sm">{value}</span>
    </div>
  )
}

function ViewEditWebhookDialog({
  source,
  agents,
  users,
  agentName,
  open,
  onOpenChange,
}: {
  source: WebhookSourceRecord
  agents: AgentListItem[]
  users: UserListItem[]
  agentName: string
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const update = useUpdateWebhookSourceMutation(source.id)

  const [editing, setEditing] = useState(false)
  const [agentId, setAgentId] = useState('')
  const [userId, setUserId] = useState('')
  const [replyTarget, setReplyTarget] = useState(NO_REPLY_TARGET)
  const [messageTemplate, setMessageTemplate] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [secretMode, setSecretMode] = useState<WebhookSecretAction>('keep')
  const [secret, setSecret] = useState('')

  const userName = (id: string): string => userLabel(users, id)

  const enterEdit = (): void => {
    setAgentId(source.agent_id == null ? '' : String(source.agent_id))
    setUserId(source.user_id)
    setReplyTarget(source.reply_target ?? NO_REPLY_TARGET)
    setMessageTemplate(source.message_template ?? '')
    setEnabled(source.enabled)
    setSecretMode('keep')
    setSecret('')
    setEditing(true)
  }

  const handleOpenChange = (next: boolean): void => {
    if (!next) setEditing(false)
    onOpenChange(next)
  }

  const submit = async (): Promise<void> => {
    const payload: WebhookSourceUpdateInput = {
      user_id: userId,
      agent_id: Number(agentId),
      message_template: messageTemplate.trim() || null,
      reply_target: replyTarget === NO_REPLY_TARGET ? null : replyTarget,
      enabled,
      secret_action: secretMode,
      ...(secretMode === 'set' ? { secret: secret.trim() } : {}),
    }
    await update.mutateAsync(payload)
    setEditing(false)
  }

  const canSave = agentId.length > 0 && userId.length > 0 && (secretMode !== 'set' || secret.trim().length > 0)

  return (
    <Dialog onOpenChange={handleOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editing ? t('webhooks.editTitle') : t('webhooks.detailsTitle')}</DialogTitle>
        </DialogHeader>

        {editing ? (
          <>
            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="edit-webhook-id">{t('webhooks.idLabel')}</Label>
                <Input disabled id="edit-webhook-id" readOnly value={source.id} />
              </div>

              <div className="grid gap-2">
                <Label>
                  {t('webhooks.agentLabel')} <span className="text-destructive">*</span>
                </Label>
                <Select onValueChange={(value) => setAgentId(value ?? '')} value={agentId}>
                  <SelectTrigger aria-label={t('webhooks.agentLabel')}>
                    <SelectValue placeholder={t('webhooks.agentPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agent) => (
                      <SelectItem key={agent.agent_name} value={String(agent.agent_id ?? '')}>
                        {agent.agent_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label>
                  {t('webhooks.userLabel')} <span className="text-destructive">*</span>
                </Label>
                <Select onValueChange={(value) => setUserId(value ?? '')} value={userId}>
                  <SelectTrigger aria-label={t('webhooks.userLabel')}>
                    <SelectValue placeholder={t('webhooks.userPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    {users.map((user) => (
                      <SelectItem key={user.id} value={user.id}>
                        {user.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label>{t('webhooks.replyTargetLabel')}</Label>
                <Select onValueChange={(value) => setReplyTarget(value ?? NO_REPLY_TARGET)} value={replyTarget}>
                  <SelectTrigger aria-label={t('webhooks.replyTargetLabel')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_REPLY_TARGET}>{t('webhooks.replyTargetNone')}</SelectItem>
                    {users.map((user) => (
                      <SelectItem key={user.id} value={user.id}>
                        {user.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label htmlFor="edit-webhook-message-template">{t('webhooks.messageTemplateLabel')}</Label>
                <Input
                  id="edit-webhook-message-template"
                  onChange={(event) => setMessageTemplate(event.target.value)}
                  value={messageTemplate}
                />
                <p className="text-muted-foreground text-xs">{t('webhooks.messageTemplateHint')}</p>
              </div>

              <div className="flex items-center justify-between">
                <Label htmlFor="edit-webhook-enabled">{t('webhooks.enabledLabel')}</Label>
                <Switch checked={enabled} id="edit-webhook-enabled" onCheckedChange={setEnabled} />
              </div>

              <div className="grid gap-2">
                <Label>{t('webhooks.secretLabel')}</Label>
                {secretMode === 'keep' ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={source.has_secret ? 'success' : 'secondary'}>
                      {source.has_secret ? t('webhooks.secretSet') : t('webhooks.secretUnset')}
                    </Badge>
                    <Button onClick={() => setSecretMode('set')} size="sm" type="button" variant="outline">
                      {source.has_secret ? t('webhooks.replaceSecret') : t('webhooks.setSecret')}
                    </Button>
                    {source.has_secret ? (
                      <Button onClick={() => setSecretMode('clear')} size="sm" type="button" variant="outline">
                        {t('webhooks.clearSecret')}
                      </Button>
                    ) : null}
                    <p className="w-full text-muted-foreground text-xs">{t('webhooks.secretKeepHint')}</p>
                  </div>
                ) : null}
                {secretMode === 'set' ? (
                  <div className="grid gap-2">
                    <div className="flex items-center gap-2">
                      <Input
                        aria-label={t('webhooks.secretLabel')}
                        className="flex-1"
                        id="edit-webhook-secret"
                        onChange={(event) => setSecret(event.target.value)}
                        value={secret}
                      />
                      <Button onClick={() => setSecret(generateSecret())} type="button" variant="outline">
                        {t('webhooks.generateSecret')}
                      </Button>
                    </div>
                    <Button
                      className="justify-self-start"
                      onClick={() => {
                        setSecret('')
                        setSecretMode('keep')
                      }}
                      size="sm"
                      type="button"
                      variant="ghost"
                    >
                      {t('webhooks.keepSecret')}
                    </Button>
                  </div>
                ) : null}
                {secretMode === 'clear' ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-muted-foreground text-sm">{t('webhooks.secretWillClear')}</span>
                    <Button onClick={() => setSecretMode('keep')} size="sm" type="button" variant="ghost">
                      {t('webhooks.keepSecret')}
                    </Button>
                  </div>
                ) : null}
              </div>
            </div>
            <DialogFooter>
              <Button onClick={() => setEditing(false)} variant="outline">
                {t('webhooks.cancel')}
              </Button>
              <Button disabled={!canSave || update.isPending} onClick={() => void submit()}>
                {t('webhooks.save')}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <div className="grid gap-4">
              <ReadonlyField label={t('webhooks.idLabel')} value={source.id} />
              <ReadonlyField label={t('webhooks.agentLabel')} value={agentName} />
              <ReadonlyField label={t('webhooks.userLabel')} value={userName(source.user_id)} />
              <ReadonlyField
                label={t('webhooks.replyTargetLabel')}
                value={source.reply_target == null ? t('webhooks.replyTargetNone') : userName(source.reply_target)}
              />
              <ReadonlyField
                label={t('webhooks.messageTemplateLabel')}
                value={source.message_template ?? t('webhooks.notSet')}
              />
              <ReadonlyField
                label={t('webhooks.columnStatus')}
                value={source.enabled ? t('webhooks.statusEnabled') : t('webhooks.statusDisabled')}
              />
              <ReadonlyField
                label={t('webhooks.secretLabel')}
                value={source.has_secret ? t('webhooks.secretSet') : t('webhooks.secretUnset')}
              />
            </div>
            <DialogFooter>
              <Button onClick={() => handleOpenChange(false)} variant="outline">
                {t('webhooks.close')}
              </Button>
              <Button onClick={enterEdit}>
                <Pencil className="size-4" /> {t('webhooks.edit')}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Source row ───────────────────────────

function SourceRow({
  source,
  agents,
  users,
  agentName,
  onDelete,
}: {
  source: WebhookSourceRecord
  agents: AgentListItem[]
  users: UserListItem[]
  agentName: string
  onDelete: () => void
}): JSX.Element {
  const t = useT()
  const remove = useDeleteWebhookSourceMutation(source.id)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)

  return (
    <tr className="border-border border-b last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3 font-mono text-foreground text-sm">{source.id}</td>
      <td className="px-4 py-3 text-muted-foreground text-sm">{agentName}</td>
      <td className="px-4 py-3 text-muted-foreground text-sm">{userLabel(users, source.user_id)}</td>
      <td className="px-4 py-3">
        <Badge variant={source.enabled ? 'success' : 'secondary'}>
          {source.enabled ? t('webhooks.statusEnabled') : t('webhooks.statusDisabled')}
        </Badge>
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button aria-label={t('webhooks.actionsFor', { name: source.id })} size="sm" variant="secondary">
                {t('webhooks.columnActions')}
              </Button>
            }
          />
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setTimeout(() => setDetailOpen(true), 0)}>
              <Eye /> {t('webhooks.viewEdit')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(() => setConfirmDelete(true), 0)} variant="destructive">
              <Trash2 /> {t('webhooks.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <ViewEditWebhookDialog
          agentName={agentName}
          agents={agents}
          onOpenChange={setDetailOpen}
          open={detailOpen}
          source={source}
          users={users}
        />

        <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('webhooks.deleteConfirmTitle', { name: source.id })}</AlertDialogTitle>
              <AlertDialogDescription>{t('webhooks.deleteConfirmDescription')}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('webhooks.cancel')}</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  void remove.mutateAsync().then(onDelete)
                }}
              >
                {t('webhooks.delete')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </td>
    </tr>
  )
}

// ─────────────────────────── Page ───────────────────────────

export function WebhooksPage(): JSX.Element {
  const t = useT()
  const sources = useWebhookSourcesQuery()
  const agents = useAgentsQuery()
  const users = useUsersQuery()
  const [dialogOpen, setDialogOpen] = useState(false)

  const agentNameById = useMemo(
    () =>
      Object.fromEntries(
        (agents.data ?? []).flatMap((agent) => (agent.agent_id == null ? [] : [[agent.agent_id, agent.agent_name]]))
      ),
    [agents.data]
  )

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-semibold text-xl tracking-tight">{t('webhooks.pageTitle')}</h2>
        <p className="mt-1 text-muted-foreground text-sm">{t('webhooks.pageDescription')}</p>
      </div>

      <div className="flex items-center justify-end">
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="size-4" /> {t('webhooks.addWebhook')}
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('webhooks.columnId')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('webhooks.columnAgent')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('webhooks.columnUser')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('webhooks.columnStatus')}
              </th>
              <th className="px-4 py-2.5 text-right font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('webhooks.columnActions')}
              </th>
            </tr>
          </thead>
          <tbody>
            {(sources.data ?? []).map((source) => (
              <SourceRow
                agentName={source.agent_id == null ? '' : (agentNameById[source.agent_id] ?? String(source.agent_id))}
                agents={agents.data ?? []}
                key={source.id}
                onDelete={() => void sources.refetch()}
                source={source}
                users={users.data ?? []}
              />
            ))}
            {sources.data && sources.data.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
                    <Inbox className="size-6 opacity-50" />
                    <span className="text-sm">{t('webhooks.empty')}</span>
                  </div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <CreateWebhookDialog
        agents={agents.data ?? []}
        onOpenChange={setDialogOpen}
        open={dialogOpen}
        users={users.data ?? []}
      />
    </div>
  )
}

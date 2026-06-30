import { useEffect, useMemo, useState } from 'react'
import { Inbox, Plus, Trash2, X } from 'lucide-react'

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
import { type AgentListItem, useAgentsQuery } from '@/features/agents/api'
import {
  type McpApiKeyPerUserAuthConfig,
  type McpAuthType,
  type McpOAuthClientCredentialsAuthConfig,
  type McpServerInput,
  type McpServerRecord,
  useCreateMcpServerMutation,
  useDeleteMcpServerMutation,
  useMcpReconnectMutation,
  useMcpServersQuery,
  useMcpServerTestMutation,
  useMcpServerToolsQuery,
  useUpdateMcpServerMutation,
} from '@/features/connectors/api'
import { useT } from '@/i18n'

const TRANSPORTS = ['stdio', 'http', 'websocket'] as const
const GLOBAL_SCOPE = 'global'

function statusVariant(status: string): 'success' | 'secondary' | 'warning' {
  if (status === 'connected' || status === 'configured') return 'success'
  if (status === 'disabled') return 'secondary'
  return 'warning'
}

type EnvPair = { key: string; value: string }

const toPairs = (map?: Record<string, string>): EnvPair[] =>
  Object.entries(map ?? {}).map(([key, value]) => ({ key, value }))

// ─────────────────────────── Add / Edit dialog ───────────────────────────

function ServerDialog({
  open,
  editing,
  agents,
  onOpenChange,
}: {
  open: boolean
  editing: McpServerRecord | null
  agents: AgentListItem[]
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const create = useCreateMcpServerMutation()
  const update = useUpdateMcpServerMutation(editing?.id ?? '')
  const isEdit = editing !== null

  const [id, setId] = useState('')
  const [transport, setTransport] = useState<string | null>('stdio')
  const [command, setCommand] = useState('')
  const [url, setUrl] = useState('')
  const [agentScope, setAgentScope] = useState<string | null>(GLOBAL_SCOPE)
  const [authType, setAuthType] = useState<McpAuthType>('none')
  const [apiKeyEnv, setApiKeyEnv] = useState('')
  const [oauthTokenUrl, setOauthTokenUrl] = useState('')
  const [oauthClientId, setOauthClientId] = useState('')
  const [oauthClientSecretEnv, setOauthClientSecretEnv] = useState('')
  const [oauthScope, setOauthScope] = useState('')
  const [headerStyle, setHeaderStyle] = useState<'bearer' | 'x_api_key'>('bearer')
  const [credentialInput, setCredentialInput] = useState<'form' | 'tool' | 'both'>('form')
  const [env, setEnv] = useState<EnvPair[]>([])
  const [args, setArgs] = useState<string[]>([])
  const [headers, setHeaders] = useState<EnvPair[]>([])

  useEffect(() => {
    if (open) {
      const authConfig = editing?.auth_config ?? {}
      const oauthConfig = authConfig as Partial<McpOAuthClientCredentialsAuthConfig>
      const perUserConfig = authConfig as Partial<McpApiKeyPerUserAuthConfig>
      setId(editing?.id ?? '')
      setTransport(editing?.transport ?? 'stdio')
      setCommand(editing?.command ?? '')
      setUrl(editing?.url ?? '')
      setAgentScope(editing?.agent_id == null ? GLOBAL_SCOPE : String(editing.agent_id))
      setAuthType(editing?.auth_type ?? 'none')
      setApiKeyEnv('key_env' in authConfig && typeof authConfig.key_env === 'string' ? authConfig.key_env : '')
      setOauthTokenUrl(oauthConfig.token_url ?? '')
      setOauthClientId(oauthConfig.client_id ?? '')
      setOauthClientSecretEnv(oauthConfig.client_secret_env ?? '')
      setOauthScope(oauthConfig.scope ?? '')
      setHeaderStyle(perUserConfig.header_style ?? 'bearer')
      setCredentialInput(perUserConfig.credential_input ?? 'form')
      setEnv(toPairs(editing?.env))
      setArgs(editing?.args ?? [])
      setHeaders(toPairs(editing?.headers))
    }
  }, [open, editing])

  const submit = async (): Promise<void> => {
    const payload: McpServerInput = {
      id: id.trim(),
      transport: transport ?? '',
      enabled: editing?.enabled ?? true,
      auth_type: authType,
      auth_config:
        authType === 'api_key'
          ? { key_env: apiKeyEnv.trim() }
          : authType === 'oauth_client_credentials'
            ? {
                token_url: oauthTokenUrl.trim(),
                client_id: oauthClientId.trim(),
                client_secret_env: oauthClientSecretEnv.trim(),
                scope: oauthScope.trim(),
              }
            : authType === 'api_key_per_user'
              ? { header_style: headerStyle, credential_input: credentialInput }
              : {},
    }
    if (!isEdit && agentScope !== GLOBAL_SCOPE) payload.agent_id = Number(agentScope)
    if (transport === 'stdio') {
      payload.command = command.trim() || undefined
      const cleanArgs = args.map((arg) => arg.trim()).filter(Boolean)
      if (cleanArgs.length > 0) payload.args = cleanArgs
    } else {
      payload.url = url.trim() || undefined
      const headerMap: Record<string, string> = {}
      headers.forEach((pair) => {
        if (pair.key.trim()) headerMap[pair.key.trim()] = pair.value
      })
      if (Object.keys(headerMap).length > 0) payload.headers = headerMap
    }
    const envMap: Record<string, string> = {}
    env.forEach((pair) => {
      if (pair.key.trim()) envMap[pair.key.trim()] = pair.value
    })
    if (Object.keys(envMap).length > 0) payload.env = envMap

    if (isEdit) {
      const { id: _omit, ...editPayload } = payload
      await update.mutateAsync(editPayload)
    } else {
      await create.mutateAsync(payload)
    }
    onOpenChange(false)
  }

  const canSubmit =
    id.trim().length > 0 &&
    (transport === 'stdio' ? command.trim().length > 0 : url.trim().length > 0) &&
    (authType === 'none' ||
      authType === 'api_key_per_user' ||
      (authType === 'api_key' && apiKeyEnv.trim().length > 0) ||
      (authType === 'oauth_client_credentials' &&
        oauthTokenUrl.trim().length > 0 &&
        oauthClientId.trim().length > 0 &&
        oauthClientSecretEnv.trim().length > 0))

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? t('mcp.editTitle', { name: editing?.id ?? '' }) : t('mcp.addTitle')}</DialogTitle>
          <DialogDescription>{t('mcp.dialogDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="mcp-id">
              {t('mcp.idLabel')} <span className="text-destructive">*</span>
            </Label>
            <Input
              disabled={isEdit}
              id="mcp-id"
              onChange={(event) => setId(event.target.value)}
              placeholder={t('mcp.idPlaceholder')}
              value={id}
            />
          </div>

          <div className="grid gap-2">
            <Label>{t('mcp.scopeLabel')}</Label>
            <SimpleSelect
              disabled={isEdit}
              onValueChange={setAgentScope}
              options={[
                { value: GLOBAL_SCOPE, label: t('mcp.scopeGlobalOption') },
                ...agents.map((agent) => ({
                  value: String(agent.agent_id ?? agent.agent_name),
                  label: agent.agent_name,
                })),
              ]}
              triggerAriaLabel={t('mcp.scopeLabel')}
              value={agentScope}
            />
          </div>

          <div className="grid gap-2">
            <Label>{t('mcp.transportLabel')}</Label>
            <SimpleSelect
              onValueChange={setTransport}
              options={TRANSPORTS.map((option) => ({ value: option, label: option }))}
              triggerAriaLabel={t('mcp.transportLabel')}
              value={transport}
            />
          </div>

          <div className="grid gap-2">
            <Label>{t('mcp.authTypeLabel')}</Label>
            <SimpleSelect
              onValueChange={(value) => setAuthType((value ?? 'none') as McpAuthType)}
              options={[
                { value: 'none', label: t('mcp.authTypeNone') },
                { value: 'api_key', label: t('mcp.authTypeApiKey') },
                { value: 'oauth_client_credentials', label: t('mcp.authTypeOauthClientCredentials') },
                { value: 'api_key_per_user', label: t('mcp.authTypeApiKeyPerUser') },
              ]}
              triggerAriaLabel={t('mcp.authTypeLabel')}
              value={authType}
            />
          </div>

          {transport === 'stdio' ? (
            <div className="grid gap-2">
              <Label htmlFor="mcp-command">
                {t('mcp.commandLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="mcp-command"
                onChange={(event) => setCommand(event.target.value)}
                placeholder={t('mcp.commandPlaceholder')}
                value={command}
              />
            </div>
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="mcp-url">
                {t('mcp.serverUrlLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="mcp-url"
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://mcp-server.example.com/mcp"
                value={url}
              />
            </div>
          )}

          {authType === 'api_key' ? (
            <div className="grid gap-2">
              <Label htmlFor="mcp-auth-key-env">
                {t('mcp.apiKeyEnvLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input id="mcp-auth-key-env" onChange={(event) => setApiKeyEnv(event.target.value)} value={apiKeyEnv} />
            </div>
          ) : null}

          {authType === 'api_key_per_user' ? (
            <>
              <div className="grid gap-2">
                <Label>{t('mcp.headerStyleLabel')}</Label>
                <SimpleSelect
                  onValueChange={(value) => setHeaderStyle((value ?? 'bearer') as 'bearer' | 'x_api_key')}
                  options={[
                    { value: 'bearer', label: t('mcp.headerStyleBearer') },
                    { value: 'x_api_key', label: t('mcp.headerStyleXApiKey') },
                  ]}
                  triggerAriaLabel={t('mcp.headerStyleLabel')}
                  value={headerStyle}
                />
              </div>
              <div className="grid gap-2">
                <Label>{t('mcp.credentialInputLabel')}</Label>
                <SimpleSelect
                  onValueChange={(value) => setCredentialInput((value ?? 'form') as 'form' | 'tool' | 'both')}
                  options={[
                    { value: 'form', label: t('mcp.credentialInputForm') },
                    { value: 'tool', label: t('mcp.credentialInputTool') },
                    { value: 'both', label: t('mcp.credentialInputBoth') },
                  ]}
                  triggerAriaLabel={t('mcp.credentialInputLabel')}
                  value={credentialInput}
                />
              </div>
            </>
          ) : null}

          {authType === 'oauth_client_credentials' ? (
            <>
              <div className="grid gap-2">
                <Label htmlFor="mcp-auth-token-url">
                  {t('mcp.oauthTokenUrlLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-auth-token-url"
                  onChange={(event) => setOauthTokenUrl(event.target.value)}
                  value={oauthTokenUrl}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-auth-client-id">
                  {t('mcp.oauthClientIdLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-auth-client-id"
                  onChange={(event) => setOauthClientId(event.target.value)}
                  value={oauthClientId}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-auth-client-secret-env">
                  {t('mcp.oauthClientSecretEnvLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-auth-client-secret-env"
                  onChange={(event) => setOauthClientSecretEnv(event.target.value)}
                  value={oauthClientSecretEnv}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-auth-scope">{t('mcp.oauthScopeLabel')}</Label>
                <Input id="mcp-auth-scope" onChange={(event) => setOauthScope(event.target.value)} value={oauthScope} />
              </div>
            </>
          ) : null}

          {transport === 'stdio' ? (
            <div className="grid gap-2">
              <Label>{t('mcp.argsLabel')}</Label>
              <div className="space-y-2">
                {args.map((arg, index) => (
                  <div className="flex items-center gap-2" key={index}>
                    <Input
                      className="flex-1"
                      onChange={(event) =>
                        setArgs((current) => current.map((a, i) => (i === index ? event.target.value : a)))
                      }
                      placeholder={t('mcp.argPlaceholder')}
                      value={arg}
                    />
                    <Button
                      aria-label={t('mcp.removeArg')}
                      onClick={() => setArgs((current) => current.filter((_, i) => i !== index))}
                      size="icon"
                      variant="ghost"
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  className="w-full border-dashed"
                  onClick={() => setArgs((current) => [...current, ''])}
                  variant="outline"
                >
                  <Plus className="size-4" /> {t('mcp.addArg')}
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid gap-2">
              <Label>{t('mcp.headersLabel')}</Label>
              <div className="space-y-2">
                {headers.map((pair, index) => (
                  <div className="flex items-center gap-2" key={index}>
                    <Input
                      className="flex-1"
                      onChange={(event) =>
                        setHeaders((current) =>
                          current.map((p, i) => (i === index ? { ...p, key: event.target.value } : p))
                        )
                      }
                      placeholder={t('mcp.headerKeyPlaceholder')}
                      value={pair.key}
                    />
                    <Input
                      className="flex-1"
                      onChange={(event) =>
                        setHeaders((current) =>
                          current.map((p, i) => (i === index ? { ...p, value: event.target.value } : p))
                        )
                      }
                      placeholder={t('mcp.headerValuePlaceholder')}
                      value={pair.value}
                    />
                    <Button
                      aria-label={t('mcp.removeHeader')}
                      onClick={() => setHeaders((current) => current.filter((_, i) => i !== index))}
                      size="icon"
                      variant="ghost"
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  className="w-full border-dashed"
                  onClick={() => setHeaders((current) => [...current, { key: '', value: '' }])}
                  variant="outline"
                >
                  <Plus className="size-4" /> {t('mcp.addHeader')}
                </Button>
              </div>
            </div>
          )}

          <div className="grid gap-2">
            <Label>{t('mcp.envLabel')}</Label>
            <div className="space-y-2">
              {env.map((pair, index) => (
                <div className="flex items-center gap-2" key={index}>
                  <Input
                    className="flex-1"
                    onChange={(event) =>
                      setEnv((current) => current.map((p, i) => (i === index ? { ...p, key: event.target.value } : p)))
                    }
                    placeholder="KEY"
                    value={pair.key}
                  />
                  <Input
                    className="flex-1"
                    onChange={(event) =>
                      setEnv((current) =>
                        current.map((p, i) => (i === index ? { ...p, value: event.target.value } : p))
                      )
                    }
                    placeholder={t('mcp.envValuePlaceholder')}
                    value={pair.value}
                  />
                  <Button
                    aria-label={t('mcp.removeEnvVar')}
                    onClick={() => setEnv((current) => current.filter((_, i) => i !== index))}
                    size="icon"
                    variant="ghost"
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              ))}
              <Button
                className="w-full border-dashed"
                onClick={() => setEnv((current) => [...current, { key: '', value: '' }])}
                variant="outline"
              >
                <Plus className="size-4" /> {t('mcp.addEnvVar')}
              </Button>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('mcp.cancel')}
          </Button>
          <Button disabled={!canSubmit || create.isPending || update.isPending} onClick={() => void submit()}>
            {isEdit ? t('mcp.save') : t('mcp.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Server row ───────────────────────────

function ServerRow({
  server,
  scopeLabel,
  onEdit,
  onViewTools,
}: {
  server: McpServerRecord
  scopeLabel: string
  onEdit: () => void
  onViewTools: () => void
}): JSX.Element {
  const t = useT()
  const test = useMcpServerTestMutation(server.id)
  const reconnect = useMcpReconnectMutation(server.id)
  const remove = useDeleteMcpServerMutation(server.id)
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <tr className="border-border border-b last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3 font-mono text-foreground text-sm">{server.id}</td>
      <td className="px-4 py-3 text-muted-foreground text-sm">{scopeLabel}</td>
      <td className="px-4 py-3 text-muted-foreground text-sm">{server.transport}</td>
      <td className="px-4 py-3">
        <Badge variant={statusVariant(server.status)}>{server.status}</Badge>
        {test.data ? (
          <span className="ml-2 text-muted-foreground text-xs">
            {test.data.connected
              ? t('mcp.connectedTools', { count: test.data.tools_count ?? 0 })
              : (test.data.error ?? t('mcp.testFailed'))}
          </span>
        ) : null}
      </td>
      <td className="px-4 py-3 text-muted-foreground text-sm">{server.tool_count}</td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button aria-label={t('mcp.actionsFor', { name: server.id })} size="sm" variant="secondary">
                {t('mcp.actions')}
              </Button>
            }
          />
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setTimeout(onEdit, 0)}>{t('mcp.edit')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => void test.mutateAsync()}>{t('mcp.testConnection')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => void reconnect.mutateAsync()}>{t('mcp.reconnect')}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTimeout(onViewTools, 0)}>{t('mcp.viewTools')}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setTimeout(() => setConfirmDelete(true), 0)} variant="destructive">
              <Trash2 /> {t('mcp.delete')}
            </DropdownMenuItem>
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
      </td>
    </tr>
  )
}

// ─────────────────────────── Tools dialog ───────────────────────────

function ToolsDialog({
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

// ─────────────────────────── Page ───────────────────────────

export function McpPage(): JSX.Element {
  const t = useT()
  const servers = useMcpServersQuery()
  const agents = useAgentsQuery()
  const [query, setQuery] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<McpServerRecord | null>(null)
  const [toolsFor, setToolsFor] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase()
    const list = servers.data ?? []
    if (!term) return list
    return list.filter((server) => server.id.toLowerCase().includes(term))
  }, [servers.data, query])
  const agentNameById = useMemo(
    () =>
      Object.fromEntries(
        (agents.data ?? []).flatMap((agent) => (agent.agent_id == null ? [] : [[agent.agent_id, agent.agent_name]]))
      ),
    [agents.data]
  )

  const openCreate = (): void => {
    setEditing(null)
    setDialogOpen(true)
  }
  const openEdit = (server: McpServerRecord): void => {
    setEditing(server)
    setDialogOpen(true)
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-semibold text-xl tracking-tight">{t('mcp.pageTitle')}</h2>
        <p className="mt-1 text-muted-foreground text-sm">{t('mcp.pageDescription')}</p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <Input
          className="max-w-xs"
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('mcp.searchPlaceholder')}
          value={query}
        />
        <Button onClick={openCreate}>
          <Plus className="size-4" /> {t('mcp.addServer')}
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('mcp.columnId')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('mcp.columnScope')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('mcp.columnTransport')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('mcp.columnStatus')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('mcp.columnTools')}
              </th>
              <th className="px-4 py-2.5 text-right font-semibold text-muted-foreground text-xs uppercase tracking-wide">
                {t('mcp.columnActions')}
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((server) => (
              <ServerRow
                key={server.id}
                onEdit={() => openEdit(server)}
                onViewTools={() => setToolsFor(server.id)}
                scopeLabel={
                  server.agent_id == null
                    ? t('mcp.scopeGlobalOption')
                    : (agentNameById[server.agent_id] ?? t('mcp.scopeAgentFallback', { id: server.agent_id }))
                }
                server={server}
              />
            ))}
            {servers.data && filtered.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
                    <Inbox className="size-6 opacity-50" />
                    <span className="text-sm">{query ? t('mcp.noMatching') : t('mcp.empty')}</span>
                  </div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <ServerDialog agents={agents.data ?? []} editing={editing} onOpenChange={setDialogOpen} open={dialogOpen} />
      <ToolsDialog onOpenChange={(open) => !open && setToolsFor(null)} serverId={toolsFor} />
    </div>
  )
}

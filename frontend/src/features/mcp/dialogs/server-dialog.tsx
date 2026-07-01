import { useEffect, useState } from 'react'
import { Plus, X } from 'lucide-react'

import { SimpleSelect } from '@/components/base/simple-select'
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
import type { AgentListItem } from '@/features/agents/api'
import {
  type McpApiKeyPerUserAuthConfig,
  type McpAuthType,
  type McpOAuthAuthorizationCodeAuthConfig,
  type McpOAuthClientCredentialsAuthConfig,
  type McpServerInput,
  type McpServerRecord,
  useCreateMcpServerMutation,
  useUpdateMcpServerMutation,
} from '@/features/connectors/api'
import { type EnvPair, GLOBAL_SCOPE, TRANSPORTS, toPairs } from '@/features/mcp/shared'
import { useT } from '@/i18n'

export function ServerDialog({
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
  const [oauthAuthorizationEndpoint, setOauthAuthorizationEndpoint] = useState('')
  const [oauthRedirectPath, setOauthRedirectPath] = useState('')
  const [oauthTokenEnv, setOauthTokenEnv] = useState('')
  const [headerStyle, setHeaderStyle] = useState<'bearer' | 'x_api_key'>('bearer')
  const [credentialInput, setCredentialInput] = useState<'form' | 'tool' | 'both'>('form')
  const [env, setEnv] = useState<EnvPair[]>([])
  const [args, setArgs] = useState<string[]>([])
  const [headers, setHeaders] = useState<EnvPair[]>([])

  useEffect(() => {
    if (open) {
      const authConfig = editing?.auth_config ?? {}
      const oauthConfig = authConfig as Partial<McpOAuthClientCredentialsAuthConfig>
      const authzCodeConfig = authConfig as Partial<McpOAuthAuthorizationCodeAuthConfig>
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
      setOauthAuthorizationEndpoint(authzCodeConfig.authorization_endpoint ?? '')
      setOauthRedirectPath(authzCodeConfig.redirect_path ?? '')
      setOauthTokenEnv(authzCodeConfig.token_env ?? '')
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
            : authType === 'oauth_authorization_code'
              ? {
                  authorization_endpoint: oauthAuthorizationEndpoint.trim(),
                  token_url: oauthTokenUrl.trim(),
                  client_id: oauthClientId.trim(),
                  client_secret_env: oauthClientSecretEnv.trim(),
                  scope: oauthScope.trim(),
                  redirect_path: oauthRedirectPath.trim(),
                  token_env: oauthTokenEnv.trim(),
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
        oauthClientSecretEnv.trim().length > 0) ||
      // authorization_code: client_secret_env is optional (PKCE public clients).
      (authType === 'oauth_authorization_code' &&
        oauthAuthorizationEndpoint.trim().length > 0 &&
        oauthTokenUrl.trim().length > 0 &&
        oauthClientId.trim().length > 0))

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
                { value: 'oauth_authorization_code', label: t('mcp.authTypeOauthAuthorizationCode') },
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

          {authType === 'oauth_authorization_code' ? (
            <>
              <div className="grid gap-2">
                <Label htmlFor="mcp-auth-authorization-endpoint">
                  {t('mcp.oauthAuthorizationEndpointLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-auth-authorization-endpoint"
                  onChange={(event) => setOauthAuthorizationEndpoint(event.target.value)}
                  value={oauthAuthorizationEndpoint}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-token-url">
                  {t('mcp.oauthTokenUrlLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-authz-token-url"
                  onChange={(event) => setOauthTokenUrl(event.target.value)}
                  value={oauthTokenUrl}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-client-id">
                  {t('mcp.oauthClientIdLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-authz-client-id"
                  onChange={(event) => setOauthClientId(event.target.value)}
                  value={oauthClientId}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-client-secret-env">{t('mcp.oauthClientSecretEnvLabel')}</Label>
                <Input
                  id="mcp-authz-client-secret-env"
                  onChange={(event) => setOauthClientSecretEnv(event.target.value)}
                  value={oauthClientSecretEnv}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-scope">{t('mcp.oauthScopeLabel')}</Label>
                <Input
                  id="mcp-authz-scope"
                  onChange={(event) => setOauthScope(event.target.value)}
                  value={oauthScope}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-redirect-path">{t('mcp.oauthRedirectPathLabel')}</Label>
                <Input
                  id="mcp-authz-redirect-path"
                  onChange={(event) => setOauthRedirectPath(event.target.value)}
                  value={oauthRedirectPath}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-token-env">{t('mcp.oauthTokenEnvLabel')}</Label>
                <Input
                  id="mcp-authz-token-env"
                  onChange={(event) => setOauthTokenEnv(event.target.value)}
                  placeholder="MCP_OAUTH_ACCESS_TOKEN"
                  value={oauthTokenEnv}
                />
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

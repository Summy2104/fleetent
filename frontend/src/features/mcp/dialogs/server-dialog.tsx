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
  type McpAuthType,
  type McpFieldSchema,
  type McpServerRecord,
  useCreateMcpServerMutation,
  useMcpFieldSchemaQuery,
  useUpdateMcpServerMutation,
} from '@/features/connectors/api'
import {
  buildServerPayload,
  canSubmitServer,
  type ServerFormFields,
  serverFormFromEditing,
} from '@/features/mcp/dialogs/server-dialog-logic'
import { type EnvPair, GLOBAL_SCOPE, TRANSPORTS } from '@/features/mcp/shared'
import { useT } from '@/i18n'

// Small print under a field showing where it lands in agent.yaml, e.g.
// "mcpServers.filesystem.x-fleetent.auth.client_id". `schema` comes from
// GET /admin/mcp/field-schema (mcp_yaml_field_paths() — the same table materialize.py
// uses to shape the real file, so this can't drift from actual write behavior).
function FieldPathHint({
  schema,
  fieldKey,
  id,
}: {
  schema: McpFieldSchema | undefined
  fieldKey: string
  id: string
}): JSX.Element | null {
  const template = schema?.[fieldKey]
  if (!template) return null
  return <p className="font-mono text-muted-foreground text-xs">{template.replace('{id}', id.trim() || '<id>')}</p>
}

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
  const fieldSchema = useMcpFieldSchemaQuery()
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
      const f = serverFormFromEditing(editing)
      setId(f.id)
      setTransport(f.transport)
      setCommand(f.command)
      setUrl(f.url)
      setAgentScope(f.agentScope)
      setAuthType(f.authType)
      setApiKeyEnv(f.apiKeyEnv)
      setOauthTokenUrl(f.oauthTokenUrl)
      setOauthClientId(f.oauthClientId)
      setOauthClientSecretEnv(f.oauthClientSecretEnv)
      setOauthScope(f.oauthScope)
      setOauthAuthorizationEndpoint(f.oauthAuthorizationEndpoint)
      setOauthRedirectPath(f.oauthRedirectPath)
      setOauthTokenEnv(f.oauthTokenEnv)
      setHeaderStyle(f.headerStyle)
      setCredentialInput(f.credentialInput)
      setEnv(f.env)
      setArgs(f.args)
      setHeaders(f.headers)
    }
  }, [open, editing])

  const fields: ServerFormFields = {
    id,
    transport,
    command,
    url,
    agentScope,
    authType,
    apiKeyEnv,
    oauthTokenUrl,
    oauthClientId,
    oauthClientSecretEnv,
    oauthScope,
    oauthAuthorizationEndpoint,
    oauthRedirectPath,
    oauthTokenEnv,
    headerStyle,
    credentialInput,
    env,
    args,
    headers,
  }

  const submit = async (): Promise<void> => {
    const payload = buildServerPayload(fields, { isEdit, editingEnabled: editing?.enabled })
    if (isEdit) {
      const { id: _omit, ...editPayload } = payload
      await update.mutateAsync(editPayload)
    } else {
      await create.mutateAsync(payload)
    }
    onOpenChange(false)
  }

  const canSubmit = canSubmitServer(fields)

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
            <p className="text-muted-foreground text-xs">{t('mcp.idYamlHint')}</p>
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
            <p className="text-muted-foreground text-xs">{t('mcp.scopeYamlHint')}</p>
          </div>

          <div className="grid gap-2">
            <Label>{t('mcp.transportLabel')}</Label>
            <SimpleSelect
              onValueChange={setTransport}
              options={TRANSPORTS.map((option) => ({ value: option, label: option }))}
              triggerAriaLabel={t('mcp.transportLabel')}
              value={transport}
            />
            <FieldPathHint fieldKey="transport" id={id} schema={fieldSchema.data} />
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
            <FieldPathHint fieldKey="auth_type" id={id} schema={fieldSchema.data} />
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
              <FieldPathHint fieldKey="command" id={id} schema={fieldSchema.data} />
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
              <FieldPathHint fieldKey="url" id={id} schema={fieldSchema.data} />
            </div>
          )}

          {authType === 'api_key' ? (
            <div className="grid gap-2">
              <Label htmlFor="mcp-auth-key-env">
                {t('mcp.apiKeyEnvLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input id="mcp-auth-key-env" onChange={(event) => setApiKeyEnv(event.target.value)} value={apiKeyEnv} />
              <FieldPathHint fieldKey="api_key_env" id={id} schema={fieldSchema.data} />
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
                <FieldPathHint fieldKey="header_style" id={id} schema={fieldSchema.data} />
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
                <FieldPathHint fieldKey="credential_input" id={id} schema={fieldSchema.data} />
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
                <FieldPathHint fieldKey="auth.token_url" id={id} schema={fieldSchema.data} />
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
                <FieldPathHint fieldKey="auth.client_id" id={id} schema={fieldSchema.data} />
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
                <FieldPathHint fieldKey="auth.client_secret_env" id={id} schema={fieldSchema.data} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-auth-scope">{t('mcp.oauthScopeLabel')}</Label>
                <Input id="mcp-auth-scope" onChange={(event) => setOauthScope(event.target.value)} value={oauthScope} />
                <FieldPathHint fieldKey="auth.scope" id={id} schema={fieldSchema.data} />
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
                <FieldPathHint fieldKey="auth.authorization_endpoint" id={id} schema={fieldSchema.data} />
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
                <FieldPathHint fieldKey="auth.token_url" id={id} schema={fieldSchema.data} />
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
                <FieldPathHint fieldKey="auth.client_id" id={id} schema={fieldSchema.data} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-client-secret-env">{t('mcp.oauthClientSecretEnvLabel')}</Label>
                <Input
                  id="mcp-authz-client-secret-env"
                  onChange={(event) => setOauthClientSecretEnv(event.target.value)}
                  value={oauthClientSecretEnv}
                />
                <FieldPathHint fieldKey="auth.client_secret_env" id={id} schema={fieldSchema.data} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-scope">{t('mcp.oauthScopeLabel')}</Label>
                <Input
                  id="mcp-authz-scope"
                  onChange={(event) => setOauthScope(event.target.value)}
                  value={oauthScope}
                />
                <FieldPathHint fieldKey="auth.scope" id={id} schema={fieldSchema.data} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-redirect-path">{t('mcp.oauthRedirectPathLabel')}</Label>
                <Input
                  id="mcp-authz-redirect-path"
                  onChange={(event) => setOauthRedirectPath(event.target.value)}
                  value={oauthRedirectPath}
                />
                <FieldPathHint fieldKey="auth.redirect_path" id={id} schema={fieldSchema.data} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-token-env">{t('mcp.oauthTokenEnvLabel')}</Label>
                <Input
                  id="mcp-authz-token-env"
                  onChange={(event) => setOauthTokenEnv(event.target.value)}
                  placeholder="MCP_OAUTH_ACCESS_TOKEN"
                  value={oauthTokenEnv}
                />
                <FieldPathHint fieldKey="auth.token_env" id={id} schema={fieldSchema.data} />
              </div>
            </>
          ) : null}

          {transport === 'stdio' ? (
            <div className="grid gap-2">
              <Label>{t('mcp.argsLabel')}</Label>
              <FieldPathHint fieldKey="args" id={id} schema={fieldSchema.data} />
              <div className="space-y-2">
                {args.map((arg, index) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: controlled inputs with no stable id; rows are added/removed and value is bound to state
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
              <FieldPathHint fieldKey="headers" id={id} schema={fieldSchema.data} />
              <div className="space-y-2">
                {headers.map((pair, index) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: controlled inputs with no stable id; rows are added/removed and value is bound to state
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
            <FieldPathHint fieldKey="env" id={id} schema={fieldSchema.data} />
            <div className="space-y-2">
              {env.map((pair, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: controlled inputs with no stable id; rows are added/removed and value is bound to state
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

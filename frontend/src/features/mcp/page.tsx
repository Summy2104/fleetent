import { useEffect, useMemo, useState } from 'react';
import { Inbox, Plus, Trash2, X } from 'lucide-react';

import { useT } from '@/i18n';
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { type AgentListItem, useAgentsQuery } from '@/features/agents/api';
import {
  type McpApiKeyPerUserAuthConfig,
  type McpAuthType,
  type McpOAuthAuthorizationCodeAuthConfig,
  type McpOAuthClientCredentialsAuthConfig,
  type McpServerInput,
  type McpServerRecord,
  useCreateMcpServerMutation,
  useDeleteMcpServerMutation,
  useMcpReconnectMutation,
  useMcpServerTestMutation,
  useMcpServerToolsQuery,
  useMcpServersQuery,
  useUpdateMcpServerMutation,
} from '@/features/connectors/api';

const TRANSPORTS = ['stdio', 'http', 'websocket'] as const;
const GLOBAL_SCOPE = 'global';

function statusVariant(status: string): 'success' | 'secondary' | 'warning' {
  if (status === 'connected' || status === 'configured') return 'success';
  if (status === 'disabled') return 'secondary';
  return 'warning';
}

type EnvPair = { key: string; value: string };

const toPairs = (map?: Record<string, string>): EnvPair[] =>
  Object.entries(map ?? {}).map(([key, value]) => ({ key, value }));

// ─────────────────────────── Add / Edit dialog ───────────────────────────

function ServerDialog({
  open,
  editing,
  agents,
  onOpenChange,
}: {
  open: boolean;
  editing: McpServerRecord | null;
  agents: AgentListItem[];
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const t = useT();
  const create = useCreateMcpServerMutation();
  const update = useUpdateMcpServerMutation(editing?.id ?? '');
  const isEdit = editing !== null;

  const [id, setId] = useState('');
  const [transport, setTransport] = useState<string>('stdio');
  const [command, setCommand] = useState('');
  const [url, setUrl] = useState('');
  const [agentScope, setAgentScope] = useState<string>(GLOBAL_SCOPE);
  const [authType, setAuthType] = useState<McpAuthType>('none');
  const [apiKeyEnv, setApiKeyEnv] = useState('');
  const [oauthTokenUrl, setOauthTokenUrl] = useState('');
  const [oauthClientId, setOauthClientId] = useState('');
  const [oauthClientSecretEnv, setOauthClientSecretEnv] = useState('');
  const [oauthScope, setOauthScope] = useState('');
  const [oauthAuthorizationEndpoint, setOauthAuthorizationEndpoint] = useState('');
  const [oauthRedirectPath, setOauthRedirectPath] = useState('');
  const [oauthTokenEnv, setOauthTokenEnv] = useState('');
  const [headerStyle, setHeaderStyle] = useState<'bearer' | 'x_api_key'>('bearer');
  const [credentialInput, setCredentialInput] = useState<'form' | 'tool' | 'both'>('form');
  const [env, setEnv] = useState<EnvPair[]>([]);
  const [args, setArgs] = useState<string[]>([]);
  const [headers, setHeaders] = useState<EnvPair[]>([]);

  useEffect(() => {
    if (open) {
      const authConfig = editing?.auth_config ?? {};
      const oauthConfig = authConfig as Partial<McpOAuthClientCredentialsAuthConfig>;
      const authzCodeConfig = authConfig as Partial<McpOAuthAuthorizationCodeAuthConfig>;
      const perUserConfig = authConfig as Partial<McpApiKeyPerUserAuthConfig>;
      setId(editing?.id ?? '');
      setTransport(editing?.transport ?? 'stdio');
      setCommand(editing?.command ?? '');
      setUrl(editing?.url ?? '');
      setAgentScope(editing?.agent_id == null ? GLOBAL_SCOPE : String(editing.agent_id));
      setAuthType(editing?.auth_type ?? 'none');
      setApiKeyEnv('key_env' in authConfig && typeof authConfig.key_env === 'string' ? authConfig.key_env : '');
      setOauthTokenUrl(oauthConfig.token_url ?? '');
      setOauthClientId(oauthConfig.client_id ?? '');
      setOauthClientSecretEnv(oauthConfig.client_secret_env ?? '');
      setOauthScope(oauthConfig.scope ?? '');
      setOauthAuthorizationEndpoint(authzCodeConfig.authorization_endpoint ?? '');
      setOauthRedirectPath(authzCodeConfig.redirect_path ?? '');
      setOauthTokenEnv(authzCodeConfig.token_env ?? '');
      setHeaderStyle(perUserConfig.header_style ?? 'bearer');
      setCredentialInput(perUserConfig.credential_input ?? 'form');
      setEnv(toPairs(editing?.env));
      setArgs(editing?.args ?? []);
      setHeaders(toPairs(editing?.headers));
    }
  }, [open, editing]);

  const submit = async (): Promise<void> => {
    const payload: McpServerInput = {
      id: id.trim(),
      transport,
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
    };
    if (!isEdit && agentScope !== GLOBAL_SCOPE) payload.agent_id = Number(agentScope);
    if (transport === 'stdio') {
      payload.command = command.trim() || undefined;
      const cleanArgs = args.map((arg) => arg.trim()).filter(Boolean);
      if (cleanArgs.length > 0) payload.args = cleanArgs;
    } else {
      payload.url = url.trim() || undefined;
      const headerMap: Record<string, string> = {};
      headers.forEach((pair) => {
        if (pair.key.trim()) headerMap[pair.key.trim()] = pair.value;
      });
      if (Object.keys(headerMap).length > 0) payload.headers = headerMap;
    }
    const envMap: Record<string, string> = {};
    env.forEach((pair) => {
      if (pair.key.trim()) envMap[pair.key.trim()] = pair.value;
    });
    if (Object.keys(envMap).length > 0) payload.env = envMap;

    if (isEdit) {
      const { id: _omit, ...editPayload } = payload;
      await update.mutateAsync(editPayload);
    } else {
      await create.mutateAsync(payload);
    }
    onOpenChange(false);
  };

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
        oauthClientId.trim().length > 0));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
              id="mcp-id"
              placeholder={t('mcp.idPlaceholder')}
              disabled={isEdit}
              value={id}
              onChange={(event) => setId(event.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>{t('mcp.scopeLabel')}</Label>
            <Select disabled={isEdit} value={agentScope} onValueChange={setAgentScope}>
              <SelectTrigger aria-label={t('mcp.scopeLabel')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={GLOBAL_SCOPE}>{t('mcp.scopeGlobalOption')}</SelectItem>
                {agents.map((agent) => (
                  <SelectItem key={agent.agent_name} value={String(agent.agent_id ?? agent.agent_name)}>
                    {agent.agent_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label>{t('mcp.transportLabel')}</Label>
            <Select value={transport} onValueChange={setTransport}>
              <SelectTrigger aria-label={t('mcp.transportLabel')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TRANSPORTS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label>{t('mcp.authTypeLabel')}</Label>
            <Select value={authType} onValueChange={(value) => setAuthType(value as McpAuthType)}>
              <SelectTrigger aria-label={t('mcp.authTypeLabel')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('mcp.authTypeNone')}</SelectItem>
                <SelectItem value="api_key">{t('mcp.authTypeApiKey')}</SelectItem>
                <SelectItem value="oauth_client_credentials">{t('mcp.authTypeOauthClientCredentials')}</SelectItem>
                <SelectItem value="oauth_authorization_code">{t('mcp.authTypeOauthAuthorizationCode')}</SelectItem>
                <SelectItem value="api_key_per_user">{t('mcp.authTypeApiKeyPerUser')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {transport === 'stdio' ? (
            <div className="grid gap-2">
              <Label htmlFor="mcp-command">
                {t('mcp.commandLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="mcp-command"
                placeholder={t('mcp.commandPlaceholder')}
                value={command}
                onChange={(event) => setCommand(event.target.value)}
              />
            </div>
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="mcp-url">
                {t('mcp.serverUrlLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="mcp-url"
                placeholder="https://mcp-server.example.com/mcp"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
              />
            </div>
          )}

          {authType === 'api_key' ? (
            <div className="grid gap-2">
              <Label htmlFor="mcp-auth-key-env">
                {t('mcp.apiKeyEnvLabel')} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="mcp-auth-key-env"
                value={apiKeyEnv}
                onChange={(event) => setApiKeyEnv(event.target.value)}
              />
            </div>
          ) : null}

          {authType === 'api_key_per_user' ? (
            <>
              <div className="grid gap-2">
                <Label>{t('mcp.headerStyleLabel')}</Label>
                <Select
                  value={headerStyle}
                  onValueChange={(value) => setHeaderStyle(value as 'bearer' | 'x_api_key')}
                >
                  <SelectTrigger aria-label={t('mcp.headerStyleLabel')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bearer">{t('mcp.headerStyleBearer')}</SelectItem>
                    <SelectItem value="x_api_key">{t('mcp.headerStyleXApiKey')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>{t('mcp.credentialInputLabel')}</Label>
                <Select
                  value={credentialInput}
                  onValueChange={(value) => setCredentialInput(value as 'form' | 'tool' | 'both')}
                >
                  <SelectTrigger aria-label={t('mcp.credentialInputLabel')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="form">{t('mcp.credentialInputForm')}</SelectItem>
                    <SelectItem value="tool">{t('mcp.credentialInputTool')}</SelectItem>
                    <SelectItem value="both">{t('mcp.credentialInputBoth')}</SelectItem>
                  </SelectContent>
                </Select>
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
                  value={oauthTokenUrl}
                  onChange={(event) => setOauthTokenUrl(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-auth-client-id">
                  {t('mcp.oauthClientIdLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-auth-client-id"
                  value={oauthClientId}
                  onChange={(event) => setOauthClientId(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-auth-client-secret-env">
                  {t('mcp.oauthClientSecretEnvLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-auth-client-secret-env"
                  value={oauthClientSecretEnv}
                  onChange={(event) => setOauthClientSecretEnv(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-auth-scope">{t('mcp.oauthScopeLabel')}</Label>
                <Input
                  id="mcp-auth-scope"
                  value={oauthScope}
                  onChange={(event) => setOauthScope(event.target.value)}
                />
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
                  value={oauthAuthorizationEndpoint}
                  onChange={(event) => setOauthAuthorizationEndpoint(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-token-url">
                  {t('mcp.oauthTokenUrlLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-authz-token-url"
                  value={oauthTokenUrl}
                  onChange={(event) => setOauthTokenUrl(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-client-id">
                  {t('mcp.oauthClientIdLabel')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="mcp-authz-client-id"
                  value={oauthClientId}
                  onChange={(event) => setOauthClientId(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-client-secret-env">{t('mcp.oauthClientSecretEnvLabel')}</Label>
                <Input
                  id="mcp-authz-client-secret-env"
                  value={oauthClientSecretEnv}
                  onChange={(event) => setOauthClientSecretEnv(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-scope">{t('mcp.oauthScopeLabel')}</Label>
                <Input
                  id="mcp-authz-scope"
                  value={oauthScope}
                  onChange={(event) => setOauthScope(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-redirect-path">{t('mcp.oauthRedirectPathLabel')}</Label>
                <Input
                  id="mcp-authz-redirect-path"
                  value={oauthRedirectPath}
                  onChange={(event) => setOauthRedirectPath(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-authz-token-env">{t('mcp.oauthTokenEnvLabel')}</Label>
                <Input
                  id="mcp-authz-token-env"
                  value={oauthTokenEnv}
                  onChange={(event) => setOauthTokenEnv(event.target.value)}
                  placeholder="MCP_OAUTH_ACCESS_TOKEN"
                />
              </div>
            </>
          ) : null}

          {transport === 'stdio' ? (
            <div className="grid gap-2">
              <Label>{t('mcp.argsLabel')}</Label>
              <div className="space-y-2">
                {args.map((arg, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      className="flex-1"
                      placeholder={t('mcp.argPlaceholder')}
                      value={arg}
                      onChange={(event) =>
                        setArgs((current) => current.map((a, i) => (i === index ? event.target.value : a)))
                      }
                    />
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={t('mcp.removeArg')}
                      onClick={() => setArgs((current) => current.filter((_, i) => i !== index))}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  className="w-full border-dashed"
                  onClick={() => setArgs((current) => [...current, ''])}
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
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      className="flex-1"
                      placeholder={t('mcp.headerKeyPlaceholder')}
                      value={pair.key}
                      onChange={(event) =>
                        setHeaders((current) =>
                          current.map((p, i) => (i === index ? { ...p, key: event.target.value } : p))
                        )
                      }
                    />
                    <Input
                      className="flex-1"
                      placeholder={t('mcp.headerValuePlaceholder')}
                      value={pair.value}
                      onChange={(event) =>
                        setHeaders((current) =>
                          current.map((p, i) => (i === index ? { ...p, value: event.target.value } : p))
                        )
                      }
                    />
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={t('mcp.removeHeader')}
                      onClick={() => setHeaders((current) => current.filter((_, i) => i !== index))}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  className="w-full border-dashed"
                  onClick={() => setHeaders((current) => [...current, { key: '', value: '' }])}
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
                <div key={index} className="flex items-center gap-2">
                  <Input
                    className="flex-1"
                    placeholder="KEY"
                    value={pair.key}
                    onChange={(event) =>
                      setEnv((current) => current.map((p, i) => (i === index ? { ...p, key: event.target.value } : p)))
                    }
                  />
                  <Input
                    className="flex-1"
                    placeholder={t('mcp.envValuePlaceholder')}
                    value={pair.value}
                    onChange={(event) =>
                      setEnv((current) => current.map((p, i) => (i === index ? { ...p, value: event.target.value } : p)))
                    }
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={t('mcp.removeEnvVar')}
                    onClick={() => setEnv((current) => current.filter((_, i) => i !== index))}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                className="w-full border-dashed"
                onClick={() => setEnv((current) => [...current, { key: '', value: '' }])}
              >
                <Plus className="size-4" /> {t('mcp.addEnvVar')}
              </Button>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('mcp.cancel')}
          </Button>
          <Button disabled={!canSubmit || create.isPending || update.isPending} onClick={() => void submit()}>
            {isEdit ? t('mcp.save') : t('mcp.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Server row ───────────────────────────

function ServerRow({
  server,
  scopeLabel,
  onEdit,
  onViewTools,
}: {
  server: McpServerRecord;
  scopeLabel: string;
  onEdit: () => void;
  onViewTools: () => void;
}): JSX.Element {
  const t = useT();
  const test = useMcpServerTestMutation(server.id);
  const reconnect = useMcpReconnectMutation(server.id);
  const remove = useDeleteMcpServerMutation(server.id);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3 font-mono text-sm text-foreground">{server.id}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{scopeLabel}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{server.transport}</td>
      <td className="px-4 py-3">
        <Badge variant={statusVariant(server.status)}>{server.status}</Badge>
        {test.data ? (
          <span className="ml-2 text-xs text-muted-foreground">
            {test.data.connected
              ? t('mcp.connectedTools', { count: test.data.tools_count ?? 0 })
              : test.data.error ?? t('mcp.testFailed')}
          </span>
        ) : null}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{server.tool_count}</td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" aria-label={t('mcp.actionsFor', { name: server.id })}>
              {t('mcp.actions')}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setTimeout(onEdit, 0)}>{t('mcp.edit')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void test.mutateAsync()}>{t('mcp.testConnection')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void reconnect.mutateAsync()}>{t('mcp.reconnect')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setTimeout(onViewTools, 0)}>{t('mcp.viewTools')}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={() => setTimeout(() => setConfirmDelete(true), 0)}>
              <Trash2 /> {t('mcp.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
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
  );
}

// ─────────────────────────── Tools dialog ───────────────────────────

function ToolsDialog({
  serverId,
  onOpenChange,
}: {
  serverId: string | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const t = useT();
  const tools = useMcpServerToolsQuery(serverId);

  return (
    <Dialog open={Boolean(serverId)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('mcp.toolsTitle', { name: serverId ?? '' })}</DialogTitle>
          <DialogDescription>{t('mcp.toolsDescription')}</DialogDescription>
        </DialogHeader>
        {tools.data?.error ? (
          <p className="text-sm text-destructive">{tools.data.error}</p>
        ) : tools.data?.tools.length ? (
          <div className="space-y-2">
            {tools.data.tools.map((tool) => (
              <div key={tool.name} className="rounded-md border border-border px-3 py-2">
                <p className="font-mono text-sm text-foreground">{tool.name}</p>
                {tool.description ? <p className="text-sm text-muted-foreground">{tool.description}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {tools.isLoading ? t('mcp.connecting') : t('mcp.noToolsReported')}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function McpPage(): JSX.Element {
  const t = useT();
  const servers = useMcpServersQuery();
  const agents = useAgentsQuery();
  const [query, setQuery] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<McpServerRecord | null>(null);
  const [toolsFor, setToolsFor] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const list = servers.data ?? [];
    if (!term) return list;
    return list.filter((server) => server.id.toLowerCase().includes(term));
  }, [servers.data, query]);
  const agentNameById = useMemo(
    () => Object.fromEntries((agents.data ?? []).flatMap((agent) => (agent.agent_id == null ? [] : [[agent.agent_id, agent.agent_name]]))),
    [agents.data]
  );

  const openCreate = (): void => {
    setEditing(null);
    setDialogOpen(true);
  };
  const openEdit = (server: McpServerRecord): void => {
    setEditing(server);
    setDialogOpen(true);
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">{t('mcp.pageTitle')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('mcp.pageDescription')}</p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <Input
          className="max-w-xs"
          placeholder={t('mcp.searchPlaceholder')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button onClick={openCreate}>
          <Plus className="size-4" /> {t('mcp.addServer')}
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnId')}</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnScope')}</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnTransport')}</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnStatus')}</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnTools')}</th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('mcp.columnActions')}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((server) => (
              <ServerRow
                key={server.id}
                server={server}
                scopeLabel={
                  server.agent_id == null
                    ? t('mcp.scopeGlobalOption')
                    : (agentNameById[server.agent_id] ?? t('mcp.scopeAgentFallback', { id: server.agent_id }))
                }
                onEdit={() => openEdit(server)}
                onViewTools={() => setToolsFor(server.id)}
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

      <ServerDialog
        open={dialogOpen}
        editing={editing}
        agents={agents.data ?? []}
        onOpenChange={setDialogOpen}
      />
      <ToolsDialog serverId={toolsFor} onOpenChange={(open) => !open && setToolsFor(null)} />
    </div>
  );
}

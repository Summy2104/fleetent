import { useEffect, useState } from 'react';

import {
  type ConnectorRecord,
  type McpServerRecord,
  useConnectorAgentBindingsQuery,
  useConnectorAuthorizeQuery,
  useConnectorCredentialsMutation,
  useConnectorGrantsQuery,
  useConnectorLifecycleQuery,
  useConnectorTestMutation,
  useConnectorsQuery,
  useCreateConnectorMutation,
  useCreateMcpServerMutation,
  useDeleteConnectorMutation,
  useDeleteMcpServerMutation,
  useMcpDoctorQuery,
  useMcpReconnectMutation,
  useMcpServerTestMutation,
  useMcpServerToolsQuery,
  useMcpServersQuery,
  useOffboardingQuery,
  useRevokeConnectorGrantMutation,
  useUpdateConnectorMutation,
  useUpdateMcpServerMutation,
} from '@/features/connectors/api';

type ConnectorFormState = {
  id: string;
  displayName: string;
  protocol: 'oauth2' | 'apikey';
  enabled: boolean;
};

type McpFormState = {
  id: string;
  transport: string;
  command: string;
  url: string;
  enabled: boolean;
};

function emptyConnectorForm(): ConnectorFormState {
  return {
    id: '',
    displayName: '',
    protocol: 'oauth2',
    enabled: true,
  };
}

function emptyMcpForm(): McpFormState {
  return {
    id: '',
    transport: 'stdio',
    command: '',
    url: '',
    enabled: true,
  };
}

function ConnectorCard({
  connector,
  onEdit,
  onLoadAuthorize,
  onSelectOffboardingUser,
  onSavedCredentials,
}: {
  connector: ConnectorRecord;
  onEdit: () => void;
  onLoadAuthorize: () => void;
  onSavedCredentials: () => void;
  onSelectOffboardingUser: (userId: string) => void;
}): JSX.Element {
  const lifecycle = useConnectorLifecycleQuery(connector.id);
  const bindings = useConnectorAgentBindingsQuery(connector.id);
  const testConnector = useConnectorTestMutation(connector.id);
  const credentialsMutation = useConnectorCredentialsMutation(connector.id);
  const deleteConnector = useDeleteConnectorMutation(connector.id);
  const [apiKey, setApiKey] = useState('');

  const lifecycleSummary = lifecycle.data
    ? `Refresh ok ${lifecycle.data.refresh_ok} / failed ${lifecycle.data.refresh_failed} / reauth ${lifecycle.data.reauths}`
    : null;
  const testSummary = testConnector.data
    ? testConnector.data.success
      ? `Token valid; ${testConnector.data.active_grants ?? 0} active grants`
      : testConnector.data.error ?? 'Connector test failed'
    : null;

  const onDelete = async (): Promise<void> => {
    if (!window.confirm(`Delete connector ${connector.id}?`)) {
      return;
    }
    await deleteConnector.mutateAsync();
  };

  const onSaveCredentials = async (): Promise<void> => {
    await credentialsMutation.mutateAsync({ api_key: apiKey });
    setApiKey('');
    onSavedCredentials();
  };

  return (
    <article className="rounded-2xl border bg-white/80 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-xl font-semibold">{connector.display_name}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{connector.id}</p>
          <p className="mt-1 text-sm text-muted-foreground">{connector.protocol}</p>
          <p className="mt-1 text-sm text-muted-foreground">{connector.enabled ? 'enabled' : 'disabled'}</p>
          {bindings.data ? (
            <p className="mt-1 text-sm text-muted-foreground">{`Agents: ${bindings.data.agent_ids.join(', ')}`}</p>
          ) : null}
          {lifecycleSummary ? <p className="mt-2 text-sm text-muted-foreground">{lifecycleSummary}</p> : null}
          {testSummary ? <p className="mt-2 text-sm font-medium">{testSummary}</p> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="rounded-md bg-secondary px-3 py-2 text-sm font-medium" onClick={onEdit} type="button">
            {`Edit ${connector.display_name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void testConnector.mutateAsync()}
            type="button"
          >
            {`Test ${connector.display_name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={onLoadAuthorize}
            type="button"
          >
            {`Load authorize link for ${connector.display_name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => onSelectOffboardingUser('u1')}
            type="button"
          >
            Load offboarding defaults
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void onDelete()}
            type="button"
          >
            {`Delete ${connector.display_name}`}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 border-t pt-4 md:grid-cols-[1fr_auto]">
        <label className="grid gap-2 text-sm font-medium">
          API key
          <input
            className="rounded-md border bg-white px-3 py-2"
            onChange={(event) => setApiKey(event.target.value)}
            type="password"
            value={apiKey}
          />
        </label>
        <div className="flex items-end">
          <button
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            onClick={() => void onSaveCredentials()}
            type="button"
          >
            {`Save ${connector.display_name} credentials`}
          </button>
        </div>
      </div>
    </article>
  );
}

function GrantRow({
  connectorId,
  grant,
}: {
  connectorId: string;
  grant: { user_id: string; connector_id: string; status: string };
}): JSX.Element {
  const revoke = useRevokeConnectorGrantMutation(grant.user_id, grant.connector_id);

  const onRevoke = async (): Promise<void> => {
    if (!window.confirm(`Revoke ${grant.connector_id} for ${grant.user_id}?`)) {
      return;
    }
    await revoke.mutateAsync();
  };

  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border bg-white/70 p-3">
      <div>
        <p className="font-medium">{grant.user_id}</p>
        <p className="text-sm text-muted-foreground">{grant.status}</p>
      </div>
      <button
        className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
        onClick={() => void onRevoke()}
        type="button"
      >
        {`Revoke ${connectorId} for ${grant.user_id}`}
      </button>
    </div>
  );
}

function McpServerCard({
  onEdit,
  onLoadTools,
  server,
}: {
  onEdit: () => void;
  onLoadTools: () => void;
  server: McpServerRecord;
}): JSX.Element {
  const reconnect = useMcpReconnectMutation(server.id);
  const testServer = useMcpServerTestMutation(server.id);
  const deleteServer = useDeleteMcpServerMutation(server.id);

  const onDelete = async (): Promise<void> => {
    if (!window.confirm(`Delete MCP server ${server.id}?`)) {
      return;
    }
    await deleteServer.mutateAsync();
  };

  return (
    <article className="rounded-2xl border bg-white/80 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-xl font-semibold">{server.id}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{server.transport}</p>
          <p className="mt-1 text-sm text-muted-foreground">{server.status}</p>
          {server.command ? <p className="mt-1 text-sm text-muted-foreground">{server.command}</p> : null}
          {server.url ? <p className="mt-1 text-sm text-muted-foreground">{server.url}</p> : null}
          {reconnect.data?.reconnected ? (
            <p className="mt-2 text-sm font-medium">{`Reconnect requested for ${server.id}`}</p>
          ) : null}
          {testServer.data ? (
            <p className="mt-2 text-sm font-medium">{`Connected; ${testServer.data.tools_count ?? 0} tools`}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="rounded-md bg-secondary px-3 py-2 text-sm font-medium" onClick={onEdit} type="button">
            {`Edit ${server.id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void reconnect.mutateAsync()}
            type="button"
          >
            {`Reconnect ${server.id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void testServer.mutateAsync()}
            type="button"
          >
            {`Test ${server.id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={onLoadTools}
            type="button"
          >
            {`Load tools for ${server.id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void onDelete()}
            type="button"
          >
            {`Delete ${server.id}`}
          </button>
        </div>
      </div>
    </article>
  );
}

export function ConnectorsPage(): JSX.Element {
  const connectors = useConnectorsQuery();
  const grants = useConnectorGrantsQuery();
  const mcpServers = useMcpServersQuery();
  const createConnector = useCreateConnectorMutation();
  const createMcpServer = useCreateMcpServerMutation();
  const [connectorForm, setConnectorForm] = useState<ConnectorFormState>(emptyConnectorForm);
  const [connectorMode, setConnectorMode] = useState<'create' | 'edit'>('create');
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [authorizeFor, setAuthorizeFor] = useState<string | null>(null);
  const [credentialsMessage, setCredentialsMessage] = useState<string | null>(null);
  const [offboardingDraft, setOffboardingDraft] = useState('u1');
  const [offboardingTarget, setOffboardingTarget] = useState<string | null>(null);

  const [mcpForm, setMcpForm] = useState<McpFormState>(emptyMcpForm);
  const [mcpMode, setMcpMode] = useState<'create' | 'edit'>('create');
  const [selectedMcpId, setSelectedMcpId] = useState<string | null>(null);
  const [toolsFor, setToolsFor] = useState<string | null>(null);
  const [doctorVisible, setDoctorVisible] = useState(false);

  const authorizeQuery = useConnectorAuthorizeQuery(authorizeFor);
  const offboarding = useOffboardingQuery(offboardingTarget);
  const updateConnector = useUpdateConnectorMutation(selectedConnectorId ?? '');
  const updateMcpServer = useUpdateMcpServerMutation(selectedMcpId ?? '');
  const tools = useMcpServerToolsQuery(toolsFor);
  const doctor = useMcpDoctorQuery();

  useEffect(() => {
    if (!selectedConnectorId && connectors.data?.length) {
      setSelectedConnectorId(connectors.data[0].id);
    }
  }, [connectors.data, selectedConnectorId]);

  useEffect(() => {
    if (!selectedMcpId && mcpServers.data?.length) {
      setSelectedMcpId(mcpServers.data[0].id);
    }
  }, [mcpServers.data, selectedMcpId]);

  const onSubmitConnector = async (): Promise<void> => {
    const payload = {
      id: connectorForm.id,
      display_name: connectorForm.displayName,
      protocol: connectorForm.protocol,
      enabled: connectorForm.enabled,
    } as const;

    if (connectorMode === 'create') {
      await createConnector.mutateAsync(payload);
      setSelectedConnectorId(connectorForm.id);
      setConnectorForm(emptyConnectorForm());
      return;
    }

    await updateConnector.mutateAsync({
      display_name: connectorForm.displayName,
      enabled: connectorForm.enabled,
      protocol: connectorForm.protocol,
    });
  };

  const onSubmitMcp = async (): Promise<void> => {
    const payload = {
      id: mcpForm.id,
      transport: mcpForm.transport,
      command: mcpForm.command || undefined,
      url: mcpForm.url || undefined,
      enabled: mcpForm.enabled,
    };

    if (mcpMode === 'create') {
      await createMcpServer.mutateAsync(payload);
      setSelectedMcpId(mcpForm.id);
      setMcpForm(emptyMcpForm());
      return;
    }

    await updateMcpServer.mutateAsync({
      enabled: mcpForm.enabled,
      transport: mcpForm.transport,
      url: mcpForm.url || undefined,
      command: mcpForm.command || undefined,
    });
  };

  return (
    <section className="space-y-8">
      <header className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">Native SPA</p>
        <h1 className="text-3xl font-semibold tracking-tight">Connectors</h1>
        <p className="text-sm text-muted-foreground">
          OAuth external services and MCP servers now run as first-class admin domains instead of
          the legacy `#oauth` tab.
        </p>
      </header>

      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          <div className="rounded-2xl border bg-white/75 p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">OAuth external services</h2>
              {connectorMode === 'edit' ? (
                <button
                  className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                  onClick={() => {
                    setConnectorMode('create');
                    setConnectorForm(emptyConnectorForm());
                  }}
                  type="button"
                >
                  New draft
                </button>
              ) : null}
            </div>

            <div className="grid gap-4">
              <label className="grid gap-2 text-sm font-medium">
                Connector ID
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  disabled={connectorMode === 'edit'}
                  onChange={(event) =>
                    setConnectorForm((current) => ({ ...current, id: event.target.value }))
                  }
                  value={connectorForm.id}
                />
              </label>
              <label className="grid gap-2 text-sm font-medium">
                Display name
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) =>
                    setConnectorForm((current) => ({ ...current, displayName: event.target.value }))
                  }
                  value={connectorForm.displayName}
                />
              </label>
              <label className="grid gap-2 text-sm font-medium">
                Protocol
                <select
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) =>
                    setConnectorForm((current) => ({
                      ...current,
                      protocol: event.target.value as 'oauth2' | 'apikey',
                    }))
                  }
                  value={connectorForm.protocol}
                >
                  <option value="oauth2">oauth2</option>
                  <option value="apikey">apikey</option>
                </select>
              </label>
              <label className="inline-flex items-center gap-2 text-sm font-medium">
                <input
                  checked={connectorForm.enabled}
                  onChange={(event) =>
                    setConnectorForm((current) => ({ ...current, enabled: event.target.checked }))
                  }
                  type="checkbox"
                />
                Connector enabled
              </label>
              <button
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
                onClick={() => void onSubmitConnector()}
                type="button"
              >
                {connectorMode === 'create' ? 'Create connector' : 'Save changes'}
              </button>
            </div>
          </div>

          <div className="grid gap-4">
            {connectors.data?.map((connector) => (
              <ConnectorCard
                connector={connector}
                key={connector.id}
                onEdit={() => {
                  setSelectedConnectorId(connector.id);
                  setConnectorMode('edit');
                  setConnectorForm({
                    id: connector.id,
                    displayName: connector.display_name,
                    protocol: connector.protocol,
                    enabled: connector.enabled,
                  });
                }}
                onLoadAuthorize={() => setAuthorizeFor(connector.id)}
                onSavedCredentials={() => {
                  setCredentialsMessage(`Credentials saved for ${connector.display_name}`);
                }}
                onSelectOffboardingUser={(userId) => {
                  setOffboardingDraft(userId);
                }}
              />
            ))}
          </div>
        </div>

        <aside className="space-y-4 rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Authorization matrix</h2>
          <p className="text-sm text-muted-foreground">{grants.data?.consent_hint}</p>
          <div className="grid gap-3">
            {grants.data?.grants.map((grant) => (
              <GrantRow
                connectorId={grant.connector_id}
                grant={grant}
                key={`${grant.user_id}:${grant.connector_id}`}
              />
            ))}
          </div>
          {authorizeQuery.data ? (
            <a
              className="inline-flex rounded-md bg-secondary px-4 py-2 text-sm font-medium"
              href={authorizeQuery.data.authorize_url}
              rel="noreferrer"
              target="_blank"
            >
              Open browser authorize flow
            </a>
          ) : null}
          {credentialsMessage ? <p className="text-sm font-medium">{credentialsMessage}</p> : null}

          <div className="grid gap-3 border-t pt-4">
            <label className="grid gap-2 text-sm font-medium">
              Offboarding user ID
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setOffboardingDraft(event.target.value)}
                value={offboardingDraft}
              />
            </label>
            <button
              className="rounded-md bg-secondary px-4 py-2 text-sm font-medium"
              onClick={() => setOffboardingTarget(offboardingDraft)}
              type="button"
            >
              Load offboarding summary
            </button>
            {offboarding.data ? (
              <div className="rounded-xl border bg-white/70 p-3 text-sm">
                <p>{`Revoked: ${offboarding.data.revoked.join(', ') || 'none'}`}</p>
                <p>{`Failed: ${offboarding.data.failed.join(', ') || 'none'}`}</p>
              </div>
            ) : null}
          </div>
        </aside>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          <div className="rounded-2xl border bg-white/75 p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">MCP servers</h2>
              {mcpMode === 'edit' ? (
                <button
                  className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                  onClick={() => {
                    setMcpMode('create');
                    setMcpForm(emptyMcpForm());
                  }}
                  type="button"
                >
                  New MCP draft
                </button>
              ) : null}
            </div>
            <div className="grid gap-4">
              <label className="grid gap-2 text-sm font-medium">
                MCP server ID
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  disabled={mcpMode === 'edit'}
                  onChange={(event) => setMcpForm((current) => ({ ...current, id: event.target.value }))}
                  value={mcpForm.id}
                />
              </label>
              <label className="grid gap-2 text-sm font-medium">
                MCP transport
                <select
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) =>
                    setMcpForm((current) => ({ ...current, transport: event.target.value }))
                  }
                  value={mcpForm.transport}
                >
                  <option value="stdio">stdio</option>
                  <option value="http">http</option>
                  <option value="websocket">websocket</option>
                </select>
              </label>
              <label className="grid gap-2 text-sm font-medium">
                Command
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) =>
                    setMcpForm((current) => ({ ...current, command: event.target.value }))
                  }
                  value={mcpForm.command}
                />
              </label>
              <label className="grid gap-2 text-sm font-medium">
                URL
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) => setMcpForm((current) => ({ ...current, url: event.target.value }))}
                  value={mcpForm.url}
                />
              </label>
              <label className="inline-flex items-center gap-2 text-sm font-medium">
                <input
                  checked={mcpForm.enabled}
                  onChange={(event) =>
                    setMcpForm((current) => ({ ...current, enabled: event.target.checked }))
                  }
                  type="checkbox"
                />
                Enabled
              </label>
              <button
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
                onClick={() => void onSubmitMcp()}
                type="button"
              >
                {mcpMode === 'create' ? 'Create MCP server' : 'Save MCP changes'}
              </button>
            </div>
          </div>

          <div className="grid gap-4">
            {mcpServers.data?.map((server) => (
              <McpServerCard
                key={server.id}
                onEdit={() => {
                  setSelectedMcpId(server.id);
                  setMcpMode('edit');
                  setMcpForm({
                    id: server.id,
                    transport: server.transport,
                    command: server.command ?? '',
                    url: server.url ?? '',
                    enabled: server.enabled ?? true,
                  });
                }}
                onLoadTools={() => setToolsFor(server.id)}
                server={server}
              />
            ))}
          </div>
        </div>

        <aside className="space-y-4 rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Live MCP inspection</h2>
          <button
            className="rounded-md bg-secondary px-4 py-2 text-sm font-medium"
            onClick={() => setDoctorVisible(true)}
            type="button"
          >
            Load doctor checks
          </button>
          {tools.data?.tools?.length ? (
            <div className="rounded-xl border bg-white/70 p-3 text-sm">
              <p className="font-medium">Tools</p>
              {tools.data.tools.map((tool) => (
                <p key={tool.name}>{tool.name}</p>
              ))}
            </div>
          ) : null}
          {doctorVisible ? (
            <div
              className="rounded-xl border bg-white/70 p-3 text-sm"
              data-testid="mcp-doctor"
            >
              {doctor.data?.checks.map((check, index) => (
                <div className="flex justify-between gap-3" key={`${String(check.name)}-${index}`}>
                  <span>{String(check.name)}</span>
                  <span>{String(check.level)}</span>
                </div>
              ))}
            </div>
          ) : null}
        </aside>
      </section>
    </section>
  );
}

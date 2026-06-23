import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';
import {
  type AgentImCapabilitiesInput,
  type AgentImGroupInput,
  type AgentListItem,
  type AgentModelOverrides,
  type AgentSecretRecord,
  type AgentSkillBinding,
  useActivateAgentVersionMutation,
  useAddAgentImGroupMutation,
  useAgentBindingsQuery,
  useAgentDetailQuery,
  useAgentKbsQuery,
  useAgentOauthBindingsQuery,
  useAgentsQuery,
  useAgentSecretsQuery,
  useAgentSkillsQuery,
  useAgentVersionsQuery,
  useBindAgentKbMutation,
  useBindAgentMcpMutation,
  useBindAgentOauthMutation,
  useBindAgentUserMutation,
  useClearDefaultAgentMutation,
  useCloneAgentMutation,
  useCreateAgentMutation,
  useDeleteAgentMutation,
  useDeleteAgentSecretMutation,
  useSetAgentImCapabilitiesMutation,
  useSetAgentSecretMutation,
  useSetAgentSkillMutation,
  useSetDefaultAgentMutation,
  useRemoveAgentImGroupMutation,
  useUnbindAgentKbMutation,
  useUnbindAgentMcpMutation,
  useUnbindAgentOauthMutation,
  useUnbindAgentUserMutation,
  useUpdateAgentMutation,
  useAgentLifecycleMutation,
} from '@/features/agents/api';
import { useConnectorsQuery, useMcpServersQuery } from '@/features/connectors/api';
import { useKbsQuery } from '@/features/kb/api';
import { useProvidersQuery } from '@/features/providers/api';
import { useSkillsQuery } from '@/features/skills/api';
import { useUsersQuery } from '@/features/users/api';

type AdminMe = {
  email: string;
  id: string;
  role: string;
};

function useAdminMeQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['admin-me'],
    queryFn: () => api.get<AdminMe>('/admin/me'),
  });
}

function parseAllowedTools(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

// The agent's default model route maps to a single provider id. The platform expands this into
// the runtime model policy (materialize); chat resolves the "default" route, so it is the one
// binding required to make an agent reach a real LLM.
function defaultRouteProviderId(overrides: AgentModelOverrides | undefined): string {
  const routes = (overrides?.routes ?? {}) as Record<string, Array<Record<string, unknown>>>;
  const entry = routes.default?.[0];
  if (!entry) {
    return '';
  }
  // A provider id may be authored under any of these keys; take the first that is a string.
  for (const value of [entry.provider_id, entry.provider, entry.target]) {
    if (typeof value === 'string' && value) {
      return value;
    }
  }
  return '';
}

// Set (or clear) the default-route provider while preserving every other key the platform stores
// alongside it (other routes, ``__credential_slots__``), so an edit never drops sibling state.
function withDefaultRouteProvider(
  overrides: AgentModelOverrides | undefined,
  providerId: string
): AgentModelOverrides {
  const next: AgentModelOverrides = { ...(overrides ?? {}) };
  const routes = { ...((next.routes as Record<string, unknown>) ?? {}) };
  if (providerId) {
    routes.default = [{ provider_id: providerId }];
  } else {
    delete routes.default;
  }
  next.routes = routes;
  return next;
}

function formatStatus(agent: AgentListItem): string[] {
  const tokens = [agent.status];
  if (agent.is_default) {
    tokens.push('default');
  }
  return tokens;
}

const ENABLE_UNBOUND_HINT = 'Pin this agent to a node before enabling';

function formatRuntime(agent: AgentListItem): string {
  if (!agent.runtime) {
    return 'not running';
  }
  const parts = [agent.runtime.phase ?? 'unknown'];
  if (agent.runtime.node_id) {
    parts.push(`on ${agent.runtime.node_id}`);
  }
  if (agent.runtime.health) {
    parts.push(`(${agent.runtime.health})`);
  }
  return parts.join(' ');
}

function AgentCard({
  agent,
  detailPrompt,
  isSelected,
  onEdit,
  onLoadVersions,
}: {
  agent: AgentListItem;
  detailPrompt?: string;
  isSelected: boolean;
  onEdit: () => void;
  onLoadVersions: () => void;
}): JSX.Element {
  const disable = useAgentLifecycleMutation(agent.agent_name, 'disable');
  const enable = useAgentLifecycleMutation(agent.agent_name, 'enable');
  const archive = useAgentLifecycleMutation(agent.agent_name, 'archive', { 'X-Confirm': 'true' });
  const restore = useAgentLifecycleMutation(agent.agent_name, 'restore');
  const clone = useCloneAgentMutation(agent.agent_name);
  const remove = useDeleteAgentMutation(agent.agent_name);

  // Enabling an agent no node hosts is a no-op promise — gate the control on placement.
  const enableBlocked = agent.status === 'disabled' && !agent.placement;

  const runDisableEnable = async (): Promise<unknown> => {
    return agent.status === 'disabled' ? enable.mutateAsync() : disable.mutateAsync();
  };

  const runArchiveRestore = async (): Promise<unknown> => {
    return agent.status === 'archived' ? restore.mutateAsync() : archive.mutateAsync();
  };

  return (
    <article className="rounded-2xl border bg-white/80 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <button
            className="text-left text-xl font-semibold"
            onClick={onEdit}
            type="button"
          >
            {agent.agent_name}
          </button>
          <p className="mt-2 text-sm text-muted-foreground">{formatStatus(agent).join(' · ')}</p>
          <p className="mt-1 text-sm text-muted-foreground">{`Runtime: ${formatRuntime(agent)}`}</p>
          {isSelected && (detailPrompt ?? agent.system_prompt) ? (
            <p className="mt-2 text-sm text-foreground">{detailPrompt ?? agent.system_prompt}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="rounded-md bg-secondary px-3 py-2 text-sm font-medium" onClick={onEdit} type="button">
            {`Edit ${agent.agent_name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => void runDisableEnable()}
            disabled={enableBlocked}
            title={enableBlocked ? ENABLE_UNBOUND_HINT : undefined}
            type="button"
          >
            {agent.status === 'disabled' ? `Enable ${agent.agent_name}` : `Disable ${agent.agent_name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void runArchiveRestore()}
            type="button"
          >
            {agent.status === 'archived' ? `Restore ${agent.agent_name}` : `Archive ${agent.agent_name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void clone.mutateAsync(`${agent.agent_name}-copy`)}
            type="button"
          >
            {`Clone ${agent.agent_name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void remove.mutateAsync()}
            type="button"
          >
            {`Delete ${agent.agent_name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={onLoadVersions}
            type="button"
          >
            {`Load versions for ${agent.agent_name}`}
          </button>
        </div>
      </div>
    </article>
  );
}

function BindingList({
  empty,
  items,
  renderItem,
}: {
  empty: string;
  items: string[];
  renderItem?: (item: string) => JSX.Element;
}): JSX.Element {
  if (!items.length) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) =>
        renderItem ? renderItem(item) : <span className="rounded-full border px-3 py-1 text-sm" key={item}>{item}</span>
      )}
    </div>
  );
}

function SkillBindingRow({
  agentName,
  canWrite,
  binding,
}: {
  agentName: string;
  canWrite: boolean;
  binding: AgentSkillBinding;
}): JSX.Element {
  const setSkill = useSetAgentSkillMutation(agentName, binding.skill_name);

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border px-3 py-2">
      <span className="text-sm font-medium">{binding.skill_name}</span>
      {canWrite ? (
        <button
          className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
          onClick={() => void setSkill.mutateAsync({ enabled: !binding.enabled })}
          type="button"
        >
          {binding.enabled ? `Disable ${binding.skill_name}` : `Enable ${binding.skill_name}`}
        </button>
      ) : (
        <span className="text-sm text-muted-foreground">{binding.enabled ? 'enabled' : 'disabled'}</span>
      )}
    </div>
  );
}

function SecretsSection({
  agentName,
  canWrite,
  secrets,
}: {
  agentName: string;
  canWrite: boolean;
  secrets: AgentSecretRecord[];
}): JSX.Element {
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  return (
    <section className="space-y-3 rounded-2xl border bg-white/70 p-4">
      <h3 className="text-lg font-semibold">Secrets</h3>
      {!secrets.length ? <p className="text-sm text-muted-foreground">No secret slots declared.</p> : null}
      <div className="space-y-3">
        {secrets.map((secret) => (
          <SecretRow
            agentName={agentName}
            canWrite={canWrite}
            draft={drafts[secret.env_name] ?? ''}
            key={secret.env_name}
            onDraftChange={(value) =>
              setDrafts((current) => ({
                ...current,
                [secret.env_name]: value,
              }))
            }
            onSaved={() =>
              setDrafts((current) => ({
                ...current,
                [secret.env_name]: '',
              }))
            }
            secret={secret}
          />
        ))}
      </div>
    </section>
  );
}

function SecretRow({
  agentName,
  canWrite,
  draft,
  onDraftChange,
  onSaved,
  secret,
}: {
  agentName: string;
  canWrite: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSaved: () => void;
  secret: AgentSecretRecord;
}): JSX.Element {
  const setSecret = useSetAgentSecretMutation(agentName, secret.env_name);
  const deleteSecret = useDeleteAgentSecretMutation(agentName, secret.env_name);

  const saveSecret = async (): Promise<void> => {
    if (!draft) {
      return;
    }
    await setSecret.mutateAsync(draft);
    onSaved();
  };

  return (
    <div className="space-y-3 rounded-xl border px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{secret.env_name}</span>
        <span className="text-sm text-muted-foreground">{secret.status}</span>
      </div>
      {canWrite ? (
        <div className="grid gap-3 md:grid-cols-[1fr_auto_auto]">
          <label className="grid gap-2 text-sm font-medium">
            {`Secret value for ${secret.env_name}`}
            <input
              className="rounded-md border bg-white px-3 py-2"
              onChange={(event) => onDraftChange(event.target.value)}
              type="password"
              value={draft}
            />
          </label>
          <button
            className="self-end rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void saveSecret()}
            type="button"
          >
            {`Save secret ${secret.env_name}`}
          </button>
          <button
            className="self-end rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void deleteSecret.mutateAsync()}
            type="button"
          >
            {`Clear secret ${secret.env_name}`}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function AgentBindingsPanel({
  agent,
  canWrite,
}: {
  agent: AgentListItem;
  canWrite: boolean;
}): JSX.Element {
  const detail = useAgentDetailQuery(agent.agent_name);
  const skills = useAgentSkillsQuery(agent.agent_name);
  const bindings = useAgentBindingsQuery(agent.agent_name);
  const oauth = useAgentOauthBindingsQuery(agent.agent_name);
  const kbs = useAgentKbsQuery(agent.agent_name);
  const secrets = useAgentSecretsQuery(agent.agent_name);
  const skillCatalog = useSkillsQuery();
  const mcpServers = useMcpServersQuery();
  const connectors = useConnectorsQuery();
  const kbCatalog = useKbsQuery();
  const users = useUsersQuery();

  const bindMcp = useBindAgentMcpMutation(agent.agent_name);
  const unbindMcp = useUnbindAgentMcpMutation(agent.agent_name);
  const bindOauth = useBindAgentOauthMutation(agent.agent_name);
  const unbindOauth = useUnbindAgentOauthMutation(agent.agent_name);
  const bindKb = useBindAgentKbMutation(agent.agent_name);
  const unbindKb = useUnbindAgentKbMutation(agent.agent_name);
  const bindUser = useBindAgentUserMutation(agent.agent_name);
  const unbindUser = useUnbindAgentUserMutation(agent.agent_name);
  const addImGroup = useAddAgentImGroupMutation(agent.agent_name);
  const removeImGroup = useRemoveAgentImGroupMutation(agent.agent_name);
  const setDefault = useSetDefaultAgentMutation(agent.agent_name);
  const clearDefault = useClearDefaultAgentMutation();
  const setImCapabilities = useSetAgentImCapabilitiesMutation(agent.agent_name);
  const updateAgent = useUpdateAgentMutation(agent.agent_name);

  const [selectedMcpServer, setSelectedMcpServer] = useState('');
  const [selectedConnector, setSelectedConnector] = useState('');
  const [runAs, setRunAs] = useState<'agent' | 'user'>('user');
  const [selectedKb, setSelectedKb] = useState('');
  const [selectedUser, setSelectedUser] = useState('');
  const [groupPlatform, setGroupPlatform] = useState('slack');
  const [groupId, setGroupId] = useState('');
  const [capabilities, setCapabilities] = useState<AgentImCapabilitiesInput>({
    supports_dm: false,
    supports_groups: false,
  });
  const [overridesYaml, setOverridesYaml] = useState('');

  useEffect(() => {
    setCapabilities({
      supports_dm: detail.data?.supports_dm ?? false,
      supports_groups: detail.data?.supports_groups ?? false,
    });
  }, [detail.data?.supports_dm, detail.data?.supports_groups, agent.agent_name]);

  useEffect(() => {
    setOverridesYaml(detail.data?.config_overrides_yaml ?? '');
  }, [detail.data?.config_overrides_yaml, agent.agent_name]);

  const availableMcpServers = useMemo(() => {
    const bound = new Set(bindings.data?.mcp_servers ?? []);
    return (mcpServers.data ?? []).filter((server) => !bound.has(server.id));
  }, [bindings.data?.mcp_servers, mcpServers.data]);

  const availableConnectors = useMemo(() => {
    const bound = new Set(oauth.data?.connector_ids ?? []);
    return (connectors.data ?? []).filter((connector) => !bound.has(connector.id));
  }, [connectors.data, oauth.data?.connector_ids]);

  const availableKbs = useMemo(() => {
    const bound = new Set(kbs.data?.kb_ids ?? []);
    return (kbCatalog.data ?? []).filter((kb) => !bound.has(kb.kb_id));
  }, [kbCatalog.data, kbs.data?.kb_ids]);

  const availableUsers = useMemo(() => {
    const bound = new Set(bindings.data?.users ?? []);
    return (users.data ?? []).filter((user) => !bound.has(user.id));
  }, [bindings.data?.users, users.data]);

  const saveImCapabilities = async (): Promise<void> => {
    await setImCapabilities.mutateAsync(capabilities);
  };

  const saveOverrides = async (): Promise<void> => {
    // Partial PATCH: send only the overrides; omitted prompt/tools are left untouched server-side.
    await updateAgent.mutateAsync({ config_overrides_yaml: overridesYaml });
  };

  const boundGroups = bindings.data?.groups ?? [];

  const createGroup = async (group: AgentImGroupInput): Promise<void> => {
    await addImGroup.mutateAsync(group);
  };

  const deleteGroup = async (group: AgentImGroupInput): Promise<void> => {
    await removeImGroup.mutateAsync(group);
  };

  return (
    <aside className="space-y-4 rounded-2xl border bg-white/75 p-5">
      <header className="space-y-2">
        <h2 className="text-lg font-semibold">Agent Bindings</h2>
        <p className="text-sm text-muted-foreground">{`Native controls for ${agent.agent_name}.`}</p>
        {!canWrite ? <p className="text-sm text-muted-foreground">Viewer access is read-only.</p> : null}
      </header>

      <section className="space-y-3 rounded-2xl border bg-white/70 p-4">
        <h3 className="text-lg font-semibold">Skills</h3>
        <div className="space-y-2">
          {(skills.data ?? []).map((binding) => (
            <SkillBindingRow agentName={agent.agent_name} binding={binding} canWrite={canWrite} key={binding.skill_name} />
          ))}
        </div>
        {!skills.data?.length && skillCatalog.data?.length ? (
          <div className="space-y-2">
            {skillCatalog.data.map((skill) => (
              <SkillBindingRow
                agentName={agent.agent_name}
                binding={{ enabled: false, skill_name: skill.name }}
                canWrite={canWrite}
                key={skill.name}
              />
            ))}
          </div>
        ) : null}
      </section>

      <section className="space-y-3 rounded-2xl border bg-white/70 p-4">
        <h3 className="text-lg font-semibold">MCP Servers</h3>
        <BindingList empty="No MCP servers bound." items={bindings.data?.mcp_servers ?? []} renderItem={(item) => (
          <div className="flex items-center gap-2 rounded-full border px-3 py-1" key={item}>
            <span className="text-sm">{item}</span>
            {canWrite ? (
              <button className="text-sm font-medium" onClick={() => void unbindMcp.mutateAsync(item)} type="button">
                {`Remove ${item}`}
              </button>
            ) : null}
          </div>
        )} />
        {canWrite ? (
          <div className="grid gap-3 md:grid-cols-[1fr_auto]">
            <label className="grid gap-2 text-sm font-medium">
              Add MCP server
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setSelectedMcpServer(event.target.value)}
                value={selectedMcpServer}
              >
                <option value="">Select a server</option>
                {availableMcpServers.map((server) => (
                  <option key={server.id} value={server.id}>
                    {server.id}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="self-end rounded-md bg-secondary px-3 py-2 text-sm font-medium"
              onClick={() => {
                if (!selectedMcpServer) {
                  return;
                }
                void bindMcp.mutateAsync(selectedMcpServer);
                setSelectedMcpServer('');
              }}
              type="button"
            >
              Bind MCP server
            </button>
          </div>
        ) : null}
      </section>

      <section className="space-y-3 rounded-2xl border bg-white/70 p-4">
        <h3 className="text-lg font-semibold">OAuth Connectors</h3>
        <BindingList empty="No OAuth connectors bound." items={oauth.data?.service_grants.map((item) => item.service_id) ?? []} renderItem={(item) => {
          const runAsValue = oauth.data?.service_grants.find((grant) => grant.service_id === item)?.run_as ?? 'user';
          return (
            <div className="flex items-center gap-2 rounded-full border px-3 py-1" key={item}>
              <span className="text-sm">{item}</span>
              <span className="text-xs text-muted-foreground">{runAsValue}</span>
              {canWrite ? (
                <button className="text-sm font-medium" onClick={() => void unbindOauth.mutateAsync(item)} type="button">
                  {`Remove ${item}`}
                </button>
              ) : null}
            </div>
          );
        }} />
        {canWrite ? (
          <div className="grid gap-3">
            <div className="grid gap-3 md:grid-cols-[1fr_160px_auto]">
              <label className="grid gap-2 text-sm font-medium">
                Add OAuth connector
                <select
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) => setSelectedConnector(event.target.value)}
                  value={selectedConnector}
                >
                  <option value="">Select a connector</option>
                  {availableConnectors.map((connector) => (
                    <option key={connector.id} value={connector.id}>
                      {connector.id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-2 text-sm font-medium">
                Run as
                <select
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) => setRunAs(event.target.value as 'agent' | 'user')}
                  value={runAs}
                >
                  <option value="user">user</option>
                  <option value="agent">agent</option>
                </select>
              </label>
              <button
                className="self-end rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                onClick={() => {
                  if (!selectedConnector) {
                    return;
                  }
                  void bindOauth.mutateAsync({ connectorId: selectedConnector, runAs });
                  setSelectedConnector('');
                }}
                type="button"
              >
                Bind OAuth connector
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="space-y-3 rounded-2xl border bg-white/70 p-4">
        <h3 className="text-lg font-semibold">Knowledge Bases</h3>
        <BindingList empty="No knowledge bases bound." items={kbs.data?.kb_ids ?? []} renderItem={(item) => (
          <div className="flex items-center gap-2 rounded-full border px-3 py-1" key={item}>
            <span className="text-sm">{item}</span>
            {canWrite ? (
              <button className="text-sm font-medium" onClick={() => void unbindKb.mutateAsync(item)} type="button">
                {`Remove ${item}`}
              </button>
            ) : null}
          </div>
        )} />
        {canWrite ? (
          <div className="grid gap-3 md:grid-cols-[1fr_auto]">
            <label className="grid gap-2 text-sm font-medium">
              Add knowledge base
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setSelectedKb(event.target.value)}
                value={selectedKb}
              >
                <option value="">Select a knowledge base</option>
                {availableKbs.map((kb) => (
                  <option key={kb.kb_id} value={kb.kb_id}>
                    {kb.kb_id}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="self-end rounded-md bg-secondary px-3 py-2 text-sm font-medium"
              onClick={() => {
                if (!selectedKb) {
                  return;
                }
                void bindKb.mutateAsync(selectedKb);
                setSelectedKb('');
              }}
              type="button"
            >
              Bind knowledge base
            </button>
          </div>
        ) : null}
      </section>

      <section className="space-y-3 rounded-2xl border bg-white/70 p-4">
        <h3 className="text-lg font-semibold">User Access</h3>
        <BindingList empty="No users bound." items={bindings.data?.users ?? []} renderItem={(item) => (
          <div className="flex items-center gap-2 rounded-full border px-3 py-1" key={item}>
            <span className="text-sm">{item}</span>
            {canWrite ? (
              <button className="text-sm font-medium" onClick={() => void unbindUser.mutateAsync(item)} type="button">
                {`Remove ${item}`}
              </button>
            ) : null}
          </div>
        )} />
        {canWrite ? (
          <div className="grid gap-3 md:grid-cols-[1fr_auto]">
            <label className="grid gap-2 text-sm font-medium">
              Add user access
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setSelectedUser(event.target.value)}
                value={selectedUser}
              >
                <option value="">Select a user</option>
                {availableUsers.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.id}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="self-end rounded-md bg-secondary px-3 py-2 text-sm font-medium"
              onClick={() => {
                if (!selectedUser) {
                  return;
                }
                void bindUser.mutateAsync(selectedUser);
                setSelectedUser('');
              }}
              type="button"
            >
              Bind user
            </button>
          </div>
        ) : null}
      </section>

      <section className="space-y-3 rounded-2xl border bg-white/70 p-4">
        <h3 className="text-lg font-semibold">IM Connectors</h3>
        <p className="text-sm text-muted-foreground">
          Configure the Slack/Telegram connector (bot/app token env names) via agent.yaml
          overrides. Tokens reference env-var names, never inline secrets.
        </p>
        <label className="grid gap-2 text-sm font-medium">
          Advanced overrides (YAML)
          <textarea
            className="min-h-[160px] rounded-md border bg-white px-3 py-2 font-mono text-sm"
            disabled={!canWrite}
            onChange={(event) => setOverridesYaml(event.target.value)}
            placeholder={'im:\n  slack:\n    bot_token_env: SLACK_BOT_TOKEN\n    app_token_env: SLACK_APP_TOKEN'}
            value={overridesYaml}
          />
        </label>
        {canWrite ? (
          <button
            className="self-start rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            disabled={updateAgent.isPending}
            onClick={() => void saveOverrides()}
            type="button"
          >
            Save overrides
          </button>
        ) : null}
      </section>

      <section className="space-y-3 rounded-2xl border bg-white/70 p-4">
        <h3 className="text-lg font-semibold">IM Access</h3>
        <BindingList empty="No IM groups allowed." items={boundGroups.map((group) => `${group.platform}:${group.group_id}`)} renderItem={(item) => (
          <div className="flex items-center gap-2 rounded-full border px-3 py-1" key={item}>
            <span className="text-sm">{item}</span>
            {canWrite ? (
              <button
                className="text-sm font-medium"
                onClick={() => {
                  const [platform, groupIdValue] = item.split(':');
                  void deleteGroup({ group_id: groupIdValue, platform });
                }}
                type="button"
              >
                {`Remove ${item}`}
              </button>
            ) : null}
          </div>
        )} />
        <div className="flex flex-wrap gap-3 text-sm text-muted-foreground">
          <span>{capabilities.supports_dm ? 'DMs enabled' : 'DMs disabled'}</span>
          <span>{capabilities.supports_groups ? 'Groups enabled' : 'Groups disabled'}</span>
        </div>
        {canWrite ? (
          <div className="grid gap-3">
            <div className="grid gap-3 md:grid-cols-[160px_1fr_auto]">
              <label className="grid gap-2 text-sm font-medium">
                Platform
                <select
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) => setGroupPlatform(event.target.value)}
                  value={groupPlatform}
                >
                  <option value="slack">slack</option>
                  <option value="telegram">telegram</option>
                </select>
              </label>
              <label className="grid gap-2 text-sm font-medium">
                Group id
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) => setGroupId(event.target.value)}
                  value={groupId}
                />
              </label>
              <button
                className="self-end rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                onClick={() => {
                  if (!groupId) {
                    return;
                  }
                  void createGroup({ group_id: groupId, platform: groupPlatform });
                  setGroupId('');
                }}
                type="button"
              >
                Add group
              </button>
            </div>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  checked={capabilities.supports_dm}
                  onChange={(event) =>
                    setCapabilities((current) => ({
                      ...current,
                      supports_dm: event.target.checked,
                    }))
                  }
                  type="checkbox"
                />
                Allow DMs
              </label>
              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  checked={capabilities.supports_groups}
                  onChange={(event) =>
                    setCapabilities((current) => ({
                      ...current,
                      supports_groups: event.target.checked,
                    }))
                  }
                  type="checkbox"
                />
                Allow groups
              </label>
              <button
                className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                onClick={() => void saveImCapabilities()}
                type="button"
              >
                Save IM capabilities
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="space-y-3 rounded-2xl border bg-white/70 p-4">
        <h3 className="text-lg font-semibold">Default Agent</h3>
        <p className="text-sm text-muted-foreground">
          {agent.is_default ? 'This agent is the default.' : 'This agent is not the default.'}
        </p>
        {canWrite ? (
          agent.is_default ? (
            <button
              className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
              onClick={() => void clearDefault.mutateAsync()}
              type="button"
            >
              Clear default agent
            </button>
          ) : (
            <button
              className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
              onClick={() => void setDefault.mutateAsync()}
              type="button"
            >
              Set as default agent
            </button>
          )
        ) : null}
      </section>

      <SecretsSection agentName={agent.agent_name} canWrite={canWrite} secrets={secrets.data?.secrets ?? []} />
    </aside>
  );
}

export function AgentsPage(): JSX.Element {
  const me = useAdminMeQuery();
  const agents = useAgentsQuery();
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [mode, setMode] = useState<'create' | 'edit'>('create');
  const [versionsOpenFor, setVersionsOpenFor] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [allowedTools, setAllowedTools] = useState('');
  const [modelProviderId, setModelProviderId] = useState('');
  const [initialModelProviderId, setInitialModelProviderId] = useState('');

  useEffect(() => {
    if (!selectedName && agents.data && agents.data.length > 0) {
      setSelectedName(agents.data[0].agent_name);
    }
  }, [agents.data, selectedName]);

  const detail = useAgentDetailQuery(selectedName);
  const providers = useProvidersQuery();
  const createAgent = useCreateAgentMutation();
  const updateAgent = useUpdateAgentMutation(selectedName ?? '');
  const versions = useAgentVersionsQuery(versionsOpenFor, versionsOpenFor === selectedName);
  const activateVersion = useActivateAgentVersionMutation(selectedName ?? '');

  const selectedAgent = useMemo(() => {
    return (agents.data ?? []).find((agent) => agent.agent_name === selectedName) ?? null;
  }, [agents.data, selectedName]);

  useEffect(() => {
    if (mode === 'edit' && detail.data) {
      setName(detail.data.agent);
      setSystemPrompt(detail.data.system_prompt);
      setAllowedTools(detail.data.allowed_tools.join(','));
      const provider = defaultRouteProviderId(detail.data.model_overrides);
      setModelProviderId(provider);
      setInitialModelProviderId(provider);
    }
  }, [detail.data, mode]);

  const resetForm = (): void => {
    setMode('create');
    setName('');
    setSystemPrompt('');
    setAllowedTools('');
    setModelProviderId('');
    setInitialModelProviderId('');
  };

  const onSubmit = async (): Promise<void> => {
    if (mode === 'create') {
      await createAgent.mutateAsync({
        name,
        system_prompt: systemPrompt,
        allowed_tools: parseAllowedTools(allowedTools),
        ...(modelProviderId
          ? { model_overrides: withDefaultRouteProvider(undefined, modelProviderId) }
          : {}),
      });
      resetForm();
      return;
    }

    if (selectedName) {
      // Omit model_overrides when unchanged so the PATCH leaves the stored policy untouched;
      // when changed, merge onto the current overrides to preserve credential slots/other routes.
      const modelChanged = modelProviderId !== initialModelProviderId;
      await updateAgent.mutateAsync({
        system_prompt: systemPrompt,
        allowed_tools: parseAllowedTools(allowedTools),
        ...(modelChanged
          ? {
              model_overrides: withDefaultRouteProvider(detail.data?.model_overrides, modelProviderId),
            }
          : {}),
      });
    }
  };

  const canWrite = me.data?.role !== 'viewer';

  return (
    <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
            Native SPA
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Agents</h1>
          <p className="text-sm text-muted-foreground">
            Lifecycle operations, bindings, IM access, default selection, and write-only secrets stay inside the React admin UI.
          </p>
          {!canWrite ? <p className="text-sm text-muted-foreground">Viewer access is read-only.</p> : null}
        </header>

        <section className="rounded-2xl border bg-white/75 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Create or edit agent</h2>
            {mode === 'edit' ? (
              <button
                className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                onClick={resetForm}
                type="button"
              >
                New draft
              </button>
            ) : null}
          </div>
          <div className="grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              Agent name
              <input
                className="rounded-md border bg-white px-3 py-2"
                disabled={mode === 'edit'}
                onChange={(event) => setName(event.target.value)}
                value={name}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              System prompt
              <textarea
                className="min-h-32 rounded-md border bg-white px-3 py-2"
                onChange={(event) => setSystemPrompt(event.target.value)}
                value={systemPrompt}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Allowed tools
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setAllowedTools(event.target.value)}
                value={allowedTools}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Model provider
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setModelProviderId(event.target.value)}
                value={modelProviderId}
              >
                <option value="">Built-in default</option>
                {(providers.data ?? []).map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.model ? `${provider.id} (${provider.model})` : provider.id}
                  </option>
                ))}
              </select>
            </label>
            <p className="-mt-2 text-xs text-muted-foreground">
              Picks the provider for the agent&apos;s default chat route. Set its API key in Secrets
              below, then the node syncs it into the agent.
            </p>
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={() => void onSubmit()}
              type="button"
            >
              {mode === 'create' ? 'Create agent' : 'Save changes'}
            </button>
          </div>
        </section>

        <section className="grid gap-4">
          {agents.data?.map((agent) => (
            <div key={agent.agent_name}>
              <AgentCard
                agent={agent}
                detailPrompt={selectedName === agent.agent_name ? detail.data?.system_prompt : undefined}
                isSelected={selectedName === agent.agent_name}
                onEdit={() => {
                  setSelectedName(agent.agent_name);
                  setMode('edit');
                }}
                onLoadVersions={() => {
                  setSelectedName(agent.agent_name);
                  setVersionsOpenFor(agent.agent_name);
                }}
              />
              {versionsOpenFor === agent.agent_name && versions.data ? (
                <div className="mt-4 space-y-2 border-t pt-4">
                  {versions.data.map((version) => (
                    <div className="flex items-center justify-between gap-4" key={version.id}>
                      <span className="text-sm font-medium">{`v${version.version}${version.is_active ? ' active' : ''}`}</span>
                      {!version.is_active ? (
                        <button
                          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
                          onClick={() => void activateVersion.mutateAsync(version.version)}
                          type="button"
                        >
                          {`Activate v${version.version} for ${agent.agent_name}`}
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </section>
      </div>

      {selectedAgent ? (
        <AgentBindingsPanel
          agent={selectedAgent}
          canWrite={canWrite}
        />
      ) : (
        <aside className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Agent Bindings</h2>
          <p className="mt-2 text-sm text-muted-foreground">Select an agent to manage bindings.</p>
        </aside>
      )}
    </section>
  );
}

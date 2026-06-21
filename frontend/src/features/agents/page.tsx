import { useEffect, useState } from 'react';

import {
  type AgentListItem,
  useActivateAgentVersionMutation,
  useAgentDetailQuery,
  useAgentLifecycleMutation,
  useAgentsQuery,
  useAgentVersionsQuery,
  useCloneAgentMutation,
  useCreateAgentMutation,
  useDeleteAgentMutation,
  useUpdateAgentMutation,
} from '@/features/agents/api';

function parseAllowedTools(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
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
          <p className="mt-2 text-sm text-muted-foreground">{agent.status}</p>
          {isSelected && (detailPrompt ?? agent.system_prompt) ? (
            <p className="mt-2 text-sm text-foreground">{detailPrompt ?? agent.system_prompt}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="rounded-md bg-secondary px-3 py-2 text-sm font-medium" onClick={onEdit} type="button">
            {`Edit ${agent.agent_name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void runDisableEnable()}
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

export function AgentsPage(): JSX.Element {
  const agents = useAgentsQuery();
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [mode, setMode] = useState<'create' | 'edit'>('create');
  const [versionsOpenFor, setVersionsOpenFor] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [allowedTools, setAllowedTools] = useState('');

  useEffect(() => {
    if (!selectedName && agents.data && agents.data.length > 0) {
      setSelectedName(agents.data[0].agent_name);
    }
  }, [agents.data, selectedName]);

  const detail = useAgentDetailQuery(selectedName);
  const createAgent = useCreateAgentMutation();
  const updateAgent = useUpdateAgentMutation(selectedName ?? '');
  const versions = useAgentVersionsQuery(versionsOpenFor, versionsOpenFor === selectedName);
  const activateVersion = useActivateAgentVersionMutation(selectedName ?? '');

  useEffect(() => {
    if (mode === 'edit' && detail.data) {
      setName(detail.data.agent);
      setSystemPrompt(detail.data.system_prompt);
      setAllowedTools(detail.data.allowed_tools.join(','));
    }
  }, [detail.data, mode]);

  const resetForm = (): void => {
    setMode('create');
    setName('');
    setSystemPrompt('');
    setAllowedTools('');
  };

  const onSubmit = async (): Promise<void> => {
    if (mode === 'create') {
      await createAgent.mutateAsync({
        name,
        system_prompt: systemPrompt,
        allowed_tools: parseAllowedTools(allowedTools),
      });
      resetForm();
      return;
    }

    if (selectedName) {
      await updateAgent.mutateAsync({
        system_prompt: systemPrompt,
        allowed_tools: parseAllowedTools(allowedTools),
      });
    }
  };

  return (
    <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
            Native SPA
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Agents</h1>
          <p className="text-sm text-muted-foreground">
            Lifecycle operations run natively here; legacy remains available for unmigrated admin
            domains and deeper bindings.
          </p>
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

      <aside className="space-y-4 rounded-2xl border bg-white/75 p-5">
        <h2 className="text-lg font-semibold">Bindings and legacy entry points</h2>
        <div className="grid gap-2">
          <a
            className="rounded-md bg-secondary px-4 py-3 text-sm font-medium"
            href="/admin/ui-legacy#skills"
          >
            Skills
          </a>
          <a
            className="rounded-md bg-secondary px-4 py-3 text-sm font-medium"
            href="/admin/ui-legacy#kb"
          >
            Knowledge Base
          </a>
          <a
            className="rounded-md bg-secondary px-4 py-3 text-sm font-medium"
            href="/admin/ui-legacy#agents"
          >
            MCP Servers
          </a>
          <a
            className="rounded-md bg-secondary px-4 py-3 text-sm font-medium"
            href="/admin/ui-legacy#agents"
          >
            OAuth Bindings
          </a>
          <a
            className="rounded-md bg-secondary px-4 py-3 text-sm font-medium"
            href="/admin/ui-legacy#agents"
          >
            User Bindings
          </a>
        </div>
      </aside>
    </section>
  );
}

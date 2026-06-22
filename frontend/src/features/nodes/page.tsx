import { useMemo, useState } from 'react';

import {
  type NodeAgentOption,
  useDeleteNodeMutation,
  useNodeAgentsQuery,
  useNodesQuery,
  usePinAgentMutation,
  useRegisterNodeMutation,
  useUnpinAgentMutation,
} from '@/features/nodes/api';

type PlacementView = {
  agent_id: number;
  agent_name: string;
};

function parseLabels(value: string): Record<string, string> {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .reduce<Record<string, string>>((acc, item) => {
      const [key, rawValue] = item.split('=');
      const trimmedKey = key?.trim();
      const trimmedValue = rawValue?.trim();
      if (trimmedKey && trimmedValue) {
        acc[trimmedKey] = trimmedValue;
      }
      return acc;
    }, {});
}

function formatLabels(labels: Record<string, string>): string[] {
  return Object.entries(labels).map(([key, value]) => `${key}=${value}`);
}

function findAgentName(agents: NodeAgentOption[] | undefined, agentId: number): string {
  return agents?.find((agent) => agent.agent_id === agentId)?.agent_name ?? String(agentId);
}

function NodeCard({
  agentOptions,
  nodeId,
  nodeName,
  labels,
  lastSeenAt,
  registeredAt,
  placements,
  onDelete,
  onPin,
  onUnpin,
}: {
  agentOptions: NodeAgentOption[];
  nodeId: string;
  nodeName: string | null;
  labels: Record<string, string>;
  lastSeenAt: string | null;
  registeredAt: string;
  placements: PlacementView[];
  onDelete: () => void;
  onPin: (agentId: number) => Promise<void>;
  onUnpin: (agentId: number, agentName: string) => Promise<void>;
}): JSX.Element {
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const remove = useDeleteNodeMutation(nodeId);
  const pin = usePinAgentMutation(nodeId);
  const unpin = useUnpinAgentMutation(nodeId);

  const availableAgents = useMemo(
    () => agentOptions.filter((agent) => !placements.some((placement) => placement.agent_id === agent.agent_id)),
    [agentOptions, placements]
  );

  const labelsText = formatLabels(labels);

  return (
    <article
      aria-label={`node ${nodeId}`}
      className="rounded-2xl border bg-white/80 p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <h2 className="text-xl font-semibold">{nodeName ?? nodeId}</h2>
          <p className="text-sm text-muted-foreground">{nodeId}</p>
          <p className="text-sm text-muted-foreground">{`Registered: ${registeredAt}`}</p>
          <p className="text-sm text-muted-foreground">
            {`Last seen: ${lastSeenAt ?? 'never reported'}`}
          </p>
          <div className="flex flex-wrap gap-2">
            {labelsText.length > 0 ? (
              labelsText.map((label) => (
                <span
                  className="rounded-full bg-secondary px-3 py-1 text-xs font-medium"
                  key={label}
                >
                  {label}
                </span>
              ))
            ) : (
              <span className="text-sm text-muted-foreground">No labels</span>
            )}
          </div>
        </div>
        <button
          className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
          onClick={() => {
            if (!window.confirm(`Delete node ${nodeId}? This will affect agent placement.`)) {
              return;
            }
            void remove.mutateAsync().then(() => onDelete());
          }}
          type="button"
        >
          {`Delete ${nodeId}`}
        </button>
      </div>

      <div className="mt-5 grid gap-3 rounded-xl border bg-card/60 p-4">
        <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Agent placement
        </h3>
        <label className="grid gap-2 text-sm font-medium">
          Agent
          <select
            className="rounded-md border bg-white px-3 py-2"
            onChange={(event) => setSelectedAgentId(event.target.value)}
            value={selectedAgentId}
          >
            <option value="">Select agent</option>
            {availableAgents.map((agent) => (
              <option
                key={agent.agent_id}
                value={String(agent.agent_id)}
              >
                {agent.agent_name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
          disabled={!selectedAgentId}
          onClick={() =>
            void pin
              .mutateAsync({ agent_id: Number(selectedAgentId) })
              .then(async () => {
                await onPin(Number(selectedAgentId));
                setSelectedAgentId('');
              })
          }
          type="button"
        >
          {`Pin agent to ${nodeId}`}
        </button>

        {placements.length > 0 ? (
          <div className="space-y-2">
            <p className="text-sm font-medium">Pinned agents</p>
            {placements.map((placement) => (
              <div
                className="flex items-center justify-between gap-3 rounded-lg border bg-white px-3 py-2"
                key={placement.agent_id}
              >
                <span className="text-sm">{placement.agent_name}</span>
                <button
                  className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                  onClick={() =>
                    void unpin.mutateAsync(placement.agent_id).then(() => onUnpin(placement.agent_id, placement.agent_name))
                  }
                  type="button"
                >
                  {`Unpin ${placement.agent_name} from ${nodeId}`}
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function NodesPage(): JSX.Element {
  const nodes = useNodesQuery();
  const agents = useNodeAgentsQuery();
  const registerNode = useRegisterNodeMutation();

  const [nodeId, setNodeId] = useState('');
  const [nodeName, setNodeName] = useState('');
  const [labels, setLabels] = useState('');
  const [lastRegisteredKey, setLastRegisteredKey] = useState<string | null>(null);
  const [placementsByNode, setPlacementsByNode] = useState<Record<string, PlacementView[]>>({});

  const onRegister = async (): Promise<void> => {
    const result = await registerNode.mutateAsync({
      labels: parseLabels(labels),
      name: nodeName || undefined,
      node_id: nodeId,
    });
    setLastRegisteredKey(result.service_key_plaintext_once);
    setNodeId('');
    setNodeName('');
    setLabels('');
  };

  return (
    <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
            Native SPA
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Nodes</h1>
          <p className="text-sm text-muted-foreground">
            Register nodes, inspect placement metadata, and pin or unpin agents without dropping to
            CLI or raw admin API calls.
          </p>
        </header>

        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Register node</h2>
          <div className="mt-4 grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              Node ID
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setNodeId(event.target.value)}
                value={nodeId}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Node name
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setNodeName(event.target.value)}
                value={nodeName}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Labels
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setLabels(event.target.value)}
                placeholder="region=us, rack=r1"
                value={labels}
              />
            </label>
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={() => void onRegister()}
              type="button"
            >
              Register node
            </button>
            {lastRegisteredKey ? (
              <p className="text-sm font-medium text-foreground">
                {`Service key (shown once): ${lastRegisteredKey}`}
              </p>
            ) : null}
          </div>
        </section>
      </div>

      <div className="space-y-4">
        {nodes.data?.map((node) => (
          <NodeCard
            agentOptions={agents.data ?? []}
            key={node.id}
            labels={node.labels}
            lastSeenAt={node.last_seen_at}
            nodeId={node.id}
            nodeName={node.name}
            onDelete={() => {
              setPlacementsByNode((current) => {
                const next = { ...current };
                delete next[node.id];
                return next;
              });
            }}
            onPin={(agentId) => {
              const agentName = findAgentName(agents.data, agentId);
              setPlacementsByNode((current) => ({
                ...current,
                [node.id]: [...(current[node.id] ?? []).filter((placement) => placement.agent_id !== agentId), {
                  agent_id: agentId,
                  agent_name: agentName,
                }],
              }));
            }}
            onUnpin={(agentId) => {
              setPlacementsByNode((current) => ({
                ...current,
                [node.id]: (current[node.id] ?? []).filter((placement) => placement.agent_id !== agentId),
              }));
            }}
            placements={placementsByNode[node.id] ?? []}
            registeredAt={node.registered_at}
          />
        ))}
      </div>
    </section>
  );
}

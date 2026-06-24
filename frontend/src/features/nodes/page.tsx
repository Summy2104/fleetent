import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Clock, Copy, Pin, PinOff, Plus, Server, Tag, Trash2 } from 'lucide-react';

import { useAdminApi } from '@/lib/api-client';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import {
  type NodeAgentOption,
  useDeleteNodeMutation,
  useNodeAgentsQuery,
  useNodePlacementsQuery,
  useNodesQuery,
  usePinAgentMutation,
  useRegisterNodeMutation,
  useUnpinAgentMutation,
} from '@/features/nodes/api';

type AdminMe = { email: string; id: string; role: string };

type PlacementView = {
  agent_id: number;
  agent_name: string;
};

function useAdminMeQuery() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

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

// ─────────────────────────── Register node dialog ───────────────────────────

function RegisterNodeDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const registerNode = useRegisterNodeMutation();
  const [nodeId, setNodeId] = useState('');
  const [nodeName, setNodeName] = useState('');
  const [labels, setLabels] = useState('');
  const [serviceKey, setServiceKey] = useState<string | null>(null);

  const reset = (): void => {
    setNodeId('');
    setNodeName('');
    setLabels('');
  };

  const onRegister = async (): Promise<void> => {
    const result = await registerNode.mutateAsync({
      labels: parseLabels(labels),
      name: nodeName || undefined,
      node_id: nodeId,
    });
    setServiceKey(result.service_key_plaintext_once);
    reset();
  };

  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      setServiceKey(null);
      reset();
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Register node</DialogTitle>
          <DialogDescription>
            Register a deployment node, then pin agents to control placement.
          </DialogDescription>
        </DialogHeader>

        {serviceKey ? (
          <div className="space-y-3 rounded-md border border-warning/40 bg-warning/10 p-4">
            <p className="text-sm font-medium text-foreground">Service key (shown once)</p>
            <code className="block max-h-40 overflow-y-auto break-all rounded-md border border-border bg-background/60 p-3 font-mono text-xs text-foreground">
              {serviceKey}
            </code>
            <p className="text-xs text-muted-foreground">
              Copy this key now — it cannot be retrieved again.
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void navigator.clipboard?.writeText(serviceKey)}
              >
                <Copy className="size-4" /> Copy key
              </Button>
              <Button size="sm" variant="secondary" onClick={() => handleOpenChange(false)}>
                Done
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="node-id">Node ID</Label>
                <Input
                  id="node-id"
                  value={nodeId}
                  onChange={(event) => setNodeId(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="node-name">Node name</Label>
                <Input
                  id="node-name"
                  value={nodeName}
                  onChange={(event) => setNodeName(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="node-labels">Labels</Label>
                <Input
                  id="node-labels"
                  placeholder="region=us, rack=r1"
                  value={labels}
                  onChange={(event) => setLabels(event.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button
                disabled={!nodeId || registerNode.isPending}
                onClick={() => void onRegister()}
              >
                Register node
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Pin agent dialog ───────────────────────────

function PinAgentDialog({
  nodeId,
  open,
  onOpenChange,
  availableAgents,
}: {
  nodeId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  availableAgents: NodeAgentOption[];
}): JSX.Element {
  const pin = usePinAgentMutation(nodeId);
  const [selectedAgentId, setSelectedAgentId] = useState('');

  const onPin = async (): Promise<void> => {
    if (!selectedAgentId) return;
    await pin.mutateAsync({ agent_id: Number(selectedAgentId) });
    setSelectedAgentId('');
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setSelectedAgentId('');
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Pin agent to {nodeId}</DialogTitle>
          <DialogDescription>
            Pinning an agent forces it to run on this node.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor={`pin-agent-${nodeId}`}>Agent</Label>
          <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
            <SelectTrigger id={`pin-agent-${nodeId}`} aria-label="Agent">
              <SelectValue placeholder="Select agent" />
            </SelectTrigger>
            <SelectContent>
              {availableAgents.map((agent) => (
                <SelectItem key={agent.agent_id} value={String(agent.agent_id)}>
                  {agent.agent_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {!availableAgents.length ? (
            <p className="text-sm text-muted-foreground">All agents are already pinned here.</p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!selectedAgentId || pin.isPending} onClick={() => void onPin()}>
            Pin agent
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Node card ───────────────────────────

function NodeCard({
  agentOptions,
  canWrite,
  nodeId,
  nodeName,
  labels,
  lastSeenAt,
  registeredAt,
}: {
  agentOptions: NodeAgentOption[];
  canWrite: boolean;
  nodeId: string;
  nodeName: string | null;
  labels: Record<string, string>;
  lastSeenAt: string | null;
  registeredAt: string;
}): JSX.Element {
  const remove = useDeleteNodeMutation(nodeId);
  const unpin = useUnpinAgentMutation(nodeId);
  const placementsQuery = useNodePlacementsQuery(nodeId);

  const [pinOpen, setPinOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const placements: PlacementView[] = useMemo(
    () =>
      (placementsQuery.data ?? []).map((placement) => ({
        agent_id: placement.agent_id,
        agent_name: placement.agent_name ?? String(placement.agent_id),
      })),
    [placementsQuery.data]
  );

  const availableAgents = useMemo(
    () =>
      agentOptions.filter(
        (agent) => !placements.some((placement) => placement.agent_id === agent.agent_id)
      ),
    [agentOptions, placements]
  );

  const labelsText = formatLabels(labels);

  return (
    <Card aria-label={`node ${nodeId}`} className="overflow-hidden">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-secondary text-muted-foreground">
              <Server className="size-5" />
            </span>
            <div className="min-w-0 space-y-1">
              <CardTitle className="truncate">{nodeName ?? nodeId}</CardTitle>
              <p className="truncate font-mono text-xs text-muted-foreground">{nodeId}</p>
            </div>
          </div>
          {canWrite ? (
            <Button
              size="icon"
              variant="ghost"
              aria-label={`Delete ${nodeId}`}
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 className="size-4" />
            </Button>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <div className="flex flex-col gap-1.5 text-xs text-muted-foreground sm:flex-row sm:gap-6">
          <span className="inline-flex items-center gap-1.5">
            <Clock className="size-3.5" /> Registered: {registeredAt}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Clock className="size-3.5" /> Last seen: {lastSeenAt ?? 'never reported'}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Tag className="size-3.5 text-muted-foreground" />
          {labelsText.length > 0 ? (
            labelsText.map((label) => (
              <Badge key={label} variant="secondary">
                {label}
              </Badge>
            ))
          ) : (
            <span className="text-sm text-muted-foreground">No labels</span>
          )}
        </div>

        <Separator />

        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-foreground">Agent placement</h3>
            {canWrite ? (
              <Button size="sm" variant="outline" onClick={() => setPinOpen(true)}>
                <Pin className="size-4" /> Pin agent to {nodeId}
              </Button>
            ) : null}
          </div>

          {placements.length > 0 ? (
            <div className="space-y-2">
              <p className="text-sm font-medium text-foreground">Pinned agents</p>
              {placements.map((placement) => (
                <div
                  key={placement.agent_id}
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-secondary/40 px-3 py-2"
                >
                  <span className="text-sm">{placement.agent_name}</span>
                  {canWrite ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Unpin ${placement.agent_name} from ${nodeId}`}
                      onClick={() => void unpin.mutateAsync(placement.agent_id)}
                    >
                      <PinOff className="size-4" /> Unpin
                    </Button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No agents pinned to this node.</p>
          )}
        </section>
      </CardContent>

      {canWrite ? (
        <PinAgentDialog
          nodeId={nodeId}
          open={pinOpen}
          onOpenChange={setPinOpen}
          availableAgents={availableAgents}
        />
      ) : null}

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete node {nodeId}?</AlertDialogTitle>
            <AlertDialogDescription>
              This will affect agent placement. Pinned agents will be rescheduled elsewhere.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void remove.mutateAsync()}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function NodesPage(): JSX.Element {
  const me = useAdminMeQuery();
  const nodes = useNodesQuery();
  const agents = useNodeAgentsQuery();
  const [registerOpen, setRegisterOpen] = useState(false);

  const canWrite = me.data?.role !== 'viewer';

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">Nodes</h2>
          <Badge variant="secondary">{nodes.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <Button onClick={() => setRegisterOpen(true)}>
            <Plus className="size-4" /> Register node
          </Button>
        ) : null}
      </div>

      <p className="max-w-2xl text-sm text-muted-foreground">
        Register nodes, inspect placement metadata, and pin or unpin agents without dropping to CLI
        or raw admin API calls.
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        {nodes.data?.map((node) => (
          <NodeCard
            key={node.id}
            agentOptions={agents.data ?? []}
            canWrite={canWrite}
            labels={node.labels}
            lastSeenAt={node.last_seen_at}
            nodeId={node.id}
            nodeName={node.name}
            registeredAt={node.registered_at}
          />
        ))}
        {nodes.data && nodes.data.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border py-12 text-center text-sm text-muted-foreground lg:col-span-2">
            No nodes registered yet.
          </div>
        ) : null}
      </div>

      {canWrite ? (
        <RegisterNodeDialog open={registerOpen} onOpenChange={setRegisterOpen} />
      ) : null}
    </div>
  );
}

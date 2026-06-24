import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';

import { useAgentsQuery } from '@/features/agents/api';
import {
  useAgentOverviewQuery,
  useAgentToolsQuery,
  useCompareAgentsQuery,
  usePerUserStatsQuery,
  useRequestDetailQuery,
  useSessionTraceQuery,
  useStatsExportMutation,
  useUserRequestsQuery,
} from '@/features/stats/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const WINDOWS = ['1h', '24h', '7d', '30d'] as const;

function describeValue(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (value === null || value === undefined) {
    return '';
  }
  return JSON.stringify(value);
}

function MetricList({ value }: { value: Record<string, unknown> | undefined }): JSX.Element | null {
  if (!value) {
    return null;
  }
  return (
    <div className="grid gap-1.5">
      {Object.entries(value).map(([key, item]) => (
        <p className="font-mono text-sm text-foreground" key={key}>
          {`${key}: ${String(item)}`}
        </p>
      ))}
    </div>
  );
}

function EventList({
  events,
  title,
}: {
  events: Array<Record<string, unknown>> | undefined;
  title: string;
}): JSX.Element {
  return (
    <Card aria-label={title}>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {events?.length ? (
          events.map((event, index) => (
            <p
              className="rounded-md border border-border bg-secondary/40 px-3 py-2 font-mono text-xs text-foreground"
              key={`${title}-${index}`}
            >
              {describeValue(event.text ?? event.kind ?? event)}
            </p>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">Select a record to inspect its event stream.</p>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────────────────────── Dashboard (mounted after Load) ───────────────────────────

function StatsDashboard({
  agentName,
  agentNames,
  window,
}: {
  agentName: string;
  agentNames: string[];
  window: string;
}): JSX.Element {
  const overview = useAgentOverviewQuery(agentName, window);
  const compare = useCompareAgentsQuery(agentNames, 'calls');
  const tools = useAgentToolsQuery(agentName);
  const perUser = usePerUserStatsQuery(agentName, 'calls');
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [selectedRequest, setSelectedRequest] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const userRequests = useUserRequestsQuery(selectedUser);
  const requestDetail = useRequestDetailQuery(selectedRequest);
  const sessionTrace = useSessionTraceQuery(selectedSession, selectedUser);

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Agent overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <MetricList value={overview.data?.usage} />
            <MetricList value={overview.data?.performance} />
            <MetricList value={overview.data?.approvals} />
            <MetricList value={overview.data?.cost} />
          </CardContent>
        </Card>

        <Card aria-label="Agent comparison">
          <CardHeader>
            <CardTitle>Agent comparison</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary/50 text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Agent</th>
                    <th className="px-3 py-2 text-right font-medium">Calls</th>
                  </tr>
                </thead>
                <tbody>
                  {compare.data?.map((row) => (
                    <tr className="border-t border-border" key={row.agent_id}>
                      <td className="px-3 py-2 font-mono text-foreground">{row.agent_id}</td>
                      <td className="px-3 py-2 text-right font-mono text-muted-foreground">{row.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>Per-user usage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {perUser.data?.map((row) => (
              <div className="rounded-lg border border-border bg-card p-4" key={row.user_id}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 space-y-1">
                    <p className="font-mono text-sm font-semibold text-foreground">{row.user_id}</p>
                    {Object.entries(row)
                      .filter(([key]) => key !== 'user_id')
                      .map(([key, value]) => (
                        <p className="text-sm text-muted-foreground" key={key}>
                          {`${key}: ${describeValue(value)}`}
                        </p>
                      ))}
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setSelectedUser(row.user_id);
                      setSelectedRequest(null);
                      setSelectedSession(null);
                    }}
                  >
                    View requests
                  </Button>
                </div>
              </div>
            ))}
            {perUser.data && perUser.data.length === 0 ? (
              <p className="text-sm text-muted-foreground">No per-user usage yet.</p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Tool coverage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <MetricList value={tools.data?.coverage} />
            <div className="space-y-1.5">
              {tools.data?.top_tools.top.map(([name, calls]) => (
                <div className="flex items-center justify-between gap-3 text-sm" key={name}>
                  <span className="font-mono text-foreground">{name}</span>
                  <Badge variant="outline">{calls}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Requests</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {userRequests.data?.length ? (
              userRequests.data.map((request) => {
                const sessionId = request.session_id;
                return (
                  <div className="space-y-2 rounded-lg border border-border bg-card p-4" key={request.request_id}>
                    <p className="font-mono text-sm font-medium text-foreground">{request.request_id}</p>
                    <p className="text-xs text-muted-foreground">{`session_id: ${sessionId ?? 'n/a'}`}</p>
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button variant="outline" size="sm" onClick={() => setSelectedRequest(request.request_id)}>
                        Open request
                      </Button>
                      {sessionId ? (
                        <Button variant="outline" size="sm" onClick={() => setSelectedSession(sessionId)}>
                          Open session trace
                        </Button>
                      ) : null}
                    </div>
                  </div>
                );
              })
            ) : (
              <p className="text-sm text-muted-foreground">Pick a user to inspect request history.</p>
            )}
          </CardContent>
        </Card>

        <EventList events={requestDetail.data?.events} title="Request detail" />
        <EventList events={sessionTrace.data?.events} title="Session trace" />
      </div>
    </div>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function StatsPage(): JSX.Element {
  const agents = useAgentsQuery();
  const exportMutation = useStatsExportMutation();

  const [pickedAgent, setPickedAgent] = useState('');
  const [pickedWindow, setPickedWindow] = useState('7d');
  const [loaded, setLoaded] = useState<{ agent: string; window: string } | null>(null);

  useEffect(() => {
    if (!pickedAgent && agents.data?.length) {
      setPickedAgent(agents.data[0].agent_name);
    }
  }, [agents.data, pickedAgent]);

  const agentNames = (agents.data ?? []).map((agent) => agent.agent_name);

  const runExport = async (view: 'per-user' | 'tools'): Promise<void> => {
    const result = await exportMutation.mutateAsync({ agentId: pickedAgent || undefined, view });
    const url = URL.createObjectURL(result.blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = result.fileName;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold tracking-tight">Statistics</h2>

      <div className="flex flex-wrap items-center gap-3">
        <Select value={pickedAgent} onValueChange={setPickedAgent} disabled={!agents.data?.length}>
          <SelectTrigger className="w-56">
            <SelectValue placeholder="Pick an agent" />
          </SelectTrigger>
          <SelectContent>
            {agentNames.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={pickedWindow} onValueChange={setPickedWindow}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {WINDOWS.map((option) => (
              <SelectItem key={option} value={option}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          disabled={!pickedAgent}
          onClick={() => setLoaded({ agent: pickedAgent, window: pickedWindow })}
        >
          Load
        </Button>

        <Button
          variant="outline"
          disabled={!pickedAgent || exportMutation.isPending}
          onClick={() => void runExport('per-user')}
        >
          <Download className="size-4" /> Export per-user CSV
        </Button>
        <Button
          variant="outline"
          disabled={!pickedAgent || exportMutation.isPending}
          onClick={() => void runExport('tools')}
        >
          <Download className="size-4" /> Export tools CSV
        </Button>
      </div>

      {loaded ? (
        <StatsDashboard agentName={loaded.agent} agentNames={agentNames} window={loaded.window} />
      ) : (
        <p className="text-sm text-muted-foreground">Pick an agent and load to view its dashboard.</p>
      )}
    </div>
  );
}

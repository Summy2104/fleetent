import { useEffect, useState } from 'react';

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
    <div className="grid gap-2">
      {Object.entries(value).map(([key, item]) => (
        <p
          className="text-sm text-foreground"
          key={key}
        >
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
    <section
      aria-label={title}
      className="rounded-2xl border bg-white/75 p-5"
    >
      <h3 className="text-lg font-semibold">{title}</h3>
      <div className="mt-4 space-y-2">
        {events?.length ? (
          events.map((event, index) => (
            <p
              className="rounded-md bg-secondary/60 px-3 py-2 text-sm"
              key={`${title}-${index}`}
            >
              {describeValue(event.text ?? event.kind ?? event)}
            </p>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">Select a record to inspect its event stream.</p>
        )}
      </div>
    </section>
  );
}

export function StatsPage(): JSX.Element {
  const agents = useAgentsQuery();
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [selectedRequest, setSelectedRequest] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedAgent && agents.data?.length) {
      setSelectedAgent(agents.data[0].agent_name);
    }
  }, [agents.data, selectedAgent]);

  const overview = useAgentOverviewQuery(selectedAgent);
  const compare = useCompareAgentsQuery(
    (agents.data ?? []).map((agent) => agent.agent_name),
    'calls'
  );
  const tools = useAgentToolsQuery(selectedAgent);
  const perUser = usePerUserStatsQuery(selectedAgent, 'calls');
  const userRequests = useUserRequestsQuery(selectedUser);
  const requestDetail = useRequestDetailQuery(selectedRequest);
  const sessionTrace = useSessionTraceQuery(selectedSession, selectedUser);
  const exportMutation = useStatsExportMutation();

  const runExport = async (): Promise<void> => {
    const result = await exportMutation.mutateAsync({
      agentId: selectedAgent ?? undefined,
      view: 'per-user',
    });
    const url = URL.createObjectURL(result.blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = result.fileName;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="space-y-6">
      <header className="space-y-3">
        <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
          Native SPA
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Statistics</h1>
        <p className="text-sm text-muted-foreground">
          Read-only agent analytics, user drill-down, trace inspection, and export now run natively
          in the admin SPA.
        </p>
      </header>

      <section className="rounded-2xl border bg-white/75 p-5">
        <div className="flex flex-wrap items-center gap-4">
          <label className="grid gap-2 text-sm font-medium">
            Agent
            <select
              className="rounded-md border bg-white px-3 py-2"
              onChange={(event) => setSelectedAgent(event.target.value)}
              value={selectedAgent ?? ''}
            >
              {(agents.data ?? []).map((agent) => (
                <option
                  key={agent.agent_name}
                  value={agent.agent_name}
                >
                  {agent.agent_name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            onClick={() => void runExport()}
            type="button"
          >
            Export current view
          </button>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-xl font-semibold">Agent overview</h2>
          <div className="mt-4 space-y-4">
            <MetricList value={overview.data?.usage} />
            <MetricList value={overview.data?.performance} />
            <MetricList value={overview.data?.approvals} />
            <MetricList value={overview.data?.cost} />
          </div>
        </section>

        <section
          aria-label="Agent comparison"
          className="rounded-2xl border bg-white/75 p-5"
        >
          <h2 className="text-xl font-semibold">Agent comparison</h2>
          <div className="mt-4 space-y-2">
            {compare.data?.map((row) => (
              <p
                className="text-sm"
                key={row.agent_id}
              >
                {`${row.agent_id}: ${row.value}`}
              </p>
            ))}
          </div>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-xl font-semibold">Per-user usage</h2>
          <div className="mt-4 space-y-3">
            {perUser.data?.map((row) => (
              <article
                className="rounded-xl border p-4"
                key={row.user_id}
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="space-y-1">
                    <p className="text-base font-semibold">{row.user_id}</p>
                    {Object.entries(row)
                      .filter(([key]) => key !== 'user_id')
                      .map(([key, value]) => (
                        <p
                          className="text-sm text-muted-foreground"
                          key={key}
                        >
                          {`${key}: ${describeValue(value)}`}
                        </p>
                      ))}
                  </div>
                  <button
                    className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                    onClick={() => {
                      setSelectedUser(row.user_id);
                      setSelectedRequest(null);
                      setSelectedSession(null);
                    }}
                    type="button"
                  >
                    {`View requests for ${row.user_id}`}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-xl font-semibold">Tool coverage</h2>
          <div className="mt-4 space-y-4">
            <MetricList value={tools.data?.coverage} />
            <div className="space-y-2">
              {tools.data?.top_tools.top.map(([name, calls]) => (
                <p
                  className="text-sm"
                  key={name}
                >
                  {`${name} (${calls})`}
                </p>
              ))}
            </div>
          </div>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Requests</h2>
          <div className="mt-4 space-y-3">
            {userRequests.data?.length ? (
              userRequests.data.map((request) => (
                (() => {
                  const sessionId = request.session_id;

                  return (
                    <article
                      className="rounded-xl border p-4"
                      key={request.request_id}
                    >
                      <p className="font-medium">{request.request_id}</p>
                      <p className="text-sm text-muted-foreground">
                        {`session_id: ${sessionId ?? 'n/a'}`}
                      </p>
                      <button
                        className="mt-3 rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                        onClick={() => setSelectedRequest(request.request_id)}
                        type="button"
                      >
                        {`Open request ${request.request_id}`}
                      </button>
                      {sessionId ? (
                        <button
                          className="mt-3 ml-2 rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                          onClick={() => setSelectedSession(sessionId)}
                          type="button"
                        >
                          {`Open session trace ${sessionId}`}
                        </button>
                      ) : null}
                    </article>
                  );
                })()
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Pick a user to inspect request history.</p>
            )}
          </div>
        </section>

        <EventList
          events={requestDetail.data?.events}
          title="Request detail"
        />
        <EventList
          events={sessionTrace.data?.events}
          title="Session trace"
        />
      </div>
    </section>
  );
}

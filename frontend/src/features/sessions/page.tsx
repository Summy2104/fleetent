import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';
import {
  useBulkSessionMutation,
  useClearSessionMutation,
  useForceEndSessionMutation,
  useInjectSessionMutation,
  useSessionDetailQuery,
  useSessionsQuery,
  useResetSessionMutation,
  useReleaseSessionMutation,
  useTakeoverSessionMutation,
  type SessionsFilter,
  type SessionListItem,
} from '@/features/sessions/api';

type AdminMe = {
  id: string;
  email: string;
  role: string;
  must_reset?: boolean;
};

function useAdminMeQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['admin-me'],
    queryFn: () => api.get<AdminMe>('/admin/me'),
  });
}

function SessionActions({
  canWrite,
  session,
}: {
  canWrite: boolean;
  session: SessionListItem;
}): JSX.Element | null {
  const takeover = useTakeoverSessionMutation(session.session_id);
  const release = useReleaseSessionMutation(session.session_id);
  const inject = useInjectSessionMutation(session.session_id);
  const reset = useResetSessionMutation(session.session_id);
  const clear = useClearSessionMutation(session.session_id);
  const forceEnd = useForceEndSessionMutation(session.session_id);

  if (!canWrite) {
    return null;
  }

  const runInject = async (): Promise<void> => {
    const content = window.prompt('Inject message content:');
    if (!content) {
      return;
    }
    await inject.mutateAsync({ content, role: 'human_agent' });
  };

  const runReset = async (): Promise<void> => {
    const keepTurnsValue = window.prompt('Keep how many recent turns?', '2');
    if (keepTurnsValue === null) {
      return;
    }
    if (!window.confirm(`Reset session ${session.session_id}? This cannot be undone.`)) {
      return;
    }
    const keepTurns = Number.parseInt(keepTurnsValue, 10);
    if (Number.isNaN(keepTurns)) {
      return;
    }
    await reset.mutateAsync({ keepTurns });
  };

  return (
    <div className="flex flex-wrap gap-2">
      <button
        className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
        onClick={() => void takeover.mutateAsync()}
        type="button"
      >
        Take over
      </button>
      <button
        className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
        onClick={() => void release.mutateAsync()}
        type="button"
      >
        Release
      </button>
      <button
        className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
        onClick={() => void runInject()}
        type="button"
      >
        Inject
      </button>
      <button
        className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
        onClick={() => void runReset()}
        type="button"
      >
        Reset
      </button>
      <button
        className="rounded-md bg-red-100 px-3 py-2 text-sm font-medium text-red-700"
        onClick={() => {
          if (!window.confirm(`Clear transcript of ${session.session_id}? This cannot be undone.`)) {
            return;
          }
          void clear.mutateAsync();
        }}
        type="button"
      >
        Clear
      </button>
      <button
        className="rounded-md bg-red-100 px-3 py-2 text-sm font-medium text-red-700"
        onClick={() => {
          if (!window.confirm(`Force-end session ${session.session_id}? This cannot be undone.`)) {
            return;
          }
          void forceEnd.mutateAsync();
        }}
        type="button"
      >
        Force end
      </button>
    </div>
  );
}

export function SessionsPage(): JSX.Element {
  const me = useAdminMeQuery();
  const [filters, setFilters] = useState<SessionsFilter>({});
  const [draftStatus, setDraftStatus] = useState('');
  const [draftUserId, setDraftUserId] = useState('');
  const [draftAgentName, setDraftAgentName] = useState('');
  const [search, setSearch] = useState('');
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [pickedSessionIds, setPickedSessionIds] = useState<string[]>([]);

  const sessions = useSessionsQuery(filters);
  const detail = useSessionDetailQuery(selectedSessionId);
  const bulk = useBulkSessionMutation();

  const isAdmin = me.data?.role !== 'viewer';
  const visibleSessions = (sessions.data ?? []).filter((session) => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return [session.session_id, session.agent_name, session.origin, session.user_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });

  useEffect(() => {
    if (!sessions.data?.length) {
      setSelectedSessionId(null);
      setPickedSessionIds([]);
      return;
    }

    const selectedStillExists = sessions.data.some((session) => session.session_id === selectedSessionId);
    if (!selectedStillExists) {
      setSelectedSessionId(sessions.data[0].session_id);
    }

    setPickedSessionIds((current) =>
      current.filter((sessionId) => sessions.data?.some((session) => session.session_id === sessionId))
    );
  }, [selectedSessionId, sessions.data]);

  const selectedMeta = detail.data?.meta;

  const togglePicked = (sessionId: string): void => {
    setPickedSessionIds((current) =>
      current.includes(sessionId)
        ? current.filter((item) => item !== sessionId)
        : [...current, sessionId]
    );
  };

  const applyFilters = (): void => {
    setFilters({
      agentName: draftAgentName || undefined,
      status: draftStatus || undefined,
      userId: draftUserId || undefined,
    });
  };

  const runBulkClear = async (): Promise<void> => {
    if (!pickedSessionIds.length) {
      return;
    }
    if (!window.confirm(`Bulk clear ${pickedSessionIds.length} session(s)? This cannot be undone.`)) {
      return;
    }
    await bulk.mutateAsync({ action: 'clear', sessionIds: pickedSessionIds });
  };

  return (
    <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
            Native SPA
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Sessions</h1>
          <p className="text-sm text-muted-foreground">
            Browse active session metadata, inspect transcript detail, and govern live sessions
            without dropping back to the legacy console.
          </p>
          {!isAdmin ? <p className="text-sm text-muted-foreground">Viewer access is read-only.</p> : null}
        </header>

        <section className="rounded-2xl border bg-white/75 p-5">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <label className="grid gap-2 text-sm font-medium">
              Search sessions
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setSearch(event.target.value)}
                value={search}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Status
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setDraftStatus(event.target.value)}
                value={draftStatus}
              >
                <option value="">All statuses</option>
                <option value="active">active</option>
                <option value="idle">idle</option>
                <option value="ended">ended</option>
              </select>
            </label>
            <label className="grid gap-2 text-sm font-medium">
              User ID
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setDraftUserId(event.target.value)}
                value={draftUserId}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Agent name
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setDraftAgentName(event.target.value)}
                value={draftAgentName}
              />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={applyFilters}
              type="button"
            >
              Apply filters
            </button>
            {isAdmin ? (
              <button
                className="rounded-md bg-red-100 px-4 py-2 text-sm font-medium text-red-700"
                onClick={() => void runBulkClear()}
                type="button"
              >
                Bulk clear selected
              </button>
            ) : null}
          </div>
        </section>

        <section className="rounded-2xl border bg-white/75 p-5">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b text-sm text-muted-foreground">
                <th className="py-3">{isAdmin ? 'Pick' : 'View'}</th>
                <th className="py-3">Session</th>
                <th className="py-3">Origin</th>
                <th className="py-3">Agent</th>
                <th className="py-3">Status</th>
                <th className="py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleSessions.map((session) => (
                <tr
                  className="border-b align-top"
                  key={session.session_id}
                >
                  <td className="py-3 pr-3">
                    {isAdmin ? (
                      <input
                        aria-label={`Select session ${session.session_id}`}
                        checked={pickedSessionIds.includes(session.session_id)}
                        onChange={() => togglePicked(session.session_id)}
                        type="checkbox"
                      />
                    ) : (
                      <button
                        className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                        onClick={() => setSelectedSessionId(session.session_id)}
                        type="button"
                      >
                        Open
                      </button>
                    )}
                  </td>
                  <td className="py-3 pr-3">
                    <button
                      className="text-left font-medium"
                      onClick={() => setSelectedSessionId(session.session_id)}
                      type="button"
                    >
                      {session.session_id}
                    </button>
                  </td>
                  <td className="py-3 pr-3 text-sm text-muted-foreground">{session.origin}</td>
                  <td className="py-3 pr-3">{session.agent_name ?? '—'}</td>
                  <td className="py-3 pr-3">{session.status}</td>
                  <td className="py-3">
                    <SessionActions
                      canWrite={isAdmin}
                      session={session}
                    />
                  </td>
                </tr>
              ))}
              {visibleSessions.length === 0 ? (
                <tr>
                  <td
                    className="py-6 text-sm text-muted-foreground"
                    colSpan={6}
                  >
                    No sessions.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>
      </div>

      <section className="rounded-2xl border bg-white/75 p-5">
        <h2 className="text-lg font-semibold">Session detail</h2>
        {selectedMeta ? (
          <div className="mt-4 space-y-4">
            <dl className="grid gap-3 text-sm md:grid-cols-2">
              <div>
                <dt className="font-medium text-muted-foreground">Session ID</dt>
                <dd>{selectedMeta.session_id}</dd>
              </div>
              <div>
                <dt className="font-medium text-muted-foreground">Status</dt>
                <dd>{selectedMeta.status}</dd>
              </div>
              <div>
                <dt className="font-medium text-muted-foreground">Origin</dt>
                <dd>{selectedMeta.origin}</dd>
              </div>
              <div>
                <dt className="font-medium text-muted-foreground">Agent</dt>
                <dd>{selectedMeta.agent_name ?? '—'}</dd>
              </div>
            </dl>
            <div className="space-y-3">
              {detail.data?.transcript.map((entry, index) => (
                <article
                  className="rounded-xl border bg-white p-4"
                  key={`${entry.role}-${index}`}
                >
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    {entry.role}
                  </p>
                  <p className="mt-2 text-sm">{entry.content}</p>
                </article>
              ))}
            </div>
          </div>
        ) : (
          <p className="mt-4 text-sm text-muted-foreground">Select a session to inspect its transcript.</p>
        )}
      </section>
    </section>
  );
}

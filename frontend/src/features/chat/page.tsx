import { useEffect, useRef, useState } from 'react';

import { useAgentChat, useAgentsQuery } from '@/features/chat/api';

function MessageBubble({
  content,
  emphasis = 'normal',
  role,
}: {
  content: string;
  emphasis?: 'error' | 'normal';
  role: 'assistant' | 'user';
}): JSX.Element {
  const baseClass =
    role === 'user'
      ? 'ml-auto bg-primary text-primary-foreground'
      : emphasis === 'error'
        ? 'bg-red-50 text-red-700 ring-1 ring-red-200'
        : 'bg-secondary text-foreground';

  return (
    <article className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm ${baseClass}`}>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.2em] opacity-70">{role}</p>
      <p className="whitespace-pre-wrap break-words">{content}</p>
    </article>
  );
}

export function ChatPage(): JSX.Element {
  const agents = useAgentsQuery();
  const { abort, error, isStreaming, messages, sendMessage } = useAgentChat();
  const [selectedAgent, setSelectedAgent] = useState('');
  const [draft, setDraft] = useState('');
  const previousAgentRef = useRef<string | null>(null);

  useEffect(() => {
    if (!selectedAgent && agents.data && agents.data.length > 0) {
      setSelectedAgent(agents.data[0].agent_name);
    }
  }, [agents.data, selectedAgent]);

  useEffect(() => {
    if (previousAgentRef.current && previousAgentRef.current !== selectedAgent) {
      abort();
    }
    previousAgentRef.current = selectedAgent || null;
  }, [abort, selectedAgent]);

  const canSend = Boolean(selectedAgent) && draft.trim().length > 0 && !isStreaming;

  const onSubmit = async (): Promise<void> => {
    if (!selectedAgent || !draft.trim()) {
      return;
    }
    const message = draft.trim();
    setDraft('');
    await sendMessage(selectedAgent, message);
  };

  const showEmptyAgents = !agents.isLoading && (agents.data?.length ?? 0) === 0;

  return (
    <section className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
      <header className="space-y-2 xl:col-span-2">
        <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
          Agent ingress
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Chat Console</h1>
        <p className="text-sm text-muted-foreground">
          Pick a managed agent, send an operator message, and inspect the streamed response from
          the platform ingress.
        </p>
      </header>

      <aside className="space-y-4 rounded-2xl border bg-white/75 p-5">
        <div className="space-y-2">
          <h2 className="text-lg font-semibold">Target agent</h2>
          {agents.isLoading ? <p className="text-sm text-muted-foreground">Loading agents…</p> : null}
          {showEmptyAgents ? <p className="text-sm text-muted-foreground">No agents available.</p> : null}
        </div>

        <label className="grid gap-2 text-sm font-medium">
          Agent
          <select
            className="rounded-md border bg-white px-3 py-2"
            disabled={agents.isLoading || showEmptyAgents}
            onChange={(event) => setSelectedAgent(event.target.value)}
            value={selectedAgent}
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

        <div className="rounded-xl bg-secondary/40 p-4 text-sm text-muted-foreground">
          {selectedAgent
            ? `Status: ${(agents.data ?? []).find((agent) => agent.agent_name === selectedAgent)?.status ?? 'unknown'}`
            : 'Select an available agent to begin.'}
        </div>
      </aside>

      <section className="space-y-4 rounded-2xl border bg-white/75 p-5">
        <div
          className="flex min-h-[320px] flex-col gap-3 rounded-2xl bg-slate-50 p-4"
          data-testid="chat-transcript"
        >
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No messages yet.</p>
          ) : (
            messages.map((message) => (
              <div
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} flex-col gap-2`}
                key={message.id}
              >
                <MessageBubble
                  content={message.content}
                  emphasis={message.state === 'error' ? 'error' : 'normal'}
                  role={message.role}
                />
                {message.role === 'assistant' &&
                message.state === 'error' &&
                error &&
                error !== message.content ? (
                  <MessageBubble
                    content={error}
                    emphasis="error"
                    role="assistant"
                  />
                ) : null}
              </div>
            ))
          )}
        </div>

        <label className="grid gap-2 text-sm font-medium">
          Message
          <textarea
            className="min-h-28 rounded-md border bg-white px-3 py-2"
            disabled={showEmptyAgents}
            onChange={(event) => setDraft(event.target.value)}
            value={draft}
          />
        </label>

        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {isStreaming ? 'Streaming response from the selected agent.' : 'Ready to send.'}
          </p>
          <button
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!canSend}
            onClick={() => void onSubmit()}
            type="button"
          >
            {isStreaming ? 'Streaming…' : 'Send message'}
          </button>
        </div>
      </section>
    </section>
  );
}

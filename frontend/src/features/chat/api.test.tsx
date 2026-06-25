import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { useAgentChat, useAgentsQuery } from '@/features/chat/api';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

function renderWithProviders(ui: ReactNode): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken="session-token"
    >
      <AppQueryProvider>{ui}</AppQueryProvider>
    </AuthProvider>
  );
}

function sseResponse(chunks: Array<string | Uint8Array>, delayMs = 0): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk);
        if (delayMs > 0) {
          await new Promise((resolve) => setTimeout(resolve, delayMs));
        }
      }
      controller.close();
    },
  });

  return new Response(body, {
    headers: {
      'content-type': 'text/event-stream',
    },
    status: 200,
  });
}

function ChatApiProbe(): JSX.Element {
  const agents = useAgentsQuery();
  const chat = useAgentChat();

  return (
    <section>
      <button
        onClick={() => {
          void chat.sendMessage('alpha', 'hello');
        }}
        type="button"
      >
        send alpha
      </button>
      <button
        onClick={() => {
          void chat.sendMessage('ghost', 'hello');
        }}
        type="button"
      >
        send ghost
      </button>
      <button
        onClick={() => {
          void chat.sendMessage('orphan', 'hello');
        }}
        type="button"
      >
        send orphan
      </button>
      <button
        onClick={() => {
          void chat.sendMessage('broken', 'hello');
        }}
        type="button"
      >
        send broken
      </button>
      <button
        onClick={() => {
          chat.abort();
        }}
        type="button"
      >
        abort
      </button>
      <div data-testid="agent-names">
        {agents.data?.map((agent) => agent.agent_name).join('|') ?? ''}
      </div>
      <div data-testid="messages">
        {chat.messages.map((message) => `${message.role}:${message.content}:${message.state}`).join('|')}
      </div>
      <div data-testid="streaming">{chat.isStreaming ? 'yes' : 'no'}</div>
      <div data-testid="error">{chat.error ?? ''}</div>
    </section>
  );
}

describe('chat api hooks', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads agents and streams SSE deltas with authorization headers', async () => {
    const user = userEvent.setup();

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([
          {
            agent_name: 'alpha',
            provenance: 'adhoc',
            status: 'enabled',
          },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/agents/alpha/chat`, async ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Session session-token');
        expect(request.headers.get('content-type')).toBe('application/json');
        expect(await request.json()).toEqual({ message: 'hello' });

        return sseResponse([
          'data: {"type":"text_delta","content":"hel',
          'lo"}\n\n',
          'data: {"type":"text_delta","content":" world"}\n\n',
          'data: {"type":"done","content":""}\n\n',
        ]);
      })
    );

    renderWithProviders(<ChatApiProbe />);

    await waitFor(() => {
      expect(screen.getByTestId('agent-names')).toHaveTextContent('alpha');
    });

    await user.click(screen.getByRole('button', { name: 'send alpha' }));

    await waitFor(() => {
      expect(screen.getByTestId('messages')).toHaveTextContent('assistant:hello world:done');
    });
    expect(screen.getByTestId('streaming')).toHaveTextContent('no');
    expect(screen.getByTestId('error')).toHaveTextContent('');
  });

  it('maps 404 and 503 ingress errors to clear user-facing messages', async () => {
    const user = userEvent.setup();

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([
          { agent_name: 'ghost', provenance: 'adhoc', status: 'disabled' },
          { agent_name: 'orphan', provenance: 'adhoc', status: 'enabled' },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/agents/ghost/chat`, () =>
        HttpResponse.json({ detail: 'agent ghost not found' }, { status: 404 })
      ),
      http.post(`${API_BASE_URL}/admin/agents/orphan/chat`, () =>
        HttpResponse.json({ detail: 'no node placement for agent orphan' }, { status: 503 })
      )
    );

    renderWithProviders(<ChatApiProbe />);
    await waitFor(() => {
      expect(screen.getByTestId('agent-names')).toHaveTextContent('ghost|orphan');
    });

    await user.click(screen.getByRole('button', { name: 'send ghost' }));
    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent(
        'Agent "ghost": agent ghost not found'
      );
    });

    await user.click(screen.getByRole('button', { name: 'send orphan' }));
    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent(
        'Agent "orphan": no node placement for agent orphan'
      );
    });
  });

  it('surfaces ingress error detail from 503 responses', async () => {
    const user = userEvent.setup();

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([{ agent_name: 'orphan', provenance: 'adhoc', status: 'enabled' }])
      ),
      http.post(`${API_BASE_URL}/admin/agents/orphan/chat`, () =>
        HttpResponse.json(
          { detail: "node 'local-node' service key unavailable" },
          { status: 503 }
        )
      )
    );

    renderWithProviders(<ChatApiProbe />);
    await waitFor(() => {
      expect(screen.getByTestId('agent-names')).toHaveTextContent('orphan');
    });

    await user.click(screen.getByRole('button', { name: 'send orphan' }));
    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent(
        `Agent "orphan": node 'local-node' service key unavailable`
      );
    });
    expect(screen.getByTestId('error')).not.toHaveTextContent('no active placement');
  });

  it('falls back to neutral messages when ingress error detail is unavailable', async () => {
    const user = userEvent.setup();

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([
          { agent_name: 'ghost', provenance: 'adhoc', status: 'disabled' },
          { agent_name: 'orphan', provenance: 'adhoc', status: 'enabled' },
        ])
      ),
      http.post(
        `${API_BASE_URL}/admin/agents/ghost/chat`,
        () => new Response(null, { status: 404 })
      ),
      http.post(
        `${API_BASE_URL}/admin/agents/orphan/chat`,
        () => new Response('upstream unavailable', { status: 503 })
      )
    );

    renderWithProviders(<ChatApiProbe />);
    await waitFor(() => {
      expect(screen.getByTestId('agent-names')).toHaveTextContent('ghost|orphan');
    });

    await user.click(screen.getByRole('button', { name: 'send ghost' }));
    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Agent "ghost" was not found.');
    });

    await user.click(screen.getByRole('button', { name: 'send orphan' }));
    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent(
        'Agent "orphan" is currently unavailable.'
      );
    });
    expect(screen.getByTestId('error')).not.toHaveTextContent('no node placement');
    expect(screen.getByTestId('error')).not.toHaveTextContent('no active placement');
  });

  it('surfaces stream error events as assistant-visible failures', async () => {
    const user = userEvent.setup();

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([{ agent_name: 'broken', provenance: 'adhoc', status: 'enabled' }])
      ),
      http.post(`${API_BASE_URL}/admin/agents/broken/chat`, () =>
        sseResponse([
          'data: {"type":"text_delta","content":"partial"}\n\n',
          'data: {"type":"error","content":"tool exploded"}\n\n',
        ])
      )
    );

    renderWithProviders(<ChatApiProbe />);
    await waitFor(() => {
      expect(screen.getByTestId('agent-names')).toHaveTextContent('broken');
    });

    await user.click(screen.getByRole('button', { name: 'send broken' }));

    await waitFor(() => {
      expect(screen.getByTestId('messages')).toHaveTextContent('assistant:partial:error');
    });
    expect(screen.getByTestId('error')).toHaveTextContent('tool exploded');
  });

  it('aborts active streams without appending later chunks', async () => {
    const user = userEvent.setup();
    const encoder = new TextEncoder();
    let releaseSecondChunk: (() => void) | null = null;

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([{ agent_name: 'alpha', provenance: 'adhoc', status: 'enabled' }])
      ),
      http.post(`${API_BASE_URL}/admin/agents/alpha/chat`, () => {
        const body = new ReadableStream<Uint8Array>({
          async start(controller) {
            controller.enqueue(encoder.encode('data: {"type":"text_delta","content":"first"}\n\n'));
            await new Promise<void>((resolve) => {
              releaseSecondChunk = resolve;
            });
            controller.enqueue(
              encoder.encode('data: {"type":"text_delta","content":" second"}\n\n')
            );
            controller.enqueue(encoder.encode('data: {"type":"done","content":""}\n\n'));
            controller.close();
          },
        });

        return new Response(body, {
          headers: {
            'content-type': 'text/event-stream',
          },
          status: 200,
        });
      })
    );

    renderWithProviders(<ChatApiProbe />);
    await waitFor(() => {
      expect(screen.getByTestId('agent-names')).toHaveTextContent('alpha');
    });

    await user.click(screen.getByRole('button', { name: 'send alpha' }));

    await waitFor(() => {
      expect(screen.getByTestId('messages')).toHaveTextContent('assistant:first:streaming');
    });

    await user.click(screen.getByRole('button', { name: 'abort' }));
    releaseSecondChunk?.();

    await waitFor(() => {
      expect(screen.getByTestId('messages')).toHaveTextContent('assistant:first:aborted');
    });
    expect(screen.getByTestId('messages')).not.toHaveTextContent('second');
    expect(screen.getByTestId('streaming')).toHaveTextContent('no');
  });
});

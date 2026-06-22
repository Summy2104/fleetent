import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { SessionsPage } from '@/features/sessions/page';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

function renderSessionsPage(token = 'session-token'): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken={token}
    >
      <QueryClientProvider client={queryClient}>
        <SessionsPage />
      </QueryClientProvider>
    </AuthProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('sessions page', () => {
  it('supports browsing, detail, governance actions, and dangerous confirmations for admins', async () => {
    const user = userEvent.setup();
    let sessions = [
      {
        session_id: 'sess-1',
        origin: 'im',
        status: 'active',
        agent_name: 'alpha',
        user_id: 'user-1',
        channel: 'slack',
        updated_at: '2026-06-21T10:00:00Z',
      },
      {
        session_id: 'sess-2',
        origin: 'web',
        status: 'idle',
        agent_name: 'beta',
        user_id: 'user-2',
        channel: 'web',
        updated_at: '2026-06-21T09:00:00Z',
      },
    ];
    const actionLog: string[] = [];

    const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => true);
    const promptSpy = vi
      .spyOn(window, 'prompt')
      .mockImplementationOnce(() => 'human override')
      .mockImplementationOnce(() => '3');

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/sessions`, ({ request }) => {
        const url = new URL(request.url);
        const status = url.searchParams.get('status');
        return HttpResponse.json(
          sessions.filter((session) => (status ? session.status === status : true))
        );
      }),
      http.get(`${API_BASE_URL}/admin/sessions/:sessionId`, ({ params }) =>
        HttpResponse.json({
          meta: sessions.find((session) => session.session_id === params.sessionId),
          transcript: [
            { role: 'user', content: `opened-${String(params.sessionId)}` },
            { role: 'assistant', content: 'ack' },
          ],
        })
      ),
      http.post(`${API_BASE_URL}/admin/sessions/:sessionId/takeover`, ({ params }) => {
        actionLog.push(`takeover:${String(params.sessionId)}`);
        return HttpResponse.json({ session_id: params.sessionId, taken_over: true });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/:sessionId/release`, ({ params }) => {
        actionLog.push(`release:${String(params.sessionId)}`);
        return HttpResponse.json({ session_id: params.sessionId, taken_over: false });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/:sessionId/inject`, async ({ params, request }) => {
        actionLog.push(`inject:${String(params.sessionId)}`);
        expect(await request.json()).toEqual({ content: 'human override', role: 'human_agent' });
        return HttpResponse.json({ injected: true, session_id: params.sessionId });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/:sessionId/force-end`, ({ params, request }) => {
        actionLog.push(`force-end:${String(params.sessionId)}`);
        expect(request.headers.get('x-confirm')).toBe('true');
        sessions = sessions.map((session) =>
          session.session_id === params.sessionId ? { ...session, status: 'ended' } : session
        );
        return HttpResponse.json({ session_id: params.sessionId, status: 'ended' });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/:sessionId/clear`, ({ params, request }) => {
        actionLog.push(`clear:${String(params.sessionId)}`);
        expect(request.headers.get('x-confirm')).toBe('true');
        return HttpResponse.json({ cleared: true, session_id: params.sessionId });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/:sessionId/reset`, async ({ params, request }) => {
        actionLog.push(`reset:${String(params.sessionId)}`);
        expect(request.headers.get('x-confirm')).toBe('true');
        expect(await request.json()).toEqual({ keep_turns: 3 });
        return HttpResponse.json({ keep_turns: 3, session_id: params.sessionId });
      }),
      http.post(`${API_BASE_URL}/admin/sessions/bulk`, async ({ request }) => {
        actionLog.push('bulk:clear');
        expect(request.headers.get('x-confirm')).toBe('true');
        expect(await request.json()).toEqual({ action: 'clear', session_ids: ['sess-1', 'sess-2'] });
        return HttpResponse.json({ action: 'clear', batch_id: 'batch-1', count: 2 });
      })
    );

    renderSessionsPage();

    expect(await screen.findByRole('heading', { name: 'Sessions' })).toBeInTheDocument();
    expect(await screen.findByText('sess-1')).toBeInTheDocument();
    expect(screen.getByText('sess-2')).toBeInTheDocument();
    expect(await screen.findByText('opened-sess-1')).toBeInTheDocument();

    const sessionsTable = screen.getByRole('table');
    await user.type(screen.getByLabelText('Search sessions'), 'sess-2');
    expect(within(sessionsTable).queryByText('sess-1')).not.toBeInTheDocument();
    expect(within(sessionsTable).getByText('sess-2')).toBeInTheDocument();

    await user.clear(screen.getByLabelText('Search sessions'));
    await user.selectOptions(screen.getByLabelText('Status'), 'idle');
    await user.click(screen.getByRole('button', { name: 'Apply filters' }));
    expect(await within(sessionsTable).findByText('sess-2')).toBeInTheDocument();
    expect(within(sessionsTable).queryByText('sess-1')).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Status'), '');
    await user.click(screen.getByRole('button', { name: 'Apply filters' }));
    expect(await within(sessionsTable).findByText('sess-1')).toBeInTheDocument();

    const firstRow = screen.getByRole('row', { name: /sess-1/i });
    await user.click(within(firstRow).getByRole('button', { name: 'Take over' }));
    await user.click(within(firstRow).getByRole('button', { name: 'Release' }));
    await user.click(within(firstRow).getByRole('button', { name: 'Inject' }));
    await user.click(within(firstRow).getByRole('button', { name: 'Reset' }));
    await user.click(within(firstRow).getByRole('button', { name: 'Clear' }));
    await user.click(within(firstRow).getByRole('button', { name: 'Force end' }));

    await user.click(screen.getByLabelText('Select session sess-1'));
    await user.click(screen.getByLabelText('Select session sess-2'));
    await user.click(screen.getByRole('button', { name: 'Bulk clear selected' }));

    await waitFor(() => {
      expect(actionLog).toEqual([
        'takeover:sess-1',
        'release:sess-1',
        'inject:sess-1',
        'reset:sess-1',
        'clear:sess-1',
        'force-end:sess-1',
        'bulk:clear',
      ]);
    });

    expect(confirmSpy).toHaveBeenCalledTimes(4);
    expect(promptSpy).toHaveBeenCalledTimes(2);
    expect(await within(sessionsTable).findByText('ended')).toBeInTheDocument();
  });

  it('keeps viewers in read-only mode', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'viewer@fleetent.test', id: 'viewer-1', role: 'viewer' })
      ),
      http.get(`${API_BASE_URL}/admin/sessions`, () =>
        HttpResponse.json([
          {
            session_id: 'sess-1',
            origin: 'im',
            status: 'active',
            agent_name: 'alpha',
            user_id: 'user-1',
            updated_at: '2026-06-21T10:00:00Z',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/sessions/sess-1`, () =>
        HttpResponse.json({
          meta: {
            session_id: 'sess-1',
            origin: 'im',
            status: 'active',
            agent_name: 'alpha',
          },
          transcript: [{ role: 'user', content: 'opened-sess-1' }],
        })
      )
    );

    renderSessionsPage();

    expect(await screen.findByText('sess-1')).toBeInTheDocument();
    expect(await screen.findByText('opened-sess-1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Take over' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Release' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Inject' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Bulk clear selected' })).not.toBeInTheDocument();
    expect(screen.getByText('Viewer access is read-only.')).toBeInTheDocument();
  });
});

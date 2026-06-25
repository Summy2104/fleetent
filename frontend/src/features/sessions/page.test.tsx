import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { SessionsPage } from '@/features/sessions/page';
import { I18nProvider } from '@/i18n';
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
    <I18nProvider>
      <AuthProvider
        baseUrl={API_BASE_URL}
        initialToken={token}
      >
        <QueryClientProvider client={queryClient}>
          <SessionsPage />
        </QueryClientProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('sessions page', () => {
  it('supports browsing, detail, governance actions, and dangerous confirmations for admins', async () => {
    const user = userEvent.setup({ delay: null });
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

    // Inject content is still gathered via window.prompt in the redesigned UI.
    const promptSpy = vi.spyOn(window, 'prompt').mockImplementation(() => 'human override');

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
    // First session is auto-selected; its transcript renders in the detail panel.
    expect(await screen.findByText('opened-sess-1')).toBeInTheDocument();

    // Client-side search filters the rendered session list. The detail panel may
    // still echo the selected session id, so assert membership via the row checkbox.
    await user.type(screen.getByPlaceholderText('Search sessions…'), 'sess-2');
    await waitFor(() => {
      expect(screen.queryByLabelText('Select session sess-1')).not.toBeInTheDocument();
    });
    expect(screen.getByLabelText('Select session sess-2')).toBeInTheDocument();
    await user.clear(screen.getByPlaceholderText('Search sessions…'));
    expect(await screen.findByLabelText('Select session sess-1')).toBeInTheDocument();

    // Status filter is a Radix Select; choosing "idle" + Apply re-queries the API.
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: 'idle' }));
    await user.click(screen.getByRole('button', { name: 'Apply filters' }));
    await waitFor(() => {
      expect(screen.queryByLabelText('Select session sess-1')).not.toBeInTheDocument();
    });
    expect(screen.getByLabelText('Select session sess-2')).toBeInTheDocument();

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: 'All statuses' }));
    await user.click(screen.getByRole('button', { name: 'Apply filters' }));
    expect(await screen.findByLabelText('Select session sess-1')).toBeInTheDocument();

    // Governance actions live behind a per-session dropdown menu.
    const openMenu = async (): Promise<void> => {
      await user.click(screen.getByRole('button', { name: 'Actions for sess-1' }));
    };

    await openMenu();
    await user.click(await screen.findByRole('menuitem', { name: 'Take over' }));

    await openMenu();
    await user.click(await screen.findByRole('menuitem', { name: 'Release' }));

    await openMenu();
    await user.click(await screen.findByRole('menuitem', { name: 'Inject' }));

    // Reset opens a confirmation dialog with an editable keep-turns input.
    await openMenu();
    await user.click(await screen.findByRole('menuitem', { name: 'Reset' }));
    const resetDialog = await screen.findByRole('alertdialog');
    const keepTurnsInput = within(resetDialog).getByLabelText('Keep how many recent turns?');
    await user.clear(keepTurnsInput);
    await user.type(keepTurnsInput, '3');
    await user.click(within(resetDialog).getByRole('button', { name: 'Reset' }));

    // Clear transcript confirmation.
    await openMenu();
    await user.click(await screen.findByRole('menuitem', { name: 'Clear transcript' }));
    const clearDialog = await screen.findByRole('alertdialog');
    await user.click(within(clearDialog).getByRole('button', { name: 'Clear' }));

    // Force end confirmation.
    await openMenu();
    await user.click(await screen.findByRole('menuitem', { name: 'Force end' }));
    const forceEndDialog = await screen.findByRole('alertdialog');
    await user.click(within(forceEndDialog).getByRole('button', { name: 'Force end' }));

    // Bulk clear: pick both sessions then confirm.
    await user.click(screen.getByLabelText('Select session sess-1'));
    await user.click(screen.getByLabelText('Select session sess-2'));
    await user.click(screen.getByRole('button', { name: /Bulk clear/ }));
    const bulkDialog = await screen.findByRole('alertdialog');
    await user.click(within(bulkDialog).getByRole('button', { name: 'Bulk clear' }));

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

    expect(promptSpy).toHaveBeenCalledTimes(1);
    expect(await screen.findByText('ended')).toBeInTheDocument();
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
    expect(screen.queryByRole('button', { name: 'Actions for sess-1' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Select session sess-1')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Bulk clear/ })).not.toBeInTheDocument();
    expect(screen.getByText('read-only')).toBeInTheDocument();
  });
});

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { AuditPage } from '@/features/audit/page';
import { I18nProvider } from '@/i18n';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

function renderAuditPage(): void {
  render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <AppQueryProvider>
          <AuditPage />
        </AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('audit page', () => {
  it('searches audit logs, renders results, shows empty state, and exports current rows', async () => {
    const user = userEvent.setup({ delay: null });
    let exportedBlob: Blob | null = null;
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn() });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      exportedBlob = blob;
      return 'blob:audit-csv';
    });
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    server.use(
      http.get(`${API_BASE_URL}/admin/audit`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get('action') === 'missing') {
          return HttpResponse.json([]);
        }
        expect(url.searchParams.get('actor')).toBe('admin-1');
        expect(url.searchParams.get('action')).toBe('rotate_key');
        expect(url.searchParams.get('target_id')).toBe('user-1');
        return HttpResponse.json([
          {
            id: 1,
            actor_user_id: 'admin-1',
            action: 'rotate_key',
            target_type: 'user',
            target_id: 'user-1',
            detail: { source: 'ui' },
            batch_id: null,
            created_at: '2026-06-27T09:00:00+00:00',
          },
        ]);
      })
    );

    renderAuditPage();

    await user.type(screen.getByLabelText('Actor'), 'admin-1');
    await user.type(screen.getByLabelText('Action'), 'rotate_key');
    await user.type(screen.getByLabelText('Target'), 'user-1');
    await user.type(screen.getByLabelText('Start time'), '2026-06-27T00:00:00+00:00');
    await user.click(screen.getByRole('button', { name: 'Search audit logs' }));

    const row = await screen.findByRole('row', { name: /rotate_key/ });
    expect(within(row).getByText('admin-1')).toBeInTheDocument();
    expect(within(row).getByText('2026-06-27T09:00:00+00:00')).toBeInTheDocument();
    expect(within(row).getByText('user:user-1')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Export CSV' }));
    expect(clickSpy).toHaveBeenCalled();
    expect(exportedBlob?.type).toBe('text/csv;charset=utf-8');
    expect(exportedBlob?.size).toBeGreaterThan(0);

    await user.clear(screen.getByLabelText('Action'));
    await user.type(screen.getByLabelText('Action'), 'missing');
    await user.click(screen.getByRole('button', { name: 'Search audit logs' }));

    await waitFor(() => {
      expect(screen.getByText('No audit logs match the current filters.')).toBeInTheDocument();
    });
  });
});

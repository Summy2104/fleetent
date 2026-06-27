import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { I18nProvider } from '@/i18n';
import { McpPage } from '@/features/mcp/page';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

function renderPage(): void {
  render(
    <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
      <AppQueryProvider>
        <I18nProvider>
          <McpPage />
        </I18nProvider>
      </AppQueryProvider>
    </AuthProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('mcp page form', () => {
  it('submits stdio server args entered in the form', async () => {
    const user = userEvent.setup({ delay: null });
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ server_id: 'filesystem', success: true }, { status: 201 });
      })
    );

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }));
    await user.type(screen.getByLabelText(/^ID/), 'filesystem');
    await user.type(screen.getByLabelText(/^Command/), 'uvx');
    await user.click(screen.getByRole('button', { name: 'Add argument' }));
    await user.type(screen.getByPlaceholderText('argument'), 'mcp-filesystem');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(captured).toEqual({
        id: 'filesystem',
        transport: 'stdio',
        enabled: true,
        command: 'uvx',
        args: ['mcp-filesystem'],
      });
    });
  });

  it('submits http server headers entered in the form', async () => {
    const user = userEvent.setup({ delay: null });
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ server_id: 'armada', success: true }, { status: 201 });
      })
    );

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }));
    await user.type(screen.getByLabelText(/^ID/), 'armada');
    const transport = screen.getByRole('combobox');
    await user.click(transport);
    await user.click(await screen.findByRole('option', { name: 'http' }));
    await user.type(screen.getByLabelText(/Server URL/), 'https://armada.internal/mcp');
    await user.click(screen.getByRole('button', { name: 'Add header' }));
    await user.type(screen.getByPlaceholderText('Header name'), 'X-API-Key');
    await user.type(screen.getByPlaceholderText('Header value'), 'env:ARMADA_AUTH');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(captured).toEqual({
        id: 'armada',
        transport: 'http',
        enabled: true,
        url: 'https://armada.internal/mcp',
        headers: { 'X-API-Key': 'env:ARMADA_AUTH' },
      });
    });
  });
});

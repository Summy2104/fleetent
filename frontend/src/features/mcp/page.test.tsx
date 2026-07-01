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
  it('submits api_key auth config and private scope', async () => {
    const user = userEvent.setup({ delay: null });
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([{ agent_id: 1, agent_name: 'docs-agent', status: 'enabled' }])
      ),
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ server_id: 'docs', success: true }, { status: 201 });
      })
    );

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }));
    await user.type(screen.getByLabelText(/^ID/), 'docs');
    await user.click(screen.getByRole('combobox', { name: 'Scope' }));
    await user.click(await screen.findByRole('option', { name: 'docs-agent' }));
    await user.click(screen.getByRole('combobox', { name: 'Transport' }));
    await user.click(await screen.findByRole('option', { name: 'http' }));
    await user.type(screen.getByLabelText(/Server URL/), 'https://docs.internal/mcp');
    await user.click(screen.getByRole('combobox', { name: 'Auth type' }));
    await user.click(await screen.findByRole('option', { name: 'API Key' }));
    await user.type(screen.getByLabelText(/API key env name/), 'FLEETENT_DOCS_MCP_KEY');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(captured).toEqual({
        id: 'docs',
        agent_id: 1,
        transport: 'http',
        enabled: true,
        url: 'https://docs.internal/mcp',
        auth_type: 'api_key',
        auth_config: { key_env: 'FLEETENT_DOCS_MCP_KEY' },
      });
    });
  });

  it('submits oauth client credentials auth config', async () => {
    const user = userEvent.setup({ delay: null });
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ server_id: 'oauth-docs', success: true }, { status: 201 });
      })
    );

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }));
    await user.type(screen.getByLabelText(/^ID/), 'oauth-docs');
    await user.click(screen.getByRole('combobox', { name: 'Transport' }));
    await user.click(await screen.findByRole('option', { name: 'http' }));
    await user.type(screen.getByLabelText(/Server URL/), 'https://oauth.internal/mcp');
    await user.click(screen.getByRole('combobox', { name: 'Auth type' }));
    await user.click(await screen.findByRole('option', { name: 'OAuth Client Credentials' }));
    await user.type(screen.getByLabelText(/Token URL/), 'https://auth.internal/token');
    await user.type(screen.getByLabelText(/Client ID/), 'docs-client');
    await user.type(screen.getByLabelText(/Client secret env name/), 'FLEETENT_DOCS_MCP_SECRET');
    await user.type(screen.getByLabelText(/OAuth scope/), 'tools:read');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(captured).toEqual({
        id: 'oauth-docs',
        transport: 'http',
        enabled: true,
        url: 'https://oauth.internal/mcp',
        auth_type: 'oauth_client_credentials',
        auth_config: {
          token_url: 'https://auth.internal/token',
          client_id: 'docs-client',
          client_secret_env: 'FLEETENT_DOCS_MCP_SECRET',
          scope: 'tools:read',
        },
      });
    });
  });

  it('submits oauth authorization_code (per-user) auth config; client secret optional (PKCE)', async () => {
    const user = userEvent.setup({ delay: null });
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ server_id: 'crm', success: true }, { status: 201 });
      })
    );

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }));
    await user.type(screen.getByLabelText(/^ID/), 'crm');
    await user.click(screen.getByRole('combobox', { name: 'Transport' }));
    await user.click(await screen.findByRole('option', { name: 'http' }));
    await user.type(screen.getByLabelText(/Server URL/), 'https://crm.internal/mcp');
    await user.click(screen.getByRole('combobox', { name: 'Auth type' }));
    await user.click(await screen.findByRole('option', { name: 'OAuth Authorization Code (per-user)' }));
    // renders the authorization_code field set
    await user.type(screen.getByLabelText(/Authorization endpoint/), 'https://auth.internal/authorize');
    await user.type(screen.getByLabelText(/Token URL/), 'https://auth.internal/token');
    await user.type(screen.getByLabelText(/Client ID/), 'fleetent-crm');
    await user.type(screen.getByLabelText(/OAuth scope/), 'mcp.read');
    await user.type(screen.getByLabelText(/Redirect path/), '/oauth/callback');
    // token_env: stdio per-user OAuth — which env var the per-user access token is injected under.
    await user.type(screen.getByLabelText(/Token env var/), 'GOOGLE_DRIVE_MCP_ACCESS_TOKEN');
    // client_secret_env intentionally left blank — PKCE public client; Create stays enabled.
    const createButton = screen.getByRole('button', { name: 'Create' });
    expect(createButton).toBeEnabled();
    await user.click(createButton);

    await waitFor(() => {
      expect(captured).toEqual({
        id: 'crm',
        transport: 'http',
        enabled: true,
        url: 'https://crm.internal/mcp',
        auth_type: 'oauth_authorization_code',
        auth_config: {
          authorization_endpoint: 'https://auth.internal/authorize',
          token_url: 'https://auth.internal/token',
          client_id: 'fleetent-crm',
          client_secret_env: '',
          scope: 'mcp.read',
          redirect_path: '/oauth/callback',
          token_env: 'GOOGLE_DRIVE_MCP_ACCESS_TOKEN',
        },
      });
    });
  });

  it('oauth authorization_code: token_env optional — blank submits empty string', async () => {
    const user = userEvent.setup({ delay: null });
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ server_id: 'crm2', success: true }, { status: 201 });
      })
    );

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }));
    await user.type(screen.getByLabelText(/^ID/), 'crm2');
    await user.click(screen.getByRole('combobox', { name: 'Transport' }));
    await user.click(await screen.findByRole('option', { name: 'http' }));
    await user.type(screen.getByLabelText(/Server URL/), 'https://crm2.internal/mcp');
    await user.click(screen.getByRole('combobox', { name: 'Auth type' }));
    await user.click(await screen.findByRole('option', { name: 'OAuth Authorization Code (per-user)' }));
    await user.type(screen.getByLabelText(/Authorization endpoint/), 'https://auth.internal/authorize');
    await user.type(screen.getByLabelText(/Token URL/), 'https://auth.internal/token');
    await user.type(screen.getByLabelText(/Client ID/), 'crm2');
    // token_env left blank — still creatable (not a required field).
    const createButton = screen.getByRole('button', { name: 'Create' });
    expect(createButton).toBeEnabled();
    await user.click(createButton);

    await waitFor(() => {
      expect((captured?.auth_config as Record<string, unknown>)?.token_env).toBe('');
    });
  });
});

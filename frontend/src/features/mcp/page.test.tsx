import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { McpServerRecord } from '@/features/connectors/api'
import { McpPage } from '@/features/mcp/page'
import { API_BASE_URL, renderMcp } from '@/features/mcp/test/render'
import { server } from '@/test/msw/server'

const ADMIN_ME = { email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' }
const VIEWER_ME = { email: 'viewer@fleetent.test', id: 'viewer-1', role: 'viewer' }

const SERVERS: McpServerRecord[] = [
  {
    id: 'filesystem',
    transport: 'stdio',
    auth_type: 'none',
    auth_config: {},
    command: 'npx server',
    status: 'connected',
    tool_count: 3,
    agent_id: null,
  },
  {
    id: 'docs',
    transport: 'http',
    auth_type: 'none',
    auth_config: {},
    url: 'https://docs.internal/mcp',
    status: 'configured',
    tool_count: 0,
    agent_id: 1,
  },
]

function mockBase(role: 'admin' | 'viewer' = 'admin', servers: McpServerRecord[] = SERVERS): void {
  server.use(
    http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(role === 'viewer' ? VIEWER_ME : ADMIN_ME)),
    http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json(servers)),
    http.get(`${API_BASE_URL}/admin/agents`, () =>
      HttpResponse.json([{ agent_id: 1, agent_name: 'docs-agent', status: 'enabled' }])
    )
  )
}

function renderPage(): void {
  renderMcp(<McpPage />)
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('mcp page table', () => {
  it('renders server rows in the table', async () => {
    mockBase()
    renderPage()
    expect(await screen.findByText('filesystem')).toBeInTheDocument()
    expect(screen.getByText('docs')).toBeInTheDocument()
    // global scope vs resolved agent name
    expect(screen.getByText('Global')).toBeInTheDocument()
    expect(screen.getByText('docs-agent')).toBeInTheDocument()
  })

  it('filters by global search', async () => {
    mockBase()
    const user = userEvent.setup({ delay: null })
    renderPage()
    await screen.findByText('filesystem')
    await user.type(screen.getByPlaceholderText('Search…'), 'docs')
    await waitFor(() => expect(screen.queryByText('filesystem')).not.toBeInTheDocument())
    expect(screen.getByText('docs')).toBeInTheDocument()
  })

  it('filters by the transport column select filter', async () => {
    mockBase()
    const user = userEvent.setup({ delay: null })
    renderPage()
    await screen.findByText('filesystem')
    await user.click(screen.getByRole('combobox', { name: 'Filter Transport' }))
    await user.click(await screen.findByRole('option', { name: 'http' }))
    await waitFor(() => expect(screen.queryByText('filesystem')).not.toBeInTheDocument())
    expect(screen.getByText('docs')).toBeInTheDocument()
  })

  it('runs a connectivity test via the row actions menu', async () => {
    mockBase()
    let tested = false
    server.use(
      http.post(`${API_BASE_URL}/admin/mcp/servers/filesystem/test`, () => {
        tested = true
        return HttpResponse.json({
          success: true,
          server_id: 'filesystem',
          connected: true,
          tools_count: 3,
        })
      })
    )
    const user = userEvent.setup({ delay: null })
    renderPage()
    await screen.findByText('filesystem')
    await user.click(screen.getByRole('button', { name: 'Actions for filesystem' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Test connection' }))
    await waitFor(() => expect(tested).toBe(true))
    expect(await screen.findByText('filesystem connected')).toBeInTheDocument()
    expect(screen.getByText('connected · 3 tools')).toBeInTheDocument()
    // the test mutation owns its feedback; the global "Done" toast must not also fire
    expect(screen.queryByText('Done')).not.toBeInTheDocument()
  })

  it('shows a failure toast with the backend error when the connectivity test fails', async () => {
    mockBase()
    server.use(
      http.post(`${API_BASE_URL}/admin/mcp/servers/filesystem/test`, () =>
        HttpResponse.json({
          success: true,
          server_id: 'filesystem',
          connected: false,
          error: "[Errno 2] No such file or directory: 'npx -y asdfasdf'",
        })
      )
    )
    const user = userEvent.setup({ delay: null })
    renderPage()
    await screen.findByText('filesystem')
    await user.click(screen.getByRole('button', { name: 'Actions for filesystem' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Test connection' }))
    expect(await screen.findByText('filesystem connection failed')).toBeInTheDocument()
    expect(screen.getByText("[Errno 2] No such file or directory: 'npx -y asdfasdf'")).toBeInTheDocument()
    // a connected:false result is a logical failure over an HTTP 200 — no global success toast
    expect(screen.queryByText('Done')).not.toBeInTheDocument()
  })

  it('reconnects via the row actions menu', async () => {
    mockBase()
    let reconnected = false
    server.use(
      http.post(`${API_BASE_URL}/admin/mcp/servers/filesystem/reconnect`, () => {
        reconnected = true
        return HttpResponse.json({ server_id: 'filesystem', reconnected: true })
      })
    )
    const user = userEvent.setup({ delay: null })
    renderPage()
    await screen.findByText('filesystem')
    await user.click(screen.getByRole('button', { name: 'Actions for filesystem' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Reconnect' }))
    await waitFor(() => expect(reconnected).toBe(true))
  })

  it('views tools via the row actions menu', async () => {
    mockBase()
    let toolsFetched = false
    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers/filesystem/tools`, () => {
        toolsFetched = true
        return HttpResponse.json({
          connected: true,
          tools: [{ name: 'read_file', description: 'Read a file' }],
        })
      })
    )
    const user = userEvent.setup({ delay: null })
    renderPage()
    await screen.findByText('filesystem')
    await user.click(screen.getByRole('button', { name: 'Actions for filesystem' }))
    await user.click(await screen.findByRole('menuitem', { name: 'View tools' }))
    await waitFor(() => expect(toolsFetched).toBe(true))
    expect(await screen.findByText('read_file')).toBeInTheDocument()
  })

  it('deletes via the row actions menu after confirmation', async () => {
    mockBase()
    let deleted = false
    server.use(
      http.delete(`${API_BASE_URL}/admin/mcp/servers/filesystem`, () => {
        deleted = true
        return HttpResponse.json({ success: true, server_id: 'filesystem' })
      })
    )
    const user = userEvent.setup({ delay: null })
    renderPage()
    await screen.findByText('filesystem')
    await user.click(screen.getByRole('button', { name: 'Actions for filesystem' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleted).toBe(true))
  })

  it('hides write actions for viewers', async () => {
    mockBase('viewer')
    renderPage()
    await screen.findByText('filesystem')
    expect(screen.queryByRole('button', { name: 'Add MCP Server' })).not.toBeInTheDocument()
    const user = userEvent.setup({ delay: null })
    await user.click(screen.getByRole('button', { name: 'Actions for filesystem' }))
    // read-only ops remain; write ops do not
    expect(await screen.findByRole('menuitem', { name: 'Test connection' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'View tools' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Reconnect' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).not.toBeInTheDocument()
  })
})

describe('mcp page form', () => {
  it('submits api_key auth config and private scope', async () => {
    mockBase('admin', [])
    const user = userEvent.setup({ delay: null })
    let captured: Record<string, unknown> | null = null
    server.use(
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ server_id: 'docs', success: true }, { status: 201 })
      })
    )

    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }))
    await user.type(screen.getByLabelText(/^ID/), 'docs')
    await user.click(screen.getByRole('combobox', { name: 'Scope' }))
    await user.click(await screen.findByRole('option', { name: 'docs-agent' }))
    await user.click(screen.getByRole('combobox', { name: 'Transport' }))
    await user.click(await screen.findByRole('option', { name: 'http' }))
    await user.type(screen.getByLabelText(/Server URL/), 'https://docs.internal/mcp')
    await user.click(screen.getByRole('combobox', { name: 'Auth type' }))
    await user.click(await screen.findByRole('option', { name: 'API Key' }))
    await user.type(screen.getByLabelText(/API key env name/), 'FLEETENT_DOCS_MCP_KEY')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(captured).toEqual({
        id: 'docs',
        agent_id: 1,
        transport: 'http',
        enabled: true,
        url: 'https://docs.internal/mcp',
        auth_type: 'api_key',
        auth_config: { key_env: 'FLEETENT_DOCS_MCP_KEY' },
      })
    })
  })

  it('submits oauth client credentials auth config', async () => {
    mockBase('admin', [])
    const user = userEvent.setup({ delay: null })
    let captured: Record<string, unknown> | null = null
    server.use(
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ server_id: 'oauth-docs', success: true }, { status: 201 })
      })
    )

    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }))
    await user.type(screen.getByLabelText(/^ID/), 'oauth-docs')
    await user.click(screen.getByRole('combobox', { name: 'Transport' }))
    await user.click(await screen.findByRole('option', { name: 'http' }))
    await user.type(screen.getByLabelText(/Server URL/), 'https://oauth.internal/mcp')
    await user.click(screen.getByRole('combobox', { name: 'Auth type' }))
    await user.click(await screen.findByRole('option', { name: 'OAuth Client Credentials' }))
    await user.type(screen.getByLabelText(/Token URL/), 'https://auth.internal/token')
    await user.type(screen.getByLabelText(/Client ID/), 'docs-client')
    await user.type(screen.getByLabelText(/Client secret env name/), 'FLEETENT_DOCS_MCP_SECRET')
    await user.type(screen.getByLabelText(/OAuth scope/), 'tools:read')
    await user.click(screen.getByRole('button', { name: 'Create' }))

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
      })
    })
  })

  it('submits oauth authorization_code (per-user) auth config; client secret optional (PKCE)', async () => {
    mockBase('admin', [])
    const user = userEvent.setup({ delay: null })
    let captured: Record<string, unknown> | null = null
    server.use(
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ server_id: 'crm', success: true }, { status: 201 })
      })
    )

    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }))
    await user.type(screen.getByLabelText(/^ID/), 'crm')
    await user.click(screen.getByRole('combobox', { name: 'Transport' }))
    await user.click(await screen.findByRole('option', { name: 'http' }))
    await user.type(screen.getByLabelText(/Server URL/), 'https://crm.internal/mcp')
    await user.click(screen.getByRole('combobox', { name: 'Auth type' }))
    await user.click(await screen.findByRole('option', { name: 'OAuth Authorization Code (per-user)' }))
    // renders the authorization_code field set
    await user.type(screen.getByLabelText(/Authorization endpoint/), 'https://auth.internal/authorize')
    await user.type(screen.getByLabelText(/Token URL/), 'https://auth.internal/token')
    await user.type(screen.getByLabelText(/Client ID/), 'fleetent-crm')
    await user.type(screen.getByLabelText(/OAuth scope/), 'mcp.read')
    await user.type(screen.getByLabelText(/Redirect path/), '/oauth/callback')
    // token_env: stdio per-user OAuth — which env var the per-user access token is injected under.
    await user.type(screen.getByLabelText(/Token env var/), 'GOOGLE_DRIVE_MCP_ACCESS_TOKEN')
    // client_secret_env intentionally left blank — PKCE public client; Create stays enabled.
    const createButton = screen.getByRole('button', { name: 'Create' })
    expect(createButton).toBeEnabled()
    await user.click(createButton)

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
      })
    })
  })

  it('oauth authorization_code: token_env optional — blank submits empty string', async () => {
    mockBase('admin', [])
    const user = userEvent.setup({ delay: null })
    let captured: Record<string, unknown> | null = null
    server.use(
      http.post(`${API_BASE_URL}/admin/mcp/servers`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ server_id: 'crm2', success: true }, { status: 201 })
      })
    )

    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Add MCP Server' }))
    await user.type(screen.getByLabelText(/^ID/), 'crm2')
    await user.click(screen.getByRole('combobox', { name: 'Transport' }))
    await user.click(await screen.findByRole('option', { name: 'http' }))
    await user.type(screen.getByLabelText(/Server URL/), 'https://crm2.internal/mcp')
    await user.click(screen.getByRole('combobox', { name: 'Auth type' }))
    await user.click(await screen.findByRole('option', { name: 'OAuth Authorization Code (per-user)' }))
    await user.type(screen.getByLabelText(/Authorization endpoint/), 'https://auth.internal/authorize')
    await user.type(screen.getByLabelText(/Token URL/), 'https://auth.internal/token')
    await user.type(screen.getByLabelText(/Client ID/), 'crm2')
    // token_env left blank — still creatable (not a required field).
    const createButton = screen.getByRole('button', { name: 'Create' })
    expect(createButton).toBeEnabled()
    await user.click(createButton)

    await waitFor(() => {
      expect((captured?.auth_config as Record<string, unknown>)?.token_env).toBe('')
    })
  })
})

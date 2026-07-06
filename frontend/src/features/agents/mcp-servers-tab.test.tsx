import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { McpServersTab } from '@/features/agents/mcp-servers-tab'
import { API_BASE_URL, renderAgents } from '@/features/agents/test/render'
import { server } from '@/test/msw/server'

const AGENT = 'alpha'

const MCP_SERVERS = [
  {
    id: 'github',
    transport: 'stdio',
    auth_type: 'none',
    auth_config: {},
    status: 'connected',
    tool_count: 4,
    agent_id: null,
  },
  {
    id: 'jira',
    transport: 'http',
    auth_type: 'none',
    auth_config: {},
    status: 'disconnected',
    tool_count: 0,
    agent_id: null,
  },
]

function mockCatalog(): void {
  server.use(
    http.get(`${API_BASE_URL}/admin/mcp/servers`, () => HttpResponse.json(MCP_SERVERS)),
    http.get(`${API_BASE_URL}/admin/agents/${AGENT}/mcp`, () => HttpResponse.json(['github']))
  )
}

afterEach(() => vi.restoreAllMocks())

describe('McpServersTab', () => {
  it('renders the MCP server catalog', async () => {
    mockCatalog()
    renderAgents(<McpServersTab agentName={AGENT} canWrite />)
    expect(await screen.findByText('github')).toBeInTheDocument()
    expect(screen.getByText('jira')).toBeInTheDocument()
  })

  it('reflects bound servers as checked toggles', async () => {
    mockCatalog()
    renderAgents(<McpServersTab agentName={AGENT} canWrite />)
    expect(await screen.findByRole('switch', { name: /github/i })).toBeChecked()
    expect(screen.getByRole('switch', { name: /jira/i })).not.toBeChecked()
  })

  it('binds a server when its toggle is switched on', async () => {
    mockCatalog()
    let bound: string | null = null
    server.use(
      http.post(`${API_BASE_URL}/admin/agents/${AGENT}/mcp/:serverId`, ({ params }) => {
        bound = params.serverId as string
        return HttpResponse.json({ agent: AGENT, bound: true, server_id: bound })
      })
    )
    const user = userEvent.setup()
    renderAgents(<McpServersTab agentName={AGENT} canWrite />)
    await user.click(await screen.findByRole('switch', { name: /jira/i }))
    await waitFor(() => expect(bound).toBe('jira'))
  })

  it('disables all toggles for viewers', async () => {
    mockCatalog()
    renderAgents(<McpServersTab agentName={AGENT} canWrite={false} />)
    expect(await screen.findByRole('switch', { name: /github/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('configures a bound server approval rule with a tool name from the live tool list', async () => {
    mockCatalog()
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers/github/tools`, () =>
        HttpResponse.json({
          connected: true,
          tools: [{ name: 'create_issue' }, { name: 'delete_repo' }],
        })
      ),
      http.get(`${API_BASE_URL}/admin/agents/${AGENT}/mcp/github/approval-rules`, () =>
        HttpResponse.json([])
      ),
      http.put(`${API_BASE_URL}/admin/agents/${AGENT}/mcp/github/approval-rules`, async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ agent: AGENT, server_id: 'github', approval_rules: [] })
      })
    )
    const user = userEvent.setup()
    renderAgents(<McpServersTab agentName={AGENT} canWrite />)

    // only the bound server (github) offers the approval-rules entry
    await user.click(await screen.findByRole('button', { name: 'Approval rules' }))
    await user.click(await screen.findByRole('button', { name: 'Add approval rule' }))

    // tool names from the server's live tool list seed the combobox
    await waitFor(() => expect(document.querySelector('option[value="create_issue"]')).toBeTruthy())
    expect(document.querySelector('option[value="delete_repo"]')).toBeTruthy()

    await user.type(screen.getByLabelText('Approval rule tool name'), 'create_issue')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(putBody).toEqual({ approval_rules: [{ tool: 'create_issue', when: null }] })
    )
  })

  it('rehydrates an existing approval rule when the dialog opens', async () => {
    mockCatalog()
    server.use(
      http.get(`${API_BASE_URL}/admin/mcp/servers/github/tools`, () =>
        HttpResponse.json({ connected: true, tools: [{ name: 'create_issue' }] })
      ),
      http.get(`${API_BASE_URL}/admin/agents/${AGENT}/mcp/github/approval-rules`, () =>
        HttpResponse.json([{ tool: 'create_issue', when: { repo: ['acme/app'] } }])
      )
    )
    const user = userEvent.setup()
    renderAgents(<McpServersTab agentName={AGENT} canWrite />)
    await user.click(await screen.findByRole('button', { name: 'Approval rules' }))

    expect(await screen.findByDisplayValue('create_issue')).toBeInTheDocument()
    expect(screen.getByDisplayValue('repo')).toBeInTheDocument()
    expect(screen.getByDisplayValue('acme/app')).toBeInTheDocument()
  })
})

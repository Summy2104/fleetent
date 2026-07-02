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
})

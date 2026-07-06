import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AgentsTable } from '@/features/agents/agents-table'
import { API_BASE_URL, renderAgents } from '@/features/agents/test/render'
import { server } from '@/test/msw/server'

const AGENTS = [
  { agent_name: 'alpha', is_default: false, status: 'enabled', system_prompt: 'Alpha prompt' },
  { agent_name: 'beta', is_default: false, status: 'disabled', system_prompt: 'Beta prompt' },
]

afterEach(() => vi.restoreAllMocks())

describe('AgentsTable', () => {
  it('renders agent rows', async () => {
    server.use(http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json(AGENTS)))
    renderAgents(<AgentsTable canWrite onConfigure={() => {}} />)
    expect(await screen.findByText('alpha')).toBeInTheDocument()
    expect(screen.getByText('beta')).toBeInTheDocument()
  })

  it('filters by global search', async () => {
    server.use(http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json(AGENTS)))
    const user = userEvent.setup()
    renderAgents(<AgentsTable canWrite onConfigure={() => {}} />)
    await screen.findByText('alpha')
    await user.type(screen.getByPlaceholderText('Search…'), 'beta')
    await waitFor(() => expect(screen.queryByText('alpha')).not.toBeInTheDocument())
    expect(screen.getByText('beta')).toBeInTheDocument()
  })
})

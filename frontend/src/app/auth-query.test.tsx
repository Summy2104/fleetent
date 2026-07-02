import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { useAgentsQuery, useCreateAgentMutation } from '@/features/agents/api'
import { useAdminApi } from '@/lib/api-client'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

function renderWithProviders(
  ui: ReactNode,
  options: {
    token?: string
    onSessionExpired?: () => void
  } = {}
): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken={options.token ?? 'session-token'}
      onSessionExpired={options.onSessionExpired}
    >
      <AppQueryProvider>{ui}</AppQueryProvider>
    </AuthProvider>
  )
}

function SessionProbe(): JSX.Element {
  const api = useAdminApi()

  const query = useQuery({
    queryKey: ['me'],
    queryFn: async () => api.get<{ email: string }>('/admin/me'),
    retry: false,
  })

  if (query.isPending) {
    return <p>loading</p>
  }

  if (query.isError) {
    return <p>error</p>
  }

  return <p>{query.data.email}</p>
}

function AgentsProbe(): JSX.Element {
  const query = useAgentsQuery()
  const createAgent = useCreateAgentMutation()

  return (
    <section>
      <button
        onClick={() =>
          createAgent.mutate({
            name: 'beta',
            system_prompt: 'Beta',
            allowed_tools: ['read_file'],
          })
        }
        type="button"
      >
        create
      </button>
      <ul>
        {query.data?.map((agent) => (
          <li key={agent.agent_name}>{agent.agent_name}</li>
        ))}
      </ul>
    </section>
  )
}

describe('admin auth + query data layer', () => {
  it('injects the session token and expires on 401', async () => {
    let requestCount = 0
    const onExpired = vi.fn()

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, ({ request }) => {
        requestCount += 1
        expect(request.headers.get('authorization')).toBe('Session session-token')
        if (requestCount === 1) {
          return HttpResponse.json({ email: 'admin@fleetent.test' })
        }
        return HttpResponse.json({ detail: 'expired' }, { status: 401 })
      })
    )

    renderWithProviders(<SessionProbe />, { onSessionExpired: onExpired })
    expect(await screen.findByText('admin@fleetent.test')).toBeInTheDocument()

    renderWithProviders(<SessionProbe />, { onSessionExpired: onExpired })
    await waitFor(() => {
      expect(onExpired).toHaveBeenCalledTimes(1)
    })
  })

  it('invalidates the agents list after a successful mutation', async () => {
    const user = userEvent.setup({ delay: null })
    let agents = [{ agent_name: 'alpha', status: 'enabled', provenance: 'adhoc' }]

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json(agents)),
      http.post(`${API_BASE_URL}/admin/agents`, async ({ request }) => {
        const body = (await request.json()) as {
          name: string
          system_prompt: string
          allowed_tools: string[]
        }
        agents = [...agents, { agent_name: body.name, status: 'enabled', provenance: 'adhoc' }]
        return HttpResponse.json(
          {
            agent: body.name,
            status: 'enabled',
            provenance: 'adhoc',
          },
          { status: 201 }
        )
      })
    )

    renderWithProviders(<AgentsProbe />)
    expect(await screen.findByText('alpha')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'create' }))

    await waitFor(() => {
      expect(screen.getByText('beta')).toBeInTheDocument()
    })
  })
})

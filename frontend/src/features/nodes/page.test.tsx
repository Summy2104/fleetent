import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { NodesPage } from '@/features/nodes/page'
import { I18nProvider } from '@/i18n'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

function renderPage(): void {
  render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <AppQueryProvider>
          <NodesPage />
        </AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  )
}

/** Resolve a NodeCard by its accessible aria-label (Card renders a plain div). */
function nodeCard(nodeId: string): HTMLElement {
  const node = document.querySelector(`[aria-label="node ${nodeId}"]`)
  if (!(node instanceof HTMLElement)) {
    throw new Error(`No node card with aria-label "node ${nodeId}"`)
  }
  return node
}

async function findNodeCard(nodeId: string): Promise<HTMLElement> {
  return waitFor(() => nodeCard(nodeId))
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('nodes page', () => {
  it('loads already-pinned agents from the backend on mount', async () => {
    const nodes = [
      {
        id: 'node-a',
        labels: {},
        last_seen_at: null,
        name: 'Node A',
        registered_at: '2026-06-21T09:00:00Z',
      },
    ]

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/nodes`, () => HttpResponse.json(nodes)),
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/nodes/node-a/placements`, () =>
        HttpResponse.json([
          {
            agent_id: 7,
            agent_name: 'alpha',
            node_id: 'node-a',
            pinned_at: '2026-06-21T11:10:00Z',
            pinned_by: null,
            updated_at: '2026-06-21T11:10:00Z',
          },
        ])
      )
    )

    renderPage()

    const nodeACard = await findNodeCard('node-a')
    expect(await within(nodeACard).findByText('Pinned agents')).toBeInTheDocument()
    expect(within(nodeACard).getByText('alpha')).toBeInTheDocument()
  })

  it('renders nodes and supports register, delete confirmation, and pin or unpin flows', async () => {
    const user = userEvent.setup({ delay: null })

    type StoredNode = {
      id: string
      labels: Record<string, string>
      last_seen_at: string | null
      name: string | null
      registered_at: string
    }

    let nodes: StoredNode[] = [
      {
        id: 'node-a',
        labels: { region: 'eu' },
        last_seen_at: '2026-06-21T10:00:00Z',
        name: 'Node A',
        registered_at: '2026-06-21T09:00:00Z',
      },
    ]
    const agents = [
      {
        agent_id: 7,
        agent_name: 'alpha',
        provenance: 'adhoc',
        status: 'enabled',
      },
      {
        agent_id: 8,
        agent_name: 'beta',
        provenance: 'adhoc',
        status: 'enabled',
      },
    ]

    let placementsByNode: Record<string, Array<{ agent_id: number; agent_name: string }>> = {}

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/nodes`, () => HttpResponse.json(nodes)),
      http.get(`${API_BASE_URL}/admin/agents`, ({ request }) => {
        expect(new URL(request.url).searchParams.get('include_archived')).toBe('true')
        return HttpResponse.json(agents)
      }),
      http.get(`${API_BASE_URL}/admin/nodes/:nodeId/placements`, ({ params }) =>
        HttpResponse.json(
          (placementsByNode[params.nodeId as string] ?? []).map((placement) => ({
            agent_id: placement.agent_id,
            agent_name: placement.agent_name,
            node_id: params.nodeId,
            pinned_at: '2026-06-21T11:10:00Z',
            pinned_by: null,
            updated_at: '2026-06-21T11:10:00Z',
          }))
        )
      ),
      http.post(`${API_BASE_URL}/admin/nodes`, async ({ request }) => {
        const body = (await request.json()) as {
          labels: Record<string, string>
          name: string
          node_id: string
        }
        const created: StoredNode = {
          id: body.node_id,
          labels: body.labels,
          last_seen_at: null,
          name: body.name,
          registered_at: '2026-06-21T11:00:00Z',
        }
        nodes = [...nodes, created]
        return HttpResponse.json(
          {
            ...created,
            service_key_plaintext_once: 'ma-node-b-secret',
          },
          { status: 201 }
        )
      }),
      http.post(`${API_BASE_URL}/admin/nodes/node-a/pin`, async ({ request }) => {
        expect(await request.json()).toEqual({ agent_id: 7 })
        placementsByNode = { ...placementsByNode, 'node-a': [{ agent_id: 7, agent_name: 'alpha' }] }
        return HttpResponse.json({
          agent_id: 7,
          node_id: 'node-a',
          pinned_at: '2026-06-21T11:10:00Z',
          pinned_by: null,
          updated_at: '2026-06-21T11:10:00Z',
        })
      }),
      http.delete(`${API_BASE_URL}/admin/nodes/node-a/pin`, ({ request }) => {
        expect(new URL(request.url).searchParams.get('agent_id')).toBe('7')
        placementsByNode = { ...placementsByNode, 'node-a': [] }
        return new HttpResponse(null, { status: 204 })
      }),
      http.delete(`${API_BASE_URL}/admin/nodes/node-b`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true')
        nodes = nodes.filter((node) => node.id !== 'node-b')
        return new HttpResponse(null, { status: 204 })
      })
    )

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Nodes' })).toBeInTheDocument()
    expect(await screen.findByText('Node A')).toBeInTheDocument()
    expect(screen.getByText('region=eu')).toBeInTheDocument()

    // Register flow lives behind a dialog launched from the page header button.
    await user.click(screen.getByRole('button', { name: 'Register node' }))
    const registerDialog = await screen.findByRole('dialog')
    await user.type(within(registerDialog).getByLabelText('Node ID'), 'node-b')
    await user.type(within(registerDialog).getByLabelText('Node name'), 'Node B')
    await user.type(within(registerDialog).getByLabelText('Labels'), 'region=us, rack=r1')
    await user.click(within(registerDialog).getByRole('button', { name: 'Register node' }))

    // The plaintext service key is shown once, inside the still-open dialog.
    expect(await within(registerDialog).findByText('Service key (shown once)')).toBeInTheDocument()
    expect(within(registerDialog).getByText('ma-node-b-secret')).toBeInTheDocument()

    // Closing the dialog reveals the newly registered node card.
    await user.click(within(registerDialog).getByRole('button', { name: 'Done' }))
    expect(await findNodeCard('node-b')).toBeInTheDocument()

    // Pin flow: open the per-card pin dialog, pick an agent via the Radix Select.
    const nodeACard = nodeCard('node-a')
    await user.click(within(nodeACard).getByRole('button', { name: 'Pin agent to node-a' }))
    const pinDialog = await screen.findByRole('dialog')
    await user.click(within(pinDialog).getByRole('combobox', { name: 'Agent' }))
    await user.click(await screen.findByRole('option', { name: 'alpha' }))
    await user.click(within(pinDialog).getByRole('button', { name: 'Pin agent' }))

    expect(await within(nodeACard).findByText('Pinned agents')).toBeInTheDocument()
    expect(within(nodeACard).getByText('alpha')).toBeInTheDocument()

    await user.click(within(nodeACard).getByRole('button', { name: 'Unpin alpha from node-a' }))
    await waitFor(() => {
      expect(within(nodeACard).queryByText('Pinned agents')).not.toBeInTheDocument()
    })

    // Delete flow: the trash button opens an AlertDialog confirmation.
    const nodeBCard = nodeCard('node-b')
    await user.click(within(nodeBCard).getByRole('button', { name: 'Delete node-b' }))
    const alert = await screen.findByRole('alertdialog')
    expect(within(alert).getByText('Delete node node-b?')).toBeInTheDocument()
    await user.click(within(alert).getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(screen.queryByText('Node B')).not.toBeInTheDocument()
    })
  })
})

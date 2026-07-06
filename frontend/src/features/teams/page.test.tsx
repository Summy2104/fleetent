import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { TeamsPage } from '@/features/teams/page'
import { I18nProvider } from '@/i18n'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

type TeamRecord = {
  approver_user_id: string | null
  created_at: string
  id: string
  name: string
  tenant_id: string
}

function renderTeamsPage(): void {
  render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <AppQueryProvider>
          <TeamsPage />
        </AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  )
}

describe('teams page', () => {
  it('lets admins list and create teams, and set a team approver', async () => {
    // Base UI locks `document.body { pointer-events: none }` while an overlay is open; with the
    // nested Select-in-Dialog flow that lock can briefly linger in jsdom. Skip userEvent's
    // pointer-events assertion (events still dispatch) — we assert on rendered content, not CSS.
    const user = userEvent.setup({ delay: null, pointerEventsCheck: 0 })
    let teams: TeamRecord[] = [
      {
        approver_user_id: null,
        created_at: '2026-06-21T10:05:00Z',
        id: 'team-a',
        name: 'Team A',
        tenant_id: 'tenant-a',
      },
    ]

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/tenancy/tenants`, () =>
        HttpResponse.json([
          {
            approver_user_id: null,
            created_at: '2026-06-21T10:00:00Z',
            id: 'tenant-a',
            name: 'Tenant A',
            status: 'active',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/tenancy/teams`, () => HttpResponse.json(teams)),
      http.get(`${API_BASE_URL}/admin/users`, () =>
        HttpResponse.json([
          {
            email: 'bob@fleetent.test',
            id: 'user-2',
            must_reset: false,
            name: 'Bob',
            role: 'admin',
            status: 'active',
            tenant_id: null,
          },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/tenancy/teams`, async ({ request }) => {
        const body = (await request.json()) as { name: string; tenant_id: string }
        const created = {
          approver_user_id: null,
          created_at: '2026-06-21T10:11:00Z',
          id: 'team-b',
          name: body.name,
          tenant_id: body.tenant_id,
        }
        teams = [...teams, created]
        return HttpResponse.json(created, { status: 201 })
      }),
      http.patch(`${API_BASE_URL}/admin/tenancy/approvers/team-a`, async ({ request }) => {
        expect(await request.json()).toEqual({ approver_user_id: 'user-2', entity_type: 'team' })
        teams = teams.map((team) => (team.id === 'team-a' ? { ...team, approver_user_id: 'user-2' } : team))
        return HttpResponse.json({ entity_type: 'team', id: 'team-a', status: 'ok' })
      })
    )

    renderTeamsPage()

    expect(await screen.findByText('Teams')).toBeInTheDocument()
    expect(await screen.findByText('Team A')).toBeInTheDocument()
    // The tenant column resolves tenant_id to "name (id)".
    expect(screen.getByRole('row', { name: /Team A/ })).toHaveTextContent('Tenant A (tenant-a)')

    // Create a team via the dialog.
    await user.click(screen.getByRole('button', { name: 'Create team' }))
    await user.type(screen.getByLabelText('Name'), 'Team B')
    await user.click(screen.getByRole('button', { name: 'Create team' }))
    expect(await screen.findByText('Team B')).toBeInTheDocument()

    // Set the approver for Team A via the row action menu + dialog.
    await user.click(screen.getByRole('button', { name: 'Actions for Team A' }))
    await user.click(await screen.findByText('Set approver'))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('combobox'))
    await user.click(await screen.findByText('Bob (bob@fleetent.test)'))
    await user.click(within(dialog).getByRole('button', { name: 'Save approver' }))

    await waitFor(() => {
      expect(screen.getByRole('row', { name: /Team A/ })).toHaveTextContent('Bob (user-2)')
    })
  })

  it('filters teams by tenant and by approver', async () => {
    const user = userEvent.setup({ delay: null, pointerEventsCheck: 0 })

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/tenancy/tenants`, () =>
        HttpResponse.json([
          {
            approver_user_id: null,
            created_at: '2026-06-21T10:00:00Z',
            id: 'tenant-a',
            name: 'Tenant A',
            status: 'active',
          },
          {
            approver_user_id: null,
            created_at: '2026-06-21T10:00:00Z',
            id: 'tenant-b',
            name: 'Tenant B',
            status: 'active',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/tenancy/teams`, () =>
        HttpResponse.json([
          {
            approver_user_id: 'user-2',
            created_at: '2026-06-21T10:05:00Z',
            id: 'team-a',
            name: 'Team A',
            tenant_id: 'tenant-a',
          },
          {
            approver_user_id: null,
            created_at: '2026-06-21T10:06:00Z',
            id: 'team-b',
            name: 'Team B',
            tenant_id: 'tenant-b',
          },
          {
            approver_user_id: 'user-3',
            created_at: '2026-06-21T10:07:00Z',
            id: 'team-c',
            name: 'Team C',
            tenant_id: 'tenant-a',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/users`, () =>
        HttpResponse.json([
          {
            email: 'bob@fleetent.test',
            id: 'user-2',
            must_reset: false,
            name: 'Bob',
            role: 'admin',
            status: 'active',
            tenant_id: null,
          },
          {
            email: 'carol@fleetent.test',
            id: 'user-3',
            must_reset: false,
            name: 'Carol',
            role: 'admin',
            status: 'active',
            tenant_id: null,
          },
        ])
      )
    )

    renderTeamsPage()

    expect(await screen.findByText('Team A')).toBeInTheDocument()
    expect(screen.getByText('Team B')).toBeInTheDocument()
    expect(screen.getByText('Team C')).toBeInTheDocument()

    // Filter by tenant → only teams in Tenant B remain.
    await user.click(screen.getByRole('combobox', { name: 'Filter Tenant' }))
    await user.click(await screen.findByRole('option', { name: 'Tenant B' }))
    await waitFor(() => expect(screen.queryByText('Team A')).not.toBeInTheDocument())
    expect(screen.getByText('Team B')).toBeInTheDocument()
    expect(screen.queryByText('Team C')).not.toBeInTheDocument()

    // Clear filters, then filter by approver → only Carol's team remains.
    await user.click(screen.getByRole('button', { name: 'Reset filters' }))
    expect(await screen.findByText('Team A')).toBeInTheDocument()

    await user.click(screen.getByRole('combobox', { name: 'Filter Approver' }))
    await user.click(await screen.findByRole('option', { name: 'Carol' }))
    await waitFor(() => expect(screen.queryByText('Team A')).not.toBeInTheDocument())
    expect(screen.queryByText('Team B')).not.toBeInTheDocument()
    expect(screen.getByText('Team C')).toBeInTheDocument()
  })

  it('keeps viewers in read-only mode', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'viewer@fleetent.test', id: 'viewer-1', role: 'viewer' })
      ),
      http.get(`${API_BASE_URL}/admin/tenancy/tenants`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/tenancy/teams`, () =>
        HttpResponse.json([
          {
            approver_user_id: null,
            created_at: '2026-06-21T10:05:00Z',
            id: 'team-a',
            name: 'Team A',
            tenant_id: 'tenant-a',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json([]))
    )

    renderTeamsPage()

    expect(await screen.findByText('Teams')).toBeInTheDocument()
    expect(await screen.findByText('Team A')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create team' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Actions for Team A' })).not.toBeInTheDocument()
  })
})

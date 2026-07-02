import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { WebhooksPage } from '@/features/webhooks/page'
import { I18nProvider } from '@/i18n'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

function renderPage(): void {
  render(
    <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
      <AppQueryProvider>
        <I18nProvider>
          <WebhooksPage />
        </I18nProvider>
      </AppQueryProvider>
    </AuthProvider>
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('webhooks page', () => {
  it('renders existing webhook sources', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/webhooks/sources`, () =>
        HttpResponse.json([
          {
            agent_id: 1,
            enabled: true,
            has_secret: true,
            id: 'github-ci',
            message_template: null,
            reply_target: null,
            user_id: 'user-a',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([{ agent_id: 1, agent_name: 'docs-agent', status: 'enabled' }])
      ),
      http.get(`${API_BASE_URL}/admin/users`, () =>
        HttpResponse.json([
          { email: 'a@x.com', id: 'user-a', must_reset: false, name: 'Alice', role: 'user', status: 'active' },
        ])
      )
    )

    renderPage()

    expect(await screen.findByText('github-ci')).toBeInTheDocument()
    expect(screen.getByText('docs-agent')).toBeInTheDocument()
  })

  it('creates a webhook source, requires agent and user, and shows the copyable webhook URL', async () => {
    const user = userEvent.setup({ delay: null })
    let captured: Record<string, unknown> | null = null
    server.use(
      http.get(`${API_BASE_URL}/admin/webhooks/sources`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([{ agent_id: 1, agent_name: 'docs-agent', status: 'enabled' }])
      ),
      http.get(`${API_BASE_URL}/admin/users`, () =>
        HttpResponse.json([
          { email: 'a@x.com', id: 'user-a', must_reset: false, name: 'Alice', role: 'user', status: 'active' },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/webhooks/sources`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            agent_id: 1,
            enabled: true,
            has_secret: true,
            id: 'github-ci',
            message_template: null,
            reply_target: null,
            user_id: 'user-a',
          },
          { status: 201 }
        )
      })
    )

    renderPage()
    await user.click(await screen.findByRole('button', { name: /add webhook/i }))

    const createButton = screen.getByRole('button', { name: 'Create' })
    expect(createButton).toBeDisabled()

    await user.type(screen.getByLabelText(/^ID/), 'github-ci')
    expect(createButton).toBeDisabled()

    await user.click(screen.getByRole('combobox', { name: /agent/i }))
    await user.click(await screen.findByRole('option', { name: 'docs-agent' }))
    expect(createButton).toBeDisabled()

    await user.click(screen.getByRole('combobox', { name: /run as user/i }))
    await user.click(await screen.findByRole('option', { name: 'Alice' }))
    expect(createButton).toBeEnabled()

    await user.click(screen.getByRole('button', { name: /generate/i }))
    const secretInput = screen.getByLabelText(/secret/i) as HTMLInputElement
    expect(secretInput.value).toMatch(/^[0-9a-f]{64}$/)

    await user.click(createButton)

    await waitFor(() => {
      expect(captured).toMatchObject({
        id: 'github-ci',
        agent_id: 1,
        user_id: 'user-a',
        enabled: true,
      })
    })
    expect((captured as unknown as { secret: string }).secret).toMatch(/^[0-9a-f]{64}$/)

    const expectedUrl = `${window.location.origin}/webhook/github-ci`
    expect(await screen.findByText(expectedUrl)).toBeInTheDocument()
  })

  const detailFixtures = (): void => {
    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([{ agent_id: 1, agent_name: 'docs-agent', status: 'enabled' }])
      ),
      http.get(`${API_BASE_URL}/admin/users`, () =>
        HttpResponse.json([
          { email: 'a@x.com', id: 'user-a', must_reset: false, name: 'Alice', role: 'user', status: 'active' },
          { email: 'b@x.com', id: 'user-b', must_reset: false, name: 'Bob', role: 'user', status: 'active' },
        ])
      )
    )
  }

  const source = {
    agent_id: 1,
    enabled: true,
    has_secret: true,
    id: 'github-ci',
    message_template: 'pushed {ref}',
    reply_target: 'user-a',
    user_id: 'user-a',
  }

  async function openViewEdit(user: ReturnType<typeof userEvent.setup>) {
    renderPage()
    expect(await screen.findByText('github-ci')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /actions for github-ci/i }))
    await user.click(await screen.findByRole('menuitem', { name: /view/i }))
    return screen.findByRole('dialog')
  }

  it('shows all fields read-only and marks id read-only in edit mode', async () => {
    const user = userEvent.setup({ delay: null, pointerEventsCheck: 0 })
    detailFixtures()
    server.use(http.get(`${API_BASE_URL}/admin/webhooks/sources`, () => HttpResponse.json([source])))

    const dialog = await openViewEdit(user)
    expect(within(dialog).getByText('pushed {ref}')).toBeInTheDocument()
    expect(within(dialog).getByText('docs-agent')).toBeInTheDocument()
    expect(within(dialog).getByText(/secret is set/i)).toBeInTheDocument()
    // plaintext secret is never present
    expect(dialog.textContent).not.toMatch(/s3cr3t/)

    await user.click(within(dialog).getByRole('button', { name: /^edit$/i }))
    expect(within(dialog).getByLabelText(/^ID/)).toBeDisabled()
  })

  it('edits regular fields and saves with secret_action keep', async () => {
    const user = userEvent.setup({ delay: null, pointerEventsCheck: 0 })
    detailFixtures()
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get(`${API_BASE_URL}/admin/webhooks/sources`, () => HttpResponse.json([source])),
      http.put(`${API_BASE_URL}/admin/webhooks/sources/:sourceId`, async ({ request, params }) => {
        expect(params.sourceId).toBe('github-ci')
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...source, user_id: 'user-b' })
      })
    )

    const dialog = await openViewEdit(user)
    await user.click(within(dialog).getByRole('button', { name: /^edit$/i }))
    await user.click(within(dialog).getByRole('combobox', { name: /run as user/i }))
    await user.click(await screen.findByRole('option', { name: 'Bob' }))
    await user.click(within(dialog).getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(putBody).toMatchObject({ user_id: 'user-b', secret_action: 'keep', enabled: true })
    })
  })

  it('replaces the secret with secret_action set', async () => {
    const user = userEvent.setup({ delay: null, pointerEventsCheck: 0 })
    detailFixtures()
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get(`${API_BASE_URL}/admin/webhooks/sources`, () => HttpResponse.json([source])),
      http.put(`${API_BASE_URL}/admin/webhooks/sources/:sourceId`, async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(source)
      })
    )

    const dialog = await openViewEdit(user)
    await user.click(within(dialog).getByRole('button', { name: /^edit$/i }))
    await user.click(within(dialog).getByRole('button', { name: /replace secret/i }))
    await user.type(within(dialog).getByLabelText(/^secret/i), 'new-secret-value')
    await user.click(within(dialog).getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(putBody).toMatchObject({ secret_action: 'set', secret: 'new-secret-value' })
    })
  })

  it('clears the secret with secret_action clear', async () => {
    const user = userEvent.setup({ delay: null, pointerEventsCheck: 0 })
    detailFixtures()
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get(`${API_BASE_URL}/admin/webhooks/sources`, () => HttpResponse.json([source])),
      http.put(`${API_BASE_URL}/admin/webhooks/sources/:sourceId`, async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...source, has_secret: false })
      })
    )

    const dialog = await openViewEdit(user)
    await user.click(within(dialog).getByRole('button', { name: /^edit$/i }))
    await user.click(within(dialog).getByRole('button', { name: /clear secret/i }))
    await user.click(within(dialog).getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(putBody).toMatchObject({ secret_action: 'clear' })
    })
    expect(putBody).not.toHaveProperty('secret')
  })

  it('deletes a webhook source after confirmation', async () => {
    // pointerEventsCheck disabled: as the dropdown closes into the confirm dialog,
    // jsdom (no transition end) transiently leaves pointer-events:none on the button.
    const user = userEvent.setup({ delay: null, pointerEventsCheck: 0 })
    let deleted = false
    server.use(
      http.get(`${API_BASE_URL}/admin/webhooks/sources`, () =>
        HttpResponse.json(
          deleted
            ? []
            : [
                {
                  agent_id: 1,
                  enabled: true,
                  has_secret: true,
                  id: 'github-ci',
                  message_template: null,
                  reply_target: null,
                  user_id: 'user-a',
                },
              ]
        )
      ),
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json([])),
      http.delete(`${API_BASE_URL}/admin/webhooks/sources/:sourceId`, ({ params }) => {
        expect(params.sourceId).toBe('github-ci')
        deleted = true
        return new HttpResponse(null, { status: 204 })
      })
    )

    renderPage()
    expect(await screen.findByText('github-ci')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /actions for github-ci/i }))
    await user.click(await screen.findByRole('menuitem', { name: /delete/i }))
    // Wait for the AlertDialog to mount before clicking confirm: closing the
    // DropdownMenu leaves `body { pointer-events: none }` in place until Radix
    // finishes tearing it down, and the dialog opens a tick later (setTimeout in
    // the row action). Querying the button synchronously races that window and
    // trips userEvent's pointer-events check on CPU-starved CI runners.
    const confirm = await screen.findByRole('alertdialog')
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(screen.queryByText('github-ci')).not.toBeInTheDocument()
    })
  })
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { StatsPage } from '@/features/stats/page'
import { I18nProvider } from '@/i18n'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

function renderStatsPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <QueryClientProvider client={queryClient}>
          <StatsPage />
        </QueryClientProvider>
      </AuthProvider>
    </I18nProvider>
  )
}

/** Resolve a Card by its accessible aria-label (Card renders a plain div). */
function cardByLabel(label: string): HTMLElement {
  const node = document.querySelector(`[aria-label="${label}"]`)
  if (!(node instanceof HTMLElement)) {
    throw new Error(`No element with aria-label "${label}"`)
  }
  return node
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('stats page', () => {
  it('renders per-user, overview, compare, request detail, session trace, and export flows', async () => {
    const user = userEvent.setup({ delay: null })
    const nativeCreateObjectUrl =
      typeof URL.createObjectURL === 'function'
        ? (blob: Blob | MediaSource) => URL.createObjectURL(blob)
        : () => 'blob:stats'
    const nativeRevokeObjectUrl =
      typeof URL.revokeObjectURL === 'function' ? (url: string) => URL.revokeObjectURL(url) : () => undefined
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: nativeCreateObjectUrl,
      writable: true,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: nativeRevokeObjectUrl,
      writable: true,
    })
    const createObjectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:stats')
    const revokeObjectUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([
          {
            agent_name: 'alpha',
            provenance: 'adhoc',
            status: 'enabled',
            system_prompt: 'Alpha prompt',
          },
          {
            agent_name: 'beta',
            provenance: 'adhoc',
            status: 'enabled',
            system_prompt: 'Beta prompt',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/stats/agents/alpha/overview`, () =>
        HttpResponse.json({
          agent_id: 'alpha',
          approvals: { approved: 3, denied: 1 },
          cost: { total: 1.2 },
          performance: { p95_ms: 750 },
          usage: { calls: 12, total_tokens: 800 },
        })
      ),
      http.get(`${API_BASE_URL}/admin/stats/compare`, () =>
        HttpResponse.json([
          { agent_id: 'alpha', value: 12 },
          { agent_id: 'beta', value: 9 },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/stats/agents/alpha/tools`, () =>
        HttpResponse.json({
          coverage: { allowed: 3, used: 2 },
          top_tools: {
            top: [
              ['read_file', 8],
              ['write_file', 3],
            ],
          },
        })
      ),
      http.get(`${API_BASE_URL}/admin/stats/per-user`, () =>
        HttpResponse.json([
          { user_id: 'u1', calls: 12, total_tokens: 800 },
          { user_id: 'u2', calls: 5, total_tokens: 320 },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/stats/users/u1/requests`, () =>
        HttpResponse.json([
          { request_id: 'req-1', session_id: 'sess-1', turns: 3 },
          { request_id: 'req-2', session_id: 'sess-2', turns: 2 },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/stats/requests/req-1`, () =>
        HttpResponse.json({
          request_id: 'req-1',
          events: [
            { kind: 'user', text: 'hello' },
            { kind: 'assistant', text: 'ack' },
          ],
          subagents: [],
        })
      ),
      http.get(`${API_BASE_URL}/admin/stats/sessions/sess-1/trace`, ({ request }) => {
        expect(new URL(request.url).searchParams.get('user_id')).toBe('u1')
        return HttpResponse.json({
          session_id: 'sess-1',
          events: [{ kind: 'tool', text: 'read_file' }],
          subagents: [],
        })
      }),
      http.post(
        `${API_BASE_URL}/admin/stats/export`,
        () =>
          new HttpResponse('user_id,calls\nu1,12\n', {
            headers: {
              'Content-Disposition': 'attachment; filename="stats-per-user.csv"',
              'Content-Type': 'text/csv',
            },
          })
      )
    )

    renderStatsPage()

    expect(await screen.findByRole('heading', { name: 'Statistics' })).toBeInTheDocument()

    // The dashboard mounts only after picking an agent (auto-filled to the first)
    // and pressing Load. The Load button stays disabled until the agents query
    // resolves and the auto-fill effect sets the picked agent, so wait for it to
    // become enabled before clicking — otherwise the click lands on a disabled
    // button and is silently dropped.
    const loadButton = await screen.findByRole('button', { name: 'Load' })
    await waitFor(() => expect(loadButton).toBeEnabled())
    await user.click(loadButton)

    await waitFor(() => {
      expect(screen.getByText('u1')).toBeInTheDocument()
      // calls: 12 appears in both overview usage and the per-user row.
      expect(screen.getAllByText('calls: 12').length).toBeGreaterThan(0)
      expect(screen.getByText('p95_ms: 750')).toBeInTheDocument()
      expect(screen.getByText('read_file')).toBeInTheDocument()
    })

    // Compare table renders agent id and value in separate cells.
    const compareSection = within(cardByLabel('Agent comparison'))
    expect(compareSection.getByText('alpha')).toBeInTheDocument()
    expect(compareSection.getByText('12')).toBeInTheDocument()
    expect(compareSection.getByText('beta')).toBeInTheDocument()
    expect(compareSection.getByText('9')).toBeInTheDocument()

    // Inspect u1's request history. Each per-user row has its own "View requests".
    const u1Row = screen.getByText('u1').closest('div.rounded-lg') as HTMLElement
    await user.click(within(u1Row).getByRole('button', { name: 'View requests' }))
    expect(await screen.findByText('req-1')).toBeInTheDocument()

    const req1Row = screen.getByText('req-1').closest('div.rounded-lg') as HTMLElement
    await user.click(within(req1Row).getByRole('button', { name: 'Open request' }))
    expect(await screen.findByText('hello')).toBeInTheDocument()
    expect(screen.getByText('ack')).toBeInTheDocument()

    await user.click(within(req1Row).getByRole('button', { name: 'Open session trace' }))
    const sessionTraceCard = within(cardByLabel('Session trace'))
    expect(await sessionTraceCard.findByText('read_file')).toBeInTheDocument()

    // Export per-user CSV triggers a blob download.
    await user.click(screen.getByRole('button', { name: 'Export per-user CSV' }))
    await waitFor(() => {
      expect(createObjectUrl).toHaveBeenCalledTimes(1)
      expect(clickSpy).toHaveBeenCalledTimes(1)
      expect(revokeObjectUrl).toHaveBeenCalledTimes(1)
    })
  })
})

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { AuditPage, auditFiltersFromColumns } from '@/features/audit/page'
import { I18nProvider } from '@/i18n'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

// Pin a non-UTC zone (团队在 UTC+8) so the local→UTC date-range bounds are deterministic.
const ORIGINAL_TZ = process.env.TZ
process.env.TZ = 'Asia/Shanghai'

afterAll(() => {
  process.env.TZ = ORIGINAL_TZ
})

function renderAuditPage(): void {
  render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <AppQueryProvider>
          <AuditPage />
        </AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('auditFiltersFromColumns', () => {
  it('maps text column filters onto the backend query shape', () => {
    expect(
      auditFiltersFromColumns([
        { id: 'actor_user_id', value: 'admin-1' },
        { id: 'action', value: 'rotate_key' },
        { id: 'resource', value: 'user-1' },
      ])
    ).toEqual({ actor: 'admin-1', action: 'rotate_key', targetId: 'user-1' })
  })

  it('expands the created_at date range into UTC since/until bounds', () => {
    expect(auditFiltersFromColumns([{ id: 'created_at', value: { from: '2026-06-27', to: '2026-06-28' } }])).toEqual({
      since: '2026-06-26T16:00:00.000Z',
      until: '2026-06-28T15:59:59.999Z',
    })
  })

  it('drops blank text filters', () => {
    expect(auditFiltersFromColumns([{ id: 'actor_user_id', value: '   ' }])).toEqual({})
  })
})

describe('audit page', () => {
  it('searches audit logs, renders results, shows empty state, and exports current rows', async () => {
    const user = userEvent.setup({ delay: null })
    let exportedBlob: Blob | null = null
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn() })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      exportedBlob = blob instanceof Blob ? blob : null
      return 'blob:audit-csv'
    })
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

    server.use(
      http.get(`${API_BASE_URL}/admin/audit`, ({ request }) => {
        const url = new URL(request.url)
        if (url.searchParams.get('action') === 'missing') {
          return HttpResponse.json([])
        }
        expect(url.searchParams.get('actor')).toBe('admin-1')
        expect(url.searchParams.get('action')).toBe('rotate_key')
        expect(url.searchParams.get('target_id')).toBe('user-1')
        return HttpResponse.json([
          {
            id: 1,
            actor_user_id: 'admin-1',
            action: 'rotate_key',
            target_type: 'user',
            target_id: 'user-1',
            detail: { source: 'ui' },
            batch_id: null,
            created_at: '2026-06-27T09:00:00+00:00',
          },
        ])
      })
    )

    renderAuditPage()

    // Before searching, the prompt is shown and no request has been made.
    expect(screen.getByText('Run a search to view audit logs.')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Filter Actor'), 'admin-1')
    await user.type(screen.getByLabelText('Filter Action'), 'rotate_key')
    await user.type(screen.getByLabelText('Filter Resource'), 'user-1')
    await user.click(screen.getByRole('button', { name: 'Search audit logs' }))

    const row = await screen.findByRole('row', { name: /rotate_key/ })
    expect(within(row).getByText('admin-1')).toBeInTheDocument()
    expect(within(row).getByText('2026-06-27T09:00:00+00:00')).toBeInTheDocument()
    expect(within(row).getByText('user:user-1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Export CSV' }))
    expect(clickSpy).toHaveBeenCalled()
    const exported = exportedBlob as Blob | null
    expect(exported?.type).toBe('text/csv;charset=utf-8')
    expect(exported?.size).toBeGreaterThan(0)

    await user.clear(screen.getByLabelText('Filter Action'))
    await user.type(screen.getByLabelText('Filter Action'), 'missing')
    await user.click(screen.getByRole('button', { name: 'Search audit logs' }))

    await waitFor(() => {
      expect(screen.getByText('No audit logs match the current filters.')).toBeInTheDocument()
    })
  })

  it('resets all filters via the built-in Reset button', async () => {
    const user = userEvent.setup({ delay: null })
    renderAuditPage()

    const actorFilter = screen.getByLabelText('Filter Actor')
    await user.type(actorFilter, 'admin-1')
    expect(actorFilter).toHaveValue('admin-1')

    // Search sits at the far right, just left of Reset.
    const searchButton = screen.getByRole('button', { name: 'Search audit logs' })
    const resetButton = screen.getByRole('button', { name: 'Reset filters' })
    expect(searchButton.compareDocumentPosition(resetButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(searchButton.parentElement).toBe(resetButton.parentElement)

    await user.click(resetButton)
    expect(screen.getByLabelText('Filter Actor')).toHaveValue('')
  })
})

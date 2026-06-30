import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UsersPage } from '@/features/users/page'
import { API_BASE_URL, renderUsers } from '@/features/users/test/render'
import { server } from '@/test/msw/server'

const ADMIN_ME = { email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' }
const USERS = [{ email: 'ann@x.io', id: 'u1', must_reset: false, name: 'Ann', role: 'admin', status: 'active' }]

beforeEach(() => {
  server.use(
    http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
    http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(USERS)),
    http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json([])),
    http.get(`${API_BASE_URL}/admin/im-users/fields`, () => HttpResponse.json({}))
  )
})
afterEach(() => vi.restoreAllMocks())

describe('UsersPage', () => {
  it('shows the users table by default', async () => {
    renderUsers(<UsersPage />)
    expect(await screen.findByText('Ann')).toBeInTheDocument()
  })

  it('switches to the IM identities tab', async () => {
    const user = userEvent.setup()
    renderUsers(<UsersPage />)
    await screen.findByText('Ann')
    await user.click(screen.getByRole('tab', { name: /IM|身份/ }))
    await waitFor(() => expect(screen.getByText(/no IM|暂无/i)).toBeInTheDocument())
  })

  it('swaps the table action button per active tab', async () => {
    const user = userEvent.setup()
    renderUsers(<UsersPage />)
    await screen.findByText('Ann')
    expect(screen.getByRole('button', { name: 'Create user' })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /IM|身份/ }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Add mapping' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Create user' })).not.toBeInTheDocument()
  })

  it('opens the edit dialog with the row user prefilled', async () => {
    const user = userEvent.setup()
    renderUsers(<UsersPage />)
    await screen.findByText('Ann')
    await user.click(screen.getByRole('button', { name: /Ann/ }))
    await user.click(await screen.findByText('Edit'))
    expect(await screen.findByDisplayValue('Ann')).toBeInTheDocument()
  })
})

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, renderUsers } from '@/features/users/test/render'
import { server } from '@/test/msw/server'
import { UsersTable } from './users-table'

const USERS = [
  { email: 'ann@x.io', id: 'u1', must_reset: false, name: 'Ann', role: 'admin', status: 'active' },
  { email: 'bob@x.io', id: 'u2', must_reset: false, name: 'Bob', role: 'viewer', status: 'blocked' },
]

afterEach(() => vi.restoreAllMocks())

describe('UsersTable', () => {
  it('renders user rows', async () => {
    server.use(http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(USERS)))
    renderUsers(<UsersTable canWrite onEdit={() => {}} onManageKeys={() => {}} />)
    expect(await screen.findByText('Ann')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('filters by global search', async () => {
    server.use(http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(USERS)))
    const user = userEvent.setup()
    renderUsers(<UsersTable canWrite onEdit={() => {}} onManageKeys={() => {}} />)
    await screen.findByText('Ann')
    await user.type(screen.getByPlaceholderText('Search…'), 'bob')
    await waitFor(() => expect(screen.queryByText('Ann')).not.toBeInTheDocument())
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })
})

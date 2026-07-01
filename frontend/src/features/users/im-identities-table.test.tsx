import { screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, renderUsers } from '@/features/users/test/render'
import { server } from '@/test/msw/server'
import { ImIdentitiesTable } from './im-identities-table'

const IM_USERS = [
  {
    allowed: true,
    id: 1,
    platform: 'slack',
    platform_user_id: 'U1',
    status: 'active',
    user_email: null,
    user_id: 'u1',
    user_name: 'Ann',
  },
  {
    allowed: false,
    id: 2,
    platform: 'telegram',
    platform_user_id: 'T2',
    status: 'blocked',
    user_email: null,
    user_id: 'u2',
    user_name: 'Bob',
  },
]

afterEach(() => vi.restoreAllMocks())

describe('ImIdentitiesTable', () => {
  it('renders IM identity rows', async () => {
    server.use(http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json(IM_USERS)))
    renderUsers(<ImIdentitiesTable canWrite users={[]} />)
    expect(await screen.findByText('U1')).toBeInTheDocument()
    expect(screen.getByText('T2')).toBeInTheDocument()
  })
})

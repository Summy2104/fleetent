import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, renderUsers } from '@/features/users/test/render'
import { server } from '@/test/msw/server'
import { UserRowActions } from './user-row-actions'

const USER = { email: 'a@b.c', id: 'u1', must_reset: false, name: 'Ann', role: 'admin', status: 'active' }

afterEach(() => vi.restoreAllMocks())

describe('UserRowActions', () => {
  it('renders nothing for viewers', () => {
    const { container } = renderUsers(
      <UserRowActions canWrite={false} onEdit={() => {}} onManageKeys={() => {}} user={USER} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('invokes onEdit from the menu', async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    renderUsers(<UserRowActions canWrite onEdit={onEdit} onManageKeys={() => {}} user={USER} />)
    await user.click(screen.getByRole('button', { name: /Ann/ }))
    await user.click(await screen.findByText('Edit'))
    expect(onEdit).toHaveBeenCalledWith(USER)
  })

  it('confirms before deleting', async () => {
    const user = userEvent.setup()
    const deleted = vi.fn()
    server.use(
      http.delete(`${API_BASE_URL}/admin/users/u1`, () => {
        deleted()
        return new HttpResponse(null, { status: 204 })
      })
    )
    renderUsers(<UserRowActions canWrite onEdit={() => {}} onManageKeys={() => {}} user={USER} />)
    await user.click(screen.getByRole('button', { name: /Ann/ }))
    await user.click(await screen.findByText('Delete'))
    await user.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleted).toHaveBeenCalled())
  })
})

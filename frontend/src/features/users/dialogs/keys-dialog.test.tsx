import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import type { UserKey, UserListItem } from '@/features/users/api'
import { KeysDialog } from '@/features/users/dialogs/keys-dialog'
import { API_BASE_URL, renderUsers } from '@/features/users/test/render'
import { server } from '@/test/msw/server'

const targetUser: UserListItem = {
  email: 'a@b.test',
  id: 'u1',
  must_reset: false,
  name: 'Alice',
  role: 'admin',
  status: 'active',
}

function key(over: Partial<UserKey> = {}): UserKey {
  return {
    created_at: '2026-01-01T00:00:00Z',
    id: 1,
    masked: 'ma-****abcd',
    note: null,
    prefix: 'ma-',
    revoked_at: null,
    scope: ['*'],
    ...over,
  }
}

function stubKeys(keys: UserKey[]): void {
  server.use(http.get(`${API_BASE_URL}/admin/users/:id/keys`, () => HttpResponse.json(keys)))
}

function renderKeys(props: { canWrite?: boolean; onSecret?: (secret: string) => void } = {}): {
  onSecret: (secret: string) => void
} {
  const onSecret = props.onSecret ?? vi.fn()
  renderUsers(
    <KeysDialog canWrite={props.canWrite ?? true} onOpenChange={vi.fn()} onSecret={onSecret} open user={targetUser} />
  )
  return { onSecret }
}

describe('KeysDialog', () => {
  it('lists keys, flags revoked ones, and only offers revoke on active keys', async () => {
    stubKeys([
      key({ id: 1, masked: 'ma-active' }),
      key({ id: 2, masked: 'ma-old', revoked_at: '2026-02-01T00:00:00Z' }),
    ])
    renderKeys()

    expect(await screen.findByText('ma-active')).toBeInTheDocument()
    expect(screen.getByText('ma-old')).toBeInTheDocument()
    expect(screen.getByText('revoked')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Revoke key 1' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Revoke key 2' })).not.toBeInTheDocument()
  })

  it('shows an empty state when the user has no keys', async () => {
    stubKeys([])
    renderKeys()

    expect(await screen.findByText('No API keys for this user.')).toBeInTheDocument()
  })

  it('hides issue/rotate/revoke controls for read-only viewers', async () => {
    stubKeys([key({ id: 1 })])
    renderKeys({ canWrite: false })

    expect(await screen.findByText('ma-****abcd')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Issue key' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rotate key' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Revoke key 1' })).not.toBeInTheDocument()
  })

  it('rotates a key and surfaces the new plaintext once', async () => {
    const user = userEvent.setup({ delay: null })
    stubKeys([key()])
    server.use(
      http.post(`${API_BASE_URL}/admin/users/:id/rotate-key`, () =>
        HttpResponse.json({ api_key_plaintext_once: 'ma-rotated', user: targetUser })
      )
    )
    const { onSecret } = renderKeys()

    await user.click(await screen.findByRole('button', { name: 'Rotate key' }))
    await waitFor(() => expect(onSecret).toHaveBeenCalledWith('ma-rotated'))
  })

  it('issues a new key with the parsed scope and returns its plaintext', async () => {
    const user = userEvent.setup({ delay: null })
    stubKeys([])
    let body: unknown
    server.use(
      http.post(`${API_BASE_URL}/admin/users/:id/keys`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ key: key(), plaintext: 'ma-new' })
      })
    )
    const { onSecret } = renderKeys()

    await user.click(await screen.findByRole('button', { name: 'Issue key' }))
    const issueDialog = await screen.findByRole('dialog', { name: /Issue key for/ })
    const scope = within(issueDialog).getByLabelText('Key scope')
    await user.clear(scope)
    await user.type(scope, 'read, write')
    await user.click(within(issueDialog).getByRole('button', { name: 'Issue key' }))

    await waitFor(() => expect(onSecret).toHaveBeenCalledWith('ma-new'))
    expect(body).toEqual({ scope: ['read', 'write'] })
  })

  it('revokes a key after confirmation', async () => {
    const user = userEvent.setup({ delay: null })
    stubKeys([key({ id: 5, masked: 'ma-x' })])
    let revokedId: number | null = null
    server.use(
      http.delete(`${API_BASE_URL}/admin/keys/:keyId`, ({ params }) => {
        revokedId = Number(params.keyId)
        return HttpResponse.json({})
      })
    )
    renderKeys()

    await user.click(await screen.findByRole('button', { name: 'Revoke key 5' }))
    const confirm = await screen.findByRole('alertdialog')
    await user.click(within(confirm).getByRole('button', { name: 'Revoke key 5' }))
    await waitFor(() => expect(revokedId).toBe(5))
  })
})

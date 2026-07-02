import type { ReactNode } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import {
  useBindImUserMutation,
  useBlockImUserMutation,
  useBlockUserMutation,
  useCreateImMappingMutation,
  useCreateKeyMutation,
  useCreateServicePrincipalMutation,
  useCreateUserMutation,
  useDeleteImUserMutation,
  useDeleteUserMutation,
  useImIdentityFieldsQuery,
  useImUsersQuery,
  useInitiateLinkMutation,
  useResetPasswordMutation,
  useRestoreImUserMutation,
  useRevokeKeyMutation,
  useRotateKeyMutation,
  useSetRoleMutation,
  useUnblockUserMutation,
  useUnlinkIdentityMutation,
  useUpdateImUserMutation,
  useUpdateUserMutation,
  useUserKeysQuery,
  useUsersQuery,
} from '@/features/users/api'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

type UserRecord = {
  email: string | null
  id: string
  must_reset: boolean
  name: string
  role: string
  status: string
}

type KeyRecord = {
  created_at: string
  id: number
  masked: string
  note: string | null
  prefix: string
  revoked_at: string | null
  scope: string[]
}

type ImUserRecord = {
  allowed: boolean
  id: number
  metadata?: Record<string, unknown>
  platform: string
  platform_user_id: string
  status: string
  user_id: string
}

function renderWithProviders(ui: ReactNode): void {
  render(
    <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
      <AppQueryProvider>{ui}</AppQueryProvider>
    </AuthProvider>
  )
}

function UsersApiProbe(): JSX.Element {
  const users = useUsersQuery()
  const keys = useUserKeysQuery('u1')
  const imUsers = useImUsersQuery()
  const imFields = useImIdentityFieldsQuery()
  const createUser = useCreateUserMutation()
  const createServicePrincipal = useCreateServicePrincipalMutation()
  const updateUser = useUpdateUserMutation('u1')
  const setRole = useSetRoleMutation('u1')
  const blockUser = useBlockUserMutation('u1')
  const unblockUser = useUnblockUserMutation('u1')
  const resetPassword = useResetPasswordMutation('u1')
  const deleteUser = useDeleteUserMutation('u2')
  const createKey = useCreateKeyMutation('u1')
  const createImMapping = useCreateImMappingMutation()
  const rotateKey = useRotateKeyMutation('u1')
  const revokeKey = useRevokeKeyMutation('u1')
  const bindImUser = useBindImUserMutation(7)
  const blockImUser = useBlockImUserMutation(7)
  const restoreImUser = useRestoreImUserMutation(7)
  const updateImUser = useUpdateImUserMutation(7)
  const deleteImUser = useDeleteImUserMutation(7)
  const initiateLink = useInitiateLinkMutation()
  const unlinkIdentity = useUnlinkIdentityMutation()

  return (
    <section>
      <button
        onClick={() =>
          createUser.mutate({
            email: 'bob@fleetent.test',
            name: 'Bob',
            password: 'pw',
            role: 'viewer',
          })
        }
        type="button"
      >
        create user
      </button>
      <button
        onClick={() => {
          void createServicePrincipal.mutateAsync({ name: 'svc-ingest' }).then((result) => {
            window.sessionStorage.setItem('service-principal-key', result.api_key_plaintext_once)
          })
        }}
        type="button"
      >
        create service principal
      </button>
      <button
        onClick={() =>
          updateUser.mutate({
            email: 'alice+new@fleetent.test',
            name: 'Alice Updated',
          })
        }
        type="button"
      >
        update user
      </button>
      <button onClick={() => setRole.mutate({ role: 'admin' })} type="button">
        set role
      </button>
      <button onClick={() => blockUser.mutate({ reason: 'abuse' })} type="button">
        block user
      </button>
      <button onClick={() => unblockUser.mutate()} type="button">
        unblock user
      </button>
      <button onClick={() => resetPassword.mutate({ new_password: 'pw2' })} type="button">
        reset password
      </button>
      <button onClick={() => deleteUser.mutate()} type="button">
        delete user
      </button>
      <button
        onClick={() => {
          void createKey.mutateAsync({ note: 'ops', scope: ['ops-bot'] }).then((result) => {
            window.sessionStorage.setItem('issued-key', result.plaintext)
          })
        }}
        type="button"
      >
        create key
      </button>
      <button
        onClick={() => {
          void rotateKey.mutateAsync().then((result) => {
            window.sessionStorage.setItem('rotated-key', result.api_key_plaintext_once)
          })
        }}
        type="button"
      >
        rotate key
      </button>
      <button onClick={() => revokeKey.mutate(1)} type="button">
        revoke key
      </button>
      <button
        onClick={() =>
          createImMapping.mutate({
            platform: 'telegram',
            platform_user_id: 'T007',
            user_id: 'u2',
          })
        }
        type="button"
      >
        create im mapping
      </button>
      <button onClick={() => bindImUser.mutate({ user_id: 'u2' })} type="button">
        bind im user
      </button>
      <button
        onClick={() =>
          updateImUser.mutate({
            metadata: { display_name: 'Alice Slack', notes: 'vip' },
            platform_user_id: 'U007-NEW',
          })
        }
        type="button"
      >
        update im user
      </button>
      <button onClick={() => deleteImUser.mutate()} type="button">
        delete im user
      </button>
      <button
        onClick={() => {
          void initiateLink.mutateAsync().then((result) => {
            window.sessionStorage.setItem('link-code', `${result.code}:${result.expires_at}`)
          })
        }}
        type="button"
      >
        initiate link
      </button>
      <button onClick={() => unlinkIdentity.mutate({ platform: 'slack', platform_user_id: 'U007-NEW' })} type="button">
        unlink identity
      </button>
      <button onClick={() => blockImUser.mutate({ reason: 'fraud' })} type="button">
        block im user
      </button>
      <button onClick={() => restoreImUser.mutate({ reason: 'verified' })} type="button">
        restore im user
      </button>

      <div data-testid="users">
        {users.data?.map((user) => `${user.id}:${user.name}:${user.role}:${user.status}`).join('|')}
      </div>
      <div data-testid="keys">{keys.data?.map((key) => `${key.id}:${key.prefix}:${key.masked}`).join('|')}</div>
      <div data-testid="im-users">
        {imUsers.data
          ?.map((user) => `${user.id}:${user.platform_user_id}:${user.user_id}:${user.status}:${user.allowed}`)
          .join('|')}
      </div>
      <div data-testid="im-fields">{imFields.data?.slack?.map((field) => `${field.key}:${field.label}`).join('|')}</div>
    </section>
  )
}

describe('users api hooks', () => {
  it('refreshes users and keys after CRUD, role, block, rotate, revoke, and password actions', async () => {
    const user = userEvent.setup({ delay: null })
    let resetCalls = 0
    let users: UserRecord[] = [
      {
        email: 'alice@fleetent.test',
        id: 'u1',
        must_reset: false,
        name: 'Alice',
        role: 'viewer',
        status: 'active',
      },
      {
        email: 'carol@fleetent.test',
        id: 'u2',
        must_reset: false,
        name: 'Carol',
        role: 'viewer',
        status: 'active',
      },
    ]
    let keys: KeyRecord[] = [
      {
        created_at: '2026-06-21T10:00:00Z',
        id: 1,
        masked: 'ma-u1...abcd',
        note: null,
        prefix: 'ma-u1',
        revoked_at: null,
        scope: ['*'],
      },
    ]

    server.use(
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(users)),
      http.post(`${API_BASE_URL}/admin/users`, async ({ request }) => {
        const body = (await request.json()) as {
          email: string
          name: string
          password: string
          role: string
        }
        users = [
          ...users,
          {
            email: body.email,
            id: 'u3',
            must_reset: false,
            name: body.name,
            role: body.role,
            status: 'active',
          },
        ]
        return HttpResponse.json(users[2], { status: 201 })
      }),
      http.post(`${API_BASE_URL}/admin/service-principals`, async ({ request }) => {
        expect(await request.json()).toEqual({ name: 'svc-ingest' })
        const created = {
          email: null,
          id: 'svc1',
          must_reset: false,
          name: 'svc-ingest',
          role: 'viewer',
          status: 'active',
        }
        users = [...users, created]
        return HttpResponse.json(
          { user: created, api_key_plaintext_once: 'ma-service-principal-secret' },
          { status: 201 }
        )
      }),
      http.patch(`${API_BASE_URL}/admin/users/u1`, async ({ request }) => {
        const body = (await request.json()) as { email: string; name: string }
        users = users.map((item) => (item.id === 'u1' ? { ...item, ...body } : item))
        return HttpResponse.json(users[0])
      }),
      http.patch(`${API_BASE_URL}/admin/users/u1/role`, async ({ request }) => {
        const body = (await request.json()) as { role: string }
        users = users.map((item) => (item.id === 'u1' ? { ...item, role: body.role } : item))
        return HttpResponse.json(users[0])
      }),
      http.post(`${API_BASE_URL}/admin/users/u1/block`, async ({ request }) => {
        expect((await request.json()) as { reason: string }).toEqual({ reason: 'abuse' })
        users = users.map((item) => (item.id === 'u1' ? { ...item, status: 'blocked' } : item))
        return HttpResponse.json({ status: 'blocked' })
      }),
      http.post(`${API_BASE_URL}/admin/users/u1/unblock`, () => {
        users = users.map((item) => (item.id === 'u1' ? { ...item, status: 'active' } : item))
        return HttpResponse.json({ status: 'active' })
      }),
      http.post(`${API_BASE_URL}/admin/users/u1/password`, async ({ request }) => {
        expect((await request.json()) as { new_password: string }).toEqual({ new_password: 'pw2' })
        resetCalls += 1
        return HttpResponse.json({ status: 'password_reset' })
      }),
      http.delete(`${API_BASE_URL}/admin/users/u2`, () => {
        users = users.filter((item) => item.id !== 'u2')
        return new HttpResponse(null, { status: 204 })
      }),
      http.get(`${API_BASE_URL}/admin/users/u1/keys`, () => HttpResponse.json(keys)),
      http.post(`${API_BASE_URL}/admin/users/u1/keys`, async ({ request }) => {
        expect((await request.json()) as { note: string; scope: string[] }).toEqual({
          note: 'ops',
          scope: ['ops-bot'],
        })
        keys = [
          ...keys,
          {
            created_at: '2026-06-21T10:05:00Z',
            id: 2,
            masked: 'ma-u1...efgh',
            note: 'ops',
            prefix: 'ma-u1',
            revoked_at: null,
            scope: ['ops-bot'],
          },
        ]
        return HttpResponse.json(
          {
            key: keys[1],
            plaintext: 'ma-issued-secret',
          },
          { status: 201 }
        )
      }),
      http.post(`${API_BASE_URL}/admin/users/u1/rotate-key`, () => {
        keys = [
          {
            created_at: '2026-06-21T10:06:00Z',
            id: 3,
            masked: 'ma-u1...ijkl',
            note: null,
            prefix: 'ma-u1',
            revoked_at: null,
            scope: ['*'],
          },
        ]
        return HttpResponse.json({
          api_key_plaintext_once: 'ma-rotated-secret',
          user: users[0],
        })
      }),
      http.delete(`${API_BASE_URL}/admin/keys/1`, () => {
        keys = []
        return new HttpResponse(null, { status: 204 })
      }),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/im-users/fields`, () => HttpResponse.json({}))
    )

    renderWithProviders(<UsersApiProbe />)
    expect(await screen.findByText(/u1:Alice:viewer:active/)).toBeInTheDocument()
    expect(screen.getByText(/1:ma-u1:ma-u1\.\.\.abcd/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'create user' }))
    await waitFor(() => {
      expect(screen.getByText(/u3:Bob:viewer:active/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'create service principal' }))
    await waitFor(() => {
      expect(screen.getByText(/svc1:svc-ingest:viewer:active/)).toBeInTheDocument()
      expect(window.sessionStorage.getItem('service-principal-key')).toBe('ma-service-principal-secret')
    })

    await user.click(screen.getByRole('button', { name: 'update user' }))
    await waitFor(() => {
      expect(screen.getByText(/u1:Alice Updated:viewer:active/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'set role' }))
    await waitFor(() => {
      expect(screen.getByText(/u1:Alice Updated:admin:active/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'block user' }))
    await waitFor(() => {
      expect(screen.getByText(/u1:Alice Updated:admin:blocked/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'unblock user' }))
    await waitFor(() => {
      expect(screen.getByText(/u1:Alice Updated:admin:active/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'reset password' }))
    await waitFor(() => {
      expect(resetCalls).toBe(1)
    })

    await user.click(screen.getByRole('button', { name: 'delete user' }))
    await waitFor(() => {
      expect(screen.getByTestId('users')).not.toHaveTextContent('u2:Carol')
    })

    await user.click(screen.getByRole('button', { name: 'create key' }))
    await waitFor(() => {
      expect(screen.getByText(/2:ma-u1:ma-u1\.\.\.efgh/)).toBeInTheDocument()
      expect(window.sessionStorage.getItem('issued-key')).toBe('ma-issued-secret')
    })

    await user.click(screen.getByRole('button', { name: 'rotate key' }))
    await waitFor(() => {
      expect(screen.getByText(/3:ma-u1:ma-u1\.\.\.ijkl/)).toBeInTheDocument()
      expect(window.sessionStorage.getItem('rotated-key')).toBe('ma-rotated-secret')
    })

    await user.click(screen.getByRole('button', { name: 'revoke key' }))
    await waitFor(() => {
      expect(screen.getByTestId('keys')).toBeEmptyDOMElement()
    })
  })

  it('refreshes IM identities after create, bind, block, and restore actions', async () => {
    const user = userEvent.setup({ delay: null })
    let imUsers: ImUserRecord[] = [
      {
        allowed: true,
        id: 7,
        platform: 'slack',
        platform_user_id: 'U007',
        status: 'active',
        user_id: 'u1',
      },
    ]

    server.use(
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/users/u1/keys`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json(imUsers)),
      http.get(`${API_BASE_URL}/admin/im-users/fields`, () =>
        HttpResponse.json({
          slack: [
            { key: 'display_name', label: 'Display name' },
            { key: 'notes', label: 'Notes', multiline: true },
          ],
        })
      ),
      http.post(`${API_BASE_URL}/admin/im-identities`, async ({ request }) => {
        expect((await request.json()) as { platform: string; platform_user_id: string; user_id: string }).toEqual({
          platform: 'telegram',
          platform_user_id: 'T007',
          user_id: 'u2',
        })
        imUsers = [
          ...imUsers,
          {
            allowed: true,
            id: 8,
            platform: 'telegram',
            platform_user_id: 'T007',
            status: 'active',
            user_id: 'u2',
          },
        ]
        return HttpResponse.json(
          {
            created_at: '2026-06-27T10:00:00Z',
            id: 8,
            platform: 'telegram',
            platform_user_id: 'T007',
            user_email: null,
            user_id: 'u2',
            user_name: 'Bob',
          },
          { status: 201 }
        )
      }),
      http.post(`${API_BASE_URL}/admin/im-users/7/bind`, async ({ request }) => {
        expect((await request.json()) as { user_id: string }).toEqual({ user_id: 'u2' })
        imUsers = imUsers.map((item) => (item.id === 7 ? { ...item, user_id: 'u2' } : item))
        return HttpResponse.json({ status: 'bound' })
      }),
      http.patch(`${API_BASE_URL}/admin/im-users/7`, async ({ request }) => {
        expect(await request.json()).toEqual({
          metadata: { display_name: 'Alice Slack', notes: 'vip' },
          platform_user_id: 'U007-NEW',
        })
        imUsers = imUsers.map((item) =>
          item.id === 7
            ? {
                ...item,
                metadata: { display_name: 'Alice Slack', notes: 'vip' },
                platform_user_id: 'U007-NEW',
              }
            : item
        )
        return HttpResponse.json({ status: 'updated' })
      }),
      http.delete(`${API_BASE_URL}/admin/im-users/7`, () => {
        imUsers = imUsers.filter((item) => item.id !== 7)
        return new HttpResponse(null, { status: 204 })
      }),
      http.post(`${API_BASE_URL}/admin/link/initiate`, async ({ request }) => {
        expect(await request.text()).toBe('')
        return HttpResponse.json({
          code: 'link-code-123',
          expires_at: '2026-06-27T10:10:00+00:00',
        })
      }),
      http.post(`${API_BASE_URL}/admin/link/unlink`, async ({ request }) => {
        expect(await request.json()).toEqual({ platform: 'slack', platform_user_id: 'U007-NEW' })
        imUsers = imUsers.filter((item) => item.platform_user_id !== 'U007-NEW')
        return HttpResponse.json({ status: 'unlinked' })
      }),
      http.post(`${API_BASE_URL}/admin/im-users/7/block`, async ({ request }) => {
        expect((await request.json()) as { reason: string }).toEqual({ reason: 'fraud' })
        imUsers = imUsers.map((item) => (item.id === 7 ? { ...item, allowed: false, status: 'blocked' } : item))
        return HttpResponse.json({ allowed: false })
      }),
      http.post(`${API_BASE_URL}/admin/im-users/7/restore`, async ({ request }) => {
        expect((await request.json()) as { reason: string }).toEqual({ reason: 'verified' })
        imUsers = imUsers.map((item) => (item.id === 7 ? { ...item, allowed: true, status: 'active' } : item))
        return HttpResponse.json({ allowed: true })
      })
    )

    renderWithProviders(<UsersApiProbe />)
    expect(await screen.findByText(/7:U007:u1:active:true/)).toBeInTheDocument()
    expect(screen.getByText(/display_name:Display name/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'create im mapping' }))
    await waitFor(() => {
      expect(screen.getByText(/8:T007:u2:active:true/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'bind im user' }))
    await waitFor(() => {
      expect(screen.getByText(/7:U007:u2:active:true/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'update im user' }))
    await waitFor(() => {
      expect(screen.getByText(/7:U007-NEW:u2:active:true/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'initiate link' }))
    await waitFor(() => {
      expect(window.sessionStorage.getItem('link-code')).toBe('link-code-123:2026-06-27T10:10:00+00:00')
    })

    await user.click(screen.getByRole('button', { name: 'block im user' }))
    await waitFor(() => {
      expect(screen.getByText(/7:U007-NEW:u2:blocked:false/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'restore im user' }))
    await waitFor(() => {
      expect(screen.getByText(/7:U007-NEW:u2:active:true/)).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'unlink identity' }))
    await waitFor(() => {
      expect(screen.getByTestId('im-users')).not.toHaveTextContent('7:U007-NEW')
    })

    await user.click(screen.getByRole('button', { name: 'delete im user' }))
    await waitFor(() => {
      expect(screen.getByTestId('im-users')).not.toHaveTextContent('7:U007-NEW')
    })
  })
})

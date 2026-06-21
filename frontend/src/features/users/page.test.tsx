import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { UsersPage } from '@/features/users/page';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

type UserRecord = {
  email: string | null;
  id: string;
  must_reset: boolean;
  name: string;
  role: string;
  status: string;
};

type KeyRecord = {
  created_at: string;
  id: number;
  masked: string;
  note: string | null;
  prefix: string;
  revoked_at: string | null;
  scope: string[];
};

type ImUserRecord = {
  allowed: boolean;
  id: number;
  platform: string;
  platform_user_id: string;
  status: string;
  user_id: string;
};

function renderUsersPage(): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken="session-token"
    >
      <AppQueryProvider>
        <UsersPage />
      </AppQueryProvider>
    </AuthProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('users page parity baseline', () => {
  it('supports user CRUD, role changes, block/unblock, delete, and one-time key secrets', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    let keyListCalls = 0;
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
    ];
    let keysByUser: Record<string, KeyRecord[]> = {
      u1: [
        {
          created_at: '2026-06-21T10:00:00Z',
          id: 10,
          masked: 'ma-u1...abcd',
          note: null,
          prefix: 'ma-u1',
          revoked_at: null,
          scope: ['*'],
        },
      ],
      u2: [],
      u3: [],
    };

    server.use(
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(users)),
      http.post(`${API_BASE_URL}/admin/users`, async ({ request }) => {
        const body = (await request.json()) as {
          email: string;
          must_reset: boolean;
          name: string;
          password: string;
          role: string;
        };
        const created = {
          email: body.email,
          id: 'u3',
          must_reset: body.must_reset,
          name: body.name,
          role: body.role,
          status: 'active',
        };
        users = [...users, created];
        return HttpResponse.json(created, { status: 201 });
      }),
      http.patch(`${API_BASE_URL}/admin/users/u1`, async ({ request }) => {
        const body = (await request.json()) as { email: string; name: string };
        users = users.map((item) => (item.id === 'u1' ? { ...item, ...body } : item));
        return HttpResponse.json(users[0]);
      }),
      http.patch(`${API_BASE_URL}/admin/users/u1/role`, async ({ request }) => {
        const body = (await request.json()) as { role: string };
        users = users.map((item) => (item.id === 'u1' ? { ...item, role: body.role } : item));
        return HttpResponse.json(users[0]);
      }),
      http.post(`${API_BASE_URL}/admin/users/u1/block`, async ({ request }) => {
        expect((await request.json()) as { reason: string }).toEqual({ reason: 'test reason' });
        users = users.map((item) => (item.id === 'u1' ? { ...item, status: 'blocked' } : item));
        return HttpResponse.json({ status: 'blocked' });
      }),
      http.post(`${API_BASE_URL}/admin/users/u1/unblock`, () => {
        users = users.map((item) => (item.id === 'u1' ? { ...item, status: 'active' } : item));
        return HttpResponse.json({ status: 'active' });
      }),
      http.post(`${API_BASE_URL}/admin/users/u1/password`, async ({ request }) => {
        expect((await request.json()) as { new_password: string }).toEqual({ new_password: 'pw-new' });
        return HttpResponse.json({ status: 'password_reset' });
      }),
      http.delete(`${API_BASE_URL}/admin/users/u2`, () => {
        users = users.filter((item) => item.id !== 'u2');
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(`${API_BASE_URL}/admin/users/:userId/keys`, ({ params }) => {
        keyListCalls += 1;
        return HttpResponse.json(keysByUser[String(params.userId)] ?? []);
      }),
      http.post(`${API_BASE_URL}/admin/users/u1/keys`, async ({ request }) => {
        expect((await request.json()) as { note: string; scope: string[] }).toEqual({
          note: 'ops',
          scope: ['ops-bot'],
        });
        const key = {
          created_at: '2026-06-21T10:05:00Z',
          id: 11,
          masked: 'ma-u1...efgh',
          note: 'ops',
          prefix: 'ma-u1',
          revoked_at: null,
          scope: ['ops-bot'],
        };
        keysByUser = { ...keysByUser, u1: [...keysByUser.u1, key] };
        return HttpResponse.json({ key, plaintext: 'ma-created-secret' }, { status: 201 });
      }),
      http.post(`${API_BASE_URL}/admin/users/u1/rotate-key`, () => {
        const rotated = {
          created_at: '2026-06-21T10:06:00Z',
          id: 12,
          masked: 'ma-u1...ijkl',
          note: null,
          prefix: 'ma-u1',
          revoked_at: null,
          scope: ['*'],
        };
        keysByUser = { ...keysByUser, u1: [rotated] };
        return HttpResponse.json({
          api_key_plaintext_once: 'ma-rotated-secret',
          user: users[0],
        });
      }),
      http.delete(`${API_BASE_URL}/admin/keys/12`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        keysByUser = { ...keysByUser, u1: [] };
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json([]))
    );

    renderUsersPage();
    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument();
    expect(await screen.findByText('Alice')).toBeInTheDocument();
    expect(await screen.findByText('ma-u1...abcd')).toBeInTheDocument();
    expect(screen.queryByText('ma-created-secret')).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('User name'), 'Bob');
    await user.type(screen.getByLabelText('Email'), 'bob@fleetent.test');
    await user.type(screen.getByLabelText('Password'), 'pw');
    await user.selectOptions(screen.getByLabelText('Role'), 'viewer');
    await user.click(screen.getByLabelText('Must reset password on first login'));
    await user.click(screen.getByRole('button', { name: 'Create user' }));
    expect(await screen.findByText('Bob')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit Alice' }));
    await user.clear(screen.getByLabelText('User name'));
    await user.type(screen.getByLabelText('User name'), 'Alice Updated');
    await user.clear(screen.getByLabelText('Email'));
    await user.type(screen.getByLabelText('Email'), 'alice+new@fleetent.test');
    await user.selectOptions(screen.getByLabelText('Role'), 'admin');
    await user.type(screen.getByLabelText('Reset password'), 'pw-new');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => {
      const card = screen.getByTestId('user-card-u1');
      expect(within(card).getByText('Alice Updated')).toBeInTheDocument();
      expect(within(card).getByText('admin')).toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText('Block reason'));
    await user.type(screen.getByLabelText('Block reason'), 'test reason');
    await user.click(screen.getByRole('button', { name: 'Block Alice Updated' }));
    await waitFor(() => {
      expect(within(screen.getByTestId('user-card-u1')).getByText('blocked')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Unblock Alice Updated' }));
    await waitFor(() => {
      expect(within(screen.getByTestId('user-card-u1')).getByText('active')).toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText('Key note'));
    await user.type(screen.getByLabelText('Key note'), 'ops');
    await user.clear(screen.getByLabelText('Key scope'));
    await user.type(screen.getByLabelText('Key scope'), 'ops-bot');
    await user.click(screen.getByRole('button', { name: 'Issue key for Alice Updated' }));
    expect(await screen.findByText('ma-created-secret')).toBeInTheDocument();
    expect(screen.queryByText('ma-issued-secret')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss new secret' }));
    expect(screen.queryByText('ma-created-secret')).not.toBeInTheDocument();
    expect(screen.getByText('ma-u1...efgh')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Rotate key for Alice Updated' }));
    expect(await screen.findByText('ma-rotated-secret')).toBeInTheDocument();
    expect(screen.getByText('ma-u1...ijkl')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss new secret' }));
    expect(screen.queryByText('ma-rotated-secret')).not.toBeInTheDocument();
    expect(screen.queryByText('ma-created-secret')).not.toBeInTheDocument();
    expect(screen.queryByText('ma-u1...abcd')).not.toBeInTheDocument();
    expect(keyListCalls).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: 'Revoke key 12' }));
    await waitFor(() => {
      expect(screen.queryByText('ma-u1...ijkl')).not.toBeInTheDocument();
    });
    expect(confirmSpy).toHaveBeenCalledWith('Revoke key ma-u1...ijkl?');

    await user.click(screen.getByRole('button', { name: 'Delete Carol' }));
    await waitFor(() => {
      expect(screen.queryByText('Carol')).not.toBeInTheDocument();
    });
  });

  it('supports IM identity bind, block, and restore flows', async () => {
    const user = userEvent.setup();
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
        email: 'bob@fleetent.test',
        id: 'u2',
        must_reset: false,
        name: 'Bob',
        role: 'viewer',
        status: 'active',
      },
    ];
    let imUsers: ImUserRecord[] = [
      {
        allowed: true,
        id: 7,
        platform: 'slack',
        platform_user_id: 'U-ALICE',
        status: 'active',
        user_id: 'u1',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(users)),
      http.get(`${API_BASE_URL}/admin/users/:userId/keys`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json(imUsers)),
      http.post(`${API_BASE_URL}/admin/im-users/7/bind`, async ({ request }) => {
        expect((await request.json()) as { user_id: string }).toEqual({ user_id: 'u2' });
        imUsers = imUsers.map((item) => (item.id === 7 ? { ...item, user_id: 'u2' } : item));
        return HttpResponse.json({ status: 'bound' });
      }),
      http.post(`${API_BASE_URL}/admin/im-users/7/block`, async ({ request }) => {
        expect((await request.json()) as { reason: string }).toEqual({ reason: 'fraud' });
        imUsers = imUsers.map((item) =>
          item.id === 7 ? { ...item, allowed: false, status: 'blocked' } : item
        );
        users = users.map((item) => (item.id === 'u2' ? { ...item, status: 'blocked' } : item));
        return HttpResponse.json({ allowed: false });
      }),
      http.post(`${API_BASE_URL}/admin/im-users/7/restore`, async ({ request }) => {
        expect((await request.json()) as { reason: string }).toEqual({ reason: 'restored' });
        imUsers = imUsers.map((item) =>
          item.id === 7 ? { ...item, allowed: true, status: 'active' } : item
        );
        users = users.map((item) => (item.id === 'u2' ? { ...item, status: 'active' } : item));
        return HttpResponse.json({ allowed: true });
      })
    );

    renderUsersPage();
    expect(await screen.findByText('U-ALICE')).toBeInTheDocument();

    const row = screen.getByTestId('im-user-7');
    await user.selectOptions(within(row).getByLabelText('Bind to user'), 'u2');
    await user.click(within(row).getByRole('button', { name: 'Bind identity' }));
    await waitFor(() => {
      expect(
        within(row).getByText((content, element) => element?.tagName === 'SPAN' && content === 'u2')
      ).toBeInTheDocument();
    });

    await user.clear(within(row).getByLabelText('IM reason'));
    await user.type(within(row).getByLabelText('IM reason'), 'fraud');
    await user.click(within(row).getByRole('button', { name: 'Block identity' }));
    await waitFor(() => {
      expect(within(row).getByText('blocked')).toBeInTheDocument();
      expect(within(row).getByText('not allowed')).toBeInTheDocument();
    });

    await user.clear(within(row).getByLabelText('IM reason'));
    await user.type(within(row).getByLabelText('IM reason'), 'restored');
    await user.click(within(row).getByRole('button', { name: 'Restore identity' }));
    await waitFor(() => {
      expect(within(row).getByText('active')).toBeInTheDocument();
      expect(within(row).getByText('allowed')).toBeInTheDocument();
    });
  });
});

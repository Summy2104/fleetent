import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { UsersPage } from '@/features/users/page';
import { I18nProvider } from '@/i18n';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

const ADMIN_ME = { email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' };

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
  metadata?: Record<string, unknown>;
  platform: string;
  platform_user_id: string;
  status: string;
  user_id: string;
};

function renderUsersPage(): void {
  render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <AppQueryProvider>
          <UsersPage />
        </AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

/** Pick an option from a Radix Select trigger inside a given scope. */
async function selectOption(
  user: ReturnType<typeof userEvent.setup>,
  trigger: HTMLElement,
  optionName: string
): Promise<void> {
  await user.click(trigger);
  await user.click(await screen.findByRole('option', { name: optionName }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('users page parity baseline', () => {
  it('supports user CRUD, role changes, block/unblock, delete, and one-time key secrets', async () => {
    const user = userEvent.setup({ delay: null });
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
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
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

    // ── Create a new user via the create dialog ──────────────────────────────
    await user.click(screen.getByRole('button', { name: 'Create user' }));
    let dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('User name'), 'Bob');
    await user.type(within(dialog).getByLabelText('Email'), 'bob@fleetent.test');
    await user.type(within(dialog).getByLabelText('Password'), 'pw');
    await selectOption(user, within(dialog).getByLabelText('Role'), 'viewer');
    await user.click(within(dialog).getByLabelText('Must reset password on first login'));
    await user.click(within(dialog).getByRole('button', { name: 'Create user' }));
    expect(await screen.findByText('Bob')).toBeInTheDocument();

    // ── Edit Alice: name, email, role, and reset password ────────────────────
    await user.click(screen.getByRole('button', { name: 'Actions for Alice' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Edit' }));
    dialog = await screen.findByRole('dialog');
    await user.clear(within(dialog).getByLabelText('User name'));
    await user.type(within(dialog).getByLabelText('User name'), 'Alice Updated');
    await user.clear(within(dialog).getByLabelText('Email'));
    await user.type(within(dialog).getByLabelText('Email'), 'alice+new@fleetent.test');
    await selectOption(user, within(dialog).getByLabelText('Role'), 'admin');
    await user.type(within(dialog).getByLabelText('Reset password'), 'pw-new');
    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => {
      const card = screen.getByTestId('user-card-u1');
      expect(within(card).getByText('Alice Updated')).toBeInTheDocument();
      expect(within(card).getByText('admin')).toBeInTheDocument();
    });

    // ── Block Alice Updated via row action + dialog ──────────────────────────
    await user.click(screen.getByRole('button', { name: 'Actions for Alice Updated' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Block' }));
    dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Block reason'), 'test reason');
    await user.click(within(dialog).getByRole('button', { name: 'Block' }));
    await waitFor(() => {
      expect(within(screen.getByTestId('user-card-u1')).getByText('blocked')).toBeInTheDocument();
    });

    // ── Unblock via row action (no dialog) ───────────────────────────────────
    await user.click(screen.getByRole('button', { name: 'Actions for Alice Updated' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Unblock' }));
    await waitFor(() => {
      expect(within(screen.getByTestId('user-card-u1')).getByText('active')).toBeInTheDocument();
    });

    // ── Manage API keys: existing key shows, secret hidden until issued ──────
    await user.click(screen.getByRole('button', { name: 'Actions for Alice Updated' }));
    await user.click(await screen.findByRole('menuitem', { name: 'API keys' }));
    const keysDialog = await screen.findByRole('dialog');
    expect(within(keysDialog).getByText('ma-u1...abcd')).toBeInTheDocument();
    expect(screen.queryByText('ma-created-secret')).not.toBeInTheDocument();

    // ── Issue a new key → one-time secret ────────────────────────────────────
    await user.click(within(keysDialog).getByRole('button', { name: 'Issue key' }));
    const issueDialog = await screen.findByRole('dialog', { name: /Issue key for Alice Updated/ });
    await user.type(within(issueDialog).getByLabelText('Key note'), 'ops');
    await user.clear(within(issueDialog).getByLabelText('Key scope'));
    await user.type(within(issueDialog).getByLabelText('Key scope'), 'ops-bot');
    await user.click(within(issueDialog).getByRole('button', { name: 'Issue key' }));
    expect(await screen.findByText('ma-created-secret')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss new secret' }));
    expect(screen.queryByText('ma-created-secret')).not.toBeInTheDocument();
    expect(screen.getByText('ma-u1...efgh')).toBeInTheDocument();

    // ── Rotate the key → new one-time secret, old keys gone ──────────────────
    await user.click(screen.getByRole('button', { name: 'Rotate key' }));
    expect(await screen.findByText('ma-rotated-secret')).toBeInTheDocument();
    expect(screen.getByText('ma-u1...ijkl')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss new secret' }));
    expect(screen.queryByText('ma-rotated-secret')).not.toBeInTheDocument();
    expect(screen.queryByText('ma-created-secret')).not.toBeInTheDocument();
    expect(screen.queryByText('ma-u1...abcd')).not.toBeInTheDocument();
    expect(keyListCalls).toBeGreaterThan(0);

    // ── Revoke the rotated key via AlertDialog confirm ───────────────────────
    await user.click(screen.getByRole('button', { name: 'Revoke key 12' }));
    const revokeAlert = await screen.findByRole('alertdialog');
    await user.click(within(revokeAlert).getByRole('button', { name: 'Revoke key 12' }));
    await waitFor(() => {
      expect(screen.queryByText('ma-u1...ijkl')).not.toBeInTheDocument();
    });

    // Close the keys dialog before deleting a user.
    await user.keyboard('{Escape}');

    // ── Delete Carol via row action + AlertDialog confirm ────────────────────
    await user.click(screen.getByRole('button', { name: 'Actions for Carol' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }));
    const deleteAlert = await screen.findByRole('alertdialog');
    await user.click(within(deleteAlert).getByRole('button', { name: 'Delete' }));
    await waitFor(() => {
      expect(screen.queryByText('Carol')).not.toBeInTheDocument();
    });
  });

  it('supports IM identity bind, block, and restore flows', async () => {
    const user = userEvent.setup({ delay: null });
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
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
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
    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument();

    // The IM identities live under the "IM identities" tab.
    await user.click(screen.getByRole('tab', { name: 'IM identities' }));
    expect(await screen.findByText('U-ALICE')).toBeInTheDocument();

    const row = screen.getByTestId('im-user-7');

    // ── Bind the identity to a different user ────────────────────────────────
    // Initially bound to u1; after binding the identity badge should show u2.
    expect(
      within(row).getByText(
        (content, element) =>
          content === 'u1' && (element?.className ?? '').includes('rounded-full')
      )
    ).toBeInTheDocument();
    await selectOption(user, within(row).getByLabelText('Bind to user'), 'u2');
    await waitFor(() => {
      expect(
        within(row).getByText(
          (content, element) =>
            content === 'u2' && (element?.className ?? '').includes('rounded-full')
        )
      ).toBeInTheDocument();
    });

    // ── Block the identity ───────────────────────────────────────────────────
    await user.type(within(row).getByLabelText('IM reason'), 'fraud');
    await user.click(within(row).getByRole('button', { name: 'Block identity' }));
    await waitFor(() => {
      expect(within(row).getByText('blocked')).toBeInTheDocument();
      expect(within(row).getByText('not allowed')).toBeInTheDocument();
    });

    // ── Restore the identity ─────────────────────────────────────────────────
    await user.clear(within(row).getByLabelText('IM reason'));
    await user.type(within(row).getByLabelText('IM reason'), 'restored');
    await user.click(within(row).getByRole('button', { name: 'Restore identity' }));
    await waitFor(() => {
      expect(within(row).getByText('active')).toBeInTheDocument();
      expect(within(row).getByText('allowed')).toBeInTheDocument();
    });
  });

  it('creates an IM mapping from the users page IM identities tab', async () => {
    const user = userEvent.setup({ delay: null });
    const users: UserRecord[] = [
      {
        email: 'alice@fleetent.test',
        id: 'u1',
        must_reset: false,
        name: 'Alice',
        role: 'viewer',
        status: 'active',
      },
      {
        email: null,
        id: 'u2',
        must_reset: false,
        name: 'Bob',
        role: 'viewer',
        status: 'active',
      },
    ];
    let imUsers: ImUserRecord[] = [];

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(users)),
      http.get(`${API_BASE_URL}/admin/users/:userId/keys`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json(imUsers)),
      http.post(`${API_BASE_URL}/admin/im-identities`, async ({ request }) => {
        expect(await request.json()).toEqual({
          platform: 'telegram',
          platform_user_id: 'T1',
          user_id: 'u2',
        });
        imUsers = [
          {
            allowed: true,
            id: 8,
            platform: 'telegram',
            platform_user_id: 'T1',
            status: 'active',
            user_id: 'u2',
          },
        ];
        return HttpResponse.json({
          created_at: '2026-06-27T10:00:00Z',
          id: 8,
          platform: 'telegram',
          platform_user_id: 'T1',
          user_email: null,
          user_id: 'u2',
          user_name: 'Bob',
        }, { status: 201 });
      })
    );

    renderUsersPage();
    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'IM identities' }));
    expect(await screen.findByText('No IM identities linked yet.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Add mapping' }));
    const dialog = await screen.findByRole('dialog');
    const submit = within(dialog).getByRole('button', { name: 'Create' });
    expect(submit).toBeDisabled();

    const comboboxes = within(dialog).getAllByRole('combobox');
    await user.click(comboboxes[0]);
    await user.click(await screen.findByRole('option', { name: 'telegram' }));
    await user.type(within(dialog).getByLabelText('External ID'), 'T1');
    await user.click(comboboxes[1]);
    await user.click(await screen.findByRole('option', { name: 'Bob' }));

    await user.click(submit);

    const row = await screen.findByTestId('im-user-8');
    expect(within(row).getByText('T1')).toBeInTheDocument();
    expect(within(row).getByText('telegram')).toBeInTheDocument();
  });

  it('edits IM metadata from field definitions and deletes an IM identity', async () => {
    const user = userEvent.setup({ delay: null });
    const users: UserRecord[] = [
      {
        email: 'alice@fleetent.test',
        id: 'u1',
        must_reset: false,
        name: 'Alice',
        role: 'viewer',
        status: 'active',
      },
    ];
    let imUsers: ImUserRecord[] = [
      {
        allowed: true,
        id: 7,
        metadata: { display_name: 'Alice Old', notes: 'old note' },
        platform: 'slack',
        platform_user_id: 'U007',
        status: 'active',
        user_id: 'u1',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(users)),
      http.get(`${API_BASE_URL}/admin/users/:userId/keys`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json(imUsers)),
      http.get(`${API_BASE_URL}/admin/im-users/fields`, () =>
        HttpResponse.json({
          slack: [
            { key: 'display_name', label: 'Display name' },
            { key: 'notes', label: 'Notes', multiline: true },
          ],
        })
      ),
      http.patch(`${API_BASE_URL}/admin/im-users/7`, async ({ request }) => {
        expect(await request.json()).toEqual({
          metadata: { display_name: 'Alice Slack', notes: 'vip' },
          platform_user_id: 'U007-NEW',
        });
        imUsers = imUsers.map((item) =>
          item.id === 7
            ? {
                ...item,
                metadata: { display_name: 'Alice Slack', notes: 'vip' },
                platform_user_id: 'U007-NEW',
              }
            : item
        );
        return HttpResponse.json({ status: 'updated' });
      }),
      http.delete(`${API_BASE_URL}/admin/im-users/7`, () => {
        imUsers = [];
        return new HttpResponse(null, { status: 204 });
      })
    );

    renderUsersPage();
    await user.click(await screen.findByRole('tab', { name: 'IM identities' }));

    const row = await screen.findByTestId('im-user-7');
    await user.click(within(row).getByRole('button', { name: 'Identity actions for slack:U007' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Edit metadata' }));

    const dialog = await screen.findByRole('dialog');
    await user.clear(within(dialog).getByLabelText('External ID'));
    await user.type(within(dialog).getByLabelText('External ID'), 'U007-NEW');
    await user.clear(within(dialog).getByLabelText('Display name'));
    await user.type(within(dialog).getByLabelText('Display name'), 'Alice Slack');
    await user.clear(within(dialog).getByLabelText('Notes'));
    await user.type(within(dialog).getByLabelText('Notes'), 'vip');
    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(screen.getByTestId('im-user-7')).toHaveTextContent('U007-NEW');
    });

    const updatedRow = screen.getByTestId('im-user-7');
    await user.click(within(updatedRow).getByRole('button', { name: 'Identity actions for slack:U007-NEW' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Delete identity' }));
    const alert = await screen.findByRole('alertdialog');
    await user.click(within(alert).getByRole('button', { name: 'Delete identity' }));

    await waitFor(() => {
      expect(screen.queryByTestId('im-user-7')).not.toBeInTheDocument();
    });
  });

  it('creates a service principal, shows its one-time key, and keeps the form open on failure', async () => {
    const user = userEvent.setup({ delay: null });
    let users: UserRecord[] = [
      {
        email: 'alice@fleetent.test',
        id: 'u1',
        must_reset: false,
        name: 'Alice',
        role: 'viewer',
        status: 'active',
      },
    ];
    let failNext = true;

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(users)),
      http.get(`${API_BASE_URL}/admin/users/:userId/keys`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/admin/service-principals`, async ({ request }) => {
        expect(await request.json()).toEqual({ name: failNext ? 'svc-fail' : 'svc-ingest' });
        if (failNext) {
          failNext = false;
          return HttpResponse.json({ detail: 'service principal exists' }, { status: 409 });
        }
        const created = {
          email: null,
          id: 'svc1',
          must_reset: false,
          name: 'svc-ingest',
          role: 'viewer',
          status: 'active',
        };
        users = [...users, created];
        return HttpResponse.json(
          { user: created, api_key_plaintext_once: 'ma-service-principal-secret' },
          { status: 201 }
        );
      })
    );

    renderUsersPage();
    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Create service principal' }));
    let dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Service principal name'), 'svc-fail');
    await user.click(within(dialog).getByRole('button', { name: 'Create service principal' }));

    expect(await within(dialog).findByText('service principal exists')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Service principal name')).toHaveValue('svc-fail');

    await user.clear(within(dialog).getByLabelText('Service principal name'));
    await user.type(within(dialog).getByLabelText('Service principal name'), 'svc-ingest');
    await user.click(within(dialog).getByRole('button', { name: 'Create service principal' }));

    expect(await screen.findByText('ma-service-principal-secret')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss new secret' }));
    expect(screen.queryByText('ma-service-principal-secret')).not.toBeInTheDocument();
    expect(await screen.findByText('svc-ingest')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Create service principal' }));
    dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('Service principal name')).toHaveValue('');
  });

  it('initiates a channel link from user row actions and unlinks a channel identity', async () => {
    const user = userEvent.setup({ delay: null });
    const users: UserRecord[] = [
      {
        email: 'alice@fleetent.test',
        id: 'u1',
        must_reset: false,
        name: 'Alice',
        role: 'viewer',
        status: 'active',
      },
    ];
    let imUsers: ImUserRecord[] = [
      {
        allowed: true,
        id: 7,
        platform: 'slack',
        platform_user_id: 'U007',
        status: 'active',
        user_id: 'u1',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(users)),
      http.get(`${API_BASE_URL}/admin/users/:userId/keys`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/im-users`, () => HttpResponse.json(imUsers)),
      http.post(`${API_BASE_URL}/admin/link/initiate`, async ({ request }) => {
        expect(await request.text()).toBe('');
        return HttpResponse.json({
          code: 'link-code-123',
          expires_at: '2026-06-27T10:10:00+00:00',
        });
      }),
      http.post(`${API_BASE_URL}/admin/link/unlink`, async ({ request }) => {
        expect(await request.json()).toEqual({ platform: 'slack', platform_user_id: 'U007' });
        imUsers = [];
        return HttpResponse.json({ status: 'unlinked' });
      })
    );

    renderUsersPage();
    expect(await screen.findByText('Alice')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Actions for Alice' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Initiate channel link' }));
    let dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('link-code-123')).toBeInTheDocument();
    expect(dialog).toHaveTextContent('2026-06-27T10:10:00+00:00');
    await user.click(within(dialog).getByRole('button', { name: 'Dismiss' }));

    await user.click(screen.getByRole('button', { name: 'Actions for Alice' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Unlink channel identity' }));
    dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Platform'), 'slack');
    await user.type(within(dialog).getByLabelText('External ID'), 'U007');
    await user.click(within(dialog).getByRole('button', { name: 'Unlink channel identity' }));

    await user.click(screen.getByRole('tab', { name: 'IM identities' }));
    await waitFor(() => {
      expect(screen.queryByTestId('im-user-7')).not.toBeInTheDocument();
    });
  });
});

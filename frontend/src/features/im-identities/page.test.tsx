import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { ImIdentitiesPage } from '@/features/im-identities/page';
import { I18nProvider } from '@/i18n';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

function renderPage(): void {
  render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <AppQueryProvider>
          <ImIdentitiesPage />
        </AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

const USERS = [
  { email: 'alice@example.com', id: 'user-alice', name: 'Alice' },
  { email: null, id: 'user-bob', name: 'Bob' },
];

const ADMIN_ME = { email: 'admin@example.com', id: 'admin-1', role: 'admin' };

describe('im-identities page', () => {
  it('lists mappings with platform, external id, and internal user', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
      http.get(`${API_BASE_URL}/admin/im-identities`, () =>
        HttpResponse.json([
          {
            created_at: '2026-06-21T09:00:00Z',
            id: 1,
            platform: 'slack',
            platform_user_id: 'U1',
            user_email: 'alice@example.com',
            user_id: 'user-alice',
            user_name: 'Alice',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(USERS))
    );

    renderPage();

    expect(await screen.findByRole('heading', { name: 'IM Identities' })).toBeInTheDocument();
    const row = await screen.findByRole('row', { name: /U1/ });
    expect(within(row).getByText('slack')).toBeInTheDocument();
    expect(within(row).getByText('U1')).toBeInTheDocument();
    expect(within(row).getByText('Alice')).toBeInTheDocument();
    expect(within(row).getByText('alice@example.com')).toBeInTheDocument();
  });

  it('creates a new binding and shows it in the list', async () => {
    const user = userEvent.setup();
    let mappings: Array<Record<string, unknown>> = [];

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
      http.get(`${API_BASE_URL}/admin/im-identities`, () => HttpResponse.json(mappings)),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(USERS)),
      http.post(`${API_BASE_URL}/admin/im-identities`, async ({ request }) => {
        expect(await request.json()).toEqual({
          platform: 'telegram',
          platform_user_id: 'T1',
          user_id: 'user-bob',
        });
        const created = {
          created_at: '2026-06-21T11:00:00Z',
          id: 2,
          platform: 'telegram',
          platform_user_id: 'T1',
          user_email: null,
          user_id: 'user-bob',
          user_name: 'Bob',
        };
        mappings = [...mappings, created];
        return HttpResponse.json(created, { status: 201 });
      })
    );

    renderPage();

    await screen.findByRole('heading', { name: 'IM Identities' });

    // Open the add-mapping dialog.
    await user.click(screen.getByRole('button', { name: 'Add mapping' }));
    const dialog = await screen.findByRole('dialog');

    const submit = within(dialog).getByRole('button', { name: 'Create' });
    expect(submit).toBeDisabled();

    // Platform select (first combobox in the dialog) → telegram.
    const comboboxes = within(dialog).getAllByRole('combobox');
    await user.click(comboboxes[0]);
    await user.click(await screen.findByRole('option', { name: 'telegram' }));

    await user.type(within(dialog).getByLabelText('External ID'), 'T1');

    // Internal user select (second combobox) → Bob.
    await user.click(comboboxes[1]);
    await user.click(await screen.findByRole('option', { name: 'Bob' }));

    expect(submit).toBeEnabled();
    await user.click(submit);

    const row = await screen.findByRole('row', { name: /T1/ });
    expect(within(row).getByText('telegram')).toBeInTheDocument();
    expect(within(row).getByText('T1')).toBeInTheDocument();
    expect(within(row).getByText('Bob')).toBeInTheDocument();
  });

  it('keeps the form open when create fails', async () => {
    const user = userEvent.setup();
    // The page fires the create mutation via `void submit()`; on failure the
    // rejected promise floats. Swallow it so it does not surface as an
    // unhandled rejection that Vitest flags as a false-positive error.
    const onUnhandled = (reason: unknown): void => {
      void reason;
    };
    process.on('unhandledRejection', onUnhandled);

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
      http.get(`${API_BASE_URL}/admin/im-identities`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(USERS)),
      http.post(`${API_BASE_URL}/admin/im-identities`, () =>
        HttpResponse.json({ detail: 'im identity already exists' }, { status: 409 })
      )
    );

    renderPage();

    await screen.findByRole('heading', { name: 'IM Identities' });

    await user.click(screen.getByRole('button', { name: 'Add mapping' }));
    const dialog = await screen.findByRole('dialog');

    const comboboxes = within(dialog).getAllByRole('combobox');
    await user.click(comboboxes[0]);
    await user.click(await screen.findByRole('option', { name: 'slack' }));
    await user.type(within(dialog).getByLabelText('External ID'), 'U1');
    await user.click(comboboxes[1]);
    await user.click(await screen.findByRole('option', { name: 'Alice (alice@example.com)' }));

    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    // The dialog stays open with the entered values; no row was added.
    await waitFor(() => {
      expect(within(dialog).getByLabelText('External ID')).toHaveValue('U1');
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.queryByRole('row', { name: /U1/ })).not.toBeInTheDocument();

    process.off('unhandledRejection', onUnhandled);
  });

  it('deletes a binding and removes it from the list', async () => {
    const user = userEvent.setup();
    let mappings = [
      {
        created_at: '2026-06-21T09:00:00Z',
        id: 1,
        platform: 'slack',
        platform_user_id: 'U1',
        user_email: 'alice@example.com',
        user_id: 'user-alice',
        user_name: 'Alice',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () => HttpResponse.json(ADMIN_ME)),
      http.get(`${API_BASE_URL}/admin/im-identities`, () => HttpResponse.json(mappings)),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(USERS)),
      http.delete(`${API_BASE_URL}/admin/im-identities/:id`, ({ params }) => {
        mappings = mappings.filter((mapping) => mapping.id !== Number(params.id));
        return new HttpResponse(null, { status: 204 });
      })
    );

    renderPage();

    const row = await screen.findByRole('row', { name: /U1/ });

    // Open the row action menu and pick Delete → confirm in the AlertDialog.
    await user.click(within(row).getByRole('button', { name: 'Actions for slack:U1' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }));
    const alert = await screen.findByRole('alertdialog');
    await user.click(within(alert).getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(screen.queryByRole('row', { name: /U1/ })).not.toBeInTheDocument();
    });
  });
});

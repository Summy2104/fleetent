import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { ImIdentitiesPage } from '@/features/im-identities/page';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

function renderPage(): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken="session-token"
    >
      <AppQueryProvider>
        <ImIdentitiesPage />
      </AppQueryProvider>
    </AuthProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

const USERS = [
  { email: 'alice@example.com', id: 'user-alice', name: 'Alice' },
  { email: null, id: 'user-bob', name: 'Bob' },
];

describe('im-identities page', () => {
  it('lists mappings with platform, external id, and internal user', async () => {
    server.use(
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

    expect(await screen.findByRole('heading', { name: '用户-IM 关系' })).toBeInTheDocument();
    const row = await screen.findByRole('article', { name: 'mapping 1' });
    expect(within(row).getByText('slack')).toBeInTheDocument();
    expect(within(row).getByText('U1')).toBeInTheDocument();
    expect(within(row).getByText(/Alice/)).toBeInTheDocument();
    expect(within(row).getByText(/alice@example.com/)).toBeInTheDocument();
  });

  it('creates a new binding and shows it in the list', async () => {
    const user = userEvent.setup({ delay: null });
    let mappings: Array<Record<string, unknown>> = [];

    server.use(
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

    await screen.findByRole('heading', { name: '用户-IM 关系' });
    const submit = screen.getByRole('button', { name: '新增绑定' });
    expect(submit).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('平台'), 'telegram');
    await user.type(screen.getByLabelText('外部 ID'), 'T1');
    await user.selectOptions(screen.getByLabelText('内部用户'), 'user-bob');
    expect(submit).toBeEnabled();
    await user.click(submit);

    const row = await screen.findByRole('article', { name: 'mapping 2' });
    expect(within(row).getByText('telegram')).toBeInTheDocument();
    expect(within(row).getByText('T1')).toBeInTheDocument();
    expect(within(row).getByText(/Bob/)).toBeInTheDocument();
  });

  it('keeps the form and shows an error when create fails', async () => {
    const user = userEvent.setup({ delay: null });

    server.use(
      http.get(`${API_BASE_URL}/admin/im-identities`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(USERS)),
      http.post(`${API_BASE_URL}/admin/im-identities`, () =>
        HttpResponse.json({ detail: 'im identity already exists' }, { status: 409 })
      )
    );

    renderPage();

    await screen.findByRole('heading', { name: '用户-IM 关系' });
    await user.selectOptions(screen.getByLabelText('平台'), 'slack');
    await user.type(screen.getByLabelText('外部 ID'), 'U1');
    await user.selectOptions(screen.getByLabelText('内部用户'), 'user-alice');
    await user.click(screen.getByRole('button', { name: '新增绑定' }));

    expect(await screen.findByText(/新增绑定失败/)).toBeInTheDocument();
    expect(screen.getByLabelText('外部 ID')).toHaveValue('U1');
    expect(screen.queryByRole('article', { name: /mapping/ })).not.toBeInTheDocument();
  });

  it('deletes a binding and removes it from the list', async () => {
    const user = userEvent.setup({ delay: null });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
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
      http.get(`${API_BASE_URL}/admin/im-identities`, () => HttpResponse.json(mappings)),
      http.get(`${API_BASE_URL}/admin/users`, () => HttpResponse.json(USERS)),
      http.delete(`${API_BASE_URL}/admin/im-identities/:id`, ({ params }) => {
        mappings = mappings.filter((mapping) => mapping.id !== Number(params.id));
        return new HttpResponse(null, { status: 204 });
      })
    );

    renderPage();

    const row = await screen.findByRole('article', { name: 'mapping 1' });
    await user.click(within(row).getByRole('button', { name: '删除 U1' }));

    await waitFor(() => {
      expect(screen.queryByRole('article', { name: 'mapping 1' })).not.toBeInTheDocument();
    });
  });
});

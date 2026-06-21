import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { AdminRoutes } from '@/app/routes';
import { server } from '@/test/msw/server';

function renderRoutes(route: string, token?: string): void {
  render(
    <AuthProvider
      baseUrl="http://fleetent.test"
      initialToken={token ?? null}
    >
      <AppQueryProvider>
        <MemoryRouter initialEntries={[route]}>
          <AdminRoutes />
        </MemoryRouter>
      </AppQueryProvider>
    </AuthProvider>
  );
}

describe('admin routes', () => {
  it('redirects unauthenticated users to the login page', async () => {
    renderRoutes('/agents');

    expect(await screen.findByRole('heading', { name: 'Admin Login' })).toBeInTheDocument();
  });

  it('renders the agents page with native navigation links', async () => {
    server.use(http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])));

    renderRoutes('/agents', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Agents' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Agents' })).toHaveAttribute('href', '/agents');
    expect(screen.getByRole('link', { name: 'Sessions' })).toHaveAttribute('href', '/sessions');
    expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users');
    expect(screen.getByRole('link', { name: 'Providers' })).toHaveAttribute(
      'href',
      '/providers'
    );
  });

  it('renders providers as a native route instead of a legacy deep link', async () => {
    server.use(http.get('http://fleetent.test/admin/providers', () => HttpResponse.json([])));

    renderRoutes('/providers', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Providers' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Providers' })).toHaveAttribute('href', '/providers');
  });

  it('renders sessions as a native route in the SPA', async () => {
    server.use(
      http.get('http://fleetent.test/admin/me', () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get('http://fleetent.test/admin/sessions', () => HttpResponse.json([]))
    );

    renderRoutes('/sessions', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Sessions' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Sessions' })).toHaveAttribute('href', '/sessions');
  });

  it('renders the users page as a native route', async () => {
    server.use(
      http.get('http://fleetent.test/admin/users', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/im-users', () => HttpResponse.json([])),
      http.get('http://fleetent.test/admin/users/u1/keys', () => HttpResponse.json([]))
    );

    renderRoutes('/users', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users');
  });
});

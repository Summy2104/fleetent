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

  it('renders the agents page and legacy deep links for unmigrated domains', async () => {
    server.use(http.get('http://fleetent.test/admin/agents', () => HttpResponse.json([])));

    renderRoutes('/agents', 'session-token');

    expect(await screen.findByRole('heading', { name: 'Agents' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Providers' })).toHaveAttribute(
      'href',
      '/admin/ui-legacy#providers'
    );
  });
});

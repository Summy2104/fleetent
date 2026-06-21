import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { AdminRoutes } from '@/app/routes';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

type AgentRecord = {
  agent_name: string;
  allowed_tools: string[];
  provenance: string;
  status: string;
  system_prompt: string;
};

function renderAgentsRoute(): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken="session-token"
    >
      <AppQueryProvider>
        <MemoryRouter initialEntries={['/agents']}>
          <AdminRoutes />
        </MemoryRouter>
      </AppQueryProvider>
    </AuthProvider>
  );
}

describe('agents page parity baseline', () => {
  it('supports lifecycle mutations and list refreshes', async () => {
    const user = userEvent.setup();
    let agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: ['read_file'],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json(agents)),
      http.get(`${API_BASE_URL}/admin/agents/:name`, ({ params }) => {
        const agent = agents.find((item) => item.agent_name === params.name);
        return HttpResponse.json({
          agent: agent?.agent_name,
          allowed_tools: agent?.allowed_tools ?? [],
          status: agent?.status ?? 'enabled',
          system_prompt: agent?.system_prompt ?? '',
        });
      }),
      http.post(`${API_BASE_URL}/admin/agents`, async ({ request }) => {
        const body = (await request.json()) as {
          allowed_tools: string[];
          name: string;
          system_prompt: string;
        };
        agents = [
          ...agents,
          {
            agent_name: body.name,
            allowed_tools: body.allowed_tools,
            provenance: 'adhoc',
            status: 'enabled',
            system_prompt: body.system_prompt,
          },
        ];
        return HttpResponse.json({ agent: body.name, status: 'enabled', provenance: 'adhoc' }, { status: 201 });
      }),
      http.patch(`${API_BASE_URL}/admin/agents/:name`, async ({ params, request }) => {
        const body = (await request.json()) as {
          allowed_tools?: string[];
          system_prompt?: string;
        };
        agents = agents.map((agent) =>
          agent.agent_name === params.name
            ? {
                ...agent,
                allowed_tools: body.allowed_tools ?? agent.allowed_tools,
                system_prompt: body.system_prompt ?? agent.system_prompt,
              }
            : agent
        );
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/disable`, ({ params }) => {
        agents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'disabled' } : agent
        );
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/enable`, ({ params }) => {
        agents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'enabled' } : agent
        );
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/archive`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        agents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'archived' } : agent
        );
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/restore`, ({ params }) => {
        agents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'enabled' } : agent
        );
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/clone`, async ({ params, request }) => {
        const body = (await request.json()) as { new_name: string };
        const source = agents.find((agent) => agent.agent_name === params.name);
        agents = [
          ...agents,
          {
            ...(source as AgentRecord),
            agent_name: body.new_name,
          },
        ];
        return HttpResponse.json({ ok: true });
      }),
      http.delete(`${API_BASE_URL}/admin/agents/:name`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        agents = agents.filter((agent) => agent.agent_name !== params.name);
        return HttpResponse.json({ ok: true });
      })
    );

    renderAgentsRoute();
    expect(await screen.findByText('alpha')).toBeInTheDocument();
    expect(screen.getByText('Alpha prompt')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Agent name'), 'beta');
    await user.type(screen.getByLabelText('System prompt'), 'Beta prompt');
    await user.type(screen.getByLabelText('Allowed tools'), 'read_file,write_file');
    await user.click(screen.getByRole('button', { name: 'Create agent' }));
    expect(await screen.findByText('beta')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit alpha' }));
    await user.clear(screen.getByLabelText('System prompt'));
    await user.type(screen.getByLabelText('System prompt'), 'Alpha v2');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => {
      expect(screen.getAllByText('Alpha v2').length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: 'Disable alpha' }));
    expect(await screen.findByText('disabled')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Enable alpha' }));
    await waitFor(() => {
      expect(screen.getAllByText('enabled').length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: 'Archive alpha' }));
    expect(await screen.findByText('archived')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Restore alpha' }));
    await waitFor(() => {
      expect(screen.getAllByText('enabled').length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: 'Clone alpha' }));
    expect(await screen.findByText('alpha-copy')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete beta' }));
    await waitFor(() => {
      expect(screen.queryByText('beta')).not.toBeInTheDocument();
    });
  });

  it('shows version activation and binding entry links', async () => {
    const user = userEvent.setup();
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: ['read_file'],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    let activeVersion = 1;

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json(agents)),
      http.get(`${API_BASE_URL}/admin/agents/:name`, ({ params }) => {
        const agent = agents.find((item) => item.agent_name === params.name);
        return HttpResponse.json({
          agent: agent?.agent_name,
          allowed_tools: agent?.allowed_tools ?? [],
          status: agent?.status ?? 'enabled',
          system_prompt: agent?.system_prompt ?? '',
        });
      }),
      http.get(`${API_BASE_URL}/admin/agents/alpha/versions`, () =>
        HttpResponse.json([
          { id: 1, is_active: activeVersion === 1, version: 1 },
          { id: 2, is_active: activeVersion === 2, version: 2 },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/agents/alpha/versions/2/activate`, () => {
        activeVersion = 2;
        return HttpResponse.json({ active_version: 2 });
      })
    );

    renderAgentsRoute();
    expect(await screen.findByText('alpha')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Load versions for alpha' }));
    expect(await screen.findByText('v1 active')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Activate v2 for alpha' }));
    expect(await screen.findByText('v2 active')).toBeInTheDocument();

    expect(screen.getByRole('link', { name: 'Skills' })).toHaveAttribute(
      'href',
      '/admin/ui-legacy#skills'
    );
    expect(screen.getByRole('link', { name: 'Knowledge Base' })).toHaveAttribute(
      'href',
      '/admin/ui-legacy#kb'
    );
    expect(screen.getByRole('link', { name: 'MCP Servers' })).toHaveAttribute(
      'href',
      '/admin/ui-legacy#agents'
    );
    expect(screen.getByRole('link', { name: 'OAuth Bindings' })).toHaveAttribute(
      'href',
      '/admin/ui-legacy#agents'
    );
    expect(screen.getByRole('link', { name: 'User Bindings' })).toHaveAttribute(
      'href',
      '/admin/ui-legacy#agents'
    );
  });
});

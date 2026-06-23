import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  is_default?: boolean;
  placement?: { node_id: string } | null;
  provenance: string;
  runtime?: { health?: string | null; node_id?: string | null; phase?: string | null } | null;
  status: string;
  system_prompt: string;
};

type AgentDetailRecord = {
  agent: string;
  allowed_tools: string[];
  config_overrides_yaml?: string;
  model_overrides?: Record<string, unknown>;
  status: string;
  supports_dm?: boolean;
  supports_groups?: boolean;
  system_prompt: string;
};

type AgentBindingState = {
  kbIds: string[];
  mcpServers: string[];
  oauth: Array<{ run_as: string; service_id: string }>;
  secrets: Array<{ env_name: string; mode: string; status: string }>;
  skills: Array<{ enabled: boolean; skill_name: string }>;
  users: string[];
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

function expectNoBindingLinks(): void {
  const bindingsPanel = screen.getByRole('heading', { name: 'Agent Bindings' }).closest('aside');
  expect(bindingsPanel).not.toBeNull();
  expect(within(bindingsPanel as HTMLElement).queryAllByRole('link')).toHaveLength(0);
}

function installAgentBindingHandlers({
  agents,
  bindingsByAgent,
  detailByAgent,
  role = 'admin',
}: {
  agents: AgentRecord[];
  bindingsByAgent: Record<string, AgentBindingState>;
  detailByAgent: Record<string, AgentDetailRecord>;
  role?: 'admin' | 'viewer';
}) {
  server.use(
    http.get(`${API_BASE_URL}/admin/me`, () =>
      HttpResponse.json({
        email: `${role}@fleetent.test`,
        id: `${role}-1`,
        role,
      })
    ),
    http.get(`${API_BASE_URL}/admin/agents`, ({ request }) => {
      expect(new URL(request.url).searchParams.get('include_archived')).toBe('true');
      return HttpResponse.json(agents);
    }),
    http.get(`${API_BASE_URL}/admin/agents/:name`, ({ params }) =>
      HttpResponse.json(detailByAgent[String(params.name)])
    ),
    http.get(`${API_BASE_URL}/admin/agents/:name/skills`, ({ params }) =>
      HttpResponse.json(bindingsByAgent[String(params.name)].skills)
    ),
    http.get(`${API_BASE_URL}/admin/agents/:name/bindings`, ({ params }) =>
      HttpResponse.json({
        mcp_servers: bindingsByAgent[String(params.name)].mcpServers,
        users: bindingsByAgent[String(params.name)].users,
      })
    ),
    http.get(`${API_BASE_URL}/admin/agents/:name/bindings/oauth`, ({ params }) => {
      const oauth = bindingsByAgent[String(params.name)].oauth;
      return HttpResponse.json({
        agent: String(params.name),
        connector_ids: oauth.map((item) => item.service_id),
        service_grants: oauth,
      });
    }),
    http.get(`${API_BASE_URL}/admin/agents/:name/kbs`, ({ params }) =>
      HttpResponse.json({
        agent: String(params.name),
        kb_ids: bindingsByAgent[String(params.name)].kbIds,
      })
    ),
    http.get(`${API_BASE_URL}/admin/agents/:name/secrets`, ({ params }) =>
      HttpResponse.json({
        agent: String(params.name),
        secrets: bindingsByAgent[String(params.name)].secrets,
      })
    ),
    http.get(`${API_BASE_URL}/admin/skills`, () =>
      HttpResponse.json([
        { name: 'crm-ops' },
        { name: 'incident-bridge' },
      ])
    ),
    http.get(`${API_BASE_URL}/admin/mcp/servers`, () =>
      HttpResponse.json([
        {
          agent_id: null,
          command: 'mcp-filesystem',
          id: 'filesystem',
          status: 'ready',
          tool_count: 4,
          transport: 'stdio',
        },
        {
          agent_id: null,
          command: 'mcp-github',
          id: 'github',
          status: 'ready',
          tool_count: 8,
          transport: 'stdio',
        },
      ])
    ),
    http.get(`${API_BASE_URL}/admin/connectors`, () =>
      HttpResponse.json([
        { display_name: 'GitHub', enabled: true, id: 'github', protocol: 'oauth2' },
        { display_name: 'Slack', enabled: true, id: 'slack', protocol: 'oauth2' },
      ])
    ),
    http.get(`${API_BASE_URL}/admin/kb`, () =>
      HttpResponse.json([
        {
          archived: false,
          bound_agents: [],
          chunk_count: 12,
          description: 'Support knowledge',
          doc_count: 2,
          kb_id: 'support',
          last_import: null,
          tenant_id: 'default',
        },
        {
          archived: false,
          bound_agents: [],
          chunk_count: 4,
          description: 'Sales knowledge',
          doc_count: 1,
          kb_id: 'sales',
          last_import: null,
          tenant_id: 'default',
        },
      ])
    ),
    http.get(`${API_BASE_URL}/admin/users`, () =>
      HttpResponse.json([
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
      ])
    ),
    http.get(`${API_BASE_URL}/admin/providers`, () =>
      HttpResponse.json([
        {
          api_key: null,
          api_key_env: 'FLEETENT_OPENAI_KEY',
          api_key_set: true,
          base_url: 'https://api.openai.example/v1',
          description: null,
          id: 'openai-gpt4',
          input_price_per_1k: null,
          model: 'gpt-4o',
          output_price_per_1k: null,
          protocol: 'openai_chat',
          provider: 'openai',
        },
        {
          api_key: null,
          api_key_env: null,
          api_key_set: false,
          base_url: 'http://localhost:11434/v1',
          description: null,
          id: 'ollama-local',
          input_price_per_1k: null,
          model: 'llama3',
          output_price_per_1k: null,
          protocol: 'openai_chat',
          provider: 'local',
        },
      ])
    )
  );
}

describe('agents page parity baseline', () => {
  it('supports lifecycle mutations and list refreshes', async () => {
    const user = userEvent.setup({ delay: null });
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: ['read_file'],
        is_default: false,
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: ['read_file'],
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    };
    const bindingsByAgent: Record<string, AgentBindingState> = {
      alpha: {
        kbIds: [],
        mcpServers: [],
        oauth: [],
        secrets: [],
        skills: [],
        users: [],
      },
      beta: {
        kbIds: [],
        mcpServers: [],
        oauth: [],
        secrets: [],
        skills: [],
        users: [],
      },
    };

    installAgentBindingHandlers({ agents, bindingsByAgent, detailByAgent });

    server.use(
      http.post(`${API_BASE_URL}/admin/agents`, async ({ request }) => {
        const body = (await request.json()) as {
          allowed_tools: string[];
          name: string;
          system_prompt: string;
        };
        agents.splice(0, agents.length, ...[
          ...agents,
          {
            agent_name: body.name,
            allowed_tools: body.allowed_tools,
            is_default: false,
            provenance: 'adhoc',
            status: 'enabled',
            system_prompt: body.system_prompt,
          },
        ]);
        detailByAgent[body.name] = {
          agent: body.name,
          allowed_tools: body.allowed_tools,
          status: 'enabled',
          supports_dm: false,
          supports_groups: false,
          system_prompt: body.system_prompt,
        };
        return HttpResponse.json({ agent: body.name, status: 'enabled', provenance: 'adhoc' }, { status: 201 });
      }),
      http.patch(`${API_BASE_URL}/admin/agents/:name`, async ({ params, request }) => {
        const body = (await request.json()) as {
          allowed_tools?: string[];
          system_prompt?: string;
        };
        const nextAgents = agents.map((agent) =>
          agent.agent_name === params.name
            ? {
                ...agent,
                allowed_tools: body.allowed_tools ?? agent.allowed_tools,
                system_prompt: body.system_prompt ?? agent.system_prompt,
              }
            : agent
        );
        agents.splice(0, agents.length, ...nextAgents);
        detailByAgent[String(params.name)] = {
          ...detailByAgent[String(params.name)],
          allowed_tools: body.allowed_tools ?? detailByAgent[String(params.name)].allowed_tools,
          system_prompt: body.system_prompt ?? detailByAgent[String(params.name)].system_prompt,
        };
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/disable`, ({ params }) => {
        const nextAgents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'disabled' } : agent
        );
        agents.splice(0, agents.length, ...nextAgents);
        detailByAgent[String(params.name)] = {
          ...detailByAgent[String(params.name)],
          status: 'disabled',
        };
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/enable`, ({ params }) => {
        const nextAgents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'enabled' } : agent
        );
        agents.splice(0, agents.length, ...nextAgents);
        detailByAgent[String(params.name)] = {
          ...detailByAgent[String(params.name)],
          status: 'enabled',
        };
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/archive`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        const nextAgents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'archived' } : agent
        );
        agents.splice(0, agents.length, ...nextAgents);
        detailByAgent[String(params.name)] = {
          ...detailByAgent[String(params.name)],
          status: 'archived',
        };
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/restore`, ({ params }) => {
        const nextAgents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'enabled' } : agent
        );
        agents.splice(0, agents.length, ...nextAgents);
        detailByAgent[String(params.name)] = {
          ...detailByAgent[String(params.name)],
          status: 'enabled',
        };
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/clone`, async ({ params, request }) => {
        const body = (await request.json()) as { new_name: string };
        const source = agents.find((agent) => agent.agent_name === params.name) as AgentRecord;
        agents.push({ ...source, agent_name: body.new_name });
        detailByAgent[body.new_name] = {
          ...detailByAgent[String(params.name)],
          agent: body.new_name,
        };
        bindingsByAgent[body.new_name] = { ...bindingsByAgent[String(params.name)] };
        return HttpResponse.json({ ok: true });
      }),
      http.delete(`${API_BASE_URL}/admin/agents/:name`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        const nextAgents = agents.filter((agent) => agent.agent_name !== params.name);
        agents.splice(0, agents.length, ...nextAgents);
        delete detailByAgent[String(params.name)];
        delete bindingsByAgent[String(params.name)];
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
  }, 15000);

  it('renders native bindings, versions, and write-only secrets without legacy deep links', async () => {
    const user = userEvent.setup({ delay: null });
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: ['read_file'],
        is_default: false,
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    let activeVersion = 1;
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: ['read_file'],
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    };
    const bindingsByAgent: Record<string, AgentBindingState> = {
      alpha: {
        kbIds: ['support'],
        mcpServers: ['filesystem'],
        oauth: [{ run_as: 'agent', service_id: 'github' }],
        secrets: [{ env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'unset' }],
        skills: [
          { enabled: true, skill_name: 'crm-ops' },
          { enabled: false, skill_name: 'incident-bridge' },
        ],
        users: ['u1'],
      },
    };

    installAgentBindingHandlers({ agents, bindingsByAgent, detailByAgent });

    server.use(
      http.get(`${API_BASE_URL}/admin/agents/alpha/versions`, () =>
        HttpResponse.json([
          { id: 1, is_active: activeVersion === 1, version: 1 },
          { id: 2, is_active: activeVersion === 2, version: 2 },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/agents/alpha/versions/2/activate`, () => {
        activeVersion = 2;
        return HttpResponse.json({ active_version: 2 });
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/skills/incident-bridge`, async ({ request }) => {
        expect(await request.json()).toEqual({ enabled: true });
        bindingsByAgent.alpha.skills = bindingsByAgent.alpha.skills.map((skill) =>
          skill.skill_name === 'incident-bridge' ? { ...skill, enabled: true } : skill
        );
        return HttpResponse.json({ agent: 'alpha', enabled: true, skill_name: 'incident-bridge' });
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/bindings/mcp/github`, () => {
        bindingsByAgent.alpha.mcpServers = ['filesystem', 'github'];
        return HttpResponse.json({ agent: 'alpha', bound: true, server_id: 'github' });
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/bindings/mcp/filesystem`, () => {
        bindingsByAgent.alpha.mcpServers = ['github'];
        return HttpResponse.json({ agent: 'alpha', bound: false, server_id: 'filesystem' });
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/bindings/oauth/slack`, async ({ request }) => {
        expect(await request.json()).toEqual({ run_as: 'user' });
        bindingsByAgent.alpha.oauth = [
          { run_as: 'agent', service_id: 'github' },
          { run_as: 'user', service_id: 'slack' },
        ];
        return HttpResponse.json({ agent: 'alpha', bound: true, connector_id: 'slack', run_as: 'user' });
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/bindings/oauth/github`, () => {
        bindingsByAgent.alpha.oauth = [{ run_as: 'user', service_id: 'slack' }];
        return HttpResponse.json({ agent: 'alpha', bound: false, connector_id: 'github' });
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/kbs`, async ({ request }) => {
        expect(await request.json()).toEqual({ kb_id: 'sales' });
        bindingsByAgent.alpha.kbIds = ['support', 'sales'];
        return HttpResponse.json({ agent: 'alpha', bound: true, kb_id: 'sales' });
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/kbs/support`, () => {
        bindingsByAgent.alpha.kbIds = ['sales'];
        return HttpResponse.json({ agent: 'alpha', bound: false, kb_id: 'support' });
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/bindings/users/u2`, () => {
        bindingsByAgent.alpha.users = ['u1', 'u2'];
        return HttpResponse.json({ agent: 'alpha', bound: true, user_id: 'u2' });
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/bindings/users/u1`, () => {
        bindingsByAgent.alpha.users = ['u2'];
        return HttpResponse.json({ agent: 'alpha', bound: false, user_id: 'u1' });
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/bindings/groups`, async ({ request }) => {
        expect(await request.json()).toEqual({ group_id: 'C0123', platform: 'slack' });
        return HttpResponse.json({ agent: 'alpha', bound: true, group_id: 'C0123', platform: 'slack' }, { status: 201 });
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/bindings/groups/slack/C0123`, () =>
        new HttpResponse(null, { status: 204 })
      ),
      http.put(`${API_BASE_URL}/admin/agents/alpha/im-capabilities`, async ({ request }) => {
        expect(await request.json()).toEqual({ supports_dm: true, supports_groups: true });
        detailByAgent.alpha = { ...detailByAgent.alpha, supports_dm: true, supports_groups: true };
        return HttpResponse.json({ agent: 'alpha', supports_dm: true, supports_groups: true });
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/default`, () => {
        const nextAgents = agents.map((agent) => ({ ...agent, is_default: true }));
        agents.splice(0, agents.length, ...nextAgents);
        return HttpResponse.json({ agent: 'alpha', is_default: true });
      }),
      http.delete(`${API_BASE_URL}/admin/agents/default`, () => {
        const nextAgents = agents.map((agent) => ({ ...agent, is_default: false }));
        agents.splice(0, agents.length, ...nextAgents);
        return HttpResponse.json({ cleared: true });
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/secrets/FLEETENT_ALPHA_API_KEY`, async ({ request }) => {
        expect(await request.json()).toEqual({ value: 'sk-live-secret' });
        bindingsByAgent.alpha.secrets = [
          { env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'set' },
        ];
        return HttpResponse.json({ env_name: 'FLEETENT_ALPHA_API_KEY', status: 'set' });
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/secrets/FLEETENT_ALPHA_API_KEY`, () => {
        bindingsByAgent.alpha.secrets = [
          { env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'unset' },
        ];
        return HttpResponse.json({ env_name: 'FLEETENT_ALPHA_API_KEY', status: 'unset' });
      })
    );

    renderAgentsRoute();
    expect(await screen.findByText('alpha')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Load versions for alpha' }));
    expect(await screen.findByText('v1 active')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Activate v2 for alpha' }));
    expect(await screen.findByText('v2 active')).toBeInTheDocument();

    const skillsSection = screen.getByRole('heading', { name: 'Skills' }).closest('section');
    const mcpSection = screen.getByRole('heading', { name: 'MCP Servers' }).closest('section');
    const oauthSection = screen.getByRole('heading', { name: 'OAuth Connectors' }).closest('section');
    const kbSection = screen.getByRole('heading', { name: 'Knowledge Bases' }).closest('section');
    const usersSection = screen.getByRole('heading', { name: 'User Access' }).closest('section');
    const imSection = screen.getByRole('heading', { name: 'IM Access' }).closest('section');
    const defaultSection = screen.getByRole('heading', { name: 'Default Agent' }).closest('section');
    const secretsSection = screen.getByRole('heading', { name: 'Secrets' }).closest('section');

    expect(skillsSection).not.toBeNull();
    expect(mcpSection).not.toBeNull();
    expect(oauthSection).not.toBeNull();
    expect(kbSection).not.toBeNull();
    expect(usersSection).not.toBeNull();
    expect(imSection).not.toBeNull();
    expect(defaultSection).not.toBeNull();
    expect(secretsSection).not.toBeNull();

    const skillsControls = within(skillsSection as HTMLElement);
    expect(skillsControls.getByText('crm-ops')).toBeInTheDocument();
    await user.click(skillsControls.getByRole('button', { name: 'Enable incident-bridge' }));
    await waitFor(() => {
      expect(skillsControls.getByRole('button', { name: 'Disable incident-bridge' })).toBeInTheDocument();
    });

    const mcpControls = within(mcpSection as HTMLElement);
    expect(mcpControls.getByText('filesystem')).toBeInTheDocument();
    await user.selectOptions(mcpControls.getByLabelText('Add MCP server'), 'github');
    await user.click(mcpControls.getByRole('button', { name: 'Bind MCP server' }));
    expect(await mcpControls.findByText('github')).toBeInTheDocument();
    await user.click(mcpControls.getByRole('button', { name: 'Remove filesystem' }));
    await waitFor(() => {
      expect(mcpControls.queryByRole('button', { name: 'Remove filesystem' })).not.toBeInTheDocument();
    });

    const oauthControls = within(oauthSection as HTMLElement);
    expect(oauthControls.getByText('github')).toBeInTheDocument();
    await user.selectOptions(oauthControls.getByLabelText('Add OAuth connector'), 'slack');
    await user.selectOptions(oauthControls.getByLabelText('Run as'), 'user');
    await user.click(oauthControls.getByRole('button', { name: 'Bind OAuth connector' }));
    expect(await oauthControls.findByText('slack')).toBeInTheDocument();
    await user.click(oauthControls.getByRole('button', { name: 'Remove github' }));
    await waitFor(() => {
      expect(oauthControls.queryByRole('button', { name: 'Remove github' })).not.toBeInTheDocument();
    });

    const kbControls = within(kbSection as HTMLElement);
    expect(kbControls.getByText('support')).toBeInTheDocument();
    await user.selectOptions(kbControls.getByLabelText('Add knowledge base'), 'sales');
    await user.click(kbControls.getByRole('button', { name: 'Bind knowledge base' }));
    expect(await kbControls.findByText('sales')).toBeInTheDocument();
    await user.click(kbControls.getByRole('button', { name: 'Remove support' }));
    await waitFor(() => {
      expect(kbControls.queryByRole('button', { name: 'Remove support' })).not.toBeInTheDocument();
    });

    const userControls = within(usersSection as HTMLElement);
    expect(userControls.getByText('u1')).toBeInTheDocument();
    await user.selectOptions(userControls.getByLabelText('Add user access'), 'u2');
    await user.click(userControls.getByRole('button', { name: 'Bind user' }));
    expect(await userControls.findByText('u2')).toBeInTheDocument();
    await user.click(userControls.getByRole('button', { name: 'Remove u1' }));
    await waitFor(() => {
      expect(userControls.queryByRole('button', { name: 'Remove u1' })).not.toBeInTheDocument();
    });

    const imControls = within(imSection as HTMLElement);
    await user.type(imControls.getByLabelText('Group id'), 'C0123');
    await user.click(imControls.getByRole('button', { name: 'Add group' }));
    expect(await imControls.findByText('slack:C0123')).toBeInTheDocument();
    await user.click(imControls.getByLabelText('Allow DMs'));
    await user.click(imControls.getByLabelText('Allow groups'));
    await user.click(imControls.getByRole('button', { name: 'Save IM capabilities' }));
    expect(await imControls.findByText('DMs enabled')).toBeInTheDocument();
    expect(await imControls.findByText('Groups enabled')).toBeInTheDocument();
    await user.click(imControls.getByRole('button', { name: 'Remove slack:C0123' }));
    await waitFor(() => {
      expect(imControls.queryByText('slack:C0123')).not.toBeInTheDocument();
    });

    const defaultControls = within(defaultSection as HTMLElement);
    await user.click(defaultControls.getByRole('button', { name: 'Set as default agent' }));
    expect(await defaultControls.findByText('This agent is the default.')).toBeInTheDocument();
    await user.click(defaultControls.getByRole('button', { name: 'Clear default agent' }));
    await waitFor(async () => {
      expect(await defaultControls.findByText('This agent is not the default.')).toBeInTheDocument();
    });

    const secretsControls = within(secretsSection as HTMLElement);
    expect(secretsControls.getByText('FLEETENT_ALPHA_API_KEY')).toBeInTheDocument();
    expect(secretsControls.getByText('unset')).toBeInTheDocument();
    expect(secretsControls.queryByText('sk-live-secret')).not.toBeInTheDocument();
    await user.type(secretsControls.getByLabelText('Secret value for FLEETENT_ALPHA_API_KEY'), 'sk-live-secret');
    await user.click(secretsControls.getByRole('button', { name: 'Save secret FLEETENT_ALPHA_API_KEY' }));
    expect(secretsControls.queryByDisplayValue('sk-live-secret')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(secretsControls.getByText('set')).toBeInTheDocument();
      expect(secretsControls.queryByText('sk-live-secret')).not.toBeInTheDocument();
    });
    await user.click(secretsControls.getByRole('button', { name: 'Clear secret FLEETENT_ALPHA_API_KEY' }));
    await waitFor(() => {
      expect(secretsControls.getByText('unset')).toBeInTheDocument();
    });

    expectNoBindingLinks();
  }, 15000);

  it('keeps viewers read-only across all binding sections', async () => {
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: ['read_file'],
        is_default: false,
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: ['read_file'],
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    };
    const bindingsByAgent: Record<string, AgentBindingState> = {
      alpha: {
        kbIds: ['support'],
        mcpServers: ['filesystem'],
        oauth: [{ run_as: 'agent', service_id: 'github' }],
        secrets: [{ env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'set' }],
        skills: [{ enabled: true, skill_name: 'crm-ops' }],
        users: ['u1'],
      },
    };

    installAgentBindingHandlers({ agents, bindingsByAgent, detailByAgent, role: 'viewer' });

    server.use(
      http.get(`${API_BASE_URL}/admin/agents/alpha/versions`, () =>
        HttpResponse.json([{ id: 1, is_active: true, version: 1 }])
      )
    );

    renderAgentsRoute();
    expect(await screen.findByText('alpha')).toBeInTheDocument();
    expect(await screen.findAllByText('Viewer access is read-only.')).not.toHaveLength(0);

    const bindingsPanel = screen.getByRole('heading', { name: 'Agent Bindings' }).closest('aside');
    expect(bindingsPanel).not.toBeNull();
    const panel = within(bindingsPanel as HTMLElement);

    expect(panel.queryByRole('button', { name: /Bind / })).not.toBeInTheDocument();
    expect(panel.queryByRole('button', { name: /Remove / })).not.toBeInTheDocument();
    expect(panel.queryByRole('button', { name: /Enable / })).not.toBeInTheDocument();
    expect(panel.queryByRole('button', { name: /Disable / })).not.toBeInTheDocument();
    expect(panel.queryByRole('button', { name: 'Set as default agent' })).not.toBeInTheDocument();
    expect(panel.queryByRole('button', { name: 'Clear default agent' })).not.toBeInTheDocument();
    expect(panel.queryByLabelText('Add MCP server')).not.toBeInTheDocument();
    expect(panel.queryByLabelText('Add OAuth connector')).not.toBeInTheDocument();
    expect(panel.queryByLabelText('Add knowledge base')).not.toBeInTheDocument();
    expect(panel.queryByLabelText('Add user access')).not.toBeInTheDocument();
    expect(panel.queryByLabelText('Group id')).not.toBeInTheDocument();
    expect(panel.queryByLabelText('Allow DMs')).not.toBeInTheDocument();
    expect(panel.queryByLabelText('Secret value for FLEETENT_ALPHA_API_KEY')).not.toBeInTheDocument();

    expectNoBindingLinks();
  });
});

describe('agents page dual-state (runtime + placement gating)', () => {
  const emptyBindings = {
    kbIds: [],
    mcpServers: [],
    oauth: [],
    secrets: [],
    skills: [],
    users: [],
  };

  it('shows runtime state on the card', async () => {
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        is_default: false,
        placement: { node_id: 'node-a' },
        provenance: 'adhoc',
        runtime: { health: 'ok', node_id: 'node-a', phase: 'running' },
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    };
    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: emptyBindings },
      detailByAgent,
    });

    renderAgentsRoute();

    expect(await screen.findByText('Runtime: running on node-a (ok)')).toBeInTheDocument();
    // the new runtime line must not displace the existing desired-state token
    expect(screen.getByText('enabled')).toBeInTheDocument();
  });

  it('renders a phase-only runtime without node/health decoration', async () => {
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        is_default: false,
        placement: { node_id: 'node-a' },
        provenance: 'adhoc',
        runtime: { phase: 'stopped' },
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: emptyBindings },
      detailByAgent: {
        alpha: { agent: 'alpha', allowed_tools: [], status: 'enabled', system_prompt: 'p' },
      },
    });

    renderAgentsRoute();

    expect(await screen.findByText('Runtime: stopped')).toBeInTheDocument();
  });

  it('renders an explicit not-running state when runtime is null', async () => {
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        is_default: false,
        placement: null,
        provenance: 'adhoc',
        runtime: null,
        status: 'disabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: emptyBindings },
      detailByAgent: {
        alpha: { agent: 'alpha', allowed_tools: [], status: 'disabled', system_prompt: 'p' },
      },
    });

    renderAgentsRoute();

    expect(await screen.findByText('Runtime: not running')).toBeInTheDocument();
  });

  it('disables Enable when the agent is not bound to a node', async () => {
    const agents: AgentRecord[] = [
      {
        agent_name: 'gamma',
        allowed_tools: [],
        is_default: false,
        placement: null,
        provenance: 'adhoc',
        runtime: null,
        status: 'disabled',
        system_prompt: 'Gamma prompt',
      },
      {
        agent_name: 'delta',
        allowed_tools: [],
        is_default: false,
        placement: { node_id: 'node-b' },
        provenance: 'adhoc',
        runtime: null,
        status: 'disabled',
        system_prompt: 'Delta prompt',
      },
    ];
    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { delta: emptyBindings, gamma: emptyBindings },
      detailByAgent: {
        delta: { agent: 'delta', allowed_tools: [], status: 'disabled', system_prompt: 'd' },
        gamma: { agent: 'gamma', allowed_tools: [], status: 'disabled', system_prompt: 'g' },
      },
    });

    renderAgentsRoute();

    const unbound = await screen.findByRole('button', { name: 'Enable gamma' });
    expect(unbound).toBeDisabled();
    expect(unbound).toHaveAttribute('title', 'Pin this agent to a node before enabling');

    const bound = screen.getByRole('button', { name: 'Enable delta' });
    expect(bound).not.toBeDisabled();
  });
});

describe('agents page model binding', () => {
  const emptyBindings = {
    kbIds: [],
    mcpServers: [],
    oauth: [],
    secrets: [],
    skills: [],
    users: [],
  };

  it('binds a model provider on create and round-trips the selection on edit', async () => {
    const user = userEvent.setup({ delay: null });
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        model_overrides: { routes: { default: [{ provider_id: 'ollama-local' }] } },
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    };

    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: { ...emptyBindings } },
      detailByAgent,
    });

    type CapturedModelBody = {
      model_overrides?: { routes?: Record<string, Array<{ provider_id?: string }>> };
      name?: string;
    };
    const captured: { create?: CapturedModelBody; patch?: CapturedModelBody } = {};
    server.use(
      http.post(`${API_BASE_URL}/admin/agents`, async ({ request }) => {
        const body = (await request.json()) as CapturedModelBody;
        captured.create = body;
        const name = body.name ?? 'beta';
        agents.push({
          agent_name: name,
          allowed_tools: [],
          provenance: 'adhoc',
          status: 'enabled',
          system_prompt: 'Beta prompt',
        });
        detailByAgent[name] = {
          agent: name,
          allowed_tools: [],
          status: 'enabled',
          system_prompt: 'Beta prompt',
        };
        return HttpResponse.json({ agent: name, provenance: 'adhoc', status: 'enabled' }, { status: 201 });
      }),
      http.patch(`${API_BASE_URL}/admin/agents/:name`, async ({ request }) => {
        captured.patch = (await request.json()) as CapturedModelBody;
        return HttpResponse.json({ ok: true });
      })
    );

    renderAgentsRoute();
    expect(await screen.findByText('alpha')).toBeInTheDocument();

    // Create: pick a provider for the default route.
    await user.type(screen.getByLabelText('Agent name'), 'beta');
    await user.type(screen.getByLabelText('System prompt'), 'Beta prompt');
    await user.selectOptions(screen.getByLabelText('Model provider'), 'openai-gpt4');
    await user.click(screen.getByRole('button', { name: 'Create agent' }));

    await waitFor(() => expect(captured.create).toBeTruthy());
    expect(captured.create?.model_overrides?.routes?.default?.[0]?.provider_id).toBe('openai-gpt4');

    // Edit alpha: the existing provider is pre-selected, then changed.
    await user.click(screen.getByRole('button', { name: 'Edit alpha' }));
    await waitFor(() =>
      expect(screen.getByLabelText<HTMLSelectElement>('Model provider').value).toBe('ollama-local')
    );
    await user.selectOptions(screen.getByLabelText('Model provider'), 'openai-gpt4');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(captured.patch).toBeTruthy());
    expect(captured.patch?.model_overrides?.routes?.default?.[0]?.provider_id).toBe('openai-gpt4');
  });
});

describe('agents page IM connector overrides', () => {
  const emptyBindings = {
    kbIds: [],
    mcpServers: [],
    oauth: [],
    secrets: [],
    skills: [],
    users: [],
  };

  it('shows config overrides yaml in the bindings panel and saves edits via PATCH', async () => {
    const user = userEvent.setup({ delay: null });
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        config_overrides_yaml: 'im:\n  slack:\n    bot_token_env: SLACK_BOT_TOKEN\n',
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    };

    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: { ...emptyBindings } },
      detailByAgent,
    });

    const captured: { patch?: { config_overrides_yaml?: string } } = {};
    server.use(
      http.patch(`${API_BASE_URL}/admin/agents/:name`, async ({ request }) => {
        captured.patch = (await request.json()) as { config_overrides_yaml?: string };
        return HttpResponse.json({ ok: true });
      })
    );

    renderAgentsRoute();
    expect(await screen.findByText('alpha')).toBeInTheDocument();

    const section = (await screen.findByRole('heading', { name: 'IM Connectors' })).closest(
      'section'
    );
    expect(section).not.toBeNull();
    const controls = within(section as HTMLElement);
    const textarea = controls.getByLabelText<HTMLTextAreaElement>('Advanced overrides (YAML)');
    await waitFor(() => expect(textarea.value).toContain('bot_token_env: SLACK_BOT_TOKEN'));

    fireEvent.change(textarea, {
      target: { value: 'im:\n  telegram:\n    bot_token_env: TG_TOKEN\n' },
    });
    await user.click(controls.getByRole('button', { name: 'Save overrides' }));

    await waitFor(() => expect(captured.patch).toBeTruthy());
    expect(captured.patch?.config_overrides_yaml).toContain('telegram');
    expect(captured.patch?.config_overrides_yaml).toContain('TG_TOKEN');
  });

  it('hides the overrides editor controls from viewers', async () => {
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ];
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        config_overrides_yaml: 'im:\n  slack:\n    bot_token_env: SLACK_BOT_TOKEN\n',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    };

    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: { ...emptyBindings } },
      detailByAgent,
      role: 'viewer',
    });

    renderAgentsRoute();
    expect(await screen.findByText('alpha')).toBeInTheDocument();

    const section = (await screen.findByRole('heading', { name: 'IM Connectors' })).closest(
      'section'
    );
    const controls = within(section as HTMLElement);
    expect(controls.queryByRole('button', { name: 'Save overrides' })).not.toBeInTheDocument();
  });
});

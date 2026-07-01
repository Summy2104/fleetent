import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { AdminRoutes } from '@/app/routes'
import { ThemeProvider } from '@/app/theme'
import { I18nProvider } from '@/i18n'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

type AgentRecord = {
  agent_name: string
  allowed_tools: string[]
  is_default?: boolean
  placement?: { node_id: string } | null
  provenance: string
  runtime?: { health?: string | null; node_id?: string | null; phase?: string | null } | null
  status: string
  system_prompt: string
}

type AgentDetailRecord = {
  agent: string
  allowed_tools: string[]
  config_overrides_yaml?: string
  model_overrides?: Record<string, unknown>
  status: string
  supports_dm?: boolean
  supports_groups?: boolean
  system_prompt: string
}

type AgentBindingState = {
  groups?: Array<{ group_id: string; platform: string }>
  kbIds: string[]
  mcpServers: string[]
  secrets: Array<{ env_name: string; mode: string; status: string }>
  skills: Array<{ enabled: boolean; skill_name: string }>
  users: string[]
}

function renderAgentsRoute(initialPath = '/agents'): void {
  render(
    <I18nProvider>
      <ThemeProvider>
        <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
          <AppQueryProvider>
            <MemoryRouter initialEntries={[initialPath]}>
              <AdminRoutes />
            </MemoryRouter>
          </AppQueryProvider>
        </AuthProvider>
      </ThemeProvider>
    </I18nProvider>
  )
}

// Open the row action menu for an agent on the list page.
async function openActions(user: ReturnType<typeof userEvent.setup>, name: string): Promise<void> {
  await user.click(await screen.findByRole('button', { name: `Actions for ${name}` }))
}

// Pick a state-changing row action: open the menu, click the item, then confirm in
// the AlertDialog. The confirm button carries the same label as the menu item.
async function runConfirmedAction(
  user: ReturnType<typeof userEvent.setup>,
  name: string,
  label: string
): Promise<void> {
  await openActions(user, name)
  await user.click(await screen.findByRole('menuitem', { name: label }))
  const confirm = await screen.findByRole('alertdialog')
  await user.click(within(confirm).getByRole('button', { name: label }))
}

// Drive a Radix <Select>: open the trigger (a combobox) and click the option text.
async function selectOption(
  user: ReturnType<typeof userEvent.setup>,
  trigger: HTMLElement,
  optionText: string | RegExp
): Promise<void> {
  await user.click(trigger)
  await user.click(await screen.findByRole('option', { name: optionText }))
}

function installAgentBindingHandlers({
  agents,
  bindingsByAgent,
  detailByAgent,
  role = 'admin',
}: {
  agents: AgentRecord[]
  bindingsByAgent: Record<string, AgentBindingState>
  detailByAgent: Record<string, AgentDetailRecord>
  role?: 'admin' | 'viewer'
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
      expect(new URL(request.url).searchParams.get('include_archived')).toBe('true')
      return HttpResponse.json(agents)
    }),
    http.get(`${API_BASE_URL}/admin/agents/:name`, ({ params }) =>
      HttpResponse.json(detailByAgent[String(params.name)])
    ),
    http.get(`${API_BASE_URL}/admin/agents/:name/skills`, ({ params }) =>
      HttpResponse.json(bindingsByAgent[String(params.name)].skills)
    ),
    http.get(`${API_BASE_URL}/admin/agents/:name/users`, ({ params }) =>
      HttpResponse.json(bindingsByAgent[String(params.name)].users)
    ),
    http.get(`${API_BASE_URL}/admin/agents/:name/groups`, ({ params }) =>
      HttpResponse.json(bindingsByAgent[String(params.name)].groups ?? [])
    ),
    http.get(`${API_BASE_URL}/admin/agents/:name/mcp`, ({ params }) =>
      HttpResponse.json(bindingsByAgent[String(params.name)].mcpServers)
    ),
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
    // The Secrets tab also pulls declared required-env slots.
    http.get(`${API_BASE_URL}/admin/agents/:name/required-env`, ({ params }) =>
      HttpResponse.json({ agent: String(params.name), required_env: [] })
    ),
    http.get(`${API_BASE_URL}/admin/skills`, () =>
      HttpResponse.json([{ name: 'crm-ops' }, { name: 'incident-bridge' }])
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
    http.get(`${API_BASE_URL}/admin/models`, () =>
      HttpResponse.json([
        {
          base_url: 'https://api.openai.example/v1',
          description: null,
          id: 'openai-gpt4',
          endpoint: null,
          input_price_per_1k: null,
          max_tokens: null,
          model_name: 'gpt-4o',
          output_price_per_1k: null,
          params: null,
          protocol: 'openai_chat',
          provider_id: 'openai',
        },
        {
          base_url: 'http://localhost:11434/v1',
          description: null,
          id: 'ollama-local',
          endpoint: null,
          input_price_per_1k: null,
          max_tokens: null,
          model_name: 'llama3',
          output_price_per_1k: null,
          params: null,
          protocol: 'openai_chat',
          provider_id: 'local',
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
          id: 'openai',
          model_count: 1,
          provider: 'openai',
        },
        {
          api_key: null,
          api_key_env: 'FLEETENT_OLLAMA_KEY',
          api_key_set: false,
          base_url: 'http://localhost:11434/v1',
          description: null,
          id: 'local',
          model_count: 1,
          provider: 'local',
        },
      ])
    )
  )
}

describe('agents list page lifecycle', () => {
  it('supports lifecycle mutations and list refreshes', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: ['read_file'],
        is_default: false,
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: ['read_file'],
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    }
    const bindingsByAgent: Record<string, AgentBindingState> = {
      alpha: {
        kbIds: [],
        mcpServers: [],
        secrets: [],
        skills: [],
        users: [],
      },
      beta: {
        kbIds: [],
        mcpServers: [],
        secrets: [],
        skills: [],
        users: [],
      },
    }

    installAgentBindingHandlers({ agents, bindingsByAgent, detailByAgent })

    server.use(
      http.post(`${API_BASE_URL}/admin/agents`, async ({ request }) => {
        const body = (await request.json()) as {
          allowed_tools: string[]
          name: string
          system_prompt: string
        }
        agents.splice(
          0,
          agents.length,
          ...[
            ...agents,
            {
              agent_name: body.name,
              allowed_tools: body.allowed_tools,
              is_default: false,
              provenance: 'adhoc',
              status: 'enabled',
              system_prompt: body.system_prompt,
            },
          ]
        )
        detailByAgent[body.name] = {
          agent: body.name,
          allowed_tools: body.allowed_tools,
          status: 'enabled',
          supports_dm: false,
          supports_groups: false,
          system_prompt: body.system_prompt,
        }
        return HttpResponse.json({ agent: body.name, status: 'enabled', provenance: 'adhoc' }, { status: 201 })
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/disable`, ({ params }) => {
        const nextAgents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'disabled' } : agent
        )
        agents.splice(0, agents.length, ...nextAgents)
        detailByAgent[String(params.name)] = {
          ...detailByAgent[String(params.name)],
          status: 'disabled',
        }
        return HttpResponse.json({ ok: true })
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/enable`, ({ params }) => {
        const nextAgents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'enabled' } : agent
        )
        agents.splice(0, agents.length, ...nextAgents)
        detailByAgent[String(params.name)] = {
          ...detailByAgent[String(params.name)],
          status: 'enabled',
        }
        return HttpResponse.json({ ok: true })
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/archive`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true')
        const nextAgents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'archived' } : agent
        )
        agents.splice(0, agents.length, ...nextAgents)
        detailByAgent[String(params.name)] = {
          ...detailByAgent[String(params.name)],
          status: 'archived',
        }
        return HttpResponse.json({ ok: true })
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/restore`, ({ params }) => {
        const nextAgents = agents.map((agent) =>
          agent.agent_name === params.name ? { ...agent, status: 'enabled' } : agent
        )
        agents.splice(0, agents.length, ...nextAgents)
        detailByAgent[String(params.name)] = {
          ...detailByAgent[String(params.name)],
          status: 'enabled',
        }
        return HttpResponse.json({ ok: true })
      }),
      http.post(`${API_BASE_URL}/admin/agents/:name/clone`, async ({ params, request }) => {
        const body = (await request.json()) as { new_name: string }
        const source = agents.find((agent) => agent.agent_name === params.name) as AgentRecord
        agents.push({ ...source, agent_name: body.new_name })
        detailByAgent[body.new_name] = {
          ...detailByAgent[String(params.name)],
          agent: body.new_name,
        }
        bindingsByAgent[body.new_name] = { ...bindingsByAgent[String(params.name)] }
        return HttpResponse.json({ ok: true })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/:name`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true')
        const nextAgents = agents.filter((agent) => agent.agent_name !== params.name)
        agents.splice(0, agents.length, ...nextAgents)
        delete detailByAgent[String(params.name)]
        delete bindingsByAgent[String(params.name)]
        return HttpResponse.json({ ok: true })
      })
    )

    renderAgentsRoute()
    expect(await screen.findByText('alpha')).toBeInTheDocument()
    expect(screen.getByText('Alpha prompt')).toBeInTheDocument()

    // Create a new agent via the "New Agent" dialog.
    await user.click(screen.getByRole('button', { name: 'New Agent' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Agent name'), 'beta')
    await user.type(within(dialog).getByLabelText('System prompt'), 'Beta prompt')
    await user.type(within(dialog).getByLabelText('Allowed tools (comma-separated)'), 'read_file,write_file')
    await user.click(within(dialog).getByRole('button', { name: 'Create agent' }))
    expect(await screen.findByText('beta')).toBeInTheDocument()

    // Disable alpha via its row action menu (confirmed).
    await runConfirmedAction(user, 'alpha', 'Disable')
    expect(await screen.findByText('disabled')).toBeInTheDocument()

    // Enable alpha again (confirmed).
    await runConfirmedAction(user, 'alpha', 'Enable')
    await waitFor(() => {
      expect(screen.getAllByText('enabled').length).toBeGreaterThan(0)
    })

    // Archive alpha (confirmed; sends X-Confirm header).
    await runConfirmedAction(user, 'alpha', 'Archive')
    expect(await screen.findByText('archived')).toBeInTheDocument()

    // Restore alpha (confirmed).
    await runConfirmedAction(user, 'alpha', 'Restore')
    await waitFor(() => {
      expect(screen.getAllByText('enabled').length).toBeGreaterThan(0)
    })

    // Clone alpha → alpha-copy.
    await openActions(user, 'alpha')
    await user.click(await screen.findByRole('menuitem', { name: 'Clone' }))
    expect(await screen.findByText('alpha-copy')).toBeInTheDocument()

    // Delete beta via the action menu + confirm dialog.
    await openActions(user, 'beta')
    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    const confirm = await screen.findByRole('alertdialog')
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }))
    await waitFor(() => {
      expect(screen.queryByText('beta')).not.toBeInTheDocument()
    })
  })

  it('toggles the default badge via the row action menu', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        is_default: false,
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: { kbIds: [], mcpServers: [], secrets: [], skills: [], users: [] } },
      detailByAgent: {
        alpha: { agent: 'alpha', allowed_tools: [], status: 'enabled', system_prompt: 'p' },
      },
    })
    server.use(
      http.put(`${API_BASE_URL}/admin/agents/alpha/default`, () => {
        agents.splice(0, agents.length, ...agents.map((agent) => ({ ...agent, is_default: true })))
        return HttpResponse.json({ agent: 'alpha', is_default: true })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/default`, () => {
        agents.splice(0, agents.length, ...agents.map((agent) => ({ ...agent, is_default: false })))
        return HttpResponse.json({ cleared: true })
      })
    )

    renderAgentsRoute()
    expect(await screen.findByText('alpha')).toBeInTheDocument()
    expect(screen.queryByText('adhoc')).not.toBeInTheDocument()

    await runConfirmedAction(user, 'alpha', 'Set as default')
    expect(await screen.findByText('default')).toBeInTheDocument()

    await runConfirmedAction(user, 'alpha', 'Clear default')
    await waitFor(() => {
      expect(screen.queryByText('default')).not.toBeInTheDocument()
    })
  })
})

describe('agent configure page bindings', () => {
  it('edits versions, skills, mcp, kb, users, im, and write-only secrets', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: ['read_file'],
        is_default: false,
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: ['read_file'],
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    }
    const bindingsByAgent: Record<string, AgentBindingState> = {
      alpha: {
        kbIds: ['support'],
        mcpServers: ['filesystem'],
        secrets: [{ env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'unset' }],
        skills: [
          { enabled: true, skill_name: 'crm-ops' },
          { enabled: false, skill_name: 'incident-bridge' },
        ],
        users: ['u1'],
      },
    }
    let versionRequests = 0
    let activateRequests = 0

    installAgentBindingHandlers({ agents, bindingsByAgent, detailByAgent })

    server.use(
      http.get(`${API_BASE_URL}/admin/agents/alpha/versions`, () => {
        versionRequests += 1
        return HttpResponse.json([])
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/versions/:version/activate`, () => {
        activateRequests += 1
        return HttpResponse.json({})
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/skills/incident-bridge`, async ({ request }) => {
        expect(await request.json()).toEqual({ enabled: true })
        bindingsByAgent.alpha.skills = bindingsByAgent.alpha.skills.map((skill) =>
          skill.skill_name === 'incident-bridge' ? { ...skill, enabled: true } : skill
        )
        return HttpResponse.json({ agent: 'alpha', enabled: true, skill_name: 'incident-bridge' })
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/mcp/github`, () => {
        bindingsByAgent.alpha.mcpServers = ['filesystem', 'github']
        return HttpResponse.json({ agent: 'alpha', bound: true, server_id: 'github' })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/mcp/filesystem`, () => {
        bindingsByAgent.alpha.mcpServers = ['github']
        return HttpResponse.json({ agent: 'alpha', bound: false, server_id: 'filesystem' })
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/kbs`, async ({ request }) => {
        expect(await request.json()).toEqual({ kb_id: 'sales' })
        bindingsByAgent.alpha.kbIds = ['support', 'sales']
        return HttpResponse.json({ agent: 'alpha', bound: true, kb_id: 'sales' })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/kbs/support`, () => {
        bindingsByAgent.alpha.kbIds = ['sales']
        return HttpResponse.json({ agent: 'alpha', bound: false, kb_id: 'support' })
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/users/u2`, () => {
        bindingsByAgent.alpha.users = ['u1', 'u2']
        return HttpResponse.json({ agent: 'alpha', bound: true, user_id: 'u2' })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/users/u1`, () => {
        bindingsByAgent.alpha.users = ['u2']
        return HttpResponse.json({ agent: 'alpha', bound: false, user_id: 'u1' })
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/groups`, async ({ request }) => {
        expect(await request.json()).toEqual({ group_id: 'C0123', platform: 'slack' })
        bindingsByAgent.alpha.groups = [
          ...(bindingsByAgent.alpha.groups ?? []),
          { group_id: 'C0123', platform: 'slack' },
        ]
        return HttpResponse.json({ agent: 'alpha', bound: true, group_id: 'C0123', platform: 'slack' }, { status: 201 })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/groups/slack/C0123`, () => {
        bindingsByAgent.alpha.groups = (bindingsByAgent.alpha.groups ?? []).filter(
          (group) => !(group.platform === 'slack' && group.group_id === 'C0123')
        )
        return new HttpResponse(null, { status: 204 })
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/im-capabilities`, async ({ request }) => {
        expect(await request.json()).toEqual({ supports_dm: true, supports_groups: true })
        detailByAgent.alpha = { ...detailByAgent.alpha, supports_dm: true, supports_groups: true }
        return HttpResponse.json({ agent: 'alpha', supports_dm: true, supports_groups: true })
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/secrets/FLEETENT_ALPHA_API_KEY`, async ({ request }) => {
        expect(await request.json()).toEqual({ value: 'sk-live-secret' })
        bindingsByAgent.alpha.secrets = [{ env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'set' }]
        return HttpResponse.json({ env_name: 'FLEETENT_ALPHA_API_KEY', status: 'set' })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/secrets/FLEETENT_ALPHA_API_KEY`, () => {
        bindingsByAgent.alpha.secrets = [{ env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'unset' }]
        return HttpResponse.json({ env_name: 'FLEETENT_ALPHA_API_KEY', status: 'unset' })
      })
    )

    // Configure lives on its own route; navigate straight to it.
    renderAgentsRoute('/agents/alpha/configure')
    expect(await screen.findByRole('heading', { name: 'Configure · alpha' })).toBeInTheDocument()
    expect(screen.queryByText('adhoc')).not.toBeInTheDocument()
    expect(screen.queryByText('Version History')).not.toBeInTheDocument()

    // Skills tab: each row a trailing toggle; incident-bridge starts disabled → toggle it on.
    await user.click(screen.getByRole('tab', { name: 'Skills' }))
    expect(await screen.findByText('crm-ops')).toBeInTheDocument()
    await user.click(screen.getByRole('switch', { name: 'Enable incident-bridge' }))
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Disable incident-bridge' })).toBeInTheDocument()
    })

    // MCP Servers tab: bind github (unbound), then unbind filesystem (bound).
    await user.click(screen.getByRole('tab', { name: 'MCP Servers' }))
    expect(await screen.findByText('filesystem')).toBeInTheDocument()
    await user.click(screen.getByRole('switch', { name: 'Bind github' }))
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Unbind github' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('switch', { name: 'Unbind filesystem' }))
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Bind filesystem' })).toBeInTheDocument()
    })

    // Knowledge Bases tab: bind sales, unbind support.
    await user.click(screen.getByRole('tab', { name: 'Knowledge Bases' }))
    expect(await screen.findByText('support · Support knowledge')).toBeInTheDocument()
    await selectOption(user, screen.getByRole('combobox'), 'sales · Sales knowledge')
    expect(await screen.findByText('sales · Sales knowledge')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remove support · Support knowledge' }))
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Remove support · Support knowledge' })).not.toBeInTheDocument()
    })

    // IM Capabilities tab: bind a user, add a group, toggle capabilities.
    await user.click(screen.getByRole('tab', { name: 'IM Capabilities' }))
    expect(await screen.findByText('alice@fleetent.test')).toBeInTheDocument()
    // The tab has a platform select and the Users BindSelectEditor combobox;
    // the latter is the last combobox rendered in this tab.
    const comboboxes = screen.getAllByRole('combobox')
    const usersCombobox = comboboxes[comboboxes.length - 1]
    await selectOption(user, usersCombobox, 'bob@fleetent.test')
    expect(await screen.findByText('bob@fleetent.test')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remove alice@fleetent.test' }))
    // Assert the binding chip is gone via its Remove button: the name also lingers
    // as a Base UI Select option label, so a bare text query would still match.
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Remove alice@fleetent.test' })).not.toBeInTheDocument()
    })

    // Add an IM group (the group-id input is identified by its placeholder).
    await user.type(screen.getByPlaceholderText('e.g. C0123 / -1001234567'), 'C0123')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('C0123')).toBeInTheDocument()

    // Toggle the capability switches and persist them.
    await user.click(screen.getByRole('switch', { name: 'Supports direct messages' }))
    await user.click(screen.getByRole('switch', { name: 'Supports group chats' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Supports direct messages' })).toBeChecked()
    })

    // Remove the IM group.
    await user.click(screen.getByRole('button', { name: 'Remove slack:C0123' }))
    await waitFor(() => {
      expect(screen.queryByText('C0123')).not.toBeInTheDocument()
    })

    // Secrets tab: write-only secret value, never echoed back.
    await user.click(screen.getByRole('tab', { name: 'Secrets' }))
    expect(await screen.findByText('FLEETENT_ALPHA_API_KEY')).toBeInTheDocument()
    expect(screen.getByText('unset')).toBeInTheDocument()
    expect(screen.queryByText('sk-live-secret')).not.toBeInTheDocument()
    await selectOption(user, screen.getByRole('combobox'), 'FLEETENT_ALPHA_API_KEY')
    await user.type(screen.getByPlaceholderText('secret value'), 'sk-live-secret')
    await user.click(screen.getByRole('button', { name: 'Set Secret' }))
    await waitFor(() => {
      expect(screen.getByText('set')).toBeInTheDocument()
    })
    expect(screen.queryByDisplayValue('sk-live-secret')).not.toBeInTheDocument()
    expect(screen.queryByText('sk-live-secret')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear FLEETENT_ALPHA_API_KEY' }))
    await waitFor(() => {
      expect(screen.getByText('unset')).toBeInTheDocument()
    })

    // Deploy tab is retired: deployment is automatic via node reconcile, so the
    // platform exposes no deploy trigger. Version history is gone too; YAML export
    // now lives on the Overview tab.
    expect(screen.queryByRole('tab', { name: 'Deploy' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Overview' }))
    expect(await screen.findByRole('button', { name: 'Export YAML' })).toBeInTheDocument()
    expect(screen.queryByText('Version History')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Activate' })).not.toBeInTheDocument()
    expect(versionRequests).toBe(0)
    expect(activateRequests).toBe(0)
  })

  it('keeps viewers read-only across binding tabs', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: ['read_file'],
        is_default: false,
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: ['read_file'],
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    }
    const bindingsByAgent: Record<string, AgentBindingState> = {
      alpha: {
        kbIds: ['support'],
        mcpServers: ['filesystem'],
        secrets: [{ env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'set' }],
        skills: [{ enabled: true, skill_name: 'crm-ops' }],
        users: ['u1'],
      },
    }

    installAgentBindingHandlers({ agents, bindingsByAgent, detailByAgent, role: 'viewer' })

    server.use(
      http.get(`${API_BASE_URL}/admin/agents/alpha/versions`, () =>
        HttpResponse.json([{ id: 1, is_active: true, version: 1 }])
      )
    )

    renderAgentsRoute('/agents/alpha/configure')
    expect(await screen.findByRole('heading', { name: 'Configure · alpha' })).toBeInTheDocument()

    // MCP Servers tab: read-only — servers show, but every toggle is disabled.
    await user.click(screen.getByRole('tab', { name: 'MCP Servers' }))
    expect(await screen.findByText('filesystem')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Unbind filesystem' })).toHaveAttribute('aria-disabled', 'true')

    // Skills tab: read-only — skills show, but every toggle is disabled.
    await user.click(screen.getByRole('tab', { name: 'Skills' }))
    expect(await screen.findByText('crm-ops')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Disable crm-ops' })).toHaveAttribute('aria-disabled', 'true')

    // Secrets tab: no set form, no clear buttons.
    await user.click(screen.getByRole('tab', { name: 'Secrets' }))
    expect(await screen.findByText('FLEETENT_ALPHA_API_KEY')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Set Secret' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Clear / })).not.toBeInTheDocument()

    // IM tab: capability switches are disabled and there is no save control.
    await user.click(screen.getByRole('tab', { name: 'IM Capabilities' }))
    expect(await screen.findByText('alice@fleetent.test')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Supports direct messages' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByPlaceholderText('e.g. C0123 / -1001234567')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument()
  })
})

describe('agents list page status display', () => {
  const emptyBindings = {
    kbIds: [],
    mcpServers: [],
    secrets: [],
    skills: [],
    users: [],
  }

  it('shows the desired-state status badge for a running agent', async () => {
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
    ]
    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: emptyBindings },
      detailByAgent: {
        alpha: { agent: 'alpha', allowed_tools: [], status: 'enabled', system_prompt: 'Alpha prompt' },
      },
    })

    renderAgentsRoute()

    expect(await screen.findByText('alpha')).toBeInTheDocument()
    expect(screen.getByText('enabled')).toBeInTheDocument()
  })

  it('shows the disabled status badge when the agent is not running', async () => {
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
    ]
    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: emptyBindings },
      detailByAgent: {
        alpha: { agent: 'alpha', allowed_tools: [], status: 'disabled', system_prompt: 'p' },
      },
    })

    renderAgentsRoute()

    expect(await screen.findByText('alpha')).toBeInTheDocument()
    expect(screen.getByText('disabled')).toBeInTheDocument()
  })
})

describe('agents configure page model binding', () => {
  it('round-trips the model provider selection on the overview tab', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        model_overrides: { routes: { default: [{ model_id: 'ollama-local' }] } },
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    }

    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: { kbIds: [], mcpServers: [], secrets: [], skills: [], users: [] } },
      detailByAgent,
    })

    type CapturedModelBody = {
      model_overrides?: { routes?: Record<string, Array<{ model_id?: string }>> }
    }
    const captured: { patch?: CapturedModelBody } = {}
    server.use(
      http.patch(`${API_BASE_URL}/admin/agents/:name`, async ({ request }) => {
        captured.patch = (await request.json()) as CapturedModelBody
        return HttpResponse.json({ ok: true })
      })
    )

    renderAgentsRoute('/agents/alpha/configure')
    expect(await screen.findByRole('heading', { name: 'Configure · alpha' })).toBeInTheDocument()

    // Overview tab is the default. The existing provider is pre-selected on the trigger.
    const trigger = screen.getByRole('combobox', { name: 'Model provider' })
    await waitFor(() => expect(trigger).toHaveTextContent('ollama-local'))

    // Switch to the openai provider and save.
    await selectOption(user, trigger, /openai-gpt4/)
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(captured.patch).toBeTruthy())
    expect(captured.patch?.model_overrides?.routes?.default?.[0]?.model_id).toBe('openai-gpt4')
  })

  it('writes a per-agent provider key override for the selected model', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        model_overrides: { routes: { default: [{ model_id: 'openai-gpt4' }] } },
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    }
    const bindingsByAgent = {
      alpha: {
        kbIds: [],
        mcpServers: [],
        secrets: [{ env_name: 'FLEETENT_OPENAI_KEY', mode: 'inject', status: 'unset' }],
        skills: [],
        users: [],
      },
    }

    installAgentBindingHandlers({
      agents,
      bindingsByAgent,
      detailByAgent,
    })

    server.use(
      http.patch(`${API_BASE_URL}/admin/agents/:name`, () => HttpResponse.json({ ok: true })),
      http.put(`${API_BASE_URL}/admin/agents/alpha/secrets/FLEETENT_OPENAI_KEY`, async ({ request }) => {
        expect(await request.json()).toEqual({ value: 'sk-live-secret' })
        bindingsByAgent.alpha.secrets = [{ env_name: 'FLEETENT_OPENAI_KEY', mode: 'inject', status: 'set' }]
        return HttpResponse.json({ env_name: 'FLEETENT_OPENAI_KEY', status: 'set' })
      })
    )

    renderAgentsRoute('/agents/alpha/configure')
    expect(await screen.findByRole('heading', { name: 'Configure · alpha' })).toBeInTheDocument()
    expect(await screen.findByText('FLEETENT_OPENAI_KEY · unset')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Provider API Key Override'), 'sk-live-secret')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(bindingsByAgent.alpha.secrets[0].status).toBe('set')
    })
  })

  it('clears the provider key override when saved empty', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        model_overrides: { routes: { default: [{ model_id: 'openai-gpt4' }] } },
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    }
    const bindingsByAgent = {
      alpha: {
        kbIds: [],
        mcpServers: [],
        secrets: [{ env_name: 'FLEETENT_OPENAI_KEY', mode: 'inject', status: 'set' }],
        skills: [],
        users: [],
      },
    }

    installAgentBindingHandlers({
      agents,
      bindingsByAgent,
      detailByAgent,
    })

    server.use(
      http.patch(`${API_BASE_URL}/admin/agents/:name`, () => HttpResponse.json({ ok: true })),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/secrets/FLEETENT_OPENAI_KEY`, () => {
        bindingsByAgent.alpha.secrets = [{ env_name: 'FLEETENT_OPENAI_KEY', mode: 'inject', status: 'unset' }]
        return HttpResponse.json({ env_name: 'FLEETENT_OPENAI_KEY', status: 'unset' })
      })
    )

    renderAgentsRoute('/agents/alpha/configure')
    expect(await screen.findByText('FLEETENT_OPENAI_KEY · set')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Provider API Key Override'), 'temp')
    await user.clear(screen.getByLabelText('Provider API Key Override'))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(bindingsByAgent.alpha.secrets[0].status).toBe('unset')
    })
  })

  it('configures embedding/memory_extraction/image_generation routes independently and preserves them on save', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        model_overrides: {
          routes: {
            default: [{ model_id: 'ollama-local' }],
            embedding: [{ model_id: 'embed-1' }],
            memory_extraction: [{ model_id: 'openai-gpt4' }],
          },
        },
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    }

    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: { kbIds: [], mcpServers: [], secrets: [], skills: [], users: [] } },
      detailByAgent,
    })

    server.use(
      http.get(`${API_BASE_URL}/admin/models`, () =>
        HttpResponse.json([
          {
            base_url: 'https://api.openai.example/v1',
            description: null,
            endpoint: null,
            id: 'openai-gpt4',
            input_price_per_1k: null,
            max_tokens: null,
            model_name: 'gpt-4o',
            output_price_per_1k: null,
            params: null,
            protocol: 'openai_chat',
            provider_id: 'openai',
          },
          {
            base_url: 'http://localhost:11434/v1',
            description: null,
            endpoint: null,
            id: 'ollama-local',
            input_price_per_1k: null,
            max_tokens: null,
            model_name: 'llama3',
            output_price_per_1k: null,
            params: null,
            protocol: 'openai_chat',
            provider_id: 'local',
          },
          {
            base_url: null,
            description: null,
            endpoint: 'http://localhost:11434/v1/embeddings',
            id: 'embed-1',
            input_price_per_1k: null,
            max_tokens: null,
            model_name: 'bge-small',
            output_price_per_1k: null,
            params: null,
            protocol: 'http_embedding',
            provider_id: 'local',
          },
          {
            base_url: null,
            description: null,
            endpoint: 'https://api.openai.example/v1/images',
            id: 'imagegen-1',
            input_price_per_1k: null,
            max_tokens: null,
            model_name: 'gpt-image-1',
            output_price_per_1k: null,
            params: null,
            protocol: 'openai_image_generation',
            provider_id: 'openai',
          },
        ])
      )
    )

    type CapturedModelBody = {
      model_overrides?: { routes?: Record<string, Array<{ model_id?: string }>> }
    }
    const captured: { patch?: CapturedModelBody } = {}
    server.use(
      http.patch(`${API_BASE_URL}/admin/agents/:name`, async ({ request }) => {
        captured.patch = (await request.json()) as CapturedModelBody
        return HttpResponse.json({ ok: true })
      })
    )

    renderAgentsRoute('/agents/alpha/configure')
    expect(await screen.findByRole('heading', { name: 'Configure · alpha' })).toBeInTheDocument()

    const defaultTrigger = screen.getByRole('combobox', { name: 'Model provider' })
    const embeddingTrigger = screen.getByRole('combobox', { name: 'Embedding model' })
    const memoryTrigger = screen.getByRole('combobox', { name: 'Memory extraction model' })
    const imageGenTrigger = screen.getByRole('combobox', { name: 'Image generation model' })

    await waitFor(() => expect(defaultTrigger).toHaveTextContent('ollama-local'))
    expect(embeddingTrigger).toHaveTextContent('embed-1')
    expect(memoryTrigger).toHaveTextContent('openai-gpt4')
    expect(imageGenTrigger).toHaveTextContent('Select a model')

    // The embedding selector only offers embedding-protocol models.
    await user.click(embeddingTrigger)
    expect(screen.queryByRole('option', { name: /openai-gpt4/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /ollama-local/ })).not.toBeInTheDocument()
    await user.keyboard('{Escape}')

    await selectOption(user, imageGenTrigger, /imagegen-1/)
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(captured.patch).toBeTruthy())
    const routes = captured.patch?.model_overrides?.routes ?? {}
    expect(routes.default?.[0]?.model_id).toBe('ollama-local')
    expect(routes.embedding?.[0]?.model_id).toBe('embed-1')
    expect(routes.memory_extraction?.[0]?.model_id).toBe('openai-gpt4')
    expect(routes.image_generation?.[0]?.model_id).toBe('imagegen-1')
  })

  it('offers openai_image_chat models for the image_generation binding and saves the selection', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        model_overrides: { routes: {} },
        status: 'enabled',
        supports_dm: false,
        supports_groups: false,
        system_prompt: 'Alpha prompt',
      },
    }

    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: { kbIds: [], mcpServers: [], secrets: [], skills: [], users: [] } },
      detailByAgent,
    })

    server.use(
      http.get(`${API_BASE_URL}/admin/models`, () =>
        HttpResponse.json([
          {
            base_url: 'https://api.openai.example/v1',
            description: null,
            endpoint: null,
            id: 'gpt4o',
            input_price_per_1k: null,
            max_tokens: null,
            model_name: 'gpt-4o',
            output_price_per_1k: null,
            params: null,
            protocol: 'openai_chat',
            provider_id: 'openai',
          },
          {
            base_url: null,
            description: null,
            endpoint: 'https://api.openai.example/v1/images',
            id: 'imagegen-1',
            input_price_per_1k: null,
            max_tokens: null,
            model_name: 'gpt-image-1',
            output_price_per_1k: null,
            params: null,
            protocol: 'openai_image_generation',
            provider_id: 'openai',
          },
          {
            base_url: 'https://newapi.example/v1',
            description: null,
            endpoint: null,
            id: 'imagechat-1',
            input_price_per_1k: null,
            max_tokens: null,
            model_name: 'gemini-3-pro-image-preview',
            output_price_per_1k: null,
            params: null,
            protocol: 'openai_image_chat',
            provider_id: 'newapi',
          },
        ])
      )
    )

    type CapturedModelBody = {
      model_overrides?: { routes?: Record<string, Array<{ model_id?: string }>> }
    }
    const captured: { patch?: CapturedModelBody } = {}
    server.use(
      http.patch(`${API_BASE_URL}/admin/agents/:name`, async ({ request }) => {
        captured.patch = (await request.json()) as CapturedModelBody
        return HttpResponse.json({ ok: true })
      })
    )

    renderAgentsRoute('/agents/alpha/configure')
    expect(await screen.findByRole('heading', { name: 'Configure · alpha' })).toBeInTheDocument()

    const imageGenTrigger = screen.getByRole('combobox', { name: 'Image generation model' })
    // The selector stays disabled until the model list loads; wait for it before opening.
    await waitFor(() => expect(imageGenTrigger).toBeEnabled())

    // The image_generation binding must offer both image protocols: the OpenAI Images API
    // (openai_image_generation) and Chat-Completions image models (openai_image_chat). Plain
    // chat models must never leak into it.
    await user.click(imageGenTrigger)
    expect(await screen.findByRole('option', { name: /imagechat-1/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /imagegen-1/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /gpt4o/ })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('option', { name: /imagechat-1/ }))

    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(captured.patch).toBeTruthy())
    const routes = captured.patch?.model_overrides?.routes ?? {}
    expect(routes.image_generation?.[0]?.model_id).toBe('imagechat-1')
  })
})

describe('agents configure page IM connector overrides', () => {
  it('shows config overrides yaml and saves edits via PATCH', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
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
    }

    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: { kbIds: [], mcpServers: [], secrets: [], skills: [], users: [] } },
      detailByAgent,
    })

    const captured: { patch?: { config_overrides_yaml?: string } } = {}
    server.use(
      http.patch(`${API_BASE_URL}/admin/agents/:name`, async ({ request }) => {
        captured.patch = (await request.json()) as { config_overrides_yaml?: string }
        return HttpResponse.json({ ok: true })
      })
    )

    renderAgentsRoute('/agents/alpha/configure')
    expect(await screen.findByRole('heading', { name: 'Configure · alpha' })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'IM Capabilities' }))
    const textarea = await screen.findByLabelText<HTMLTextAreaElement>('Advanced overrides (YAML)')
    await waitFor(() => expect(textarea.value).toContain('bot_token_env: SLACK_BOT_TOKEN'))

    fireEvent.change(textarea, {
      target: { value: 'im:\n  telegram:\n    bot_token_env: TG_TOKEN\n' },
    })
    await user.click(screen.getByRole('button', { name: 'Save overrides' }))

    await waitFor(() => expect(captured.patch).toBeTruthy())
    expect(captured.patch?.config_overrides_yaml).toContain('telegram')
    expect(captured.patch?.config_overrides_yaml).toContain('TG_TOKEN')
  })

  it('hides the overrides editor controls from viewers', async () => {
    const user = userEvent.setup({ delay: null })
    const agents: AgentRecord[] = [
      {
        agent_name: 'alpha',
        allowed_tools: [],
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    const detailByAgent: Record<string, AgentDetailRecord> = {
      alpha: {
        agent: 'alpha',
        allowed_tools: [],
        config_overrides_yaml: 'im:\n  slack:\n    bot_token_env: SLACK_BOT_TOKEN\n',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    }

    installAgentBindingHandlers({
      agents,
      bindingsByAgent: { alpha: { kbIds: [], mcpServers: [], secrets: [], skills: [], users: [] } },
      detailByAgent,
      role: 'viewer',
    })

    renderAgentsRoute('/agents/alpha/configure')
    expect(await screen.findByRole('heading', { name: 'Configure · alpha' })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'IM Capabilities' }))
    expect(await screen.findByLabelText('Advanced overrides (YAML)')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save overrides' })).not.toBeInTheDocument()
  })
})

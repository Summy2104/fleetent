import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/app/auth'
import {
  useAddAgentImGroupMutation,
  useAgentDetailQuery,
  useAgentGroupsQuery,
  useAgentKbsQuery,
  useAgentMcpQuery,
  useAgentSecretsQuery,
  useAgentSkillsQuery,
  useAgentsQuery,
  useAgentUsersQuery,
  useBindAgentKbMutation,
  useBindAgentMcpMutation,
  useBindAgentUserMutation,
  useClearDefaultAgentMutation,
  useDeleteAgentSecretMutation,
  useRemoveAgentImGroupMutation,
  useSetAgentImCapabilitiesMutation,
  useSetAgentSecretMutation,
  useSetAgentSkillMutation,
  useSetDefaultAgentMutation,
  useUnbindAgentKbMutation,
  useUnbindAgentMcpMutation,
  useUnbindAgentUserMutation,
} from '@/features/agents/api'

const API_BASE_URL = 'http://fleetent.test'

function createWrapper(): ({ children }: { children: ReactNode }) => JSX.Element {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </AuthProvider>
    )
  }
}

describe('agents api bindings hooks', () => {
  it('loads per-type agent bindings and refreshes affected queries after mutations', async () => {
    const { server } = await import('@/test/msw/server')

    let skillsCalls = 0
    let usersCalls = 0
    let groupsCalls = 0
    let mcpCalls = 0
    let kbsCalls = 0
    let skills = [
      { enabled: true, skill_name: 'crm-ops' },
      { enabled: false, skill_name: 'incident-bridge' },
    ]
    let mcpServers = ['filesystem']
    let users = ['u1']
    let groups = [{ platform: 'slack', group_id: 'C1' }]
    let kbIds = ['support']

    server.use(
      http.get(`${API_BASE_URL}/admin/agents/alpha/skills`, () => {
        skillsCalls += 1
        return HttpResponse.json(skills)
      }),
      http.get(`${API_BASE_URL}/admin/agents/alpha/users`, () => {
        usersCalls += 1
        return HttpResponse.json(users)
      }),
      http.get(`${API_BASE_URL}/admin/agents/alpha/groups`, () => {
        groupsCalls += 1
        return HttpResponse.json(groups)
      }),
      http.get(`${API_BASE_URL}/admin/agents/alpha/mcp`, () => {
        mcpCalls += 1
        return HttpResponse.json(mcpServers)
      }),
      http.get(`${API_BASE_URL}/admin/agents/alpha/kbs`, () => {
        kbsCalls += 1
        return HttpResponse.json({ agent: 'alpha', kb_ids: kbIds })
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/skills/incident-bridge`, async ({ request }) => {
        expect(await request.json()).toEqual({ enabled: true })
        skills = skills.map((skill) => (skill.skill_name === 'incident-bridge' ? { ...skill, enabled: true } : skill))
        return HttpResponse.json({ agent: 'alpha', enabled: true, skill_name: 'incident-bridge' })
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/mcp/github`, () => {
        mcpServers = ['filesystem', 'github']
        return HttpResponse.json({ agent: 'alpha', bound: true, server_id: 'github' })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/mcp/filesystem`, () => {
        mcpServers = ['github']
        return HttpResponse.json({ agent: 'alpha', bound: false, server_id: 'filesystem' })
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/kbs`, async ({ request }) => {
        expect(await request.json()).toEqual({ kb_id: 'sales' })
        kbIds = ['support', 'sales']
        return HttpResponse.json({ agent: 'alpha', bound: true, kb_id: 'sales' })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/kbs/support`, () => {
        kbIds = ['sales']
        return HttpResponse.json({ agent: 'alpha', bound: false, kb_id: 'support' })
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/users/u2`, () => {
        users = ['u1', 'u2']
        return HttpResponse.json({ agent: 'alpha', bound: true, user_id: 'u2' })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/users/u1`, () => {
        users = ['u2']
        return HttpResponse.json({ agent: 'alpha', bound: false, user_id: 'u1' })
      }),
      http.post(`${API_BASE_URL}/admin/agents/alpha/groups`, async ({ request }) => {
        expect(await request.json()).toEqual({ platform: 'slack', group_id: 'C2' })
        groups = [
          { platform: 'slack', group_id: 'C1' },
          { platform: 'slack', group_id: 'C2' },
        ]
        return HttpResponse.json({ agent: 'alpha', bound: true, platform: 'slack', group_id: 'C2' })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/groups/slack/C1`, () => {
        groups = [{ platform: 'slack', group_id: 'C2' }]
        return new HttpResponse(null, { status: 204 })
      })
    )

    const wrapper = createWrapper()
    const skillsQuery = renderHook(() => useAgentSkillsQuery('alpha'), { wrapper })
    const usersQuery = renderHook(() => useAgentUsersQuery('alpha'), { wrapper })
    const groupsQuery = renderHook(() => useAgentGroupsQuery('alpha'), { wrapper })
    const mcpQuery = renderHook(() => useAgentMcpQuery('alpha'), { wrapper })
    const kbsQuery = renderHook(() => useAgentKbsQuery('alpha'), { wrapper })

    await waitFor(() => {
      expect(skillsQuery.result.current.data?.[1]).toEqual({
        enabled: false,
        skill_name: 'incident-bridge',
      })
      expect(usersQuery.result.current.data).toEqual(['u1'])
      expect(groupsQuery.result.current.data).toEqual([{ platform: 'slack', group_id: 'C1' }])
      expect(mcpQuery.result.current.data).toEqual(['filesystem'])
      expect(kbsQuery.result.current.data?.kb_ids).toEqual(['support'])
    })

    const setSkill = renderHook(() => useSetAgentSkillMutation('alpha'), { wrapper })
    const bindMcp = renderHook(() => useBindAgentMcpMutation('alpha'), { wrapper })
    const unbindMcp = renderHook(() => useUnbindAgentMcpMutation('alpha'), { wrapper })
    const bindKb = renderHook(() => useBindAgentKbMutation('alpha'), { wrapper })
    const unbindKb = renderHook(() => useUnbindAgentKbMutation('alpha'), { wrapper })
    const bindUser = renderHook(() => useBindAgentUserMutation('alpha'), { wrapper })
    const unbindUser = renderHook(() => useUnbindAgentUserMutation('alpha'), { wrapper })
    const addGroup = renderHook(() => useAddAgentImGroupMutation('alpha'), { wrapper })
    const removeGroup = renderHook(() => useRemoveAgentImGroupMutation('alpha'), { wrapper })

    let previousSkillsCalls = skillsCalls
    let previousUsersCalls = usersCalls
    let previousGroupsCalls = groupsCalls
    let previousMcpCalls = mcpCalls
    let previousKbsCalls = kbsCalls

    await setSkill.result.current.mutateAsync({ skill_name: 'incident-bridge', enabled: true })
    await waitFor(() => {
      expect(skillsCalls).toBeGreaterThan(previousSkillsCalls)
      expect(skillsQuery.result.current.data?.[1]?.enabled).toBe(true)
    })
    previousSkillsCalls = skillsCalls

    await bindMcp.result.current.mutateAsync('github')
    await waitFor(() => {
      expect(mcpCalls).toBeGreaterThan(previousMcpCalls)
      expect(mcpQuery.result.current.data).toEqual(['filesystem', 'github'])
    })
    previousMcpCalls = mcpCalls

    await unbindMcp.result.current.mutateAsync('filesystem')
    await waitFor(() => {
      expect(mcpCalls).toBeGreaterThan(previousMcpCalls)
      expect(mcpQuery.result.current.data).toEqual(['github'])
    })
    previousMcpCalls = mcpCalls

    await bindKb.result.current.mutateAsync('sales')
    await waitFor(() => {
      expect(kbsCalls).toBeGreaterThan(previousKbsCalls)
      expect(kbsQuery.result.current.data?.kb_ids).toEqual(['support', 'sales'])
    })
    previousKbsCalls = kbsCalls

    await unbindKb.result.current.mutateAsync('support')
    await waitFor(() => {
      expect(kbsCalls).toBeGreaterThan(previousKbsCalls)
      expect(kbsQuery.result.current.data?.kb_ids).toEqual(['sales'])
    })
    previousKbsCalls = kbsCalls

    await bindUser.result.current.mutateAsync('u2')
    await waitFor(() => {
      expect(usersCalls).toBeGreaterThan(previousUsersCalls)
      expect(usersQuery.result.current.data).toEqual(['u1', 'u2'])
    })
    previousUsersCalls = usersCalls

    await unbindUser.result.current.mutateAsync('u1')
    await waitFor(() => {
      expect(usersCalls).toBeGreaterThan(previousUsersCalls)
      expect(usersQuery.result.current.data).toEqual(['u2'])
    })
    previousUsersCalls = usersCalls

    await addGroup.result.current.mutateAsync({ platform: 'slack', group_id: 'C2' })
    await waitFor(() => {
      expect(groupsCalls).toBeGreaterThan(previousGroupsCalls)
      expect(groupsQuery.result.current.data).toEqual([
        { platform: 'slack', group_id: 'C1' },
        { platform: 'slack', group_id: 'C2' },
      ])
    })
    previousGroupsCalls = groupsCalls

    await removeGroup.result.current.mutateAsync({ platform: 'slack', group_id: 'C1' })
    await waitFor(() => {
      expect(groupsCalls).toBeGreaterThan(previousGroupsCalls)
      expect(groupsQuery.result.current.data).toEqual([{ platform: 'slack', group_id: 'C2' }])
    })
  })

  it('supports im access, default agent, and write-only secret management', async () => {
    const { server } = await import('@/test/msw/server')

    let agentListCalls = 0
    let detailCalls = 0
    let secretsCalls = 0
    let agents = [
      {
        agent_name: 'alpha',
        allowed_tools: ['read_file'],
        is_default: false,
        provenance: 'adhoc',
        status: 'enabled',
        system_prompt: 'Alpha prompt',
      },
    ]
    let detail = {
      agent: 'alpha',
      allowed_tools: ['read_file'],
      status: 'enabled',
      supports_dm: false,
      supports_groups: false,
      system_prompt: 'Alpha prompt',
    }
    let secrets = [{ env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'unset' }]

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, ({ request }) => {
        expect(new URL(request.url).searchParams.get('include_archived')).toBe('true')
        agentListCalls += 1
        return HttpResponse.json(agents)
      }),
      http.get(`${API_BASE_URL}/admin/agents/alpha`, () => {
        detailCalls += 1
        return HttpResponse.json(detail)
      }),
      http.get(`${API_BASE_URL}/admin/agents/alpha/secrets`, () => {
        secretsCalls += 1
        return HttpResponse.json({ agent: 'alpha', secrets })
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/im-capabilities`, async ({ request }) => {
        expect(await request.json()).toEqual({ supports_dm: true, supports_groups: true })
        detail = { ...detail, supports_dm: true, supports_groups: true }
        return HttpResponse.json({ agent: 'alpha', supports_dm: true, supports_groups: true })
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/default`, () => {
        agents = agents.map((agent) => ({ ...agent, is_default: true }))
        return HttpResponse.json({ agent: 'alpha', is_default: true })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/default`, () => {
        agents = agents.map((agent) => ({ ...agent, is_default: false }))
        return HttpResponse.json({ cleared: true })
      }),
      http.put(`${API_BASE_URL}/admin/agents/alpha/secrets/FLEETENT_ALPHA_API_KEY`, async ({ request }) => {
        expect(await request.json()).toEqual({ value: 'sk-live-secret' })
        secrets = [{ env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'set' }]
        return HttpResponse.json({ env_name: 'FLEETENT_ALPHA_API_KEY', status: 'set' })
      }),
      http.delete(`${API_BASE_URL}/admin/agents/alpha/secrets/FLEETENT_ALPHA_API_KEY`, () => {
        secrets = [{ env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'unset' }]
        return HttpResponse.json({ env_name: 'FLEETENT_ALPHA_API_KEY', status: 'unset' })
      })
    )

    const wrapper = createWrapper()
    const detailQuery = renderHook(() => useAgentDetailQuery('alpha'), { wrapper })
    const secretsQuery = renderHook(() => useAgentSecretsQuery('alpha'), { wrapper })
    renderHook(() => useAgentsQuery(), { wrapper })

    await waitFor(() => {
      expect(detailQuery.result.current.data?.supports_dm).toBe(false)
      expect(secretsQuery.result.current.data?.secrets).toEqual([
        { env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'unset' },
      ])
    })

    const setImCapabilities = renderHook(() => useSetAgentImCapabilitiesMutation('alpha'), { wrapper })
    const setDefault = renderHook(() => useSetDefaultAgentMutation('alpha'), { wrapper })
    const clearDefault = renderHook(() => useClearDefaultAgentMutation(), { wrapper })
    const setSecret = renderHook(() => useSetAgentSecretMutation('alpha', 'FLEETENT_ALPHA_API_KEY'), { wrapper })
    const deleteSecret = renderHook(() => useDeleteAgentSecretMutation('alpha', 'FLEETENT_ALPHA_API_KEY'), { wrapper })

    let previousDetailCalls = detailCalls
    let previousAgentListCalls = agentListCalls
    let previousSecretsCalls = secretsCalls

    await setImCapabilities.result.current.mutateAsync({ supports_dm: true, supports_groups: true })
    await waitFor(() => {
      expect(detailCalls).toBeGreaterThan(previousDetailCalls)
      expect(detailQuery.result.current.data?.supports_dm).toBe(true)
      expect(detailQuery.result.current.data?.supports_groups).toBe(true)
    })
    previousDetailCalls = detailCalls

    await setDefault.result.current.mutateAsync()
    await waitFor(() => {
      expect(agentListCalls).toBeGreaterThan(previousAgentListCalls)
    })
    previousAgentListCalls = agentListCalls

    const setSecretResult = await setSecret.result.current.mutateAsync('sk-live-secret')
    expect(setSecretResult).toEqual({ env_name: 'FLEETENT_ALPHA_API_KEY', status: 'set' })
    expect(JSON.stringify(setSecretResult)).not.toContain('sk-live-secret')
    await waitFor(() => {
      expect(secretsCalls).toBeGreaterThan(previousSecretsCalls)
      expect(secretsQuery.result.current.data?.secrets).toEqual([
        { env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'set' },
      ])
    })
    previousSecretsCalls = secretsCalls

    await deleteSecret.result.current.mutateAsync()
    await waitFor(() => {
      expect(secretsCalls).toBeGreaterThan(previousSecretsCalls)
      expect(secretsQuery.result.current.data?.secrets).toEqual([
        { env_name: 'FLEETENT_ALPHA_API_KEY', mode: 'inject', status: 'unset' },
      ])
    })

    await clearDefault.result.current.mutateAsync()
    await waitFor(() => {
      expect(agentListCalls).toBeGreaterThan(previousAgentListCalls)
    })
  })
})

describe('agents list dual-state contract', () => {
  it('surfaces runtime and placement from the list endpoint', async () => {
    const { server } = await import('@/test/msw/server')
    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([
          {
            agent_name: 'alpha',
            provenance: 'adhoc',
            status: 'enabled',
            runtime: { phase: 'running', health: 'ok', pid: 7, node_id: 'node-a' },
            placement: { node_id: 'node-a' },
          },
          {
            agent_name: 'beta',
            provenance: 'adhoc',
            status: 'disabled',
            runtime: null,
            placement: null,
          },
        ])
      )
    )
    const wrapper = createWrapper()

    const { result } = renderHook(() => useAgentsQuery(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [alpha, beta] = result.current.data ?? []
    expect(alpha.runtime?.phase).toBe('running')
    expect(alpha.placement?.node_id).toBe('node-a')
    expect(beta.runtime).toBeNull()
    expect(beta.placement).toBeNull()
  })
})

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import { SkillsPage } from '@/features/skills/page'
import { API_BASE_URL, renderSkills } from '@/features/skills/test/render'
import { server } from '@/test/msw/server'

type SkillRecord = {
  audit_verdict: string
  description: string
  drifted_agents: string[]
  enabling_agents: string[]
  global_enabled: boolean
  name: string
  source: string
  status: string
}

type AgentBindingRecord = {
  agent_id: number
  enabled: boolean
  name: string
}

function renderSkillsPage(): void {
  renderSkills(<SkillsPage />)
}

describe('skills page parity baseline', () => {
  // Shared read/write stubs for the skills admin surface. Each test calls this to
  // get its own fresh mutable state, then drives a single flow — splitting what was
  // one long 7-dialog test keeps each case short so it stays well inside the timeout
  // even on a CPU-starved CI runner (the old mega-test was the suite's flake source).
  function stubSkillsAdmin(): { getReloadCount: () => number } {
    let reloadCount = 0
    const activeVersion = 'sha-1'
    let skills: SkillRecord[] = [
      {
        audit_verdict: 'rejected',
        description: 'Ops runbook helper',
        drifted_agents: ['agent-b'],
        enabling_agents: ['agent-a'],
        global_enabled: true,
        name: 'ops-guide',
        source: 'adhoc',
        status: 'quarantined',
      },
      {
        audit_verdict: 'pass',
        description: 'Onboarding helper',
        drifted_agents: [],
        enabling_agents: [],
        global_enabled: false,
        name: 'welcome-pack',
        source: 'marketplace',
        status: 'archived',
      },
    ]
    let bindings: AgentBindingRecord[] = [
      { agent_id: 7, enabled: true, name: 'agent-a' },
      { agent_id: 8, enabled: false, name: 'agent-b' },
    ]

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/skills/git/status`, () => HttpResponse.json({ enabled: false })),
      http.get(`${API_BASE_URL}/admin/skills`, () => HttpResponse.json(skills)),
      http.get(`${API_BASE_URL}/admin/skills/:name/content`, ({ params }) =>
        HttpResponse.json({
          content: `---\nname: ${String(params.name ?? '')}\ndescription: skill\n---\n${String(params.name ?? '')} body`,
          name: String(params.name ?? ''),
        })
      ),
      http.post(`${API_BASE_URL}/admin/skills/:name/disable`, ({ params }) => {
        skills = skills.map((skill) =>
          skill.name === params.name ? { ...skill, global_enabled: false, status: 'active' } : skill
        )
        return HttpResponse.json({ global_enabled: 0, name: params.name })
      }),
      http.post(`${API_BASE_URL}/admin/skills/:name/enable`, ({ params }) => {
        skills = skills.map((skill) =>
          skill.name === params.name ? { ...skill, global_enabled: true, status: 'active' } : skill
        )
        return HttpResponse.json({ global_enabled: 1, name: params.name })
      }),
      http.delete(`${API_BASE_URL}/admin/skills/:name`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true')
        skills = skills.map((skill) => (skill.name === params.name ? { ...skill, status: 'archived' } : skill))
        return HttpResponse.json({ name: params.name, status: 'archived' })
      }),
      http.post(`${API_BASE_URL}/admin/skills/:name/restore`, ({ params }) => {
        skills = skills.map((skill) => (skill.name === params.name ? { ...skill, status: 'active' } : skill))
        return HttpResponse.json({ name: params.name, status: 'active' })
      }),
      http.post(`${API_BASE_URL}/admin/skills/:name/force-publish`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true')
        skills = skills.map((skill) =>
          skill.name === params.name ? { ...skill, audit_verdict: 'pass', status: 'active' } : skill
        )
        return HttpResponse.json({ forced: 1, name: params.name, status: 'active' })
      }),
      http.post(`${API_BASE_URL}/admin/skills/reload`, () => {
        reloadCount += 1
        return HttpResponse.json({ ok: true })
      }),
      http.get(`${API_BASE_URL}/admin/skills/:name/agents`, ({ params }) =>
        HttpResponse.json(
          String(params.name ?? '') === 'ops-guide' ? bindings : [{ agent_id: 9, enabled: false, name: 'agent-c' }]
        )
      ),
      http.put(`${API_BASE_URL}/admin/skills/:name/agents/:agentId`, async ({ params, request }) => {
        const body = (await request.json()) as { enabled: boolean }
        bindings = bindings.map((binding) =>
          binding.agent_id === Number(params.agentId) ? { ...binding, enabled: body.enabled } : binding
        )
        skills = skills.map((skill) =>
          skill.name === String(params.name ?? '')
            ? {
                ...skill,
                enabling_agents: bindings.filter((binding) => binding.enabled).map((binding) => binding.name),
              }
            : skill
        )
        return HttpResponse.json({
          agent_id: Number(params.agentId),
          enabled: body.enabled,
          name: String(params.name ?? ''),
        })
      }),
      http.get(`${API_BASE_URL}/admin/skills/:name/versions`, ({ params }) =>
        HttpResponse.json([
          { author: 'Ops', message: 'Initial publish', sha: 'sha-1', timestamp: '2026-06-20T10:00:00Z' },
          {
            author: 'Ops',
            message: `${String(params.name ?? '')} refresh`,
            sha: 'sha-2',
            timestamp: '2026-06-21T10:00:00Z',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/skills/:name/versions/:ref/diff`, ({ params }) =>
        HttpResponse.json({
          diff: `diff ${String(params.name ?? '')} ${
            String(params.ref ?? '') === activeVersion ? 'active' : String(params.ref ?? '')
          }`,
        })
      ),
      http.get(`${API_BASE_URL}/admin/skills/proposals`, () =>
        HttpResponse.json([
          {
            has_diff: true,
            id: 'prop-1',
            reason: 'Tighten escalation wording',
            risk_level: 'medium',
            target_skill: 'ops-guide',
            type: 'update_skill',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/skills/proposals/:id/diff`, ({ params }) =>
        HttpResponse.json({ diff: `proposal diff ${String(params.id ?? '')}` })
      ),
      http.get(`${API_BASE_URL}/admin/skills/backflow`, () => HttpResponse.json([]))
    )

    return { getReloadCount: () => reloadCount }
  }

  it('renders the skill rows with their status', async () => {
    stubSkillsAdmin()
    renderSkillsPage()

    expect(await screen.findByText('Skills')).toBeInTheDocument()
    // The DataTable renders skills as rows; each row exposes an "Actions for {name}" menu trigger.
    expect(await screen.findByRole('button', { name: 'Actions for ops-guide' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Actions for welcome-pack' })).toBeInTheDocument()
    expect(screen.getByText('quarantined')).toBeInTheDocument()
  })

  it('views the published skill content', async () => {
    const user = userEvent.setup({ delay: null })
    stubSkillsAdmin()
    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Actions for ops-guide' }))
    await user.click(await screen.findByText('View content'))
    expect(await screen.findByText(/ops-guide body/)).toBeInTheDocument()
    // Closing exercises the table's onOpenChange(false) reset path.
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('lists agent bindings and toggles one', async () => {
    const user = userEvent.setup({ delay: null })
    stubSkillsAdmin()
    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Actions for ops-guide' }))
    await user.click(await screen.findByText('Agent bindings'))
    const bindingControls = within(await screen.findByRole('dialog'))
    // Bindings load async after the dialog mounts; await the controls. Query by
    // the switch role: Base UI's Switch renders both a hidden <input> and the
    // role="switch" element sharing one label, so getByLabelText is ambiguous.
    expect(await bindingControls.findByRole('switch', { name: 'agent-a' })).toBeChecked()
    await user.click(await bindingControls.findByRole('switch', { name: 'agent-b' }))
    await waitFor(() => {
      expect(bindingControls.getByRole('switch', { name: 'agent-b' })).toBeChecked()
    })
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('shows a revision diff in the versions dialog', async () => {
    const user = userEvent.setup({ delay: null })
    stubSkillsAdmin()
    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Actions for ops-guide' }))
    await user.click(await screen.findByText('Versions'))
    const versionsDialog = await screen.findByRole('dialog')
    // Two revisions, each with its own "Diff" button; the second row is sha-2.
    const diffButtons = await within(versionsDialog).findAllByRole('button', { name: 'Diff' })
    await user.click(diffButtons[1])
    expect(await within(versionsDialog).findByText('diff ops-guide sha-2')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('keeps the proposals dialog read-only', async () => {
    const user = userEvent.setup({ delay: null })
    stubSkillsAdmin()
    renderSkillsPage()

    // Proposals dialog is read-only: shows reasons + diff, never approve/reject.
    await user.click(await screen.findByRole('button', { name: 'Actions for ops-guide' }))
    await user.click(await screen.findByText(/^Proposals/))
    const proposals = within(await screen.findByRole('dialog'))
    expect(proposals.getByText('Tighten escalation wording')).toBeInTheDocument()
    expect(proposals.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
    expect(proposals.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument()
    await user.click(proposals.getByRole('button', { name: 'Diff' }))
    expect(await screen.findByText('proposal diff prop-1')).toBeInTheDocument()
    // Close the proposal-diff dialog, then the proposals dialog.
    await user.keyboard('{Escape}')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('force-publishes a quarantined skill and drops the option afterward', async () => {
    const user = userEvent.setup({ delay: null })
    stubSkillsAdmin()
    renderSkillsPage()

    // Force publish (only offered for rejected/quarantined skills) clears quarantine.
    await user.click(await screen.findByRole('button', { name: 'Actions for ops-guide' }))
    await user.click(await screen.findByText('Force publish'))
    const forcePublishConfirm = await screen.findByRole('alertdialog')
    await user.click(within(forcePublishConfirm).getByRole('button', { name: 'Force publish' }))
    await waitFor(() => {
      expect(screen.getByText('active')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }))
    expect(screen.queryByText('Force publish')).not.toBeInTheDocument()
  })

  it('disables a skill and then surfaces the enable action', async () => {
    const user = userEvent.setup({ delay: null })
    stubSkillsAdmin()
    renderSkillsPage()

    // Disable is destructive: it opens a confirm dialog before toggling.
    await user.click(await screen.findByRole('button', { name: 'Actions for ops-guide' }))
    await user.click(await screen.findByText('Disable'))
    const disableConfirm = await screen.findByRole('alertdialog')
    await user.click(within(disableConfirm).getByRole('button', { name: 'Disable' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }))
    expect(await screen.findByText('Enable')).toBeInTheDocument()
  })

  it('archives a skill and restores an archived one', async () => {
    const user = userEvent.setup({ delay: null })
    const { getReloadCount } = stubSkillsAdmin()
    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Actions for ops-guide' }))
    await user.click(await screen.findByText('Archive'))
    const archiveConfirm = await screen.findByRole('alertdialog')
    await user.click(within(archiveConfirm).getByRole('button', { name: 'Archive' }))
    await waitFor(() => {
      expect(screen.getAllByText('archived').length).toBeGreaterThan(0)
    })
    // Wait for the confirm dialog to unmount: until it does, Base UI keeps the
    // background `aria-hidden`, so the row's action button isn't yet queryable.
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())

    // welcome-pack starts archived -> its menu offers Restore (which does not reload).
    await user.click(screen.getByRole('button', { name: 'Actions for welcome-pack' }))
    await user.click(await screen.findByText('Restore'))
    await waitFor(() => {
      expect(getReloadCount()).toBe(0)
    })
  })

  it('reloads the skill index from the header', async () => {
    const user = userEvent.setup({ delay: null })
    const { getReloadCount } = stubSkillsAdmin()
    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Reload index' }))
    await waitFor(() => {
      expect(getReloadCount()).toBe(1)
    })
  })
})

describe('skills page backflow approval', () => {
  const baseSkills: SkillRecord[] = [
    {
      audit_verdict: 'pass',
      description: 'CRM ops helper',
      drifted_agents: ['support'],
      enabling_agents: ['support'],
      global_enabled: true,
      name: 'crm-ops',
      source: 'adhoc',
      status: 'active',
    },
  ]

  function stubBaseReads(): void {
    server.use(
      http.get(`${API_BASE_URL}/admin/skills/git/status`, () => HttpResponse.json({ enabled: false })),
      http.get(`${API_BASE_URL}/admin/skills`, () => HttpResponse.json(baseSkills)),
      http.get(`${API_BASE_URL}/admin/skills/:name/content`, ({ params }) =>
        HttpResponse.json({ content: `${String(params.name ?? '')} body`, name: String(params.name ?? '') })
      ),
      http.get(`${API_BASE_URL}/admin/skills/:name/agents`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/skills/proposals`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/skills/backflow`, () =>
        HttpResponse.json([
          {
            agent_id: 7,
            agent_name: 'support',
            base_commit: 'c1',
            base_version: 'v1',
            conflict: 1,
            created_at: '2026-06-25T00:00:00Z',
            forked_as: null,
            id: 1,
            skill_name: 'crm-ops',
            status: 'pending',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/skills/backflow/:id/diff`, ({ params }) =>
        HttpResponse.json({
          conflict: true,
          diff_vs_base: `bf base ${String(params.id ?? '')}`,
          diff_vs_head: `bf head ${String(params.id ?? '')}`,
        })
      )
    )
  }

  it('lists proposals, shows diff, and posts accept/reject/fork decisions', async () => {
    const user = userEvent.setup({ delay: null })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('crm-ops-fork')
    const acceptHeaders: (string | null)[] = []
    let rejected = false
    let forkedWith: { fork_name: string } | null = null

    stubBaseReads()
    server.use(
      http.post(`${API_BASE_URL}/admin/skills/backflow/:id/accept`, ({ request }) => {
        acceptHeaders.push(request.headers.get('x-confirm'))
        return HttpResponse.json({ new_version: 'sha', ok: true, proposal_id: 1, user: 'admin' })
      }),
      http.post(`${API_BASE_URL}/admin/skills/backflow/:id/reject`, () => {
        rejected = true
        return HttpResponse.json({ ok: true, proposal_id: 1, user: 'admin' })
      }),
      http.post(`${API_BASE_URL}/admin/skills/backflow/:id/fork`, async ({ request }) => {
        forkedWith = (await request.json()) as { fork_name: string }
        return HttpResponse.json({ forked_as: forkedWith.fork_name, ok: true, proposal_id: 1, user: 'admin' })
      })
    )

    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Actions for crm-ops' }))
    await user.click(await screen.findByRole('menuitem', { name: /Backflow/ }))
    const backflow = within(await screen.findByRole('dialog'))
    expect(await backflow.findByRole('button', { name: 'Accept backflow 1' })).toBeInTheDocument()

    await user.click(backflow.getByRole('button', { name: 'View backflow diff for 1' }))
    expect(await backflow.findByText('bf head 1')).toBeInTheDocument()

    await user.click(backflow.getByRole('button', { name: 'Accept backflow 1' }))
    await waitFor(() => expect(acceptHeaders).toHaveLength(1))
    expect(confirmSpy).toHaveBeenCalled()
    expect(acceptHeaders[0]).toBe('true')

    await user.click(backflow.getByRole('button', { name: 'Reject backflow 1' }))
    await waitFor(() => expect(rejected).toBe(true))

    await user.click(backflow.getByRole('button', { name: 'Fork backflow 1' }))
    await waitFor(() => expect(forkedWith).toEqual({ fork_name: 'crm-ops-fork' }))
    expect(promptSpy).toHaveBeenCalled()

    confirmSpy.mockRestore()
    promptSpy.mockRestore()
  })

  it('does not accept a conflict proposal when confirmation is cancelled', async () => {
    const user = userEvent.setup({ delay: null })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const acceptHeaders: (string | null)[] = []

    stubBaseReads()
    server.use(
      http.post(`${API_BASE_URL}/admin/skills/backflow/:id/accept`, ({ request }) => {
        acceptHeaders.push(request.headers.get('x-confirm'))
        return HttpResponse.json({ ok: true, proposal_id: 1, user: 'admin' })
      })
    )

    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Actions for crm-ops' }))
    await user.click(await screen.findByRole('menuitem', { name: /Backflow/ }))
    const backflow = within(await screen.findByRole('dialog'))

    await user.click(await backflow.findByRole('button', { name: 'Accept backflow 1' }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(acceptHeaders).toHaveLength(0)

    confirmSpy.mockRestore()
  })
})

describe('skills page content + search', () => {
  function stubReadEndpoints(getSkills: () => SkillRecord[], getContent: () => string): void {
    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/skills/git/status`, () => HttpResponse.json({ enabled: false })),
      http.get(`${API_BASE_URL}/admin/skills`, () => HttpResponse.json(getSkills())),
      http.get(`${API_BASE_URL}/admin/skills/:name/content`, ({ params }) =>
        HttpResponse.json({ content: getContent(), name: String(params.name ?? '') })
      ),
      http.get(`${API_BASE_URL}/admin/skills/:name/agents`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/skills/proposals`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/skills/backflow`, () => HttpResponse.json([]))
    )
  }

  it('filters skills by name via the global search box', async () => {
    const user = userEvent.setup({ delay: null })
    const skills: SkillRecord[] = [
      {
        audit_verdict: 'pass',
        description: 'Onboarding helper',
        drifted_agents: [],
        enabling_agents: [],
        global_enabled: true,
        name: 'welcome-pack',
        source: 'marketplace',
        status: 'active',
      },
      {
        audit_verdict: 'pass',
        description: 'Promo helper',
        drifted_agents: [],
        enabling_agents: [],
        global_enabled: true,
        name: 'promo-helper',
        source: 'adhoc',
        status: 'active',
      },
    ]

    stubReadEndpoints(
      () => skills,
      () => 'welcome body'
    )

    renderSkillsPage()

    expect(await screen.findByRole('button', { name: 'Actions for welcome-pack' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Actions for promo-helper' })).toBeInTheDocument()

    await user.type(screen.getByPlaceholderText('Search…'), 'promo')
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Actions for welcome-pack' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Actions for promo-helper' })).toBeInTheDocument()
  })

  it('filters skills by status via the column filter', async () => {
    const user = userEvent.setup({ delay: null })
    const skills: SkillRecord[] = [
      {
        audit_verdict: 'pass',
        description: 'Active helper',
        drifted_agents: [],
        enabling_agents: [],
        global_enabled: true,
        name: 'active-skill',
        source: 'adhoc',
        status: 'active',
      },
      {
        audit_verdict: 'pass',
        description: 'Archived helper',
        drifted_agents: [],
        enabling_agents: [],
        global_enabled: false,
        name: 'archived-skill',
        source: 'adhoc',
        status: 'archived',
      },
    ]

    stubReadEndpoints(
      () => skills,
      () => 'body'
    )

    renderSkillsPage()

    expect(await screen.findByRole('button', { name: 'Actions for active-skill' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Actions for archived-skill' })).toBeInTheDocument()

    // The status column exposes a select filter ("All Status" + per-status options).
    await user.click(screen.getByRole('combobox', { name: 'Filter Status' }))
    await user.click(await screen.findByRole('option', { name: 'archived' }))
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Actions for active-skill' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Actions for archived-skill' })).toBeInTheDocument()
  })

  it('shows the published skill content in the content dialog', async () => {
    const user = userEvent.setup({ delay: null })
    const skills: SkillRecord[] = [
      {
        audit_verdict: 'pass',
        description: 'Onboarding helper',
        drifted_agents: [],
        enabling_agents: [],
        global_enabled: true,
        name: 'welcome-pack',
        source: 'marketplace',
        status: 'active',
      },
    ]
    const content = '---\nname: welcome-pack\ndescription: helper\n---\noriginal body'

    stubReadEndpoints(
      () => skills,
      () => content
    )

    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Actions for welcome-pack' }))
    await user.click(await screen.findByText('View content'))
    const dialog = await screen.findByRole('dialog')
    // Content is fetched async after the dialog mounts; await it.
    expect(await within(dialog).findByText(/original body/)).toBeInTheDocument()
    expect(within(dialog).getByText('Content · welcome-pack')).toBeInTheDocument()
  })
})

describe('skills page gitops mode', () => {
  const gitStatus = {
    branch: 'main',
    enabled: true,
    last_sync_at: '2026-07-02T08:00:00Z',
    last_sync_error: null,
    last_synced_commit: 'abc1234def5678',
    provider: 'bitbucket',
    remote_url: 'git@bitbucket.org:acme/skills.git',
    sync_interval_seconds: 300,
  }
  const gitopsSkills: SkillRecord[] = [
    {
      audit_verdict: 'rejected',
      description: 'CRM ops helper',
      drifted_agents: [],
      enabling_agents: [],
      global_enabled: true,
      name: 'crm-ops',
      source: 'adhoc',
      status: 'quarantined',
    },
    {
      audit_verdict: 'pass',
      description: 'Onboarding helper',
      drifted_agents: [],
      enabling_agents: [],
      global_enabled: false,
      name: 'welcome-pack',
      source: 'marketplace',
      status: 'archived',
    },
  ]

  function stubGitopsReads(backflow: unknown[] = []): void {
    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/skills/git/status`, () => HttpResponse.json(gitStatus)),
      http.get(`${API_BASE_URL}/admin/skills`, () => HttpResponse.json(gitopsSkills)),
      http.get(`${API_BASE_URL}/admin/skills/proposals`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/skills/backflow`, () => HttpResponse.json(backflow)),
      http.get(`${API_BASE_URL}/admin/skills/backflow/:id/diff`, ({ params }) =>
        HttpResponse.json({
          conflict: false,
          diff_vs_base: `bf base ${String(params.id ?? '')}`,
          diff_vs_head: `bf head ${String(params.id ?? '')}`,
        })
      )
    )
  }

  it('shows the read-only banner and git sync status card', async () => {
    stubGitopsReads()
    renderSkillsPage()

    expect(await screen.findByText('Managed via external git')).toBeInTheDocument()
    expect(screen.getByText('Git sync status')).toBeInTheDocument()
    expect(screen.getByText('bitbucket')).toBeInTheDocument()
    // Commit shas render truncated to 10 chars.
    expect(screen.getByText('abc1234def')).toBeInTheDocument()
    // #4: the standalone "Reload index" header action is hidden in gitops mode; "Sync now"
    // on the status card owns refresh (it reloads the index as part of the sync).
    expect(screen.queryByRole('button', { name: 'Reload index' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Sync now/ })).toBeInTheDocument()
    // Last-synced time is localized, not the raw UTC ISO string the server returns.
    expect(screen.queryByText('2026-07-02T08:00:00Z')).not.toBeInTheDocument()
  })

  it('triggers a manual git sync from the status card', async () => {
    const user = userEvent.setup({ delay: null })
    let synced = 0

    stubGitopsReads()
    server.use(
      http.post(`${API_BASE_URL}/admin/skills/git/sync`, () => {
        synced += 1
        return HttpResponse.json({ ok: true })
      })
    )

    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Sync now' }))
    await waitFor(() => expect(synced).toBe(1))
  })

  it('hides content-write row actions while keeping enable/disable', async () => {
    const user = userEvent.setup({ delay: null })
    stubGitopsReads()
    renderSkillsPage()

    // Quarantined + rejected skill: outside gitops it would offer Archive + Force publish.
    await user.click(await screen.findByRole('button', { name: 'Actions for crm-ops' }))
    expect(await screen.findByText('Disable')).toBeInTheDocument()
    expect(screen.queryByText('Archive')).not.toBeInTheDocument()
    expect(screen.queryByText('Force publish')).not.toBeInTheDocument()
    await user.keyboard('{Escape}')

    // Archived skill: outside gitops it would offer Restore.
    await user.click(screen.getByRole('button', { name: 'Actions for welcome-pack' }))
    expect(await screen.findByText('Enable')).toBeInTheDocument()
    expect(screen.queryByText('Restore')).not.toBeInTheDocument()
  })

  it('shows backflow PR state, opens a PR, and syncs backflow', async () => {
    const user = userEvent.setup({ delay: null })
    let prOpened = 0
    let backflowSynced = 0

    stubGitopsReads([
      {
        agent_id: 7,
        agent_name: 'support',
        base_commit: 'c1',
        base_version: 'v1',
        conflict: 0,
        created_at: '2026-07-01T00:00:00Z',
        forked_as: null,
        id: 1,
        pr_branch: 'backflow/7/crm-ops',
        pr_state: 'backed_up',
        pr_url: null,
        skill_name: 'crm-ops',
        status: 'pending',
      },
    ])
    server.use(
      http.post(`${API_BASE_URL}/admin/skills/backflow/:id/open-pr`, () => {
        prOpened += 1
        return HttpResponse.json({ ok: true, proposal_id: 1 })
      }),
      http.post(`${API_BASE_URL}/admin/skills/backflow/sync-backflow`, () => {
        backflowSynced += 1
        return HttpResponse.json({ ok: true })
      })
    )

    renderSkillsPage()

    await user.click(await screen.findByRole('button', { name: 'Actions for crm-ops' }))
    await user.click(await screen.findByRole('menuitem', { name: /Backflow/ }))
    const backflow = within(await screen.findByRole('dialog'))

    expect(await backflow.findByText('backed_up')).toBeInTheDocument()
    expect(backflow.getByText('backflow/7/crm-ops')).toBeInTheDocument()

    await user.click(backflow.getByRole('button', { name: 'Open PR 1' }))
    await waitFor(() => expect(prOpened).toBe(1))

    await user.click(backflow.getByRole('button', { name: 'Sync backflow' }))
    await waitFor(() => expect(backflowSynced).toBe(1))
  })
})

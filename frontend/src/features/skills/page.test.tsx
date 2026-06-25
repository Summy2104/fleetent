import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { I18nProvider } from '@/i18n';
import { SkillsPage } from '@/features/skills/page';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

type SkillRecord = {
  audit_verdict: string;
  description: string;
  drifted_agents: string[];
  enabling_agents: string[];
  global_enabled: boolean;
  name: string;
  source: string;
  status: string;
};

type AgentBindingRecord = {
  agent_id: number;
  enabled: boolean;
  name: string;
};

function renderSkillsPage(): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken="session-token"
    >
      <AppQueryProvider>
        <I18nProvider>
          <MemoryRouter>
            <SkillsPage />
          </MemoryRouter>
        </I18nProvider>
      </AppQueryProvider>
    </AuthProvider>
  );
}

describe('skills page parity baseline', () => {
  it('supports native skills admin flows and keeps proposals read-only', async () => {
    const user = userEvent.setup({ delay: null });
    let reloadCount = 0;
    const activeVersion = 'sha-1';
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
    ];
    let bindings: AgentBindingRecord[] = [
      { agent_id: 7, enabled: true, name: 'agent-a' },
      { agent_id: 8, enabled: false, name: 'agent-b' },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
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
        );
        return HttpResponse.json({ global_enabled: 0, name: params.name });
      }),
      http.post(`${API_BASE_URL}/admin/skills/:name/enable`, ({ params }) => {
        skills = skills.map((skill) =>
          skill.name === params.name ? { ...skill, global_enabled: true, status: 'active' } : skill
        );
        return HttpResponse.json({ global_enabled: 1, name: params.name });
      }),
      http.delete(`${API_BASE_URL}/admin/skills/:name`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        skills = skills.map((skill) =>
          skill.name === params.name ? { ...skill, status: 'archived' } : skill
        );
        return HttpResponse.json({ name: params.name, status: 'archived' });
      }),
      http.post(`${API_BASE_URL}/admin/skills/:name/restore`, ({ params }) => {
        skills = skills.map((skill) =>
          skill.name === params.name ? { ...skill, status: 'active' } : skill
        );
        return HttpResponse.json({ name: params.name, status: 'active' });
      }),
      http.post(`${API_BASE_URL}/admin/skills/:name/force-publish`, ({ params, request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        skills = skills.map((skill) =>
          skill.name === params.name ? { ...skill, audit_verdict: 'pass', status: 'active' } : skill
        );
        return HttpResponse.json({ forced: 1, name: params.name, status: 'active' });
      }),
      http.post(`${API_BASE_URL}/admin/skills/reload`, () => {
        reloadCount += 1;
        return HttpResponse.json({ ok: true });
      }),
      http.get(`${API_BASE_URL}/admin/skills/:name/agents`, ({ params }) =>
        HttpResponse.json(
          String(params.name ?? '') === 'ops-guide'
            ? bindings
            : [{ agent_id: 9, enabled: false, name: 'agent-c' }]
        )
      ),
      http.put(`${API_BASE_URL}/admin/skills/:name/agents/:agentId`, async ({ params, request }) => {
        const body = (await request.json()) as { enabled: boolean };
        bindings = bindings.map((binding) =>
          binding.agent_id === Number(params.agentId) ? { ...binding, enabled: body.enabled } : binding
        );
        skills = skills.map((skill) =>
          skill.name === String(params.name ?? '')
            ? {
                ...skill,
                enabling_agents: bindings.filter((binding) => binding.enabled).map((binding) => binding.name),
              }
            : skill
        );
        return HttpResponse.json({
          agent_id: Number(params.agentId),
          enabled: body.enabled,
          name: String(params.name ?? ''),
        });
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
    );

    renderSkillsPage();

    expect(await screen.findByRole('heading', { name: 'Skills' })).toBeInTheDocument();
    // The current UI renders skills as table rows; each row exposes an "Actions for {name}" menu trigger.
    expect(await screen.findByRole('button', { name: 'Actions for ops-guide' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actions for welcome-pack' })).toBeInTheDocument();
    expect(screen.getByText('quarantined')).toBeInTheDocument();

    // View the published skill content via the row's Actions menu.
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }));
    await user.click(await screen.findByText('View content'));
    expect(await screen.findByText(/ops-guide body/)).toBeInTheDocument();
    await user.keyboard('{Escape}');

    // Agent bindings: open the dialog, confirm bound state, toggle a binding.
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }));
    await user.click(await screen.findByText('Agent bindings'));
    const bindingsDialog = await screen.findByRole('dialog');
    const bindingControls = within(bindingsDialog);
    expect(bindingControls.getByLabelText('agent-a')).toBeChecked();
    await user.click(bindingControls.getByLabelText('agent-b'));
    await waitFor(() => {
      expect(bindingControls.getByLabelText('agent-b')).toBeChecked();
    });
    await user.keyboard('{Escape}');

    // Versions dialog: pick the second revision and view its diff.
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }));
    await user.click(await screen.findByText('Versions'));
    const versionsDialog = await screen.findByRole('dialog');
    // Two revisions, each with its own "Diff" button; the second row is sha-2.
    const diffButtons = await within(versionsDialog).findAllByRole('button', { name: 'Diff' });
    await user.click(diffButtons[1]);
    expect(await within(versionsDialog).findByText('diff ops-guide sha-2')).toBeInTheDocument();
    await user.keyboard('{Escape}');

    // Proposals dialog is read-only: shows reasons + diff, never approve/reject.
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }));
    await user.click(await screen.findByText(/^Proposals/));
    const proposalsDialog = await screen.findByRole('dialog');
    const proposals = within(proposalsDialog);
    expect(proposals.getByText('Tighten escalation wording')).toBeInTheDocument();
    expect(proposals.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
    expect(proposals.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument();
    await user.click(proposals.getByRole('button', { name: 'Diff' }));
    expect(await screen.findByText('proposal diff prop-1')).toBeInTheDocument();
    // Close the proposal-diff dialog, then the proposals dialog.
    await user.keyboard('{Escape}');
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    // Force publish (only offered for rejected/quarantined skills) clears quarantine.
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }));
    await user.click(await screen.findByText('Force publish'));
    await waitFor(() => {
      expect(screen.getByText('active')).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }));
    expect(screen.queryByText('Force publish')).not.toBeInTheDocument();
    await user.keyboard('{Escape}');

    // Disable -> Enable toggle.
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }));
    await user.click(await screen.findByText('Disable'));
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }));
    expect(await screen.findByText('Enable')).toBeInTheDocument();
    await user.keyboard('{Escape}');

    // Archive ops-guide via confirm dialog.
    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }));
    await user.click(await screen.findByText('Archive'));
    const archiveConfirm = await screen.findByRole('alertdialog');
    await user.click(within(archiveConfirm).getByRole('button', { name: 'Archive' }));
    await waitFor(() => {
      expect(screen.getAllByText('archived').length).toBeGreaterThan(0);
    });

    // welcome-pack is archived -> its menu offers Restore.
    await user.click(screen.getByRole('button', { name: 'Actions for welcome-pack' }));
    await user.click(await screen.findByText('Restore'));
    await waitFor(() => {
      expect(reloadCount).toBe(0);
    });
    await user.keyboard('{Escape}');

    // Reload skill index button on the header.
    await user.click(screen.getByRole('button', { name: 'Reload index' }));
    await waitFor(() => {
      expect(reloadCount).toBe(1);
    });
  });
});

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
  ];

  function stubBaseReads(): void {
    server.use(
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
    );
  }

  it('lists proposals, shows diff, and posts accept/reject/fork decisions', async () => {
    const user = userEvent.setup({ delay: null });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('crm-ops-fork');
    const acceptHeaders: (string | null)[] = [];
    let rejected = false;
    let forkedWith: { fork_name: string } | null = null;

    stubBaseReads();
    server.use(
      http.post(`${API_BASE_URL}/admin/skills/backflow/:id/accept`, ({ request }) => {
        acceptHeaders.push(request.headers.get('x-confirm'));
        return HttpResponse.json({ new_version: 'sha', ok: true, proposal_id: 1, user: 'admin' });
      }),
      http.post(`${API_BASE_URL}/admin/skills/backflow/:id/reject`, () => {
        rejected = true;
        return HttpResponse.json({ ok: true, proposal_id: 1, user: 'admin' });
      }),
      http.post(`${API_BASE_URL}/admin/skills/backflow/:id/fork`, async ({ request }) => {
        forkedWith = (await request.json()) as { fork_name: string };
        return HttpResponse.json({ forked_as: forkedWith.fork_name, ok: true, proposal_id: 1, user: 'admin' });
      })
    );

    renderSkillsPage();

    await user.click(await screen.findByRole('button', { name: 'Actions for crm-ops' }));
    await user.click(await screen.findByRole('menuitem', { name: /Backflow/ }));
    const backflow = within(await screen.findByRole('dialog'));
    expect(await backflow.findByRole('button', { name: 'Accept backflow 1' })).toBeInTheDocument();

    await user.click(backflow.getByRole('button', { name: 'View backflow diff for 1' }));
    expect(await backflow.findByText('bf head 1')).toBeInTheDocument();

    await user.click(backflow.getByRole('button', { name: 'Accept backflow 1' }));
    await waitFor(() => expect(acceptHeaders).toHaveLength(1));
    expect(confirmSpy).toHaveBeenCalled();
    expect(acceptHeaders[0]).toBe('true');

    await user.click(backflow.getByRole('button', { name: 'Reject backflow 1' }));
    await waitFor(() => expect(rejected).toBe(true));

    await user.click(backflow.getByRole('button', { name: 'Fork backflow 1' }));
    await waitFor(() => expect(forkedWith).toEqual({ fork_name: 'crm-ops-fork' }));
    expect(promptSpy).toHaveBeenCalled();

    confirmSpy.mockRestore();
    promptSpy.mockRestore();
  });

  it('does not accept a conflict proposal when confirmation is cancelled', async () => {
    const user = userEvent.setup({ delay: null });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const acceptHeaders: (string | null)[] = [];

    stubBaseReads();
    server.use(
      http.post(`${API_BASE_URL}/admin/skills/backflow/:id/accept`, ({ request }) => {
        acceptHeaders.push(request.headers.get('x-confirm'));
        return HttpResponse.json({ ok: true, proposal_id: 1, user: 'admin' });
      })
    );

    renderSkillsPage();

    await user.click(await screen.findByRole('button', { name: 'Actions for crm-ops' }));
    await user.click(await screen.findByRole('menuitem', { name: /Backflow/ }));
    const backflow = within(await screen.findByRole('dialog'));

    await user.click(await backflow.findByRole('button', { name: 'Accept backflow 1' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(acceptHeaders).toHaveLength(0);

    confirmSpy.mockRestore();
  });
});

describe('skills page content + search', () => {
  function stubReadEndpoints(getSkills: () => SkillRecord[], getContent: () => string): void {
    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/skills`, () => HttpResponse.json(getSkills())),
      http.get(`${API_BASE_URL}/admin/skills/:name/content`, ({ params }) =>
        HttpResponse.json({ content: getContent(), name: String(params.name ?? '') })
      ),
      http.get(`${API_BASE_URL}/admin/skills/:name/agents`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/skills/proposals`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/skills/backflow`, () => HttpResponse.json([]))
    );
  }

  it('filters skills by name via the search box', async () => {
    const user = userEvent.setup({ delay: null });
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
    ];

    stubReadEndpoints(
      () => skills,
      () => 'welcome body'
    );

    renderSkillsPage();

    expect(await screen.findByRole('button', { name: 'Actions for welcome-pack' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actions for promo-helper' })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText('Search skills…'), 'promo');
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Actions for welcome-pack' })).not.toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Actions for promo-helper' })).toBeInTheDocument();
  });

  it('shows the published skill content in the content dialog', async () => {
    const user = userEvent.setup({ delay: null });
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
    ];
    const content = '---\nname: welcome-pack\ndescription: helper\n---\noriginal body';

    stubReadEndpoints(
      () => skills,
      () => content
    );

    renderSkillsPage();

    await user.click(await screen.findByRole('button', { name: 'Actions for welcome-pack' }));
    await user.click(await screen.findByText('View content'));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/original body/)).toBeInTheDocument();
    expect(within(dialog).getByText('Content · welcome-pack')).toBeInTheDocument();
  });
});

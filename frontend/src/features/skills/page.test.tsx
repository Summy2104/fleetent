import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
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
        <MemoryRouter>
          <SkillsPage />
        </MemoryRouter>
      </AppQueryProvider>
    </AuthProvider>
  );
}

describe('skills page parity baseline', () => {
  it('supports native skills admin flows and keeps proposals read-only', async () => {
    const user = userEvent.setup();
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
      )
    );

    renderSkillsPage();

    expect(await screen.findByRole('heading', { name: 'Skills' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'ops-guide' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'welcome-pack' })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/ops-guide body/)).toBeInTheDocument();
      expect(screen.getByText('quarantined')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'Force publish ops-guide' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Disable ops-guide' })).toBeInTheDocument();

    const bindingsSection = screen.getByRole('heading', { name: 'Agent bindings' }).closest('section');
    expect(bindingsSection).not.toBeNull();
    const bindingControls = within(bindingsSection as HTMLElement);
    expect(bindingControls.getByLabelText('agent-a')).toBeChecked();

    await user.click(bindingControls.getByLabelText('agent-b'));
    await waitFor(() => {
      expect(bindingControls.getByLabelText('agent-b')).toBeChecked();
    });

    await user.click(screen.getByRole('button', { name: 'Show versions for ops-guide' }));
    expect(await screen.findByRole('button', { name: 'View diff for sha-2' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'View diff for sha-2' }));
    expect(await screen.findByText('diff ops-guide sha-2')).toBeInTheDocument();

    const proposalsSection = screen.getByRole('heading', { name: 'Reflection proposals' }).closest('section');
    expect(proposalsSection).not.toBeNull();
    const proposals = within(proposalsSection as HTMLElement);
    expect(proposals.getByText('Tighten escalation wording')).toBeInTheDocument();
    expect(proposals.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
    expect(proposals.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument();
    await user.click(proposals.getByRole('button', { name: 'View diff for proposal prop-1' }));
    expect(await screen.findByText('proposal diff prop-1')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Force publish ops-guide' }));
    await waitFor(() => {
      expect(screen.getByText('active')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Force publish ops-guide' })).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Disable ops-guide' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Enable ops-guide' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Archive ops-guide' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Restore ops-guide' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Restore welcome-pack' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Archive welcome-pack' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Reload skill index' }));
    await waitFor(() => {
      expect(reloadCount).toBe(1);
    });
  });
});

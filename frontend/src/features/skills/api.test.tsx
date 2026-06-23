import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import {
  useCreateSkillMutation,
  useEditSkillMutation,
  useForcePublishSkillMutation,
  useReloadSkillsMutation,
  useSetSkillAgentBindingMutation,
  useSkillAgentBindingsQuery,
  useSkillContentQuery,
  useSkillDiffQuery,
  useSkillLifecycleMutation,
  useSkillProposalDiffQuery,
  useSkillProposalsQuery,
  useSkillVersionsQuery,
  useSkillsQuery,
} from '@/features/skills/api';
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

type VersionRecord = {
  author: string;
  message: string;
  sha: string;
  timestamp: string;
};

type ProposalRecord = {
  has_diff: boolean;
  id: string;
  reason: string;
  risk_level: string;
  target_skill: string;
  type: string;
};

function renderWithProviders(ui: ReactNode): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken="session-token"
    >
      <AppQueryProvider>{ui}</AppQueryProvider>
    </AuthProvider>
  );
}

function SkillsApiProbe(): JSX.Element {
  const skills = useSkillsQuery();
  const content = useSkillContentQuery('ops-guide');
  const bindings = useSkillAgentBindingsQuery('ops-guide');
  const versions = useSkillVersionsQuery('ops-guide', true);
  const diff = useSkillDiffQuery('ops-guide', 'sha-2', true);
  const proposals = useSkillProposalsQuery();
  const proposalDiff = useSkillProposalDiffQuery('prop-1', true);
  const disable = useSkillLifecycleMutation('ops-guide', 'disable');
  const enable = useSkillLifecycleMutation('ops-guide', 'enable');
  const archive = useSkillLifecycleMutation('ops-guide', 'delete');
  const restore = useSkillLifecycleMutation('ops-guide', 'restore');
  const forcePublish = useForcePublishSkillMutation('ops-guide');
  const reload = useReloadSkillsMutation();
  const setBinding = useSetSkillAgentBindingMutation('ops-guide', 7);

  return (
    <section>
      <button
        onClick={() => disable.mutate()}
        type="button"
      >
        disable
      </button>
      <button
        onClick={() => enable.mutate()}
        type="button"
      >
        enable
      </button>
      <button
        onClick={() => archive.mutate()}
        type="button"
      >
        archive
      </button>
      <button
        onClick={() => restore.mutate()}
        type="button"
      >
        restore
      </button>
      <button
        onClick={() => forcePublish.mutate()}
        type="button"
      >
        force publish
      </button>
      <button
        onClick={() => reload.mutate()}
        type="button"
      >
        reload
      </button>
      <button
        onClick={() => setBinding.mutate({ enabled: false })}
        type="button"
      >
        disable binding
      </button>

      <div data-testid="skills">
        {skills.data
          ?.map(
            (skill) =>
              `${skill.name}:${skill.status}:${skill.global_enabled}:${skill.audit_verdict}:${skill.enabling_agents.join(',')}`
          )
          .join('|')}
      </div>
      <div data-testid="content">{content.data?.content}</div>
      <div data-testid="bindings">
        {bindings.data?.map((binding) => `${binding.agent_id}:${binding.enabled}`).join('|')}
      </div>
      <div data-testid="versions">
        {versions.data?.map((version) => `${version.sha}:${version.message}`).join('|')}
      </div>
      <div data-testid="diff">{diff.data?.diff}</div>
      <div data-testid="proposals">
        {proposals.data?.map((proposal) => `${proposal.id}:${proposal.target_skill}:${proposal.type}`).join('|')}
      </div>
      <div data-testid="proposal-diff">{proposalDiff.data?.diff}</div>
    </section>
  );
}

describe('skills api hooks', () => {
  it('loads skills data and refreshes affected queries after lifecycle mutations', async () => {
    const user = userEvent.setup();
    let skills: SkillRecord[] = [
      {
        audit_verdict: 'pass',
        description: 'Ops runbook helper',
        drifted_agents: ['agent-b'],
        enabling_agents: ['agent-a'],
        global_enabled: true,
        name: 'ops-guide',
        source: 'adhoc',
        status: 'active',
      },
    ];
    let bindings: AgentBindingRecord[] = [
      { agent_id: 7, enabled: true, name: 'agent-a' },
      { agent_id: 8, enabled: false, name: 'agent-b' },
    ];
    const versions: VersionRecord[] = [
      { author: 'Ops', message: 'Initial publish', sha: 'sha-1', timestamp: '2026-06-20T10:00:00Z' },
      { author: 'Ops', message: 'Clarify restart note', sha: 'sha-2', timestamp: '2026-06-21T10:00:00Z' },
    ];
    const proposals: ProposalRecord[] = [
      {
        has_diff: true,
        id: 'prop-1',
        reason: 'Tighten escalation wording',
        risk_level: 'medium',
        target_skill: 'ops-guide',
        type: 'update_skill',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/skills`, () => HttpResponse.json(skills)),
      http.get(`${API_BASE_URL}/admin/skills/:name/content`, ({ params }) =>
        HttpResponse.json({
          content: `---\nname: ${String(params.name ?? '')}\ndescription: Ops runbook helper\n---\ncontent`,
          name: String(params.name ?? ''),
        })
      ),
      http.get(`${API_BASE_URL}/admin/skills/:name/agents`, () => HttpResponse.json(bindings)),
      http.get(`${API_BASE_URL}/admin/skills/:name/versions`, () => HttpResponse.json(versions)),
      http.get(`${API_BASE_URL}/admin/skills/:name/versions/:ref/diff`, ({ params }) =>
        HttpResponse.json({ diff: `diff for ${String(params.ref ?? '')}`, truncated: false })
      ),
      http.get(`${API_BASE_URL}/admin/skills/proposals`, () => HttpResponse.json(proposals)),
      http.get(`${API_BASE_URL}/admin/skills/proposals/:id/diff`, ({ params }) =>
        HttpResponse.json({ diff: `proposal diff ${String(params.id ?? '')}` })
      ),
      http.post(`${API_BASE_URL}/admin/skills/:name/disable`, ({ params }) => {
        skills = skills.map((skill) =>
          skill.name === params.name ? { ...skill, global_enabled: false } : skill
        );
        return HttpResponse.json({ global_enabled: 0, name: params.name });
      }),
      http.post(`${API_BASE_URL}/admin/skills/:name/enable`, ({ params }) => {
        skills = skills.map((skill) =>
          skill.name === params.name ? { ...skill, global_enabled: true } : skill
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
          skill.name === String(params.name ?? '')
            ? { ...skill, audit_verdict: 'pass', status: 'active' }
            : skill
        );
        return HttpResponse.json({ forced: 1, name: String(params.name ?? ''), status: 'active' });
      }),
      http.post(`${API_BASE_URL}/admin/skills/reload`, () => HttpResponse.json({ ok: true })),
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
      })
    );

    renderWithProviders(<SkillsApiProbe />);

    await waitFor(() => {
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide:active:true:pass:agent-a');
      expect(screen.getByTestId('content')).toHaveTextContent('content');
      expect(screen.getByTestId('bindings')).toHaveTextContent('7:true|8:false');
      expect(screen.getByTestId('versions')).toHaveTextContent('sha-1:Initial publish|sha-2:Clarify restart note');
      expect(screen.getByTestId('diff')).toHaveTextContent('diff for sha-2');
      expect(screen.getByTestId('proposals')).toHaveTextContent('prop-1:ops-guide:update_skill');
      expect(screen.getByTestId('proposal-diff')).toHaveTextContent('proposal diff prop-1');
    });

    await user.click(screen.getByRole('button', { name: 'disable' }));
    await waitFor(() => {
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide:active:false:pass:agent-a');
    });

    await user.click(screen.getByRole('button', { name: 'enable' }));
    await waitFor(() => {
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide:active:true:pass:agent-a');
    });

    await user.click(screen.getByRole('button', { name: 'archive' }));
    await waitFor(() => {
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide:archived:true:pass:agent-a');
    });

    await user.click(screen.getByRole('button', { name: 'restore' }));
    await waitFor(() => {
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide:active:true:pass:agent-a');
    });

    skills = skills.map((skill) =>
      skill.name === 'ops-guide' ? { ...skill, audit_verdict: 'rejected', status: 'quarantined' } : skill
    );
    await user.click(screen.getByRole('button', { name: 'force publish' }));
    await waitFor(() => {
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide:active:true:pass:agent-a');
    });

    await user.click(screen.getByRole('button', { name: 'disable binding' }));
    await waitFor(() => {
      expect(screen.getByTestId('bindings')).toHaveTextContent('7:false|8:false');
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide:active:true:pass:');
    });

    await user.click(screen.getByRole('button', { name: 'reload' }));
    await waitFor(() => {
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide:active:true:pass:');
    });
  });
});

function SkillsCrudProbe(): JSX.Element {
  const skills = useSkillsQuery();
  const content = useSkillContentQuery('ops-guide');
  const create = useCreateSkillMutation();
  const edit = useEditSkillMutation('ops-guide');

  return (
    <section>
      <button
        onClick={() =>
          create.mutate({
            content: '---\nname: new-skill\ndescription: fresh\n---\nnew body',
            name: 'new-skill',
          })
        }
        type="button"
      >
        create
      </button>
      <button
        onClick={() =>
          edit.mutate({ content: '---\nname: ops-guide\ndescription: helper\n---\nedited body' })
        }
        type="button"
      >
        edit
      </button>
      <div data-testid="skills">{skills.data?.map((skill) => skill.name).join('|')}</div>
      <div data-testid="content">{content.data?.content}</div>
    </section>
  );
}

describe('skills create and edit hooks', () => {
  it('creates a skill and refreshes the list', async () => {
    const user = userEvent.setup();
    let skills: SkillRecord[] = [
      {
        audit_verdict: 'pass',
        description: 'Ops runbook helper',
        drifted_agents: [],
        enabling_agents: [],
        global_enabled: true,
        name: 'ops-guide',
        source: 'adhoc',
        status: 'active',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/skills`, () => HttpResponse.json(skills)),
      http.get(`${API_BASE_URL}/admin/skills/:name/content`, ({ params }) =>
        HttpResponse.json({ content: 'ops body', name: String(params.name ?? '') })
      ),
      http.post(`${API_BASE_URL}/admin/skills`, async ({ request }) => {
        const body = (await request.json()) as { content: string; name: string; source?: string };
        expect(body.name).toBe('new-skill');
        expect(body.content).toContain('name: new-skill');
        skills = [
          ...skills,
          {
            audit_verdict: 'pass',
            description: 'fresh',
            drifted_agents: [],
            enabling_agents: [],
            global_enabled: false,
            name: body.name,
            source: body.source ?? 'adhoc',
            status: 'active',
          },
        ];
        return HttpResponse.json({ name: body.name, verdict: 'pass' });
      })
    );

    renderWithProviders(<SkillsCrudProbe />);

    await waitFor(() => {
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide');
    });

    await user.click(screen.getByRole('button', { name: 'create' }));
    await waitFor(() => {
      expect(screen.getByTestId('skills')).toHaveTextContent('ops-guide|new-skill');
    });
  });

  it('edits a skill and refreshes its content', async () => {
    const user = userEvent.setup();
    const skills: SkillRecord[] = [
      {
        audit_verdict: 'pass',
        description: 'Ops runbook helper',
        drifted_agents: [],
        enabling_agents: [],
        global_enabled: true,
        name: 'ops-guide',
        source: 'adhoc',
        status: 'active',
      },
    ];
    let content = '---\nname: ops-guide\ndescription: helper\n---\noriginal body';

    server.use(
      http.get(`${API_BASE_URL}/admin/skills`, () => HttpResponse.json(skills)),
      http.get(`${API_BASE_URL}/admin/skills/:name/content`, ({ params }) =>
        HttpResponse.json({ content, name: String(params.name ?? '') })
      ),
      http.put(`${API_BASE_URL}/admin/skills/:name`, async ({ params, request }) => {
        const body = (await request.json()) as { content: string };
        expect(String(params.name ?? '')).toBe('ops-guide');
        content = body.content;
        return HttpResponse.json({ name: String(params.name ?? ''), verdict: 'pass' });
      })
    );

    renderWithProviders(<SkillsCrudProbe />);

    await waitFor(() => {
      expect(screen.getByTestId('content')).toHaveTextContent('original body');
    });

    await user.click(screen.getByRole('button', { name: 'edit' }));
    await waitFor(() => {
      expect(screen.getByTestId('content')).toHaveTextContent('edited body');
    });
  });
});

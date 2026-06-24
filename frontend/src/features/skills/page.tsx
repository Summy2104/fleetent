import { useEffect, useState } from 'react';

import {
  type SkillAgentBinding,
  type SkillListItem,
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

function SkillActions({ skill }: { skill: SkillListItem }): JSX.Element {
  const toggle = useSkillLifecycleMutation(skill.name, skill.global_enabled ? 'disable' : 'enable');
  const archiveOrRestore = useSkillLifecycleMutation(
    skill.name,
    skill.status === 'archived' ? 'restore' : 'delete'
  );
  const forcePublish = useForcePublishSkillMutation(skill.name);

  return (
    <div className="flex flex-wrap gap-2">
      <button
        className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
        onClick={() => void toggle.mutateAsync()}
        type="button"
      >
        {skill.global_enabled ? `Disable ${skill.name}` : `Enable ${skill.name}`}
      </button>
      <button
        className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
        onClick={() => void archiveOrRestore.mutateAsync()}
        type="button"
      >
        {skill.status === 'archived' ? `Restore ${skill.name}` : `Archive ${skill.name}`}
      </button>
      {skill.audit_verdict === 'rejected' || skill.status === 'quarantined' ? (
        <button
          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
          onClick={() => void forcePublish.mutateAsync()}
          type="button"
        >
          {`Force publish ${skill.name}`}
        </button>
      ) : null}
    </div>
  );
}

function BindingsEditor({
  bindings,
  skillName,
}: {
  bindings: SkillAgentBinding[];
  skillName: string;
}): JSX.Element {
  return (
    <section className="rounded-2xl border bg-white/75 p-5">
      <h2 className="text-lg font-semibold">Agent bindings</h2>
      <div className="mt-4 grid gap-3">
        {bindings.map((binding) => (
          <BindingToggle
            binding={binding}
            key={binding.agent_id}
            skillName={skillName}
          />
        ))}
      </div>
    </section>
  );
}

function BindingToggle({
  binding,
  skillName,
}: {
  binding: SkillAgentBinding;
  skillName: string;
}): JSX.Element {
  const updateBinding = useSetSkillAgentBindingMutation(skillName, binding.agent_id);
  const label = binding.name ?? String(binding.agent_id);

  return (
    <label className="flex items-center gap-3 text-sm font-medium">
      <input
        aria-label={label}
        checked={binding.enabled}
        onChange={(event) => updateBinding.mutate({ enabled: event.target.checked })}
        type="checkbox"
      />
      <span>{label}</span>
    </label>
  );
}

const CREATE_TEMPLATE = '---\nname: \ndescription: \n---\n\n';

function CreateSkillForm({ onDone }: { onDone: () => void }): JSX.Element {
  const create = useCreateSkillMutation();
  const [name, setName] = useState('');
  const [content, setContent] = useState('');

  const submit = async (): Promise<void> => {
    await create.mutateAsync({ content, name });
    onDone();
  };

  return (
    <section className="rounded-2xl border bg-white/75 p-5">
      <h2 className="text-lg font-semibold">New skill</h2>
      <div className="mt-4 grid gap-3">
        <input
          aria-label="New skill name"
          className="rounded-md border px-3 py-2 text-sm"
          onChange={(event) => setName(event.target.value)}
          placeholder="skill-name"
          value={name}
        />
        <textarea
          aria-label="New skill content"
          className="min-h-48 rounded-md border px-3 py-2 font-mono text-sm"
          onChange={(event) => setContent(event.target.value)}
          placeholder={CREATE_TEMPLATE}
          value={content}
        />
        <div className="flex gap-2">
          <button
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            disabled={!name.trim() || !content.trim() || create.isPending}
            onClick={() => void submit()}
            type="button"
          >
            Create skill
          </button>
          <button
            className="rounded-md bg-secondary px-4 py-2 text-sm font-medium"
            onClick={onDone}
            type="button"
          >
            Cancel new skill
          </button>
        </div>
      </div>
    </section>
  );
}

function SelectedSkillPanel({
  content,
  name,
}: {
  content: string;
  name: string | null;
}): JSX.Element {
  const edit = useEditSkillMutation(name ?? '');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);

  // Keep the read-only view in sync with refetched content while not editing; an
  // active edit keeps the operator's in-progress draft instead of clobbering it.
  useEffect(() => {
    if (!editing) {
      setDraft(content);
    }
  }, [content, editing]);

  const save = async (): Promise<void> => {
    await edit.mutateAsync({ content: draft });
    setEditing(false);
  };

  return (
    <section className="rounded-2xl border bg-white/75 p-5">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">
          {name ? `Selected skill: ${name}` : 'Selected skill'}
        </h2>
        {name && !editing ? (
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => {
              setDraft(content);
              setEditing(true);
            }}
            type="button"
          >
            Edit content
          </button>
        ) : null}
      </div>
      {editing ? (
        <div className="mt-4 grid gap-3">
          <textarea
            aria-label="Skill content editor"
            className="min-h-72 rounded-xl border px-3 py-2 font-mono text-sm"
            onChange={(event) => setDraft(event.target.value)}
            value={draft}
          />
          <div className="flex gap-2">
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              disabled={edit.isPending}
              onClick={() => void save()}
              type="button"
            >
              Save content
            </button>
            <button
              className="rounded-md bg-secondary px-4 py-2 text-sm font-medium"
              onClick={() => setEditing(false)}
              type="button"
            >
              Cancel edit
            </button>
          </div>
        </div>
      ) : (
        <pre className="mt-4 max-h-80 overflow-auto rounded-xl bg-slate-950 p-4 text-sm text-slate-50">
          {content}
        </pre>
      )}
    </section>
  );
}

export function SkillsPage(): JSX.Element {
  const skills = useSkillsQuery();
  const proposals = useSkillProposalsQuery();
  const reload = useReloadSkillsMutation();

  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [versionsOpenFor, setVersionsOpenFor] = useState<string | null>(null);
  const [selectedRef, setSelectedRef] = useState<string | null>(null);
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);

  useEffect(() => {
    if (!skills.data || skills.data.length === 0) {
      setSelectedName(null);
      return;
    }
    if (!selectedName || !skills.data.some((skill) => skill.name === selectedName)) {
      setSelectedName(skills.data[0].name);
    }
  }, [selectedName, skills.data]);

  const selectedSkill = skills.data?.find((skill) => skill.name === selectedName) ?? null;
  const content = useSkillContentQuery(selectedName);
  const bindings = useSkillAgentBindingsQuery(selectedName);
  const versions = useSkillVersionsQuery(versionsOpenFor, versionsOpenFor === selectedName);
  const diff = useSkillDiffQuery(selectedName, selectedRef, Boolean(selectedRef));
  const proposalDiff = useSkillProposalDiffQuery(selectedProposalId, Boolean(selectedProposalId));

  return (
    <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <div className="space-y-6">
        <header className="space-y-3">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
            Native SPA
          </p>
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">Skills</h1>
              <p className="text-sm text-muted-foreground">
                Manage skill rollout, bindings, and read-only reflection proposals without
                returning to the legacy console.
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className="rounded-md bg-secondary px-4 py-2 text-sm font-medium"
                onClick={() => setCreating((open) => !open)}
                type="button"
              >
                New skill
              </button>
              <button
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
                onClick={() => void reload.mutateAsync()}
                type="button"
              >
                Reload skill index
              </button>
            </div>
          </div>
        </header>

        {creating ? <CreateSkillForm onDone={() => setCreating(false)} /> : null}

        <section className="grid gap-4">
          {skills.data?.map((skill) => (
            <article
              className="rounded-2xl border bg-white/80 p-5"
              key={skill.name}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-2">
                  <button
                    className="text-left text-xl font-semibold"
                    onClick={() => {
                      setSelectedName(skill.name);
                      setSelectedRef(null);
                    }}
                    type="button"
                  >
                    {skill.name}
                  </button>
                  <p className="text-sm text-muted-foreground">{skill.description}</p>
                  <div className="flex flex-wrap gap-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                    <span>{skill.status}</span>
                    <span>{skill.global_enabled ? 'enabled globally' : 'disabled globally'}</span>
                    <span>{`audit ${skill.audit_verdict}`}</span>
                  </div>
                  {skill.enabling_agents.length > 0 ? (
                    <p className="text-sm text-foreground">
                      {`Enabled for ${skill.enabling_agents.join(', ')}`}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-col items-end gap-2">
                  <SkillActions skill={skill} />
                  <button
                    className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                    onClick={() => {
                      setSelectedName(skill.name);
                      setVersionsOpenFor(skill.name);
                      setSelectedRef(null);
                    }}
                    type="button"
                  >
                    {`Show versions for ${skill.name}`}
                  </button>
                </div>
              </div>
            </article>
          ))}
        </section>
      </div>

      <div className="space-y-6">
        {/* key resets editor state (editing/draft) when the operator switches skills */}
        <SelectedSkillPanel
          content={content.data?.content ?? ''}
          key={selectedSkill?.name ?? 'none'}
          name={selectedSkill?.name ?? null}
        />

        {selectedName && bindings.data ? (
          <BindingsEditor
            bindings={bindings.data}
            skillName={selectedName}
          />
        ) : null}

        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Version history</h2>
          <div className="mt-4 grid gap-3">
            {versions.data?.map((version) => (
              <div
                className="flex items-center justify-between gap-4"
                key={version.sha}
              >
                <div>
                  <p className="text-sm font-medium">{version.sha}</p>
                  <p className="text-sm text-muted-foreground">{version.message}</p>
                </div>
                <button
                  className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                  onClick={() => setSelectedRef(version.sha)}
                  type="button"
                >
                  {`View diff for ${version.sha}`}
                </button>
              </div>
            ))}
          </div>
          {diff.data?.diff ? (
            <pre className="mt-4 max-h-72 overflow-auto rounded-xl bg-slate-950 p-4 text-sm text-slate-50">
              {diff.data.diff}
            </pre>
          ) : null}
        </section>

        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Reflection proposals</h2>
          <div className="mt-4 grid gap-4">
            {proposals.data?.map((proposal) => (
              <article
                className="rounded-xl border bg-white p-4"
                key={proposal.id}
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold">{proposal.target_skill}</p>
                    <p className="text-sm text-muted-foreground">{proposal.reason}</p>
                  </div>
                  <button
                    className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                    onClick={() => setSelectedProposalId(proposal.id)}
                    type="button"
                  >
                    {`View diff for proposal ${proposal.id}`}
                  </button>
                </div>
              </article>
            ))}
          </div>
          {proposalDiff.data?.diff ? (
            <pre className="mt-4 max-h-72 overflow-auto rounded-xl bg-slate-950 p-4 text-sm text-slate-50">
              {proposalDiff.data.diff}
            </pre>
          ) : null}
        </section>
      </div>
    </section>
  );
}

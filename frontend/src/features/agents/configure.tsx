import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Download, Eye, EyeOff, Inbox, Trash2, X } from 'lucide-react';

import { useAdminApi } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  type AgentImCapabilitiesInput,
  type AgentImGroupInput,
  type AgentSkillBinding,
  useActivateAgentVersionMutation,
  useAddAgentImGroupMutation,
  useAgentBindingsQuery,
  useAgentDetailQuery,
  useAgentKbsQuery,
  useAgentRequiredEnvQuery,
  useAgentSecretsQuery,
  useAgentSkillsQuery,
  useAgentVersionsQuery,
  useBindAgentKbMutation,
  useBindAgentMcpMutation,
  useBindAgentUserMutation,
  useDeleteAgentSecretMutation,
  useDeployAgentMutation,
  useExportAgentYamlMutation,
  useRemoveAgentImGroupMutation,
  useSetAgentImCapabilitiesMutation,
  useSetAgentSecretValueMutation,
  useSetAgentSkillMutation,
  useUnbindAgentKbMutation,
  useUnbindAgentMcpMutation,
  useUnbindAgentUserMutation,
  useUpdateAgentMutation,
} from '@/features/agents/api';
import { useMcpServersQuery } from '@/features/connectors/api';
import { useKbsQuery } from '@/features/kb/api';
import { useUsersQuery } from '@/features/users/api';

type AdminMe = { email: string; id: string; role: string };

function useAdminMeQuery() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

function parseAllowedTools(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

// ─────────────────────────── shared bits ───────────────────────────

function EmptyState({ label }: { label: string }): JSX.Element {
  return (
    <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
      <Inbox className="size-6 opacity-50" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

function TabHeading({ children }: { children: ReactNode }): JSX.Element {
  return <h3 className="text-sm font-semibold text-foreground">{children}</h3>;
}

function Th({ children, className }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <th className={cn('px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground', className)}>
      {children}
    </th>
  );
}

type BindOption = { value: string; label: string };

function BindSelectEditor({
  title,
  placeholder,
  options,
  items,
  canWrite,
  loading,
  emptyLabel,
  onBind,
  onUnbind,
}: {
  title: string;
  placeholder: string;
  options: BindOption[];
  items: string[];
  canWrite: boolean;
  loading: boolean;
  emptyLabel: string;
  onBind: (value: string) => void;
  onUnbind: (value: string) => void;
}): JSX.Element {
  // Resolve a bound id back to its human label (email / name) for the chips.
  const labelOf = useMemo(() => {
    const map = new Map(options.map((option) => [option.value, option.label]));
    return (value: string) => map.get(value) ?? value;
  }, [options]);
  // Only offer what isn't bound yet; selecting an option binds it immediately.
  const available = options.filter((option) => !items.includes(option.value));

  return (
    <section className="space-y-3">
      <TabHeading>{title}</TabHeading>
      {canWrite ? (
        <Select
          value=""
          disabled={loading || available.length === 0}
          onValueChange={(value) => {
            if (value) onBind(value);
          }}
        >
          <SelectTrigger className="max-w-xs">
            <SelectValue placeholder={available.length === 0 ? 'Nothing to add' : placeholder} />
          </SelectTrigger>
          <SelectContent>
            {available.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
      {items.length === 0 ? (
        <EmptyState label={emptyLabel} />
      ) : (
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <span
              key={item}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary/60 py-1 pl-3 pr-1.5 text-sm"
            >
              {labelOf(item)}
              {canWrite ? (
                <button
                  type="button"
                  aria-label={`Remove ${labelOf(item)}`}
                  className="grid size-4 place-items-center rounded-full text-muted-foreground hover:bg-destructive/15 hover:text-destructive"
                  onClick={() => onUnbind(item)}
                >
                  <X className="size-3" />
                </button>
              ) : null}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

// ─────────────────────────── tabs ───────────────────────────

function OverviewTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const detail = useAgentDetailQuery(agentName);
  const update = useUpdateAgentMutation(agentName);

  const [systemPrompt, setSystemPrompt] = useState('');
  const [allowedTools, setAllowedTools] = useState('');
  const [memoryNamespace, setMemoryNamespace] = useState('');

  useEffect(() => {
    if (detail.data) {
      setSystemPrompt(detail.data.system_prompt);
      setAllowedTools(detail.data.allowed_tools.join(', '));
      setMemoryNamespace(detail.data.memory_namespace ?? 'default');
    }
  }, [detail.data]);

  return (
    <div className="grid max-w-2xl gap-5">
      <div className="grid gap-2">
        <Label>Name</Label>
        <Input value={agentName} disabled />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cfg-prompt">System prompt</Label>
        <Textarea
          id="cfg-prompt"
          className="min-h-40"
          disabled={!canWrite}
          value={systemPrompt}
          onChange={(event) => setSystemPrompt(event.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cfg-tools">Allowed tools (comma-separated)</Label>
        <Input
          id="cfg-tools"
          placeholder="tool_a, tool_b"
          disabled={!canWrite}
          value={allowedTools}
          onChange={(event) => setAllowedTools(event.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cfg-ns">Memory namespace</Label>
        <Input
          id="cfg-ns"
          disabled={!canWrite}
          value={memoryNamespace}
          onChange={(event) => setMemoryNamespace(event.target.value)}
        />
      </div>
      {canWrite ? (
        <div>
          <Button
            disabled={update.isPending}
            onClick={() =>
              void update.mutateAsync({
                system_prompt: systemPrompt,
                allowed_tools: parseAllowedTools(allowedTools),
                memory_namespace: memoryNamespace.trim() || 'default',
              })
            }
          >
            Save
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function BindingsTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const bindings = useAgentBindingsQuery(agentName);
  const kbs = useAgentKbsQuery(agentName);

  // Catalogs that populate the dropdowns (all selectable targets in the platform).
  const allUsers = useUsersQuery();
  const allServers = useMcpServersQuery();
  const allKbs = useKbsQuery();

  const bindUser = useBindAgentUserMutation(agentName);
  const unbindUser = useUnbindAgentUserMutation(agentName);
  const bindMcp = useBindAgentMcpMutation(agentName);
  const unbindMcp = useUnbindAgentMcpMutation(agentName);
  const bindKb = useBindAgentKbMutation(agentName);
  const unbindKb = useUnbindAgentKbMutation(agentName);

  const userOptions = useMemo<BindOption[]>(
    () => (allUsers.data ?? []).map((user) => ({ value: user.id, label: user.email || user.name || user.id })),
    [allUsers.data]
  );
  const serverOptions = useMemo<BindOption[]>(
    () => (allServers.data ?? []).map((server) => ({ value: server.id, label: server.id })),
    [allServers.data]
  );
  const kbOptions = useMemo<BindOption[]>(
    () =>
      (allKbs.data ?? [])
        .filter((kb) => !kb.archived)
        .map((kb) => ({ value: kb.kb_id, label: kb.description ? `${kb.kb_id} · ${kb.description}` : kb.kb_id })),
    [allKbs.data]
  );

  return (
    <div className="space-y-6">
      <BindSelectEditor
        title="Users"
        placeholder="Select a user"
        canWrite={canWrite}
        loading={allUsers.isLoading}
        options={userOptions}
        items={bindings.data?.users ?? []}
        emptyLabel="No users"
        onBind={(value) => void bindUser.mutateAsync(value)}
        onUnbind={(value) => void unbindUser.mutateAsync(value)}
      />
      <Separator />
      <BindSelectEditor
        title="MCP Servers"
        placeholder="Select an MCP server"
        canWrite={canWrite}
        loading={allServers.isLoading}
        options={serverOptions}
        items={bindings.data?.mcp_servers ?? []}
        emptyLabel="No MCP servers"
        onBind={(value) => void bindMcp.mutateAsync(value)}
        onUnbind={(value) => void unbindMcp.mutateAsync(value)}
      />
      <Separator />
      <BindSelectEditor
        title="Knowledge Bases"
        placeholder="Select a knowledge base"
        canWrite={canWrite}
        loading={allKbs.isLoading}
        options={kbOptions}
        items={kbs.data?.kb_ids ?? []}
        emptyLabel="No knowledge bases"
        onBind={(value) => void bindKb.mutateAsync(value)}
        onUnbind={(value) => void unbindKb.mutateAsync(value)}
      />
    </div>
  );
}

function SkillRow({
  agentName,
  binding,
  canWrite,
}: {
  agentName: string;
  binding: AgentSkillBinding;
  canWrite: boolean;
}): JSX.Element {
  const setSkill = useSetAgentSkillMutation(agentName, binding.skill_name);
  return (
    <tr className="border-b border-border last:border-0">
      <td className="px-3 py-2.5 text-sm text-foreground">{binding.skill_name}</td>
      <td className="px-3 py-2.5 text-right">
        {canWrite ? (
          <Switch
            aria-label={binding.skill_name}
            checked={binding.enabled}
            onCheckedChange={(checked) => void setSkill.mutateAsync({ enabled: checked })}
          />
        ) : (
          <span className="text-xs text-muted-foreground">{binding.enabled ? 'enabled' : 'disabled'}</span>
        )}
      </td>
    </tr>
  );
}

function SkillsTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const skills = useAgentSkillsQuery(agentName);
  if (skills.data && skills.data.length === 0) {
    return <EmptyState label="No skills available" />;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full">
        <thead className="bg-secondary/50">
          <tr>
            <Th>Skill</Th>
            <Th className="text-right">Enabled</Th>
          </tr>
        </thead>
        <tbody>
          {(skills.data ?? []).map((binding) => (
            <SkillRow key={binding.skill_name} agentName={agentName} binding={binding} canWrite={canWrite} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SecretRow({
  agentName,
  envName,
  status,
  canWrite,
}: {
  agentName: string;
  envName: string;
  status: string;
  canWrite: boolean;
}): JSX.Element {
  const deleteSecret = useDeleteAgentSecretMutation(agentName, envName);
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
      <span className="font-mono text-sm">{envName}</span>
      <div className="flex items-center gap-2">
        <Badge variant={status === 'set' ? 'success' : 'outline'}>{status}</Badge>
        {canWrite ? (
          <Button size="icon" variant="ghost" aria-label={`Clear ${envName}`} onClick={() => void deleteSecret.mutateAsync()}>
            <Trash2 className="size-4" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function SecretsTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const required = useAgentRequiredEnvQuery(agentName);
  const secrets = useAgentSecretsQuery(agentName);
  const setSecret = useSetAgentSecretValueMutation(agentName);

  const [selectedEnv, setSelectedEnv] = useState('');
  const [value, setValue] = useState('');
  const [reveal, setReveal] = useState(false);

  const envOptions = useMemo(() => {
    const names = new Set<string>();
    (required.data?.required_env ?? []).forEach((row) => names.add(row.env_name));
    (secrets.data?.secrets ?? []).forEach((row) => names.add(row.env_name));
    return Array.from(names);
  }, [required.data, secrets.data]);

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <TabHeading>Required environment</TabHeading>
        {required.data && required.data.required_env.length === 0 ? (
          <EmptyState label="No required environment" />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full">
              <thead className="bg-secondary/50">
                <tr>
                  <Th>Env name</Th>
                  <Th>Source</Th>
                  <Th>Mode</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {(required.data?.required_env ?? []).map((row) => (
                  <tr key={row.env_name} className="border-b border-border last:border-0">
                    <td className="px-3 py-2.5 font-mono text-sm text-foreground">{row.env_name}</td>
                    <td className="px-3 py-2.5 text-sm text-muted-foreground">{row.source}</td>
                    <td className="px-3 py-2.5 text-sm text-muted-foreground">{row.mode}</td>
                    <td className="px-3 py-2.5">
                      <Badge variant={row.status === 'set' ? 'success' : 'outline'}>{row.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Separator />

      <section className="space-y-3">
        <TabHeading>Secrets</TabHeading>
        {canWrite ? (
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label className="text-xs text-muted-foreground">Env name</Label>
              <Select value={selectedEnv} onValueChange={setSelectedEnv}>
                <SelectTrigger className="w-48">
                  <SelectValue placeholder="Select env" />
                </SelectTrigger>
                <SelectContent>
                  {envOptions.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label className="text-xs text-muted-foreground">Value</Label>
              <div className="relative">
                <Input
                  className="w-64 pr-9"
                  type={reveal ? 'text' : 'password'}
                  placeholder="secret value"
                  value={value}
                  onChange={(event) => setValue(event.target.value)}
                />
                <button
                  type="button"
                  aria-label={reveal ? 'Hide value' : 'Show value'}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                  onClick={() => setReveal((current) => !current)}
                >
                  {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>
            <Button
              disabled={!selectedEnv || !value}
              onClick={() => {
                void setSecret.mutateAsync({ envName: selectedEnv, value });
                setValue('');
              }}
            >
              Set Secret
            </Button>
          </div>
        ) : null}

        {secrets.data && secrets.data.secrets.length === 0 ? (
          <EmptyState label="No secrets" />
        ) : (
          <div className="space-y-2">
            {(secrets.data?.secrets ?? []).map((secret) => (
              <SecretRow
                key={secret.env_name}
                agentName={agentName}
                envName={secret.env_name}
                status={secret.status}
                canWrite={canWrite}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function DeployTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const versions = useAgentVersionsQuery(agentName, true);
  const deploy = useDeployAgentMutation(agentName);
  const activate = useActivateAgentVersionMutation(agentName);
  const exportYaml = useExportAgentYamlMutation(agentName);

  const downloadYaml = async (): Promise<void> => {
    const result = await exportYaml.mutateAsync();
    const blob = new Blob([result.yaml], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${agentName}.agent.yaml`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {canWrite ? (
        <Button disabled={deploy.isPending} onClick={() => void deploy.mutateAsync()}>
          Deploy current version
        </Button>
      ) : null}

      <section className="space-y-3">
        <TabHeading>Version history</TabHeading>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full">
            <thead className="bg-secondary/50">
              <tr>
                <Th>Version</Th>
                <Th>Active</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {(versions.data ?? []).map((version) => (
                <tr key={version.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2.5 font-mono text-sm text-foreground">v{version.version}</td>
                  <td className="px-3 py-2.5">
                    {version.is_active ? <Badge variant="success">active</Badge> : null}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    {!version.is_active && canWrite ? (
                      <Button size="sm" variant="outline" onClick={() => void activate.mutateAsync(version.version)}>
                        Activate
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
              {versions.data && versions.data.length === 0 ? (
                <tr>
                  <td colSpan={3}>
                    <EmptyState label="No versions" />
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <TabHeading>YAML export</TabHeading>
        <Button variant="outline" disabled={exportYaml.isPending} onClick={() => void downloadYaml()}>
          <Download className="size-4" /> Export YAML
        </Button>
      </section>
    </div>
  );
}

const IM_PLATFORMS = ['slack', 'telegram'] as const;

function ImCapabilitiesTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const detail = useAgentDetailQuery(agentName);
  const bindings = useAgentBindingsQuery(agentName);
  const setCaps = useSetAgentImCapabilitiesMutation(agentName);
  const addGroup = useAddAgentImGroupMutation(agentName);
  const removeGroup = useRemoveAgentImGroupMutation(agentName);

  const [caps, setCaps2] = useState<AgentImCapabilitiesInput>({ supports_dm: false, supports_groups: false });
  const [platform, setPlatform] = useState<string>('slack');
  const [groupId, setGroupId] = useState('');

  // Bound groups are read back from the bindings endpoint; add/remove invalidate
  // that query, so the list reflects the persisted state (and survives reload).
  const groups = bindings.data?.groups ?? [];

  useEffect(() => {
    setCaps2({
      supports_dm: detail.data?.supports_dm ?? false,
      supports_groups: detail.data?.supports_groups ?? false,
    });
  }, [detail.data?.supports_dm, detail.data?.supports_groups]);

  const onAddGroup = async (): Promise<void> => {
    const id = groupId.trim();
    if (!id) return;
    await addGroup.mutateAsync({ platform, group_id: id });
    setGroupId('');
  };

  const onRemoveGroup = async (target: AgentImGroupInput): Promise<void> => {
    await removeGroup.mutateAsync(target);
  };

  return (
    <div className="max-w-xl space-y-6">
      <section className="space-y-4">
        <TabHeading>Capabilities</TabHeading>
        <label className="flex items-center justify-between gap-4 text-sm">
          Supports direct messages
          <Switch
            aria-label="Supports direct messages"
            disabled={!canWrite}
            checked={caps.supports_dm}
            onCheckedChange={(checked) => setCaps2((current) => ({ ...current, supports_dm: checked }))}
          />
        </label>
        <label className="flex items-center justify-between gap-4 text-sm">
          Supports group chats
          <Switch
            aria-label="Supports group chats"
            disabled={!canWrite}
            checked={caps.supports_groups}
            onCheckedChange={(checked) => setCaps2((current) => ({ ...current, supports_groups: checked }))}
          />
        </label>
        {canWrite ? (
          <Button size="sm" disabled={setCaps.isPending} onClick={() => void setCaps.mutateAsync(caps)}>
            Save
          </Button>
        ) : null}
      </section>

      <Separator />

      <section className="space-y-3">
        <TabHeading>Group access</TabHeading>
        <p className="text-sm text-muted-foreground">
          Bind the Slack / Telegram groups this agent is allowed to respond in.
        </p>
        {canWrite ? (
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label className="text-xs text-muted-foreground">Platform</Label>
              <Select value={platform} onValueChange={setPlatform}>
                <SelectTrigger className="w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {IM_PLATFORMS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label className="text-xs text-muted-foreground">Group id</Label>
              <Input
                className="w-56"
                placeholder="e.g. C0123 / -1001234567"
                value={groupId}
                onChange={(event) => setGroupId(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void onAddGroup();
                }}
              />
            </div>
            <Button
              variant="secondary"
              disabled={!groupId.trim() || addGroup.isPending}
              onClick={() => void onAddGroup()}
            >
              Add
            </Button>
          </div>
        ) : null}
        {groups.length === 0 ? (
          <EmptyState label="No groups bound" />
        ) : (
          <div className="flex flex-wrap gap-2">
            {groups.map((group) => (
              <span
                key={`${group.platform}:${group.group_id}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary/60 py-1 pl-3 pr-1.5 text-sm"
              >
                <span className="text-muted-foreground">{group.platform}:</span>
                {group.group_id}
                {canWrite ? (
                  <button
                    type="button"
                    aria-label={`Remove ${group.platform}:${group.group_id}`}
                    className="grid size-4 place-items-center rounded-full text-muted-foreground hover:bg-destructive/15 hover:text-destructive"
                    onClick={() => void onRemoveGroup(group)}
                  >
                    <X className="size-3" />
                  </button>
                ) : null}
              </span>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function AgentConfigurePage(): JSX.Element {
  const params = useParams();
  const navigate = useNavigate();
  const me = useAdminMeQuery();
  const agentName = params.name ?? '';
  const canWrite = me.data?.role !== 'viewer';

  if (!agentName) {
    return <p className="text-sm text-muted-foreground">Agent not found.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" aria-label="Back to agents" onClick={() => navigate('/agents')}>
          <ArrowLeft className="size-4" />
        </Button>
        <h2 className="text-xl font-semibold tracking-tight">Configure · {agentName}</h2>
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="flex w-full flex-wrap justify-start">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="bindings">Bindings</TabsTrigger>
          <TabsTrigger value="skills">Skills</TabsTrigger>
          <TabsTrigger value="secrets">Secrets</TabsTrigger>
          <TabsTrigger value="deploy">Deploy</TabsTrigger>
          <TabsTrigger value="im">IM Capabilities</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="bindings">
          <BindingsTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="skills">
          <SkillsTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="secrets">
          <SecretsTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="deploy">
          <DeployTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="im">
          <ImCapabilitiesTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

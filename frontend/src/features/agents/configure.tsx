import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Download, Eye, EyeOff, Inbox, Trash2, X } from 'lucide-react';

import { useT } from '@/i18n';
import { useAdminApi } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { MultiSelect, type MultiSelectOption } from '@/components/ui/multi-select';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  type AgentImCapabilitiesInput,
  type AgentImGroupInput,
  type AgentModelOverrides,
  useAddAgentImGroupMutation,
  useAgentBindingsQuery,
  useAgentDetailQuery,
  useAgentKbsQuery,
  useAgentRequiredEnvQuery,
  useAgentSecretsQuery,
  useAgentSkillsQuery,
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
import { useProvidersQuery } from '@/features/providers/api';
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

// The agent's default model route maps to a single provider id; the platform expands it
// into the full model policy. Read it from model_overrides, taking the first string key any
// authoring style may have used.
function defaultRouteProviderId(overrides: AgentModelOverrides | undefined): string {
  const routes = (overrides?.routes ?? {}) as Record<string, Array<Record<string, unknown>>>;
  const entry = routes.default?.[0];
  if (!entry) return '';
  for (const value of [entry.provider_id, entry.provider, entry.target]) {
    if (typeof value === 'string' && value) return value;
  }
  return '';
}

// Set (or clear) the default-route provider while preserving every sibling key the platform
// stores alongside it (other routes, credential slots), so an edit never drops that state.
function withDefaultRouteProvider(
  overrides: AgentModelOverrides | undefined,
  providerId: string
): AgentModelOverrides {
  const next: AgentModelOverrides = { ...(overrides ?? {}) };
  const routes = { ...((next.routes as Record<string, unknown>) ?? {}) };
  if (providerId) {
    routes.default = [{ provider_id: providerId }];
  } else {
    delete routes.default;
  }
  next.routes = routes;
  return next;
}

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
  const t = useT();
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
            <SelectValue placeholder={available.length === 0 ? t('agents.nothingToAdd') : placeholder} />
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
                  aria-label={t('agents.remove', { name: labelOf(item) })}
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
  const t = useT();
  const detail = useAgentDetailQuery(agentName);
  const update = useUpdateAgentMutation(agentName);
  const allProviders = useProvidersQuery();

  const [systemPrompt, setSystemPrompt] = useState('');
  const [allowedTools, setAllowedTools] = useState('');
  const [memoryNamespace, setMemoryNamespace] = useState('');
  const [providerId, setProviderId] = useState('');

  useEffect(() => {
    if (detail.data) {
      setSystemPrompt(detail.data.system_prompt);
      setAllowedTools(detail.data.allowed_tools.join(', '));
      setMemoryNamespace(detail.data.memory_namespace ?? 'default');
      setProviderId(defaultRouteProviderId(detail.data.model_overrides));
    }
  }, [detail.data]);

  const onSave = (): void => {
    void update.mutateAsync({
      system_prompt: systemPrompt,
      allowed_tools: parseAllowedTools(allowedTools),
      memory_namespace: memoryNamespace.trim() || 'default',
      model_overrides: withDefaultRouteProvider(detail.data?.model_overrides, providerId),
    });
  };

  return (
    <div className="grid max-w-2xl gap-5">
      <div className="grid gap-2">
        <Label>{t('agents.nameFieldLabel')}</Label>
        <Input value={agentName} disabled />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cfg-prompt">{t('agents.systemPromptLabel')}</Label>
        <Textarea
          id="cfg-prompt"
          className="min-h-40"
          disabled={!canWrite}
          value={systemPrompt}
          onChange={(event) => setSystemPrompt(event.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cfg-tools">{t('agents.allowedToolsLabel')}</Label>
        <Input
          id="cfg-tools"
          placeholder="tool_a, tool_b"
          disabled={!canWrite}
          value={allowedTools}
          onChange={(event) => setAllowedTools(event.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cfg-ns">{t('agents.memoryNamespaceLabel')}</Label>
        <Input
          id="cfg-ns"
          disabled={!canWrite}
          value={memoryNamespace}
          onChange={(event) => setMemoryNamespace(event.target.value)}
        />
      </div>
      <section className="space-y-3">
        <TabHeading>{t('agents.modelProvider')}</TabHeading>
        <p className="text-sm text-muted-foreground">{t('agents.modelProviderHint')}</p>
        {canWrite ? (
          <Select
            value={providerId || undefined}
            disabled={allProviders.isLoading || update.isPending}
            onValueChange={setProviderId}
          >
            <SelectTrigger className="max-w-xs">
              <SelectValue placeholder={t('agents.selectProvider')} />
            </SelectTrigger>
            <SelectContent>
              {(allProviders.data ?? []).map((provider) => (
                <SelectItem key={provider.id} value={provider.id}>
                  {provider.model ? `${provider.id} · ${provider.model}` : provider.id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <p className="text-sm text-foreground">{providerId || '—'}</p>
        )}
      </section>

      {canWrite ? (
        <div>
          <Button disabled={update.isPending} onClick={onSave}>
            {t('common.save')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function McpServersTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT();
  const bindings = useAgentBindingsQuery(agentName);
  const allServers = useMcpServersQuery();
  const bindMcp = useBindAgentMcpMutation(agentName);
  const unbindMcp = useUnbindAgentMcpMutation(agentName);

  const serverOptions = useMemo<BindOption[]>(
    () => (allServers.data ?? []).map((server) => ({ value: server.id, label: server.id })),
    [allServers.data]
  );

  return (
    <BindSelectEditor
      title={t('agents.mcpServers')}
      placeholder={t('agents.selectMcpServer')}
      canWrite={canWrite}
      loading={allServers.isLoading}
      options={serverOptions}
      items={bindings.data?.mcp_servers ?? []}
      emptyLabel={t('agents.noMcpServers')}
      onBind={(value) => void bindMcp.mutateAsync(value)}
      onUnbind={(value) => void unbindMcp.mutateAsync(value)}
    />
  );
}

function KnowledgeBasesTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT();
  const kbs = useAgentKbsQuery(agentName);
  const allKbs = useKbsQuery();
  const bindKb = useBindAgentKbMutation(agentName);
  const unbindKb = useUnbindAgentKbMutation(agentName);

  const kbOptions = useMemo<BindOption[]>(
    () =>
      (allKbs.data ?? [])
        .filter((kb) => !kb.archived)
        .map((kb) => ({ value: kb.kb_id, label: kb.description ? `${kb.kb_id} · ${kb.description}` : kb.kb_id })),
    [allKbs.data]
  );

  return (
    <BindSelectEditor
      title={t('agents.knowledgeBases')}
      placeholder={t('agents.selectKnowledgeBase')}
      canWrite={canWrite}
      loading={allKbs.isLoading}
      options={kbOptions}
      items={kbs.data?.kb_ids ?? []}
      emptyLabel={t('agents.noKnowledgeBases')}
      onBind={(value) => void bindKb.mutateAsync(value)}
      onUnbind={(value) => void unbindKb.mutateAsync(value)}
    />
  );
}

function SkillsTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT();
  const skills = useAgentSkillsQuery(agentName);
  const setSkill = useSetAgentSkillMutation(agentName);

  const options = useMemo<MultiSelectOption[]>(
    () => (skills.data ?? []).map((binding) => ({ value: binding.skill_name, label: binding.skill_name })),
    [skills.data]
  );
  const selected = useMemo(
    () => (skills.data ?? []).filter((binding) => binding.enabled).map((binding) => binding.skill_name),
    [skills.data]
  );

  if (skills.data && skills.data.length === 0) {
    return <EmptyState label={t('agents.noSkillsAvailable')} />;
  }

  if (!canWrite) {
    return (
      <section className="space-y-3">
        <TabHeading>{t('agents.skillsTitle')}</TabHeading>
        {selected.length === 0 ? (
          <EmptyState label={t('agents.noSkillsBound')} />
        ) : (
          <div className="flex flex-wrap gap-2">
            {selected.map((name) => (
              <span
                key={name}
                className="inline-flex items-center rounded-full border border-border bg-secondary/60 px-3 py-1 text-sm"
              >
                {name}
              </span>
            ))}
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <TabHeading>{t('agents.skillsTitle')}</TabHeading>
      <MultiSelect
        className="max-w-xl"
        triggerLabel={t('agents.skillsTitle')}
        placeholder={t('agents.selectSkills')}
        searchPlaceholder={t('agents.searchSkills')}
        noMatchLabel={t('agents.noSkillsMatch')}
        removeLabel={(name) => t('agents.remove', { name })}
        options={options}
        selected={selected}
        onToggle={(value, enabled) => void setSkill.mutateAsync({ skill_name: value, enabled })}
      />
    </section>
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
  const t = useT();
  const deleteSecret = useDeleteAgentSecretMutation(agentName, envName);
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
      <span className="font-mono text-sm">{envName}</span>
      <div className="flex items-center gap-2">
        <Badge variant={status === 'set' ? 'success' : 'outline'}>{status}</Badge>
        {canWrite ? (
          <Button size="icon" variant="ghost" aria-label={t('agents.clearSecret', { name: envName })} onClick={() => void deleteSecret.mutateAsync()}>
            <Trash2 className="size-4" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function SecretsTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT();
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
        <TabHeading>{t('agents.requiredEnvironment')}</TabHeading>
        {required.data && required.data.required_env.length === 0 ? (
          <EmptyState label={t('agents.noRequiredEnvironment')} />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full">
              <thead className="bg-secondary/50">
                <tr>
                  <Th>{t('agents.envNameColumn')}</Th>
                  <Th>{t('agents.sourceColumn')}</Th>
                  <Th>{t('agents.modeColumn')}</Th>
                  <Th>{t('agents.statusColumn')}</Th>
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
        <TabHeading>{t('agents.secrets')}</TabHeading>
        {canWrite ? (
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label className="text-xs text-muted-foreground">{t('agents.envNameColumn')}</Label>
              <Select value={selectedEnv} onValueChange={setSelectedEnv}>
                <SelectTrigger className="w-48">
                  <SelectValue placeholder={t('agents.selectEnv')} />
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
              <Label className="text-xs text-muted-foreground">{t('agents.valueLabel')}</Label>
              <div className="relative">
                <Input
                  className="w-64 pr-9"
                  type={reveal ? 'text' : 'password'}
                  placeholder={t('agents.secretValuePlaceholder')}
                  value={value}
                  onChange={(event) => setValue(event.target.value)}
                />
                <button
                  type="button"
                  aria-label={reveal ? t('agents.hideValue') : t('agents.showValue')}
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
              {t('agents.setSecret')}
            </Button>
          </div>
        ) : null}

        {secrets.data && secrets.data.secrets.length === 0 ? (
          <EmptyState label={t('agents.noSecrets')} />
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
  const t = useT();
  const deploy = useDeployAgentMutation(agentName);
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
          {t('agents.deployCurrentVersion')}
        </Button>
      ) : null}

      <section className="space-y-3">
        <TabHeading>{t('agents.yamlExport')}</TabHeading>
        <Button variant="outline" disabled={exportYaml.isPending} onClick={() => void downloadYaml()}>
          <Download className="size-4" /> {t('agents.exportYaml')}
        </Button>
      </section>
    </div>
  );
}

const IM_PLATFORMS = ['slack', 'telegram'] as const;

function ImCapabilitiesTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT();
  const detail = useAgentDetailQuery(agentName);
  const bindings = useAgentBindingsQuery(agentName);
  const setCaps = useSetAgentImCapabilitiesMutation(agentName);
  const addGroup = useAddAgentImGroupMutation(agentName);
  const removeGroup = useRemoveAgentImGroupMutation(agentName);
  const bindUser = useBindAgentUserMutation(agentName);
  const unbindUser = useUnbindAgentUserMutation(agentName);
  const update = useUpdateAgentMutation(agentName);
  const allUsers = useUsersQuery();

  const [caps, setCaps2] = useState<AgentImCapabilitiesInput>({ supports_dm: false, supports_groups: false });
  const [platform, setPlatform] = useState<string>('slack');
  const [groupId, setGroupId] = useState('');
  const [configYaml, setConfigYaml] = useState('');
  const [configDirty, setConfigDirty] = useState(false);

  // Bound groups are read back from the bindings endpoint; add/remove invalidate
  // that query, so the list reflects the persisted state (and survives reload).
  const groups = bindings.data?.groups ?? [];

  const userOptions = useMemo<BindOption[]>(
    () => (allUsers.data ?? []).map((user) => ({ value: user.id, label: user.email || user.name || user.id })),
    [allUsers.data]
  );

  useEffect(() => {
    setCaps2({
      supports_dm: detail.data?.supports_dm ?? false,
      supports_groups: detail.data?.supports_groups ?? false,
    });
  }, [detail.data?.supports_dm, detail.data?.supports_groups]);

  // Mirror server-side overrides into the editor, but never clobber an in-progress edit.
  useEffect(() => {
    if (!configDirty) {
      setConfigYaml(detail.data?.config_overrides_yaml ?? '');
    }
  }, [detail.data?.config_overrides_yaml, configDirty]);

  const onAddGroup = async (): Promise<void> => {
    const id = groupId.trim();
    if (!id) return;
    await addGroup.mutateAsync({ platform, group_id: id });
    setGroupId('');
  };

  const onRemoveGroup = async (target: AgentImGroupInput): Promise<void> => {
    await removeGroup.mutateAsync(target);
  };

  const onSaveOverrides = async (): Promise<void> => {
    await update.mutateAsync({ config_overrides_yaml: configYaml });
    setConfigDirty(false);
  };

  return (
    <div className="max-w-xl space-y-6">
      <section className="space-y-4">
        <TabHeading>{t('agents.capabilities')}</TabHeading>
        <label className="flex items-center justify-between gap-4 text-sm">
          {t('agents.supportsDirectMessages')}
          <Switch
            aria-label={t('agents.supportsDirectMessages')}
            disabled={!canWrite}
            checked={caps.supports_dm}
            onCheckedChange={(checked) => setCaps2((current) => ({ ...current, supports_dm: checked }))}
          />
        </label>
        <label className="flex items-center justify-between gap-4 text-sm">
          {t('agents.supportsGroupChats')}
          <Switch
            aria-label={t('agents.supportsGroupChats')}
            disabled={!canWrite}
            checked={caps.supports_groups}
            onCheckedChange={(checked) => setCaps2((current) => ({ ...current, supports_groups: checked }))}
          />
        </label>
        {canWrite ? (
          <Button size="sm" disabled={setCaps.isPending} onClick={() => void setCaps.mutateAsync(caps)}>
            {t('common.save')}
          </Button>
        ) : null}
      </section>

      <Separator />

      <section className="space-y-3">
        <TabHeading>{t('agents.groupAccess')}</TabHeading>
        <p className="text-sm text-muted-foreground">{t('agents.groupAccessHint')}</p>
        {canWrite ? (
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label className="text-xs text-muted-foreground">{t('agents.platformLabel')}</Label>
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
              <Label className="text-xs text-muted-foreground">{t('agents.groupIdLabel')}</Label>
              <Input
                className="w-56"
                placeholder={t('agents.groupIdPlaceholder')}
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
              {t('agents.add')}
            </Button>
          </div>
        ) : null}
        {groups.length === 0 ? (
          <EmptyState label={t('agents.noGroupsBound')} />
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
                    aria-label={t('agents.remove', { name: `${group.platform}:${group.group_id}` })}
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

      <Separator />

      <BindSelectEditor
        title={t('agents.users')}
        placeholder={t('agents.selectUser')}
        canWrite={canWrite}
        loading={allUsers.isLoading}
        options={userOptions}
        items={bindings.data?.users ?? []}
        emptyLabel={t('agents.noUsers')}
        onBind={(value) => void bindUser.mutateAsync(value)}
        onUnbind={(value) => void unbindUser.mutateAsync(value)}
      />

      <Separator />

      <section className="space-y-3">
        <TabHeading>{t('agents.imConnectors')}</TabHeading>
        <p className="text-sm text-muted-foreground">{t('agents.imConnectorsHint')}</p>
        <div className="grid gap-2">
          <Label htmlFor="cfg-overrides" className="text-xs text-muted-foreground">
            {t('agents.advancedOverrides')}
          </Label>
          <Textarea
            id="cfg-overrides"
            className="min-h-48 font-mono"
            disabled={!canWrite}
            placeholder={'im:\n  slack:\n    bot_token_env: SLACK_BOT_TOKEN\n    app_token_env: SLACK_APP_TOKEN'}
            value={configYaml}
            onChange={(event) => {
              setConfigDirty(true);
              setConfigYaml(event.target.value);
            }}
          />
        </div>
        {canWrite ? (
          <Button size="sm" disabled={!configDirty || update.isPending} onClick={() => void onSaveOverrides()}>
            {t('agents.saveOverrides')}
          </Button>
        ) : null}
      </section>
    </div>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function AgentConfigurePage(): JSX.Element {
  const t = useT();
  const params = useParams();
  const navigate = useNavigate();
  const me = useAdminMeQuery();
  const agentName = params.name ?? '';
  const canWrite = me.data?.role !== 'viewer';

  if (!agentName) {
    return <p className="text-sm text-muted-foreground">{t('agents.notFound')}</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" aria-label={t('agents.backToAgents')} onClick={() => navigate('/agents')}>
          <ArrowLeft className="size-4" />
        </Button>
        <h2 className="text-xl font-semibold tracking-tight">{t('agents.configureTitle', { name: agentName })}</h2>
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="flex w-full flex-wrap justify-start">
          <TabsTrigger value="overview">{t('agents.tabOverview')}</TabsTrigger>
          <TabsTrigger value="mcp">{t('agents.mcpServers')}</TabsTrigger>
          <TabsTrigger value="kb">{t('agents.knowledgeBases')}</TabsTrigger>
          <TabsTrigger value="skills">{t('agents.tabSkills')}</TabsTrigger>
          <TabsTrigger value="secrets">{t('agents.secrets')}</TabsTrigger>
          <TabsTrigger value="deploy">{t('agents.tabDeploy')}</TabsTrigger>
          <TabsTrigger value="im">{t('agents.tabImCapabilities')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="mcp">
          <McpServersTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="kb">
          <KnowledgeBasesTab agentName={agentName} canWrite={canWrite} />
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

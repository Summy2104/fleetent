import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download, Eye, EyeOff, Inbox, Trash2, X } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { Badge } from '@/components/base/badge'
import { SimpleSelect } from '@/components/base/simple-select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import {
  type AgentImCapabilitiesInput,
  type AgentImGroupInput,
  useAddAgentImGroupMutation,
  useAgentDetailQuery,
  useAgentGroupsQuery,
  useAgentKbsQuery,
  useAgentRequiredEnvQuery,
  useAgentSecretsQuery,
  useAgentUsersQuery,
  useBindAgentKbMutation,
  useBindAgentUserMutation,
  useDeleteAgentSecretMutation,
  useDeleteAgentSecretValueMutation,
  useExportAgentYamlMutation,
  useRemoveAgentImGroupMutation,
  useSetAgentImCapabilitiesMutation,
  useSetAgentSecretValueMutation,
  useUnbindAgentKbMutation,
  useUnbindAgentUserMutation,
  useUpdateAgentMutation,
} from '@/features/agents/api'
import {
  buildAgentConfigUpdate,
  defaultRouteModelId,
  resolveProviderKeyAction,
} from '@/features/agents/configure-logic'
import { McpServersTab } from '@/features/agents/mcp-servers-tab'
import { SkillsTab } from '@/features/agents/skills-tab'
import { useKbsQuery } from '@/features/kb/api'
import { useModelsQuery, useProvidersQuery } from '@/features/providers/api'
import { useUsersQuery } from '@/features/users/api'
import { useT } from '@/i18n'
import { useAdminApi } from '@/lib/api-client'
import { cn } from '@/lib/utils'

type AdminMe = { email: string; id: string; role: string }

function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

// ─────────────────────────── shared bits ───────────────────────────

function EmptyState({ label }: { label: string }): JSX.Element {
  return (
    <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
      <Inbox className="size-6 opacity-50" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

function TabHeading({ children }: { children: ReactNode }): JSX.Element {
  return <h3 className="font-semibold text-foreground text-sm">{children}</h3>
}

function Th({ children, className }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <th
      className={cn(
        'px-3 py-2 text-left font-semibold text-muted-foreground text-xs uppercase tracking-wide',
        className
      )}
    >
      {children}
    </th>
  )
}

type BindOption = { value: string; label: string }

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
  title: string
  placeholder: string
  options: BindOption[]
  items: string[]
  canWrite: boolean
  loading: boolean
  emptyLabel: string
  onBind: (value: string) => void
  onUnbind: (value: string) => void
}): JSX.Element {
  const t = useT()
  // Resolve a bound id back to its human label (email / name) for the chips.
  const labelOf = useMemo(() => {
    const map = new Map(options.map((option) => [option.value, option.label]))
    return (value: string) => map.get(value) ?? value
  }, [options])
  // Only offer what isn't bound yet; selecting an option binds it immediately.
  const available = options.filter((option) => !items.includes(option.value))

  return (
    <section className="space-y-3">
      <TabHeading>{title}</TabHeading>
      {canWrite ? (
        <Select
          disabled={loading || available.length === 0}
          onValueChange={(value) => {
            if (value) onBind(value)
          }}
          value=""
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
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary/60 py-1 pr-1.5 pl-3 text-sm"
              key={item}
            >
              {labelOf(item)}
              {canWrite ? (
                <button
                  aria-label={t('agents.remove', { name: labelOf(item) })}
                  className="grid size-4 place-items-center rounded-full text-muted-foreground hover:bg-destructive/15 hover:text-destructive"
                  onClick={() => onUnbind(item)}
                  type="button"
                >
                  <X className="size-3" />
                </button>
              ) : null}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

// ─────────────────────────── tabs ───────────────────────────

function OverviewTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT()
  const detail = useAgentDetailQuery(agentName)
  const update = useUpdateAgentMutation(agentName)
  const allModels = useModelsQuery()
  const allProviders = useProvidersQuery()
  const secrets = useAgentSecretsQuery(agentName)
  const setSecret = useSetAgentSecretValueMutation(agentName)
  const deleteSecretValue = useDeleteAgentSecretValueMutation(agentName)

  const [systemPrompt, setSystemPrompt] = useState('')
  const [allowedTools, setAllowedTools] = useState('')
  const [memoryNamespace, setMemoryNamespace] = useState('')
  const [modelId, setModelId] = useState<string | null>('')
  const [providerKeyOverride, setProviderKeyOverride] = useState('')
  const [providerKeyDirty, setProviderKeyDirty] = useState(false)

  const selectedModel = useMemo(
    () => (allModels.data ?? []).find((model) => model.id === modelId) ?? null,
    [allModels.data, modelId]
  )
  const selectedProvider = useMemo(
    () =>
      selectedModel
        ? ((allProviders.data ?? []).find((provider) => provider.id === selectedModel.provider_id) ?? null)
        : null,
    [allProviders.data, selectedModel]
  )
  const selectedProviderEnv = selectedProvider?.api_key_env ?? ''
  const selectedProviderSecretStatus = useMemo(
    () =>
      selectedProviderEnv
        ? ((secrets.data?.secrets ?? []).find((secret) => secret.env_name === selectedProviderEnv)?.status ?? 'unset')
        : 'unset',
    [secrets.data, selectedProviderEnv]
  )

  useEffect(() => {
    if (detail.data) {
      setSystemPrompt(detail.data.system_prompt)
      setAllowedTools(detail.data.allowed_tools.join(', '))
      setMemoryNamespace(detail.data.memory_namespace ?? 'default')
      setModelId(defaultRouteModelId(detail.data.model_overrides))
      setProviderKeyOverride('')
      setProviderKeyDirty(false)
    }
  }, [detail.data])

  const onSave = (): void => {
    void (async () => {
      await update.mutateAsync(
        buildAgentConfigUpdate({
          systemPrompt,
          allowedTools,
          memoryNamespace,
          modelId,
          currentOverrides: detail.data?.model_overrides,
        })
      )
      if (providerKeyDirty && selectedProviderEnv) {
        const keyAction = resolveProviderKeyAction(providerKeyOverride, selectedProviderSecretStatus)
        if (keyAction === 'set') {
          await setSecret.mutateAsync({ envName: selectedProviderEnv, value: providerKeyOverride })
        } else if (keyAction === 'delete') {
          await deleteSecretValue.mutateAsync(selectedProviderEnv)
        }
        setProviderKeyDirty(false)
        setProviderKeyOverride('')
      }
    })()
  }

  return (
    <div className="grid max-w-2xl gap-5">
      <div className="grid gap-2">
        <Label>{t('agents.nameFieldLabel')}</Label>
        <Input disabled value={agentName} />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cfg-prompt">{t('agents.systemPromptLabel')}</Label>
        <Textarea
          className="min-h-40"
          disabled={!canWrite}
          id="cfg-prompt"
          onChange={(event) => setSystemPrompt(event.target.value)}
          value={systemPrompt}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cfg-tools">{t('agents.allowedToolsLabel')}</Label>
        <Input
          disabled={!canWrite}
          id="cfg-tools"
          onChange={(event) => setAllowedTools(event.target.value)}
          placeholder="tool_a, tool_b"
          value={allowedTools}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cfg-ns">{t('agents.memoryNamespaceLabel')}</Label>
        <Input
          disabled={!canWrite}
          id="cfg-ns"
          onChange={(event) => setMemoryNamespace(event.target.value)}
          value={memoryNamespace}
        />
      </div>
      <section className="space-y-3">
        <TabHeading>{t('agents.modelProvider')}</TabHeading>
        <p className="text-muted-foreground text-sm">{t('agents.modelProviderHint')}</p>
        {canWrite ? (
          <SimpleSelect
            disabled={allModels.isLoading || update.isPending}
            onValueChange={setModelId}
            options={(allModels.data ?? []).map((model) => ({
              value: model.id,
              label: model.model_name ? `${model.id} · ${model.model_name}` : model.id,
            }))}
            placeholder={t('agents.selectProvider')}
            triggerClassName="max-w-xs"
            value={modelId}
          />
        ) : (
          <p className="text-foreground text-sm">{modelId || '—'}</p>
        )}
      </section>

      {selectedProviderEnv ? (
        <section className="space-y-3">
          <TabHeading>Provider key override</TabHeading>
          <p className="text-muted-foreground text-sm">
            {selectedProviderEnv} · {selectedProviderSecretStatus}
          </p>
          {canWrite ? (
            <div className="grid gap-2">
              <Label htmlFor="cfg-provider-key">Provider API Key Override</Label>
              <Input
                id="cfg-provider-key"
                onChange={(event) => {
                  setProviderKeyOverride(event.target.value)
                  setProviderKeyDirty(true)
                }}
                placeholder="Leave empty to use the shared provider key"
                type="password"
                value={providerKeyOverride}
              />
            </div>
          ) : null}
        </section>
      ) : null}

      {canWrite ? (
        <div>
          <Button disabled={update.isPending} onClick={onSave}>
            {t('common.save')}
          </Button>
        </div>
      ) : null}

      <AgentYamlExport agentName={agentName} />
    </div>
  )
}

function KnowledgeBasesTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT()
  const kbs = useAgentKbsQuery(agentName)
  const allKbs = useKbsQuery()
  const bindKb = useBindAgentKbMutation(agentName)
  const unbindKb = useUnbindAgentKbMutation(agentName)

  const kbOptions = useMemo<BindOption[]>(
    () =>
      (allKbs.data ?? [])
        .filter((kb) => !kb.archived)
        .map((kb) => ({ value: kb.kb_id, label: kb.description ? `${kb.kb_id} · ${kb.description}` : kb.kb_id })),
    [allKbs.data]
  )

  return (
    <BindSelectEditor
      canWrite={canWrite}
      emptyLabel={t('agents.noKnowledgeBases')}
      items={kbs.data?.kb_ids ?? []}
      loading={allKbs.isLoading}
      onBind={(value) => void bindKb.mutateAsync(value)}
      onUnbind={(value) => void unbindKb.mutateAsync(value)}
      options={kbOptions}
      placeholder={t('agents.selectKnowledgeBase')}
      title={t('agents.knowledgeBases')}
    />
  )
}

function SecretRow({
  agentName,
  envName,
  status,
  canWrite,
}: {
  agentName: string
  envName: string
  status: string
  canWrite: boolean
}): JSX.Element {
  const t = useT()
  const deleteSecret = useDeleteAgentSecretMutation(agentName, envName)
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
      <span className="font-mono text-sm">{envName}</span>
      <div className="flex items-center gap-2">
        <Badge variant={status === 'set' ? 'success' : 'outline'}>{status}</Badge>
        {canWrite ? (
          <Button
            aria-label={t('agents.clearSecret', { name: envName })}
            onClick={() => void deleteSecret.mutateAsync()}
            size="icon"
            variant="ghost"
          >
            <Trash2 className="size-4" />
          </Button>
        ) : null}
      </div>
    </div>
  )
}

function SecretsTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT()
  const required = useAgentRequiredEnvQuery(agentName)
  const secrets = useAgentSecretsQuery(agentName)
  const setSecret = useSetAgentSecretValueMutation(agentName)

  const [selectedEnv, setSelectedEnv] = useState<string | null>('')
  const [value, setValue] = useState('')
  const [reveal, setReveal] = useState(false)

  const envOptions = useMemo(() => {
    const names = new Set<string>()
    for (const row of required.data?.required_env ?? []) names.add(row.env_name)
    for (const row of secrets.data?.secrets ?? []) names.add(row.env_name)
    return Array.from(names)
  }, [required.data, secrets.data])

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
                  <tr className="border-border border-b last:border-0" key={row.env_name}>
                    <td className="px-3 py-2.5 font-mono text-foreground text-sm">{row.env_name}</td>
                    <td className="px-3 py-2.5 text-muted-foreground text-sm">{row.source}</td>
                    <td className="px-3 py-2.5 text-muted-foreground text-sm">{row.mode}</td>
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
              <Label className="text-muted-foreground text-xs">{t('agents.envNameColumn')}</Label>
              <SimpleSelect
                onValueChange={setSelectedEnv}
                options={envOptions.map((name) => ({ value: name, label: name }))}
                placeholder={t('agents.selectEnv')}
                triggerClassName="w-48"
                value={selectedEnv}
              />
            </div>
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground text-xs">{t('agents.valueLabel')}</Label>
              <div className="relative">
                <Input
                  className="w-64 pr-9"
                  onChange={(event) => setValue(event.target.value)}
                  placeholder={t('agents.secretValuePlaceholder')}
                  type={reveal ? 'text' : 'password'}
                  value={value}
                />
                <button
                  aria-label={reveal ? t('agents.hideValue') : t('agents.showValue')}
                  className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground"
                  onClick={() => setReveal((current) => !current)}
                  type="button"
                >
                  {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>
            <Button
              disabled={!selectedEnv || !value}
              onClick={() => {
                void setSecret.mutateAsync({ envName: selectedEnv ?? '', value })
                setValue('')
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
                agentName={agentName}
                canWrite={canWrite}
                envName={secret.env_name}
                key={secret.env_name}
                status={secret.status}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

// Deployment is automatic: the platform never writes agent homes — node reconcile
// materializes desired state. So this is a read-only export, not a deploy trigger.
function AgentYamlExport({ agentName }: { agentName: string }): JSX.Element {
  const t = useT()
  const exportYaml = useExportAgentYamlMutation(agentName)

  const downloadYaml = async (): Promise<void> => {
    const result = await exportYaml.mutateAsync()
    const blob = new Blob([result.yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${agentName}.agent.yaml`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="space-y-3">
      <TabHeading>{t('agents.yamlExport')}</TabHeading>
      <Button disabled={exportYaml.isPending} onClick={() => void downloadYaml()} variant="outline">
        <Download className="size-4" /> {t('agents.exportYaml')}
      </Button>
    </section>
  )
}

const IM_PLATFORMS = ['slack', 'telegram'] as const

function ImCapabilitiesTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT()
  const detail = useAgentDetailQuery(agentName)
  const groupsQuery = useAgentGroupsQuery(agentName)
  const usersQuery = useAgentUsersQuery(agentName)
  const setCaps = useSetAgentImCapabilitiesMutation(agentName)
  const addGroup = useAddAgentImGroupMutation(agentName)
  const removeGroup = useRemoveAgentImGroupMutation(agentName)
  const bindUser = useBindAgentUserMutation(agentName)
  const unbindUser = useUnbindAgentUserMutation(agentName)
  const update = useUpdateAgentMutation(agentName)
  const allUsers = useUsersQuery()

  const [caps, setCaps2] = useState<AgentImCapabilitiesInput>({ supports_dm: false, supports_groups: false })
  const [platform, setPlatform] = useState<string | null>('slack')
  const [groupId, setGroupId] = useState('')
  const [configYaml, setConfigYaml] = useState('')
  const [configDirty, setConfigDirty] = useState(false)

  // Bound groups are read back from the bindings endpoint; add/remove invalidate
  // that query, so the list reflects the persisted state (and survives reload).
  const groups = groupsQuery.data ?? []

  const userOptions = useMemo<BindOption[]>(
    () => (allUsers.data ?? []).map((user) => ({ value: user.id, label: user.email || user.name || user.id })),
    [allUsers.data]
  )

  useEffect(() => {
    setCaps2({
      supports_dm: detail.data?.supports_dm ?? false,
      supports_groups: detail.data?.supports_groups ?? false,
    })
  }, [detail.data?.supports_dm, detail.data?.supports_groups])

  // Mirror server-side overrides into the editor, but never clobber an in-progress edit.
  useEffect(() => {
    if (!configDirty) {
      setConfigYaml(detail.data?.config_overrides_yaml ?? '')
    }
  }, [detail.data?.config_overrides_yaml, configDirty])

  const onAddGroup = async (): Promise<void> => {
    const id = groupId.trim()
    if (!id) return
    await addGroup.mutateAsync({ platform: platform ?? '', group_id: id })
    setGroupId('')
  }

  const onRemoveGroup = async (target: AgentImGroupInput): Promise<void> => {
    await removeGroup.mutateAsync(target)
  }

  const onSaveOverrides = async (): Promise<void> => {
    await update.mutateAsync({ config_overrides_yaml: configYaml })
    setConfigDirty(false)
  }

  return (
    <div className="max-w-xl space-y-6">
      <section className="space-y-4">
        <TabHeading>{t('agents.capabilities')}</TabHeading>
        <div className="flex items-center justify-between gap-4 text-sm">
          <Label htmlFor="agent-supports-dm">{t('agents.supportsDirectMessages')}</Label>
          <Switch
            checked={caps.supports_dm}
            disabled={!canWrite}
            id="agent-supports-dm"
            onCheckedChange={(checked) => setCaps2((current) => ({ ...current, supports_dm: checked }))}
          />
        </div>
        <div className="flex items-center justify-between gap-4 text-sm">
          <Label htmlFor="agent-supports-groups">{t('agents.supportsGroupChats')}</Label>
          <Switch
            checked={caps.supports_groups}
            disabled={!canWrite}
            id="agent-supports-groups"
            onCheckedChange={(checked) => setCaps2((current) => ({ ...current, supports_groups: checked }))}
          />
        </div>
        {canWrite ? (
          <Button disabled={setCaps.isPending} onClick={() => void setCaps.mutateAsync(caps)} size="sm">
            {t('common.save')}
          </Button>
        ) : null}
      </section>

      <Separator />

      <section className="space-y-3">
        <TabHeading>{t('agents.groupAccess')}</TabHeading>
        <p className="text-muted-foreground text-sm">{t('agents.groupAccessHint')}</p>
        {canWrite ? (
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground text-xs">{t('agents.platformLabel')}</Label>
              <SimpleSelect
                onValueChange={setPlatform}
                options={IM_PLATFORMS.map((item) => ({ value: item, label: item }))}
                triggerClassName="w-36"
                value={platform}
              />
            </div>
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground text-xs">{t('agents.groupIdLabel')}</Label>
              <Input
                className="w-56"
                onChange={(event) => setGroupId(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void onAddGroup()
                }}
                placeholder={t('agents.groupIdPlaceholder')}
                value={groupId}
              />
            </div>
            <Button
              disabled={!groupId.trim() || addGroup.isPending}
              onClick={() => void onAddGroup()}
              variant="secondary"
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
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary/60 py-1 pr-1.5 pl-3 text-sm"
                key={`${group.platform}:${group.group_id}`}
              >
                <span className="text-muted-foreground">{group.platform}:</span>
                {group.group_id}
                {canWrite ? (
                  <button
                    aria-label={t('agents.remove', { name: `${group.platform}:${group.group_id}` })}
                    className="grid size-4 place-items-center rounded-full text-muted-foreground hover:bg-destructive/15 hover:text-destructive"
                    onClick={() => void onRemoveGroup(group)}
                    type="button"
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
        canWrite={canWrite}
        emptyLabel={t('agents.noUsers')}
        items={usersQuery.data ?? []}
        loading={allUsers.isLoading}
        onBind={(value) => void bindUser.mutateAsync(value)}
        onUnbind={(value) => void unbindUser.mutateAsync(value)}
        options={userOptions}
        placeholder={t('agents.selectUser')}
        title={t('agents.users')}
      />

      <Separator />

      <section className="space-y-3">
        <TabHeading>{t('agents.imConnectors')}</TabHeading>
        <p className="text-muted-foreground text-sm">{t('agents.imConnectorsHint')}</p>
        <div className="grid gap-2">
          <Label className="text-muted-foreground text-xs" htmlFor="cfg-overrides">
            {t('agents.advancedOverrides')}
          </Label>
          <Textarea
            className="min-h-48 font-mono"
            disabled={!canWrite}
            id="cfg-overrides"
            onChange={(event) => {
              setConfigDirty(true)
              setConfigYaml(event.target.value)
            }}
            placeholder={'im:\n  slack:\n    bot_token_env: SLACK_BOT_TOKEN\n    app_token_env: SLACK_APP_TOKEN'}
            value={configYaml}
          />
        </div>
        {canWrite ? (
          <Button disabled={!configDirty || update.isPending} onClick={() => void onSaveOverrides()} size="sm">
            {t('agents.saveOverrides')}
          </Button>
        ) : null}
      </section>
    </div>
  )
}

// ─────────────────────────── Page ───────────────────────────

export function AgentConfigurePage(): JSX.Element {
  const t = useT()
  const params = useParams()
  const navigate = useNavigate()
  const me = useAdminMeQuery()
  const agentName = params.name ?? ''
  const canWrite = me.data?.role !== 'viewer'

  if (!agentName) {
    return <p className="text-muted-foreground text-sm">{t('agents.notFound')}</p>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button aria-label={t('agents.backToAgents')} onClick={() => navigate('/agents')} size="icon" variant="ghost">
          <ArrowLeft className="size-4" />
        </Button>
        <h2 className="font-semibold text-xl tracking-tight">{t('agents.configureTitle', { name: agentName })}</h2>
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="flex w-full flex-wrap justify-start">
          <TabsTrigger value="overview">{t('agents.tabOverview')}</TabsTrigger>
          <TabsTrigger value="mcp">{t('agents.mcpServers')}</TabsTrigger>
          <TabsTrigger value="skills">{t('agents.skillsTitle')}</TabsTrigger>
          <TabsTrigger value="kb">{t('agents.knowledgeBases')}</TabsTrigger>
          <TabsTrigger value="secrets">{t('agents.secrets')}</TabsTrigger>
          <TabsTrigger value="im">{t('agents.tabImCapabilities')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="mcp">
          <McpServersTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="skills">
          <SkillsTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="kb">
          <KnowledgeBasesTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="secrets">
          <SecretsTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="im">
          <ImCapabilitiesTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

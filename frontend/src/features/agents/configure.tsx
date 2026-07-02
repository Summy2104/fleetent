import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ChevronDown, ChevronUp, Download, Eye, EyeOff, Inbox, Plus, Trash2, X } from 'lucide-react'
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
  type AgentModelOverrides,
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
  useExportAgentYamlMutation,
  useRemoveAgentImGroupMutation,
  useSetAgentImCapabilitiesMutation,
  useSetAgentSecretValueMutation,
  useUnbindAgentKbMutation,
  useUnbindAgentUserMutation,
  useUpdateAgentMutation,
} from '@/features/agents/api'
import {
  type RouteEntry,
  type RouteRefKey,
  TIER_KEYS,
  type TierKey,
  parseAllowedTools,
  readTiers,
  routeEntries,
  withRouteEntries,
  withTiers,
} from '@/features/agents/configure-logic'
import { McpServersTab } from '@/features/agents/mcp-servers-tab'
import { SkillsTab } from '@/features/agents/skills-tab'
import { useKbsQuery } from '@/features/kb/api'
import { useModelsQuery } from '@/features/providers/api'
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

// UI-side entry for one model in a route's fallback chain. temperature/max_tokens are kept as raw
// strings while editing (so decimals type cleanly) and parsed to numbers only at save via toRouteEntry.
type UiEntry = { modelId: string; temperature: string; maxTokens: string }

const EMPTY_UI_ENTRY: UiEntry = { modelId: '', temperature: '', maxTokens: '' }

function uiFromRouteEntry(entry: RouteEntry): UiEntry {
  return {
    modelId: entry.modelId,
    temperature: entry.temperature?.toString() ?? '',
    maxTokens: entry.maxTokens?.toString() ?? '',
  }
}

function emptyTiers(): Record<TierKey, UiEntry> {
  return Object.fromEntries(TIER_KEYS.map((key) => [key, { ...EMPTY_UI_ENTRY }])) as Record<
    TierKey,
    UiEntry
  >
}

// Load a stored route into UI entries (always at least one row so there's a primary picker).
// refKey selects how entries reference their model: `target` (tier name) for chat routes.
function uiEntriesForRoute(
  overrides: AgentModelOverrides | undefined,
  routeKey: string,
  refKey: RouteRefKey = 'model_id'
): UiEntry[] {
  const entries = routeEntries(overrides, routeKey, refKey).map(uiFromRouteEntry)
  return entries.length > 0 ? entries : [{ ...EMPTY_UI_ENTRY }]
}

// Parse a UI entry into a RouteEntry, dropping blank/invalid overrides (tolerant, never throws).
function toRouteEntry(entry: UiEntry): RouteEntry {
  const out: RouteEntry = { modelId: entry.modelId }
  const temperature = Number(entry.temperature)
  if (entry.temperature.trim() !== '' && !Number.isNaN(temperature)) out.temperature = temperature
  const maxTokens = Number(entry.maxTokens)
  if (entry.maxTokens.trim() !== '' && Number.isInteger(maxTokens) && maxTokens > 0) {
    out.maxTokens = maxTokens
  }
  return out
}

// Standard routes exposed as independent bindings on the overview tab, covering every
// route key the runtime resolves (fleetent.model.resolver.STANDARD_ROUTE_KEYS). `default`
// stays required and prominent. `protocols` filters the candidate models per route; a route
// left unset keeps resolving to its platform default target. The two audio routes are reserved
// — no provider protocol supports them yet, so their candidate list is empty and the UI shows
// an explicit no-candidates hint instead of a silently empty picker.
// `usesTiers` routes are chat routes: their chain entries reference a named tier (primary/fast/
// backup) rather than a model directly. The other (specialized) routes pick a registry model by
// protocol. `protocols` is the candidate filter for the tier pickers (chat) / the route (specialized).
const ROUTE_BINDINGS = [
  {
    labelKey: 'agents.modelProvider' as const,
    protocols: ['openai_chat'],
    routeKey: 'default',
    usesTiers: true,
  },
  {
    labelKey: 'agents.modelEmbedding' as const,
    protocols: ['http_embedding'],
    routeKey: 'embedding',
  },
  {
    labelKey: 'agents.modelMemoryExtraction' as const,
    protocols: ['openai_chat'],
    routeKey: 'memory_extraction',
    usesTiers: true,
  },
  {
    // Multimodal chat input; references a chat tier, like the default route.
    labelKey: 'agents.modelVision' as const,
    protocols: ['openai_chat'],
    routeKey: 'vision',
    usesTiers: true,
  },
  {
    // Internal KB extraction; references a chat tier (typically the cheaper `fast` one).
    labelKey: 'agents.modelKbExtraction' as const,
    protocols: ['openai_chat'],
    routeKey: 'kb_extraction',
    usesTiers: true,
  },
  {
    labelKey: 'agents.modelRerank' as const,
    protocols: ['http_rerank'],
    routeKey: 'rerank',
  },
  {
    // Both image protocols share this route: the OpenAI Images API (openai_image_generation)
    // and Chat-Completions image models (openai_image_chat, e.g. Gemini image preview via a gateway).
    labelKey: 'agents.modelImageGeneration' as const,
    protocols: ['openai_image_generation', 'openai_image_chat'],
    routeKey: 'image_generation',
  },
  {
    // Reserved: no audio-transcription provider protocol exists yet, so this picker has no
    // candidates today and renders the no-candidates hint.
    labelKey: 'agents.modelAudioTranscription' as const,
    protocols: ['openai_audio_transcription'],
    routeKey: 'audio_transcription',
  },
  {
    // Reserved: no audio-generation provider protocol exists yet (see above).
    labelKey: 'agents.modelAudioGeneration' as const,
    protocols: ['openai_audio_generation'],
    routeKey: 'audio_generation',
  },
]

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

export function OverviewTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT()
  const detail = useAgentDetailQuery(agentName)
  const update = useUpdateAgentMutation(agentName)

  const [systemPrompt, setSystemPrompt] = useState('')
  const [allowedTools, setAllowedTools] = useState('')
  const [memoryNamespace, setMemoryNamespace] = useState('')

  useEffect(() => {
    if (detail.data) {
      setSystemPrompt(detail.data.system_prompt)
      setAllowedTools(detail.data.allowed_tools.join(', '))
      setMemoryNamespace(detail.data.memory_namespace ?? 'default')
    }
  }, [detail.data])

  const onSave = (): void => {
    void update.mutateAsync({
      system_prompt: systemPrompt,
      allowed_tools: parseAllowedTools(allowedTools),
      memory_namespace: memoryNamespace.trim() || 'default',
    })
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

// One editable model in a route's fallback chain: model picker + reorder/remove (only when the
// chain has ≥2 entries) + a collapsible temperature/max_tokens override.
function RouteEntryRow({
  ariaLabel,
  options,
  entry,
  index,
  isDefault,
  isLast,
  canReorder,
  disabled,
  onUpdate,
  onRemove,
  onMove,
}: {
  ariaLabel: string
  options: BindOption[]
  entry: UiEntry
  index: number
  isDefault: boolean
  isLast: boolean
  canReorder: boolean
  disabled: boolean
  onUpdate: (patch: Partial<UiEntry>) => void
  onRemove: () => void
  onMove: (delta: number) => void
}): JSX.Element {
  const t = useT()
  const [showParams, setShowParams] = useState(Boolean(entry.temperature || entry.maxTokens))
  const iconBtn =
    'grid size-5 place-items-center rounded text-muted-foreground hover:text-foreground disabled:opacity-40'
  return (
    <fieldset aria-label={ariaLabel} className="space-y-2 rounded-md border border-border p-2">
      <div className="flex items-center gap-1.5">
        {canReorder ? (
          <div className="flex flex-col">
            <button
              aria-label={t('agents.moveModelUp')}
              className={iconBtn}
              disabled={disabled || index === 0}
              onClick={() => onMove(-1)}
              type="button"
            >
              <ChevronUp className="size-3.5" />
            </button>
            <button
              aria-label={t('agents.moveModelDown')}
              className={iconBtn}
              disabled={disabled || isLast}
              onClick={() => onMove(1)}
              type="button"
            >
              <ChevronDown className="size-3.5" />
            </button>
          </div>
        ) : null}
        <SimpleSelect
          disabled={disabled}
          onValueChange={(value) => onUpdate({ modelId: value ?? '' })}
          options={options}
          placeholder={isDefault && index === 0 ? t('agents.selectProvider') : t('agents.selectModel')}
          triggerAriaLabel={ariaLabel}
          triggerClassName="max-w-xs"
          value={entry.modelId}
        />
        {canReorder ? (
          <button aria-label={t('agents.removeModelEntry')} className={iconBtn} onClick={onRemove} type="button">
            <X className="size-3.5" />
          </button>
        ) : null}
      </div>
      <button
        className="text-muted-foreground text-xs hover:text-foreground"
        onClick={() => setShowParams((current) => !current)}
        type="button"
      >
        {t('agents.overrideParams')}
      </button>
      {showParams ? (
        <div className="flex flex-wrap gap-3 pl-1">
          <div className="grid gap-1">
            <span className="text-muted-foreground text-xs">{t('agents.temperatureLabel')}</span>
            <Input
              aria-label={t('agents.temperatureLabel')}
              className="w-28"
              disabled={disabled}
              inputMode="decimal"
              onChange={(event) => onUpdate({ temperature: event.target.value })}
              placeholder="—"
              value={entry.temperature}
            />
          </div>
          <div className="grid gap-1">
            <span className="text-muted-foreground text-xs">{t('agents.maxTokensLabel')}</span>
            <Input
              aria-label={t('agents.maxTokensLabel')}
              className="w-28"
              disabled={disabled}
              inputMode="numeric"
              onChange={(event) => onUpdate({ maxTokens: event.target.value })}
              placeholder="—"
              value={entry.maxTokens}
            />
          </div>
        </div>
      ) : null}
    </fieldset>
  )
}

// One route's ordered fallback chain: a primary model picker + `add fallback` for extra entries.
// Progressive disclosure — a single-model route with no overrides reads like a plain picker.
function RouteChainEditor({
  label,
  isDefault,
  options,
  emptyHint,
  entries,
  canWrite,
  loading,
  disabled,
  onChange,
}: {
  label: string
  isDefault: boolean
  // All selectable options for this route: registry models (specialized routes) or named tiers
  // (chat routes). The editor is agnostic to which — it edits a chain of option values.
  options: BindOption[]
  emptyHint: string
  entries: UiEntry[]
  canWrite: boolean
  loading: boolean
  disabled: boolean
  onChange: (entries: UiEntry[]) => void
}): JSX.Element {
  const t = useT()
  const hasSelection = entries.some((entry) => entry.modelId)

  // Exclude options already chosen in the chain's OTHER entries — no point retrying the same target.
  const optionsExcluding = (index: number): BindOption[] => {
    const chosen = new Set(
      entries.filter((_, i) => i !== index).map((entry) => entry.modelId).filter(Boolean)
    )
    return options.filter((option) => !chosen.has(option.value))
  }

  const updateEntry = (index: number, patch: Partial<UiEntry>): void =>
    onChange(entries.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)))
  const removeEntry = (index: number): void => {
    const next = entries.filter((_, i) => i !== index)
    onChange(next.length > 0 ? next : [{ ...EMPTY_UI_ENTRY }])
  }
  const moveEntry = (index: number, delta: number): void => {
    const target = index + delta
    if (target < 0 || target >= entries.length) return
    const next = [...entries]
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next)
  }

  const lastHasModel = Boolean(entries[entries.length - 1]?.modelId)
  const remaining = options.length - entries.filter((entry) => entry.modelId).length
  const canAdd = lastHasModel && remaining > 0

  return (
    <section className="space-y-3">
      <TabHeading>{label}</TabHeading>
      {isDefault ? <p className="text-muted-foreground text-sm">{t('agents.modelProviderHint')}</p> : null}

      {canWrite && !loading && options.length === 0 && !hasSelection ? (
        // Reserved audio routes, chat routes with no tiers defined, or any route lacking a
        // selectable option explain the gap instead of showing a dead picker.
        <p className="text-muted-foreground text-sm">{emptyHint}</p>
      ) : canWrite ? (
        <div className="space-y-2">
          {entries.map((entry, index) => (
            <RouteEntryRow
              ariaLabel={index === 0 ? label : `${label} · ${t('agents.modelFallbackTag', { n: String(index) })}`}
              canReorder={entries.length >= 2}
              disabled={disabled || loading}
              entry={entry}
              index={index}
              isDefault={isDefault}
              isLast={index === entries.length - 1}
              // biome-ignore lint/suspicious/noArrayIndexKey: entries are positional (fallback order) with no stable id
              key={index}
              onMove={(delta) => moveEntry(index, delta)}
              onRemove={() => removeEntry(index)}
              onUpdate={(patch) => updateEntry(index, patch)}
              options={optionsExcluding(index)}
            />
          ))}
          {canAdd ? (
            <Button
              aria-label={t('agents.addFallbackTo', { route: label })}
              onClick={() => onChange([...entries, { ...EMPTY_UI_ENTRY }])}
              size="sm"
              variant="outline"
            >
              <Plus className="size-3.5" /> {t('agents.addFallback')}
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="space-y-1">
          {hasSelection ? (
            entries
              .filter((entry) => entry.modelId)
              .map((entry, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: read-only positional summary
                <p className="text-foreground text-sm" key={i}>
                  {entry.modelId}
                  {entry.temperature || entry.maxTokens
                    ? ` · ${[entry.temperature && `temp ${entry.temperature}`, entry.maxTokens && `max ${entry.maxTokens}`]
                        .filter(Boolean)
                        .join(' / ')}`
                    : ''}
                </p>
              ))
          ) : (
            <p className="text-foreground text-sm">—</p>
          )}
        </div>
      )}
    </section>
  )
}

// The agent-local named model tiers (primary / fast / backup) — a reusable pool of chat models the
// chat routes below reference by name. Slot names are fixed; the user only assigns a model + params.
function ModelTiersEditor({
  tiers,
  options,
  canWrite,
  loading,
  disabled,
  onChange,
}: {
  tiers: Record<TierKey, UiEntry>
  options: BindOption[]
  canWrite: boolean
  loading: boolean
  disabled: boolean
  onChange: (updater: (current: Record<TierKey, UiEntry>) => Record<TierKey, UiEntry>) => void
}): JSX.Element {
  const t = useT()
  return (
    <section className="space-y-3">
      <TabHeading>{t('agents.modelTiers')}</TabHeading>
      <p className="text-muted-foreground text-sm">{t('agents.modelTiersHint')}</p>
      {TIER_KEYS.map((key) => (
        <div className="space-y-1" key={key}>
          <span className="font-medium text-foreground text-sm">{key}</span>
          {canWrite ? (
            <RouteEntryRow
              ariaLabel={key}
              canReorder={false}
              disabled={disabled || loading}
              entry={tiers[key]}
              index={0}
              isDefault={false}
              isLast
              onMove={() => undefined}
              onRemove={() => undefined}
              onUpdate={(patch) => onChange((current) => ({ ...current, [key]: { ...current[key], ...patch } }))}
              options={options}
            />
          ) : (
            <p className="text-foreground text-sm">{tiers[key]?.modelId || '—'}</p>
          )}
        </div>
      ))}
    </section>
  )
}

// Model routing lives on its own tab: the named tiers pool + a fallback-chain editor per route
// (chat routes reference tiers; specialized routes pick a model) plus the primary tier's
// provider-key override. Kept separate from the overview so the pickers don't crowd the basics.
export function ModelsTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT()
  const detail = useAgentDetailQuery(agentName)
  const update = useUpdateAgentMutation(agentName)
  const allModels = useModelsQuery()

  const [tiers, setTiers] = useState<Record<TierKey, UiEntry>>(emptyTiers)
  const [routeChains, setRouteChains] = useState<Record<string, UiEntry[]>>({})

  const chatModelOptions = useMemo<BindOption[]>(
    () =>
      (allModels.data ?? [])
        .filter((model) => model.protocol === 'openai_chat')
        .map((model) => ({
          value: model.id,
          label: model.model_name ? `${model.id} · ${model.model_name}` : model.id,
        })),
    [allModels.data]
  )
  // Options a chat route can reference: the tiers that have a model assigned, labeled with the
  // model so the role→model mapping is visible in the picker.
  const tierOptions = useMemo<BindOption[]>(() => {
    const modelName = (id: string) => (allModels.data ?? []).find((model) => model.id === id)?.model_name
    return TIER_KEYS.filter((key) => tiers[key]?.modelId).map((key) => {
      const name = modelName(tiers[key].modelId)
      return { value: key, label: name ? `${key} · ${name}` : key }
    })
  }, [allModels.data, tiers])

  useEffect(() => {
    if (detail.data) {
      setTiers(
        Object.fromEntries(
          TIER_KEYS.map((key) => [key, uiFromRouteEntry(readTiers(detail.data.model_overrides)[key])])
        ) as Record<TierKey, UiEntry>
      )
      setRouteChains(
        Object.fromEntries(
          ROUTE_BINDINGS.map((binding) => [
            binding.routeKey,
            uiEntriesForRoute(
              detail.data.model_overrides,
              binding.routeKey,
              binding.usesTiers ? 'target' : 'model_id'
            ),
          ])
        )
      )
    }
  }, [detail.data])

  const onSave = (): void => {
    void (async () => {
      // Write the tier definitions first, then each route (chat routes reference tiers by name).
      const withTierDefs = withTiers(
        detail.data?.model_overrides,
        Object.fromEntries(TIER_KEYS.map((key) => [key, toRouteEntry(tiers[key])])) as Record<TierKey, RouteEntry>
      )
      const modelOverrides = ROUTE_BINDINGS.reduce(
        (overrides, binding) =>
          withRouteEntries(
            overrides,
            binding.routeKey,
            (routeChains[binding.routeKey] ?? []).map(toRouteEntry),
            binding.usesTiers ? 'target' : 'model_id'
          ),
        withTierDefs
      )
      await update.mutateAsync({ model_overrides: modelOverrides })
    })()
  }

  return (
    <div className="grid max-w-2xl gap-5">
      <ModelTiersEditor
        canWrite={canWrite}
        disabled={update.isPending}
        loading={allModels.isLoading}
        onChange={setTiers}
        options={chatModelOptions}
        tiers={tiers}
      />

      <Separator />

      <p className="text-muted-foreground text-sm">{t('agents.modelTargetsHint')}</p>
      {ROUTE_BINDINGS.map((binding) => (
        <RouteChainEditor
          canWrite={canWrite}
          disabled={update.isPending}
          emptyHint={binding.usesTiers ? t('agents.defineTiersFirst') : t('agents.modelRouteNoCandidates')}
          entries={routeChains[binding.routeKey] ?? [{ ...EMPTY_UI_ENTRY }]}
          isDefault={binding.routeKey === 'default'}
          key={binding.routeKey}
          label={t(binding.labelKey)}
          loading={allModels.isLoading}
          onChange={(next) => setRouteChains((current) => ({ ...current, [binding.routeKey]: next }))}
          options={
            binding.usesTiers
              ? tierOptions
              : (allModels.data ?? [])
                  .filter((model) => binding.protocols.includes(model.protocol))
                  .map((model) => ({
                    value: model.id,
                    label: model.model_name ? `${model.id} · ${model.model_name}` : model.id,
                  }))
          }
        />
      ))}

      {canWrite ? (
        <div>
          <Button disabled={update.isPending} onClick={onSave}>
            {t('common.save')}
          </Button>
        </div>
      ) : null}
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
          <TabsTrigger value="models">{t('agents.tabModels')}</TabsTrigger>
          <TabsTrigger value="mcp">{t('agents.mcpServers')}</TabsTrigger>
          <TabsTrigger value="skills">{t('agents.skillsTitle')}</TabsTrigger>
          <TabsTrigger value="kb">{t('agents.knowledgeBases')}</TabsTrigger>
          <TabsTrigger value="secrets">{t('agents.secrets')}</TabsTrigger>
          <TabsTrigger value="im">{t('agents.tabImCapabilities')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab agentName={agentName} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="models">
          <ModelsTab agentName={agentName} canWrite={canWrite} />
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

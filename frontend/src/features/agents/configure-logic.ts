import type { AgentModelOverrides, UpdateAgentInput } from '@/features/agents/api'

// Split the comma-separated "allowed tools" input into a trimmed, non-empty list.
export function parseAllowedTools(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

// The agent's default model route maps to a single provider id; the platform expands it
// into the full model policy. Read it from model_overrides, taking the first string key any
// authoring style may have used.
export function defaultRouteModelId(overrides: AgentModelOverrides | undefined): string {
  const routes = (overrides?.routes ?? {}) as Record<string, Array<Record<string, unknown>>>
  const entry = routes.default?.[0]
  if (!entry) return ''
  for (const value of [entry.model_id, entry.provider_id, entry.provider, entry.target]) {
    if (typeof value === 'string' && value) return value
  }
  return ''
}

// Set (or clear) the default-route provider while preserving every sibling key the platform
// stores alongside it (other routes, credential slots), so an edit never drops that state.
export function withDefaultRouteModel(
  overrides: AgentModelOverrides | undefined,
  modelId: string
): AgentModelOverrides {
  const next: AgentModelOverrides = { ...(overrides ?? {}) }
  const routes = { ...((next.routes as Record<string, unknown>) ?? {}) }
  if (modelId) {
    routes.default = [{ model_id: modelId }]
  } else {
    delete routes.default
  }
  next.routes = routes
  return next
}

// Assemble the agent config PATCH from the Overview form. memory_namespace falls back to
// "default" when blank; model_overrides preserves siblings via withDefaultRouteModel.
export function buildAgentConfigUpdate(fields: {
  systemPrompt: string
  allowedTools: string
  memoryNamespace: string
  modelId: string | null
  currentOverrides: AgentModelOverrides | undefined
}): UpdateAgentInput {
  return {
    system_prompt: fields.systemPrompt,
    allowed_tools: parseAllowedTools(fields.allowedTools),
    memory_namespace: fields.memoryNamespace.trim() || 'default',
    model_overrides: withDefaultRouteModel(fields.currentOverrides, fields.modelId ?? ''),
  }
}

// One entry in a route's ordered fallback chain: which model, plus optional per-entry overrides
// (blank = inherit the model's registered default). temperature lives under the entry's `params`,
// max_tokens is the entry's native field — matching how the platform materializes them.
export type RouteEntry = { modelId: string; temperature?: number; maxTokens?: number }

// How a route entry references its model: `model_id` (specialized routes pick a registry model
// directly) or `target` (chat routes reference a named tier — primary/fast/backup). For tier
// references RouteEntry.modelId holds the tier name.
export type RouteRefKey = 'model_id' | 'target'

// The fixed, system-defined chat model tiers. Users assign a model to each slot per agent; they
// never type these names. Chat routes reference them as an ordered fallback chain.
export const TIER_KEYS = ['primary', 'fast', 'backup'] as const
export type TierKey = (typeof TIER_KEYS)[number]

// Resolve one route's stored entries into an ordered chain. For `model_id` refs, tolerates every
// authoring style (model_id first, then provider_id/target/provider); for `target` refs reads the
// tier name. Entries without a resolvable reference are dropped.
export function routeEntries(
  overrides: AgentModelOverrides | undefined,
  routeKey: string,
  refKey: RouteRefKey = 'model_id'
): RouteEntry[] {
  const routes = (overrides?.routes ?? {}) as Record<string, Array<Record<string, unknown>>>
  const raw = routes[routeKey]
  if (!Array.isArray(raw)) return []
  const entries: RouteEntry[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const modelId =
      refKey === 'target'
        ? firstString(item.target)
        : firstString(item.model_id, item.provider_id, item.target, item.provider)
    if (!modelId) continue
    const entry: RouteEntry = { modelId }
    const temperature = (item.params as Record<string, unknown> | undefined)?.temperature
    if (typeof temperature === 'number') entry.temperature = temperature
    if (typeof item.max_tokens === 'number') entry.maxTokens = item.max_tokens
    entries.push(entry)
  }
  return entries
}

// Rebuild one route's stored entry list from an edited chain while preserving every sibling key the
// platform stores (other routes, credential slots, the targets block). An entry only writes
// max_tokens / params when set; an empty chain deletes the route key entirely — never
// `routes[key]: []`, which the runtime rejects.
export function withRouteEntries(
  overrides: AgentModelOverrides | undefined,
  routeKey: string,
  entries: RouteEntry[],
  refKey: RouteRefKey = 'model_id'
): AgentModelOverrides {
  const next: AgentModelOverrides = { ...(overrides ?? {}) }
  const routes = { ...((next.routes as Record<string, unknown>) ?? {}) }
  const serialized = entries
    .filter((entry) => entry.modelId)
    .map((entry) => {
      const out: Record<string, unknown> = { [refKey]: entry.modelId }
      if (typeof entry.maxTokens === 'number') out.max_tokens = entry.maxTokens
      if (typeof entry.temperature === 'number') out.params = { temperature: entry.temperature }
      return out
    })
  if (serialized.length === 0) {
    delete routes[routeKey]
  } else {
    routes[routeKey] = serialized
  }
  next.routes = routes
  return next
}

// Read the agent-local tier definitions (the `targets` block) into an entry per fixed tier slot.
// A slot with no model reads back as an empty entry (so the picker renders blank).
export function readTiers(overrides: AgentModelOverrides | undefined): Record<TierKey, RouteEntry> {
  const targets = (overrides?.targets ?? {}) as Record<string, Record<string, unknown>>
  const out = {} as Record<TierKey, RouteEntry>
  for (const key of TIER_KEYS) {
    const def = targets[key]
    const entry: RouteEntry = { modelId: '' }
    if (def && typeof def === 'object') {
      entry.modelId = firstString(def.model_id, def.provider_id, def.model)
      const temperature = (def.params as Record<string, unknown> | undefined)?.temperature
      if (typeof temperature === 'number') entry.temperature = temperature
      if (typeof def.max_tokens === 'number') entry.maxTokens = def.max_tokens
    }
    out[key] = entry
  }
  return out
}

// Write the `targets` block from the edited tier slots, dropping slots with no model. When no tier
// has a model the block is removed entirely (so an all-empty tiers section leaves no stray targets).
export function withTiers(
  overrides: AgentModelOverrides | undefined,
  tiers: Record<TierKey, RouteEntry>
): AgentModelOverrides {
  const next: AgentModelOverrides = { ...(overrides ?? {}) }
  const targets: Record<string, unknown> = {}
  for (const key of TIER_KEYS) {
    const tier = tiers[key]
    if (!tier?.modelId) continue
    const def: Record<string, unknown> = { model_id: tier.modelId }
    if (typeof tier.maxTokens === 'number') def.max_tokens = tier.maxTokens
    if (typeof tier.temperature === 'number') def.params = { temperature: tier.temperature }
    targets[key] = def
  }
  if (Object.keys(targets).length > 0) next.targets = targets
  else delete next.targets
  return next
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value) return value
  }
  return ''
}

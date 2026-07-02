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

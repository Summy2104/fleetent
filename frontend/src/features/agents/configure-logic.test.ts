import { describe, expect, it } from 'vitest'

import {
  buildAgentConfigUpdate,
  defaultRouteModelId,
  parseAllowedTools,
  withDefaultRouteModel,
} from '@/features/agents/configure-logic'

describe('parseAllowedTools', () => {
  it('splits on commas, trims, and drops empties', () => {
    expect(parseAllowedTools(' read_file, , write_file ,')).toEqual(['read_file', 'write_file'])
  })

  it('returns an empty list for a blank string', () => {
    expect(parseAllowedTools('   ')).toEqual([])
  })
})

describe('defaultRouteModelId', () => {
  it('returns an empty string when there is no default route', () => {
    expect(defaultRouteModelId(undefined)).toBe('')
    expect(defaultRouteModelId({})).toBe('')
    expect(defaultRouteModelId({ routes: { default: [] } })).toBe('')
  })

  it('reads model_id first, then falls back through provider_id/provider/target', () => {
    expect(defaultRouteModelId({ routes: { default: [{ model_id: 'gpt' }] } })).toBe('gpt')
    expect(defaultRouteModelId({ routes: { default: [{ provider_id: 'openai' }] } })).toBe('openai')
    expect(defaultRouteModelId({ routes: { default: [{ target: 'anthropic' }] } })).toBe('anthropic')
  })

  it('ignores non-string or empty candidates', () => {
    expect(defaultRouteModelId({ routes: { default: [{ model_id: '', provider: 'p' }] } })).toBe('p')
    expect(defaultRouteModelId({ routes: { default: [{ model_id: 123 }] } })).toBe('')
  })
})

describe('withDefaultRouteModel', () => {
  it('sets the default route to the given model id', () => {
    expect(withDefaultRouteModel(undefined, 'gpt')).toEqual({ routes: { default: [{ model_id: 'gpt' }] } })
  })

  it('clears the default route when the model id is empty', () => {
    expect(withDefaultRouteModel({ routes: { default: [{ model_id: 'gpt' }] } }, '')).toEqual({ routes: {} })
  })

  it('preserves sibling routes and top-level keys', () => {
    const result = withDefaultRouteModel({ routes: { fast: [{ model_id: 'haiku' }] }, credentials: { k: 1 } }, 'gpt')
    expect(result).toEqual({
      routes: { fast: [{ model_id: 'haiku' }], default: [{ model_id: 'gpt' }] },
      credentials: { k: 1 },
    })
  })
})

describe('buildAgentConfigUpdate', () => {
  it('assembles the patch, parsing tools and defaulting the namespace', () => {
    expect(
      buildAgentConfigUpdate({
        systemPrompt: 'be helpful',
        allowedTools: 'read_file, write_file',
        memoryNamespace: '  ',
        modelId: 'gpt',
        currentOverrides: undefined,
      })
    ).toEqual({
      system_prompt: 'be helpful',
      allowed_tools: ['read_file', 'write_file'],
      memory_namespace: 'default',
      model_overrides: { routes: { default: [{ model_id: 'gpt' }] } },
    })
  })

  it('keeps a provided namespace and clears the route when modelId is null', () => {
    const patch = buildAgentConfigUpdate({
      systemPrompt: 'p',
      allowedTools: '',
      memoryNamespace: 'team-a',
      modelId: null,
      currentOverrides: { routes: { default: [{ model_id: 'old' }] } },
    })
    expect(patch.memory_namespace).toBe('team-a')
    expect(patch.allowed_tools).toEqual([])
    expect(patch.model_overrides).toEqual({ routes: {} })
  })
})

import { describe, expect, it } from 'vitest'

import {
  buildAgentConfigUpdate,
  defaultRouteModelId,
  parseAllowedTools,
  readTiers,
  routeEntries,
  withDefaultRouteModel,
  withRouteEntries,
  withTiers,
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

describe('routeEntries', () => {
  it('returns an empty array when the route is missing or empty', () => {
    expect(routeEntries(undefined, 'default')).toEqual([])
    expect(routeEntries({}, 'default')).toEqual([])
    expect(routeEntries({ routes: { default: [] } }, 'default')).toEqual([])
  })

  it('parses a multi-entry chain with per-entry temperature and max_tokens', () => {
    const overrides = {
      routes: {
        default: [
          { model_id: 'primary', params: { temperature: 0.7 } },
          { model_id: 'backup', max_tokens: 1024, params: { temperature: 0.5 } },
        ],
      },
    }
    expect(routeEntries(overrides, 'default')).toEqual([
      { modelId: 'primary', temperature: 0.7 },
      { modelId: 'backup', temperature: 0.5, maxTokens: 1024 },
    ])
  })

  it('reads a legacy single-entry override as a one-element chain', () => {
    expect(routeEntries({ routes: { default: [{ provider_id: 'ollama' }] } }, 'default')).toEqual([
      { modelId: 'ollama' },
    ])
  })

  it('skips entries without a resolvable model id', () => {
    expect(routeEntries({ routes: { default: [{ params: { temperature: 1 } }, { model_id: 'x' }] } }, 'default')).toEqual([
      { modelId: 'x' },
    ])
  })
})

describe('withRouteEntries', () => {
  it('writes a chain, omitting empty overrides', () => {
    const result = withRouteEntries(undefined, 'default', [
      { modelId: 'primary', temperature: 0.7 },
      { modelId: 'backup', maxTokens: 1024, temperature: 0.5 },
    ])
    expect(result).toEqual({
      routes: {
        default: [
          { model_id: 'primary', params: { temperature: 0.7 } },
          { model_id: 'backup', max_tokens: 1024, params: { temperature: 0.5 } },
        ],
      },
    })
  })

  it('writes a bare {model_id} entry when it has no overrides', () => {
    expect(withRouteEntries(undefined, 'embedding', [{ modelId: 'embed-1' }])).toEqual({
      routes: { embedding: [{ model_id: 'embed-1' }] },
    })
  })

  it('deletes the route key when the chain is empty (never writes [])', () => {
    expect(withRouteEntries({ routes: { default: [{ model_id: 'x' }] } }, 'default', [])).toEqual({ routes: {} })
    // entries with no model id collapse to an empty chain and delete the key too
    expect(withRouteEntries({ routes: { default: [{ model_id: 'x' }] } }, 'default', [{ modelId: '' }])).toEqual({
      routes: {},
    })
  })

  it('preserves sibling routes and top-level keys', () => {
    const result = withRouteEntries(
      { routes: { fast: [{ model_id: 'haiku' }] }, credentials: { k: 1 } },
      'default',
      [{ modelId: 'gpt' }]
    )
    expect(result).toEqual({
      routes: { fast: [{ model_id: 'haiku' }], default: [{ model_id: 'gpt' }] },
      credentials: { k: 1 },
    })
  })
})

describe('tier and target-ref helpers', () => {
  it('reads tier definitions from the targets block', () => {
    const overrides = {
      targets: {
        primary: { model_id: 'gpt4o', params: { temperature: 0.5 } },
        fast: { model_id: 'haiku', max_tokens: 2048 },
      },
    }
    const tiers = readTiers(overrides)
    expect(tiers.primary).toEqual({ modelId: 'gpt4o', temperature: 0.5 })
    expect(tiers.fast).toEqual({ modelId: 'haiku', maxTokens: 2048 })
    expect(tiers.backup).toEqual({ modelId: '' })
  })

  it('writes the targets block, dropping empty slots and removing it when all empty', () => {
    expect(
      withTiers(undefined, {
        primary: { modelId: 'gpt4o', temperature: 0.5 },
        fast: { modelId: '' },
        backup: { modelId: '' },
      })
    ).toEqual({ targets: { primary: { model_id: 'gpt4o', params: { temperature: 0.5 } } } })
    expect(withTiers({ targets: { primary: { model_id: 'x' } } }, { primary: { modelId: '' }, fast: { modelId: '' }, backup: { modelId: '' } })).toEqual({})
  })

  it('reads and writes tier-referencing route entries via the target ref key', () => {
    const overrides = { routes: { default: [{ target: 'primary', params: { temperature: 0.7 } }, { target: 'backup' }] } }
    expect(routeEntries(overrides, 'default', 'target')).toEqual([
      { modelId: 'primary', temperature: 0.7 },
      { modelId: 'backup' },
    ])
    expect(
      withRouteEntries(undefined, 'default', [{ modelId: 'primary', temperature: 0.7 }, { modelId: 'backup' }], 'target')
    ).toEqual({ routes: { default: [{ target: 'primary', params: { temperature: 0.7 } }, { target: 'backup' }] } })
  })
})

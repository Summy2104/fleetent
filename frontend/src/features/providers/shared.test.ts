import { describe, expect, it } from 'vitest'

import type { ProviderListItem } from '@/features/providers/api'
import {
  buildCreateModelPayload,
  buildCreateProviderPayload,
  buildUpdateProviderPayload,
  emptyModelForm,
  emptyProviderForm,
  providerFormFromProvider,
} from '@/features/providers/shared'

function provider(over: Partial<ProviderListItem> = {}): ProviderListItem {
  return {
    api_key: null,
    api_key_env: null,
    api_key_set: false,
    base_url: 'https://api.test',
    description: 'desc',
    id: 'openai',
    model_count: 0,
    provider: 'openai',
    ...over,
  }
}

describe('empty form factories', () => {
  it('start blank; model form defaults to openai_chat and carries the provider id', () => {
    expect(emptyProviderForm()).toEqual({ apiKey: '', baseUrl: '', description: '', id: '', provider: '' })
    expect(emptyModelForm('openai')).toEqual({
      baseUrl: '',
      id: '',
      modelName: '',
      protocol: 'openai_chat',
      providerId: 'openai',
    })
  })
})

describe('providerFormFromProvider', () => {
  it('maps a record into the form and never prefills the api key', () => {
    expect(providerFormFromProvider(provider())).toEqual({
      apiKey: '',
      baseUrl: 'https://api.test',
      description: 'desc',
      id: 'openai',
      provider: 'openai',
    })
  })

  it('coerces null base_url/description/provider to empty strings', () => {
    expect(providerFormFromProvider(provider({ base_url: null, description: null, provider: null }))).toMatchObject({
      baseUrl: '',
      description: '',
      provider: '',
    })
  })
})

describe('buildCreateProviderPayload', () => {
  it('keeps the id but drops blank optional fields', () => {
    expect(buildCreateProviderPayload({ apiKey: '', baseUrl: '', description: '', id: 'x', provider: '' })).toEqual({
      id: 'x',
      api_key: undefined,
      base_url: undefined,
      description: undefined,
      provider: undefined,
    })
  })

  it('passes non-blank fields through', () => {
    expect(
      buildCreateProviderPayload({ apiKey: 'sk', baseUrl: 'u', description: 'd', id: 'x', provider: 'openai' })
    ).toEqual({ id: 'x', api_key: 'sk', base_url: 'u', description: 'd', provider: 'openai' })
  })
})

describe('buildUpdateProviderPayload', () => {
  it('omits the id and drops blank optional fields', () => {
    const payload = buildUpdateProviderPayload({ apiKey: '', baseUrl: 'u', description: '', id: 'x', provider: '' })
    expect(payload).toEqual({ api_key: undefined, base_url: 'u', description: undefined, provider: undefined })
    expect('id' in payload).toBe(false)
  })
})

describe('buildCreateModelPayload', () => {
  it('keeps required fields and drops a blank base_url', () => {
    expect(
      buildCreateModelPayload({
        baseUrl: '',
        id: 'gpt',
        modelName: 'gpt-4',
        protocol: 'openai_chat',
        providerId: 'openai',
      })
    ).toEqual({ base_url: undefined, id: 'gpt', model_name: 'gpt-4', protocol: 'openai_chat', provider_id: 'openai' })
  })
})

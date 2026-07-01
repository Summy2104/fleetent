import type {
  CreateModelInput,
  CreateProviderInput,
  ProviderListItem,
  UpdateProviderInput,
} from '@/features/providers/api'

export type ProviderFormState = {
  apiKey: string
  baseUrl: string
  description: string
  id: string
  provider: string
}

export type ModelFormState = {
  baseUrl: string
  endpoint: string
  id: string
  modelName: string
  protocol: string
  providerId: string
}

// Mirrors the backend's `_ENDPOINT_PROTOCOLS`: these protocols require `endpoint` and forbid
// `base_url`; every other protocol (openai_chat, openai_image_chat) requires `base_url`.
export const MODEL_PROTOCOLS = [
  'openai_chat',
  'http_embedding',
  'http_rerank',
  'openai_image_generation',
  'openai_image_chat',
] as const
export const ENDPOINT_PROTOCOLS = new Set<string>(['http_embedding', 'http_rerank', 'openai_image_generation'])

export function emptyProviderForm(): ProviderFormState {
  return { apiKey: '', baseUrl: '', description: '', id: '', provider: '' }
}

export function emptyModelForm(providerId = ''): ModelFormState {
  return { baseUrl: '', endpoint: '', id: '', modelName: '', protocol: 'openai_chat', providerId }
}

// Populate the provider form from an existing record for edit; the api key is never
// prefilled (write-only secret), so a blank submit leaves the stored key untouched.
export function providerFormFromProvider(provider: ProviderListItem): ProviderFormState {
  return {
    apiKey: '',
    baseUrl: provider.base_url ?? '',
    description: provider.description ?? '',
    id: provider.id,
    provider: provider.provider ?? '',
  }
}

// Optional string fields collapse to undefined when blank so the API omits them
// (rather than persisting empty strings / clearing the stored api key).
export function buildCreateProviderPayload(form: ProviderFormState): CreateProviderInput {
  return {
    api_key: form.apiKey || undefined,
    base_url: form.baseUrl || undefined,
    description: form.description || undefined,
    id: form.id,
    provider: form.provider || undefined,
  }
}

export function buildUpdateProviderPayload(form: ProviderFormState): UpdateProviderInput {
  return {
    api_key: form.apiKey || undefined,
    base_url: form.baseUrl || undefined,
    description: form.description || undefined,
    provider: form.provider || undefined,
  }
}

export function buildCreateModelPayload(form: ModelFormState): CreateModelInput {
  const usesEndpoint = ENDPOINT_PROTOCOLS.has(form.protocol)
  return {
    base_url: usesEndpoint ? undefined : form.baseUrl || undefined,
    endpoint: usesEndpoint ? form.endpoint || undefined : undefined,
    id: form.id,
    model_name: form.modelName,
    protocol: form.protocol,
    provider_id: form.providerId,
  }
}

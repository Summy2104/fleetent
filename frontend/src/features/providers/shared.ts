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
  id: string
  modelName: string
  protocol: string
  providerId: string
}

export function emptyProviderForm(): ProviderFormState {
  return { apiKey: '', baseUrl: '', description: '', id: '', provider: '' }
}

export function emptyModelForm(providerId = ''): ModelFormState {
  return { baseUrl: '', id: '', modelName: '', protocol: 'openai_chat', providerId }
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
  return {
    base_url: form.baseUrl || undefined,
    id: form.id,
    model_name: form.modelName,
    protocol: form.protocol,
    provider_id: form.providerId,
  }
}

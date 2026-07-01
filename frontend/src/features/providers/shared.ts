import { useQuery } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export type AdminMe = { email: string; id: string; role: string }

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

export function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export type ProviderListItem = {
  api_key: string | null
  api_key_env: string | null
  api_key_set: boolean
  base_url: string | null
  description: string | null
  id: string
  model_count: number
  provider: string | null
  vendor?: string | null
}

export type ModelListItem = {
  base_url: string | null
  description: string | null
  endpoint: string | null
  id: string
  input_price_per_1k: number | null
  max_tokens: number | null
  model_name: string
  output_price_per_1k: number | null
  params: Record<string, unknown> | null
  protocol: string
  provider_id: string
}

export type CreateProviderInput = {
  api_key?: string
  api_key_env?: string
  base_url?: string
  description?: string
  id: string
  provider?: string
}

export type UpdateProviderInput = Omit<CreateProviderInput, 'id'>

export type CreateModelInput = {
  base_url?: string
  description?: string
  endpoint?: string
  id: string
  input_price_per_1k?: number | null
  max_tokens?: number
  model_name: string
  output_price_per_1k?: number | null
  params?: Record<string, unknown>
  protocol: string
  provider_id: string
}

export type UpdateModelInput = Omit<CreateModelInput, 'id' | 'provider_id' | 'protocol'> & {
  provider_id?: string
  protocol?: string
}

export type ConnectivityTestResult = {
  details?: string
  error?: string
  latency_ms?: number
  model?: string
  provider_id?: string
  reachable: boolean
}

export function useProvidersQuery() {
  const api = useAdminApi()
  return useQuery({
    queryKey: ['providers'],
    queryFn: () => api.get<ProviderListItem[]>('/admin/providers'),
  })
}

export function useModelsQuery() {
  const api = useAdminApi()
  return useQuery({
    queryKey: ['models'],
    queryFn: () => api.get<ModelListItem[]>('/admin/models'),
  })
}

export function useCreateProviderMutation() {
  const api = useAdminApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateProviderInput) => api.post<ProviderListItem>('/admin/providers', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })
}

export function useUpdateProviderMutation(providerId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: UpdateProviderInput) => api.put<ProviderListItem>(`/admin/providers/${providerId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })
}

export function useDeleteProviderMutation(providerId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete<{ deleted: boolean; id: string }>(`/admin/providers/${providerId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
      await queryClient.invalidateQueries({ queryKey: ['models'] })
    },
  })
}

export function useCreateModelMutation() {
  const api = useAdminApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateModelInput) => api.post<ModelListItem>('/admin/models', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
      await queryClient.invalidateQueries({ queryKey: ['models'] })
    },
  })
}

export function useUpdateModelMutation(modelId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: UpdateModelInput) => api.put<ModelListItem>(`/admin/models/${modelId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['models'] })
    },
  })
}

export function useDeleteModelMutation(modelId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete<{ deleted: boolean; id: string }>(`/admin/models/${modelId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
      await queryClient.invalidateQueries({ queryKey: ['models'] })
    },
  })
}

export function useConnectivityTestMutation(modelId: string) {
  const api = useAdminApi()
  return useMutation({
    mutationFn: () => api.post<ConnectivityTestResult>(`/admin/models/${modelId}/connectivity-test`),
  })
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';

export type ProviderListItem = {
  api_key: string | null;
  api_key_env: string | null;
  api_key_set: boolean;
  base_url: string;
  description: string | null;
  id: string;
  input_price_per_1k: number | string | null;
  model: string;
  output_price_per_1k: number | string | null;
  protocol: string | null;
  provider: string | null;
};

export type CreateProviderInput = {
  api_key?: string;
  api_key_env?: string;
  base_url: string;
  description?: string;
  id: string;
  max_tokens?: number;
  model: string;
  params?: Record<string, unknown>;
  protocol?: string;
  provider?: string;
  temperature?: number;
};

export type UpdateProviderInput = Omit<CreateProviderInput, 'id'>;

export type ConnectivityTestResult = {
  base_url?: string;
  details?: string;
  error?: string;
  latency_ms?: number;
  model?: string;
  reachable: boolean;
};

export type UpdatePricingInput = {
  input_price_per_1k: number | null;
  output_price_per_1k: number | null;
};

export type ProviderPricing = {
  id?: string;
  input_price_per_1k: number | string | null;
  output_price_per_1k: number | string | null;
};

export function useProvidersQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['providers'],
    queryFn: () => api.get<ProviderListItem[]>('/admin/providers'),
  });
}

export function useCreateProviderMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateProviderInput) => api.post<ProviderListItem>('/admin/providers', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] });
    },
  });
}

export function useUpdateProviderMutation(providerId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateProviderInput) =>
      api.put<ProviderListItem>(`/admin/providers/${providerId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] });
    },
  });
}

export function useDeleteProviderMutation(providerId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete<{ deleted: boolean; id: string }>(`/admin/providers/${providerId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] });
    },
  });
}

export function useConnectivityTestMutation(providerId: string) {
  const api = useAdminApi();

  return useMutation({
    mutationFn: () =>
      api.post<ConnectivityTestResult>(`/admin/providers/${providerId}/connectivity-test`),
  });
}

export function useUpdatePricingMutation(providerId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdatePricingInput) =>
      api.put<ProviderPricing>(`/admin/providers/${providerId}/pricing`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] });
    },
  });
}

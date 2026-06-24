import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';

export type ImMapping = {
  created_at: string;
  id: number;
  platform: string;
  platform_user_id: string;
  user_email: string | null;
  user_id: string;
  user_name: string;
};

export type CreateMappingInput = {
  platform: string;
  platform_user_id: string;
  user_id: string;
};

export type BindableUser = {
  email: string | null;
  id: string;
  name: string;
};

export function useImMappingsQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['im-identities'],
    queryFn: () => api.get<ImMapping[]>('/admin/im-identities'),
  });
}

export function useBindableUsersQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['users'],
    queryFn: () => api.get<BindableUser[]>('/admin/users'),
  });
}

export function useCreateMappingMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateMappingInput) => api.post<ImMapping>('/admin/im-identities', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['im-identities'] });
    },
  });
}

export function useDeleteMappingMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (imUserId: number) => api.delete<void>(`/admin/im-identities/${imUserId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['im-identities'] });
    },
  });
}

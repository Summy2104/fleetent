import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';

export type UserListItem = {
  email: string | null;
  id: string;
  must_reset: boolean;
  name: string;
  role: string;
  status: string;
};

export type CreateUserInput = {
  email: string;
  must_reset?: boolean;
  name: string;
  password?: string;
  role: string;
};

export type UpdateUserInput = {
  email?: string;
  name?: string;
};

export type SetRoleInput = {
  role: string;
};

export type ReasonInput = {
  reason: string;
};

export type ResetPasswordInput = {
  new_password: string;
};

export type UserKey = {
  created_at: string;
  id: number;
  masked: string;
  note: string | null;
  prefix: string;
  revoked_at: string | null;
  scope: string[];
};

export type CreateKeyInput = {
  expires_at?: string;
  note?: string;
  scope: string[];
};

export type CreateKeyResult = {
  key: UserKey;
  plaintext: string;
};

export type RotateKeyResult = {
  api_key_plaintext_once: string;
  user: UserListItem;
};

export type CreateServicePrincipalInput = {
  name: string;
};

export type CreateServicePrincipalResult = {
  api_key_plaintext_once: string;
  user: UserListItem;
};

export type ImUser = {
  allowed: boolean;
  created_at?: string;
  id: number;
  metadata?: Record<string, unknown>;
  platform: string;
  platform_user_id: string;
  status: string;
  user_id: string;
};

export type ImIdentityField = {
  key: string;
  label: string;
  multiline?: boolean;
};

export type BindImUserInput = {
  user_id: string;
};

export type UpdateImUserInput = {
  metadata: Record<string, unknown>;
  platform_user_id?: string;
};

export type InitiateLinkResult = {
  code: string;
  expires_at: string;
};

export type UnlinkIdentityInput = {
  platform: string;
  platform_user_id: string;
};

export type CreateImMappingInput = {
  platform: string;
  platform_user_id: string;
  user_id: string;
};

export type ImMapping = {
  created_at: string;
  id: number;
  platform: string;
  platform_user_id: string;
  user_email: string | null;
  user_id: string;
  user_name: string;
};

function invalidateUserState(queryClient: ReturnType<typeof useQueryClient>, userId: string) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ['users'] }),
    queryClient.invalidateQueries({ queryKey: ['user-keys', userId] }),
    queryClient.invalidateQueries({ queryKey: ['im-users'] }),
  ]);
}

export function useUsersQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['users'],
    queryFn: () => api.get<UserListItem[]>('/admin/users'),
  });
}

export function useCreateUserMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateUserInput) => api.post<UserListItem>('/admin/users', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}

export function useCreateServicePrincipalMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateServicePrincipalInput) =>
      api.post<CreateServicePrincipalResult>('/admin/service-principals', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}

export function useInitiateLinkMutation() {
  const api = useAdminApi();

  return useMutation({
    mutationFn: () => api.post<InitiateLinkResult>('/admin/link/initiate'),
  });
}

export function useUnlinkIdentityMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UnlinkIdentityInput) => api.post<{ status: string }>('/admin/link/unlink', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['im-users'] });
    },
  });
}

export function useUpdateUserMutation(userId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateUserInput) => api.patch<UserListItem>(`/admin/users/${userId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}

export function useSetRoleMutation(userId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: SetRoleInput) => api.patch<UserListItem>(`/admin/users/${userId}/role`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}

export function useBlockUserMutation(userId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ReasonInput) => api.post<{ status: string }>(`/admin/users/${userId}/block`, input),
    onSuccess: async () => {
      await invalidateUserState(queryClient, userId);
    },
  });
}

export function useUnblockUserMutation(userId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<{ status: string }>(`/admin/users/${userId}/unblock`),
    onSuccess: async () => {
      await invalidateUserState(queryClient, userId);
    },
  });
}

export function useResetPasswordMutation(userId: string) {
  const api = useAdminApi();

  return useMutation({
    mutationFn: (input: ResetPasswordInput) =>
      api.post<{ status: string }>(`/admin/users/${userId}/password`, input),
  });
}

export function useDeleteUserMutation(userId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete<void>(`/admin/users/${userId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.removeQueries({ queryKey: ['user-keys', userId] });
    },
  });
}

export function useUserKeysQuery(userId: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(userId),
    queryKey: ['user-keys', userId],
    queryFn: () => api.get<UserKey[]>(`/admin/users/${userId}/keys`),
  });
}

export function useCreateKeyMutation(userId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateKeyInput) =>
      api.post<CreateKeyResult>(`/admin/users/${userId}/keys`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['user-keys', userId] });
    },
  });
}

export function useRotateKeyMutation(userId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<RotateKeyResult>(`/admin/users/${userId}/rotate-key`),
    onSuccess: async () => {
      await invalidateUserState(queryClient, userId);
    },
  });
}

export function useRevokeKeyMutation(userId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (keyId: number) => api.delete<void>(`/admin/keys/${keyId}`, { 'X-Confirm': 'true' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['user-keys', userId] });
    },
  });
}

export function useImUsersQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['im-users'],
    queryFn: () => api.get<ImUser[]>('/admin/im-users'),
  });
}

export function useImIdentityFieldsQuery(enabled = true) {
  const api = useAdminApi();

  return useQuery({
    enabled,
    queryKey: ['im-user-fields'],
    queryFn: () => api.get<Record<string, ImIdentityField[]>>('/admin/im-users/fields'),
  });
}

export function useCreateImMappingMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateImMappingInput) => api.post<ImMapping>('/admin/im-identities', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['im-users'] });
    },
  });
}

export function useUpdateImUserMutation(imUserId: number) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateImUserInput) =>
      api.patch<{ status: string }>(`/admin/im-users/${imUserId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['im-users'] });
    },
  });
}

export function useDeleteImUserMutation(imUserId: number) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete<void>(`/admin/im-users/${imUserId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['im-users'] });
    },
  });
}

export function useBindImUserMutation(imUserId: number) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: BindImUserInput) =>
      api.post<{ status: string }>(`/admin/im-users/${imUserId}/bind`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['im-users'] });
    },
  });
}

export function useBlockImUserMutation(imUserId: number) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ReasonInput) =>
      api.post<{ allowed: boolean }>(`/admin/im-users/${imUserId}/block`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['im-users'] });
    },
  });
}

export function useRestoreImUserMutation(imUserId: number) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ReasonInput) =>
      api.post<{ allowed: boolean }>(`/admin/im-users/${imUserId}/restore`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['im-users'] });
    },
  });
}

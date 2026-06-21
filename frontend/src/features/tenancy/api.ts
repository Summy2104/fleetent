import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';

export type TenantListItem = {
  approver_user_id: string | null;
  created_at: string;
  id: string;
  name: string;
  status: string;
};

export type TeamListItem = {
  approver_user_id: string | null;
  created_at: string;
  id: string;
  name: string;
  tenant_id: string;
};

export type CreateTenantInput = {
  id?: string;
  name: string;
  status?: string;
};

export type CreateTeamInput = {
  id?: string;
  name: string;
  tenant_id: string;
};

export type AssignUserTenantInput = {
  tenant_id: string;
  user_id: string;
};

export type SetApproverInput = {
  approver_user_id: string | null;
  entity_type: 'tenant' | 'team';
};

function invalidateTenancyLists(queryClient: ReturnType<typeof useQueryClient>): Promise<void[]> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ['tenants'] }),
    queryClient.invalidateQueries({ queryKey: ['teams'] }),
    queryClient.invalidateQueries({ queryKey: ['users'] }),
  ]);
}

export function useTenantsQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['tenants'],
    queryFn: () => api.get<TenantListItem[]>('/admin/tenancy/tenants'),
  });
}

export function useCreateTenantMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateTenantInput) =>
      api.post<TenantListItem>('/admin/tenancy/tenants', {
        ...input,
        status: input.status ?? 'active',
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tenants'] });
    },
  });
}

export function useTeamsQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: ['teams'],
    queryFn: () => api.get<TeamListItem[]>('/admin/tenancy/teams'),
  });
}

export function useCreateTeamMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateTeamInput) => api.post<TeamListItem>('/admin/tenancy/teams', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });
}

export function useAssignUserTenantMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ tenant_id, user_id }: AssignUserTenantInput) =>
      api.post<{ status: string; tenant_id: string; user_id: string }>(
        `/admin/tenancy/users/${user_id}/tenant`,
        { tenant_id }
      ),
    onSuccess: async () => {
      await invalidateTenancyLists(queryClient);
    },
  });
}

export function useSetApproverMutation(entityId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: SetApproverInput) =>
      api.patch<{ entity_type: string; id: string; status: string }>(
        `/admin/tenancy/approvers/${entityId}`,
        input
      ),
    onSuccess: async (_, variables) => {
      if (variables.entity_type === 'tenant') {
        await queryClient.invalidateQueries({ queryKey: ['tenants'] });
        return;
      }
      await queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });
}

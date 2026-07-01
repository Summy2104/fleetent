import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';

export type KnowledgeBase = {
  archived: boolean;
  bound_agents: number[];
  chunk_count: number;
  description: string;
  doc_count: number;
  kb_id: string;
  last_import: string | null;
  tenant_id: string;
};

export type CreateKbInput = {
  description: string;
  kb_id: string;
  tenant_id?: string;
};

export type UpdateKbInput = {
  description: string;
};

export type DeleteKbInput = {
  tenant_id?: string;
};

export type KnowledgeDocument = {
  chunks: number;
  created_at: string;
  document_id: string;
  filename: string;
  source: string;
  source_url: string | null;
};

export type DeleteDocumentInput = {
  document_id?: string;
  tenant_id?: string;
};

const kbListKey = ['kb'] as const;

function kbDocumentsKey(kbId: string) {
  return ['kb', kbId, 'documents'] as const;
}

function kbAgentsKey(kbId: string) {
  return ['kb', kbId, 'agents'] as const;
}

function invalidateKbDetailQueries(queryClient: ReturnType<typeof useQueryClient>, kbId: string) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: kbListKey }),
    queryClient.invalidateQueries({ queryKey: kbDocumentsKey(kbId) }),
    queryClient.invalidateQueries({ queryKey: kbAgentsKey(kbId) }),
  ]);
}

export function useKbsQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: kbListKey,
    queryFn: () => api.get<KnowledgeBase[]>('/admin/kb'),
  });
}

export function useCreateKbMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateKbInput) => api.post<CreateKbInput>('/admin/kb', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbListKey });
    },
  });
}

export function useUpdateKbMutation(kbId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateKbInput) => api.patch<UpdateKbInput>(`/admin/kb/${kbId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbListKey });
    },
  });
}

export function useDeleteKbMutation(kbId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input?: DeleteKbInput) => {
      const search = new URLSearchParams();
      if (input?.tenant_id) {
        search.set('tenant_id', input.tenant_id);
      }
      const suffix = search.toString() ? `?${search.toString()}` : '';
      return api.delete<{ archived: boolean; kb_id: string }>(`/admin/kb/${kbId}${suffix}`, {
        'X-Confirm': 'true',
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbListKey });
      queryClient.removeQueries({ queryKey: kbDocumentsKey(kbId) });
      queryClient.removeQueries({ queryKey: kbAgentsKey(kbId) });
    },
  });
}

export function useDocumentsQuery(kbId: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(kbId),
    queryKey: kbId ? kbDocumentsKey(kbId) : ['kb', 'documents', 'idle'],
    queryFn: () => api.get<KnowledgeDocument[]>(`/admin/kb/${kbId}/documents`),
  });
}

export function useDeleteDocumentMutation(kbId: string, defaultDocumentId?: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input?: DeleteDocumentInput) => {
      const documentId = input?.document_id ?? defaultDocumentId;
      if (!documentId) {
        throw new Error('document_id is required');
      }
      const search = new URLSearchParams();
      if (input?.tenant_id) {
        search.set('tenant_id', input.tenant_id);
      }
      const suffix = search.toString() ? `?${search.toString()}` : '';
      return api.delete<{ deleted: boolean; document_id: string; kb_id: string }>(
        `/admin/kb/${kbId}/documents/${documentId}${suffix}`,
        { 'X-Confirm': 'true' }
      );
    },
    onSuccess: async () => {
      await invalidateKbDetailQueries(queryClient, kbId);
    },
  });
}

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

export type IngestDocumentInput = {
  content: string;
  document_format: string;
  source: string;
  tenant_id?: string;
};

export type IngestDocumentResult = {
  chunks: number;
  document_id: string;
  filename: string;
  source: string;
  source_url: string | null;
  wired?: boolean;
};

export type DeleteDocumentInput = {
  document_id?: string;
  tenant_id?: string;
};

export type SyncDocumentsInput = {
  path: string;
  tenant_id?: string;
};

export type SyncDocumentsResult = {
  failed: number;
  ingested: number;
  job_id: string;
  scanned: number;
  skipped: number;
  wired?: boolean;
};

export type KbAgentsResult = {
  agents: number[];
  kb_id: string;
};

export type KbConnector = {
  config: Record<string, unknown>;
  connector_id: string;
  custom?: Record<string, unknown>;
  custom_yaml?: string;
  description: string;
  enabled: boolean;
  kb_id: string;
  kind: string;
  tenant_id: string;
};

export type CreateConnectorInput = {
  config: Record<string, unknown>;
  connector_id: string;
  custom?: Record<string, unknown>;
  custom_yaml?: string;
  description: string;
  enabled?: boolean;
  kb_id: string;
  kind: string;
  tenant_id?: string;
};

export type UpdateConnectorInput = Partial<Omit<CreateConnectorInput, 'connector_id' | 'kind'>>;

export type ConnectorCheckResult = {
  connector_id: string;
  message: string;
  status: string;
};

export type ConnectorStatusResult = {
  connector_id: string;
  error: string | null;
  status: string;
  summary: Record<string, unknown> | null;
};

export type ConnectorSyncInput = {
  dry_run: boolean;
};

export type ConnectorSyncResult = {
  connector_id: string;
  error: string | null;
  job_id?: string;
  status: string;
  summary: Record<string, unknown> | null;
};

const kbListKey = ['kb'] as const;

function kbDocumentsKey(kbId: string) {
  return ['kb', kbId, 'documents'] as const;
}

function kbAgentsKey(kbId: string) {
  return ['kb', kbId, 'agents'] as const;
}

const kbConnectorsKey = ['kb', 'connectors'] as const;

function connectorStatusKey(connectorId: string) {
  return ['kb', 'connectors', connectorId, 'status'] as const;
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

export function useIngestDocumentMutation(kbId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: IngestDocumentInput) =>
      api.post<IngestDocumentResult>(`/admin/kb/${kbId}/documents`, input),
    onSuccess: async () => {
      await invalidateKbDetailQueries(queryClient, kbId);
    },
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

export function useSyncDocumentsMutation(kbId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: SyncDocumentsInput) =>
      api.post<SyncDocumentsResult>(`/admin/kb/${kbId}/sync`, input, { 'X-Confirm': 'true' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbListKey });
    },
  });
}

export function useKbAgentsQuery(kbId: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(kbId),
    queryKey: kbId ? kbAgentsKey(kbId) : ['kb', 'agents', 'idle'],
    queryFn: () => api.get<KbAgentsResult>(`/admin/kb/${kbId}/agents`),
  });
}

export function useKbConnectorsQuery() {
  const api = useAdminApi();

  return useQuery({
    queryKey: kbConnectorsKey,
    queryFn: () => api.get<KbConnector[]>('/admin/kb/connectors'),
  });
}

export function useCreateConnectorMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateConnectorInput) => api.post<KbConnector>('/admin/kb/connectors', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbConnectorsKey });
    },
  });
}

export function useUpdateConnectorMutation(connectorId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateConnectorInput) =>
      api.patch<KbConnector>(`/admin/kb/connectors/${connectorId}`, input),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: kbConnectorsKey }),
        queryClient.invalidateQueries({ queryKey: connectorStatusKey(connectorId) }),
      ]);
    },
  });
}

export function useDeleteConnectorMutation(connectorId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.delete<void>(`/admin/kb/connectors/${connectorId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbConnectorsKey });
      queryClient.removeQueries({ queryKey: connectorStatusKey(connectorId) });
    },
  });
}

export function useConnectorCheckMutation(connectorId: string) {
  const api = useAdminApi();

  return useMutation({
    mutationFn: () =>
      api.post<ConnectorCheckResult>(`/admin/kb/connectors/${connectorId}/check`),
  });
}

export function useConnectorStatusQuery(connectorId: string | null) {
  const api = useAdminApi();

  return useQuery({
    enabled: Boolean(connectorId),
    queryKey: connectorId ? connectorStatusKey(connectorId) : ['kb', 'connectors', 'status', 'idle'],
    queryFn: () => api.get<ConnectorStatusResult>(`/admin/kb/connectors/${connectorId}/status`),
  });
}

export function useConnectorSyncMutation(connectorId: string) {
  const api = useAdminApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ConnectorSyncInput) =>
      api.post<ConnectorSyncResult>(`/admin/kb/connectors/${connectorId}/sync`, input),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: kbConnectorsKey }),
        queryClient.invalidateQueries({ queryKey: connectorStatusKey(connectorId) }),
      ]);
    },
  });
}

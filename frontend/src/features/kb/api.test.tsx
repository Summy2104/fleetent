import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import {
  useConnectorCheckMutation,
  useConnectorStatusQuery,
  useConnectorSyncMutation,
  useCreateConnectorMutation,
  useCreateKbMutation,
  useDeleteConnectorMutation,
  useDeleteDocumentMutation,
  useDeleteKbMutation,
  useDocumentsQuery,
  useKbsQuery,
  useKbAgentsQuery,
  useSyncDocumentsMutation,
  useIngestDocumentMutation,
  useKbConnectorsQuery,
  useUpdateConnectorMutation,
  useUpdateKbMutation,
} from '@/features/kb/api';

import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

type KnowledgeBaseRecord = {
  archived: boolean;
  bound_agents: number[];
  chunk_count: number;
  description: string;
  doc_count: number;
  kb_id: string;
  last_import: string | null;
  tenant_id: string;
};

type DocumentRecord = {
  chunks: number;
  created_at: string;
  document_id: string;
  filename: string;
  source: string;
  source_url: string | null;
};

type ConnectorRecord = {
  config: Record<string, unknown>;
  connector_id: string;
  custom: Record<string, unknown>;
  custom_yaml: string;
  description: string;
  enabled: boolean;
  kb_id: string;
  kind: string;
  tenant_id: string;
};

function createWrapper(): ({ children }: { children: ReactNode }) => JSX.Element {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </AuthProvider>
    );
  };
}

describe('kb api', () => {
  it('loads kb lists and refreshes kb, documents, and agents after kb/document mutations', async () => {
    let kbListRequests = 0;
    let documentListRequests = 0;
    let knowledgeBases: KnowledgeBaseRecord[] = [
      {
        archived: false,
        bound_agents: [7],
        chunk_count: 4,
        description: 'Support handbook',
        doc_count: 1,
        kb_id: 'support',
        last_import: null,
        tenant_id: 'default',
      },
    ];
    let documents: DocumentRecord[] = [
      {
        chunks: 4,
        created_at: '2026-06-21T09:00:00Z',
        document_id: 'doc-1',
        filename: 'support.md',
        source: 'support.md',
        source_url: null,
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, ({ request }) => {
        kbListRequests += 1;
        expect(request.headers.get('authorization')).toBe('Session session-token');
        return HttpResponse.json(knowledgeBases);
      }),
      http.post(`${API_BASE_URL}/admin/kb`, async ({ request }) => {
        const body = (await request.json()) as { description: string; kb_id: string; tenant_id?: string };
        knowledgeBases = [
          ...knowledgeBases,
          {
            archived: false,
            bound_agents: [],
            chunk_count: 0,
            description: body.description,
            doc_count: 0,
            kb_id: body.kb_id,
            last_import: null,
            tenant_id: body.tenant_id ?? 'default',
          },
        ];
        return HttpResponse.json(body);
      }),
      http.patch(`${API_BASE_URL}/admin/kb/support`, async ({ request }) => {
        const body = (await request.json()) as { description: string };
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, description: body.description } : kb
        );
        return HttpResponse.json({ description: body.description, kb_id: 'support' });
      }),
      http.delete(`${API_BASE_URL}/admin/kb/support`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        knowledgeBases = knowledgeBases.filter((kb) => kb.kb_id !== 'support');
        return HttpResponse.json({ archived: true, kb_id: 'support' });
      }),
      http.get(`${API_BASE_URL}/admin/kb/support/documents`, () => {
        documentListRequests += 1;
        return HttpResponse.json(documents);
      }),
      http.post(`${API_BASE_URL}/admin/kb/support/documents`, async ({ request }) => {
        const body = (await request.json()) as {
          content: string;
          document_format: string;
          source: string;
        };
        expect(body.document_format).toBe('markdown');
        documents = [
          ...documents,
          {
            chunks: 2,
            created_at: '2026-06-21T10:00:00Z',
            document_id: 'doc-2',
            filename: body.source,
            source: body.source,
            source_url: null,
          },
        ];
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, doc_count: documents.length } : kb
        );
        return HttpResponse.json({
          chunks: 2,
          document_id: 'doc-2',
          filename: body.source,
          source: body.source,
          source_url: null,
          wired: true,
        });
      }),
      http.delete(`${API_BASE_URL}/admin/kb/support/documents/doc-1`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        documents = documents.filter((document) => document.document_id !== 'doc-1');
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, doc_count: documents.length } : kb
        );
        return HttpResponse.json({ deleted: true, document_id: 'doc-1', kb_id: 'support' });
      }),
      http.post(`${API_BASE_URL}/admin/kb/support/sync`, async ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        expect(await request.json()).toEqual({ path: '/data/support', tenant_id: 'default' });
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, last_import: '2026-06-21T11:00:00Z' } : kb
        );
        return HttpResponse.json({
          failed: 0,
          ingested: 1,
          job_id: 'job-sync-1',
          scanned: 1,
          skipped: 0,
        });
      }),
      http.get(`${API_BASE_URL}/admin/kb/support/agents`, () => {
        return HttpResponse.json({ agents: [7], kb_id: 'support' });
      })
    );

    const wrapper = createWrapper();
    renderHook(() => useKbsQuery(), { wrapper });
    renderHook(() => useDocumentsQuery('support'), { wrapper });
    const agents = renderHook(() => useKbAgentsQuery('support'), { wrapper });

    await waitFor(() => {
      expect(kbListRequests).toBe(1);
      expect(documentListRequests).toBe(1);
      expect(agents.result.current.data?.agents).toEqual([7]);
    });

    const createKb = renderHook(() => useCreateKbMutation(), { wrapper });
    const updateKb = renderHook(() => useUpdateKbMutation('support'), { wrapper });
    const deleteKb = renderHook(() => useDeleteKbMutation('support'), { wrapper });
    const ingestDocument = renderHook(() => useIngestDocumentMutation('support'), { wrapper });
    const deleteDocument = renderHook(() => useDeleteDocumentMutation('support', 'doc-1'), { wrapper });
    const syncDocuments = renderHook(() => useSyncDocumentsMutation('support'), { wrapper });

    let previousKbRequests = kbListRequests;
    await createKb.result.current.mutateAsync({
      description: 'Operations runbook',
      kb_id: 'ops',
      tenant_id: 'default',
    });
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbRequests);
    });

    previousKbRequests = kbListRequests;
    await updateKb.result.current.mutateAsync({ description: 'Support runbook' });
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbRequests);
    });

    const previousDocumentRequests = documentListRequests;
    previousKbRequests = kbListRequests;
    await ingestDocument.result.current.mutateAsync({
      content: '# Support\n\nReset billing.',
      document_format: 'markdown',
      source: 'new-support.md',
      tenant_id: 'default',
    });
    await waitFor(() => {
      expect(documentListRequests).toBeGreaterThan(previousDocumentRequests);
      expect(kbListRequests).toBeGreaterThan(previousKbRequests);
    });

    previousKbRequests = kbListRequests;
    const previousDeleteDocumentRequests = documentListRequests;
    await deleteDocument.result.current.mutateAsync({ tenant_id: 'default' });
    await waitFor(() => {
      expect(documentListRequests).toBeGreaterThan(previousDeleteDocumentRequests);
      expect(kbListRequests).toBeGreaterThan(previousKbRequests);
    });

    previousKbRequests = kbListRequests;
    await syncDocuments.result.current.mutateAsync({ path: '/data/support', tenant_id: 'default' });
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbRequests);
    });

    previousKbRequests = kbListRequests;
    await deleteKb.result.current.mutateAsync({ tenant_id: 'default' });
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbRequests);
    });
  });

  it('loads connectors and status, then refreshes connector queries after connector mutations', async () => {
    let connectorListRequests = 0;
    let statusRequests = 0;
    let connectors: ConnectorRecord[] = [
      {
        config: { folder_id: 'FOLDER123' },
        connector_id: 'pilot-drive',
        custom: { poll_interval: 3600 },
        custom_yaml: 'poll_interval: 3600\n',
        description: 'Support handbook',
        enabled: true,
        kb_id: 'support',
        kind: 'google_drive',
        tenant_id: 'default',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/kb/connectors`, () => {
        connectorListRequests += 1;
        return HttpResponse.json(connectors);
      }),
      http.post(`${API_BASE_URL}/admin/kb/connectors`, async ({ request }) => {
        const body = (await request.json()) as ConnectorRecord;
        connectors = [...connectors, body];
        return HttpResponse.json(body, { status: 201 });
      }),
      http.patch(`${API_BASE_URL}/admin/kb/connectors/pilot-drive`, async ({ request }) => {
        const body = (await request.json()) as Partial<ConnectorRecord>;
        connectors = connectors.map((connector) =>
          connector.connector_id === 'pilot-drive' ? { ...connector, ...body } : connector
        );
        return HttpResponse.json(connectors[0]);
      }),
      http.delete(`${API_BASE_URL}/admin/kb/connectors/pilot-drive`, () => {
        connectors = connectors.filter((connector) => connector.connector_id !== 'pilot-drive');
        return new HttpResponse(null, { status: 204 });
      }),
      http.post(`${API_BASE_URL}/admin/kb/connectors/pilot-drive/check`, () =>
        HttpResponse.json({
          connector_id: 'pilot-drive',
          message: 'reachable',
          status: 'ok',
        })
      ),
      http.get(`${API_BASE_URL}/admin/kb/connectors/pilot-drive/status`, () => {
        statusRequests += 1;
        return HttpResponse.json({
          connector_id: 'pilot-drive',
          error: null,
          status: 'idle',
          summary: { scanned: 3 },
        });
      }),
      http.post(`${API_BASE_URL}/admin/kb/connectors/pilot-drive/sync`, async ({ request }) => {
        expect(await request.json()).toEqual({ dry_run: true });
        return HttpResponse.json({
          connector_id: 'pilot-drive',
          error: null,
          status: 'dry_run_ok',
          summary: { planned: 2 },
        });
      })
    );

    const wrapper = createWrapper();
    renderHook(() => useKbConnectorsQuery(), { wrapper });
    const status = renderHook(() => useConnectorStatusQuery('pilot-drive'), { wrapper });

    await waitFor(() => {
      expect(connectorListRequests).toBe(1);
      expect(statusRequests).toBe(1);
      expect(status.result.current.data?.status).toBe('idle');
    });

    const createConnector = renderHook(() => useCreateConnectorMutation(), { wrapper });
    const updateConnector = renderHook(() => useUpdateConnectorMutation('pilot-drive'), { wrapper });
    const deleteConnector = renderHook(() => useDeleteConnectorMutation('pilot-drive'), { wrapper });
    const checkConnector = renderHook(() => useConnectorCheckMutation('pilot-drive'), { wrapper });
    const syncConnector = renderHook(() => useConnectorSyncMutation('pilot-drive'), { wrapper });

    let previousConnectorRequests = connectorListRequests;
    await createConnector.result.current.mutateAsync({
      config: { folder_id: 'FOLDER999' },
      connector_id: 'pilot-drive-2',
      custom_yaml: '',
      description: 'Second drive',
      enabled: true,
      kb_id: 'ops',
      kind: 'google_drive',
      tenant_id: 'default',
    });
    await waitFor(() => {
      expect(connectorListRequests).toBeGreaterThan(previousConnectorRequests);
    });

    previousConnectorRequests = connectorListRequests;
    await updateConnector.result.current.mutateAsync({ enabled: false });
    await waitFor(() => {
      expect(connectorListRequests).toBeGreaterThan(previousConnectorRequests);
    });

    const checkResult = await checkConnector.result.current.mutateAsync();
    expect(checkResult).toEqual({
      connector_id: 'pilot-drive',
      message: 'reachable',
      status: 'ok',
    });

    const syncResult = await syncConnector.result.current.mutateAsync({ dry_run: true });
    expect(syncResult).toEqual({
      connector_id: 'pilot-drive',
      error: null,
      status: 'dry_run_ok',
      summary: { planned: 2 },
    });

    previousConnectorRequests = connectorListRequests;
    await deleteConnector.result.current.mutateAsync();
    await waitFor(() => {
      expect(connectorListRequests).toBeGreaterThan(previousConnectorRequests);
    });
  });
});

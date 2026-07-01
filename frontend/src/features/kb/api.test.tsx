import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import * as kbApi from '@/features/kb/api';
import {
  useCreateKbMutation,
  useDeleteDocumentMutation,
  useDeleteKbMutation,
  useDocumentsQuery,
  useKbsQuery,
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
  it('loads kb lists and refreshes kb and documents after surviving mutations', async () => {
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
      http.delete(`${API_BASE_URL}/admin/kb/support/documents/doc-1`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        documents = documents.filter((document) => document.document_id !== 'doc-1');
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, doc_count: documents.length } : kb
        );
        return HttpResponse.json({ deleted: true, document_id: 'doc-1', kb_id: 'support' });
      })
    );

    const wrapper = createWrapper();
    renderHook(() => useKbsQuery(), { wrapper });
    renderHook(() => useDocumentsQuery('support'), { wrapper });

    await waitFor(() => {
      expect(kbListRequests).toBe(1);
      expect(documentListRequests).toBe(1);
      expect('useKbAgentsQuery' in kbApi).toBe(false);
    });

    const createKb = renderHook(() => useCreateKbMutation(), { wrapper });
    const updateKb = renderHook(() => useUpdateKbMutation('support'), { wrapper });
    const deleteKb = renderHook(() => useDeleteKbMutation('support'), { wrapper });
    const deleteDocument = renderHook(() => useDeleteDocumentMutation('support', 'doc-1'), { wrapper });

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

    const previousDeleteDocumentRequests = documentListRequests;
    previousKbRequests = kbListRequests;
    await deleteDocument.result.current.mutateAsync({ tenant_id: 'default' });
    await waitFor(() => {
      expect(documentListRequests).toBeGreaterThan(previousDeleteDocumentRequests);
      expect(kbListRequests).toBeGreaterThan(previousKbRequests);
    });

    previousKbRequests = kbListRequests;
    await deleteKb.result.current.mutateAsync({ tenant_id: 'default' });
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbRequests);
    });
  });
});

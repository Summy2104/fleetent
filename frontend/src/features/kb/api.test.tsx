import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/app/auth'
import {
  useBindAgentMutation,
  useCreateKbMutation,
  useDocumentChunksQuery,
  useDeleteDocumentMutation,
  useDeleteKbMutation,
  useDocumentsQuery,
  useKbAgentsQuery,
  useKbsQuery,
  useSearchKbMutation,
  useUnbindAgentMutation,
  useUploadDocumentMutation,
  useUpdateKbMutation,
} from '@/features/kb/api'
import type { ApiError } from '@/lib/api-client'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

type KnowledgeBaseRecord = {
  archived: boolean
  bound_agents: number[]
  chunk_count: number
  description: string
  doc_count: number
  kb_id: string
  last_import: string | null
  tenant_id: string
}

type DocumentRecord = {
  chunks: number
  created_at: string
  document_id: string
  filename: string
  source: string
  source_url: string | null
}

type DocumentChunkRecord = {
  chunk_id: string
  content: string
  document_id: string
  filename: string
  kb_id: string
  position: number | null
  score: number | null
  section: string
  section_path: string
  source: string
  source_url: string | null
}

function createWrapper(): ({ children }: { children: ReactNode }) => JSX.Element {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </AuthProvider>
    )
  }
}

describe('kb api', () => {
  it('loads kb lists and refreshes kb, documents, and agents after surviving mutations', async () => {
    let kbListRequests = 0
    let documentListRequests = 0
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
    ]
    let documents: DocumentRecord[] = [
      {
        chunks: 4,
        created_at: '2026-06-21T09:00:00Z',
        document_id: 'doc-1',
        filename: 'support.md',
        source: 'support.md',
        source_url: null,
      },
    ]

    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, ({ request }) => {
        kbListRequests += 1
        expect(request.headers.get('authorization')).toBe('Session session-token')
        return HttpResponse.json(knowledgeBases)
      }),
      http.post(`${API_BASE_URL}/admin/kb`, async ({ request }) => {
        const body = (await request.json()) as { description: string; kb_id: string; tenant_id?: string }
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
        ]
        return HttpResponse.json(body)
      }),
      http.patch(`${API_BASE_URL}/admin/kb/support`, async ({ request }) => {
        const body = (await request.json()) as { description: string }
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, description: body.description } : kb
        )
        return HttpResponse.json({ description: body.description, kb_id: 'support' })
      }),
      http.delete(`${API_BASE_URL}/admin/kb/support`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true')
        knowledgeBases = knowledgeBases.filter((kb) => kb.kb_id !== 'support')
        return HttpResponse.json({ archived: true, kb_id: 'support' })
      }),
      http.get(`${API_BASE_URL}/admin/kb/support/documents`, () => {
        documentListRequests += 1
        return HttpResponse.json(documents)
      }),
      http.delete(`${API_BASE_URL}/admin/kb/support/documents/doc-1`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true')
        documents = documents.filter((document) => document.document_id !== 'doc-1')
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, doc_count: documents.length } : kb
        )
        return HttpResponse.json({ deleted: true, document_id: 'doc-1', kb_id: 'support' })
      }),
      http.get(`${API_BASE_URL}/admin/kb/support/agents`, () => HttpResponse.json({ agents: [7], kb_id: 'support' }))
    )

    const wrapper = createWrapper()
    renderHook(() => useKbsQuery(), { wrapper })
    renderHook(() => useDocumentsQuery('support'), { wrapper })
    const agents = renderHook(() => useKbAgentsQuery('support'), { wrapper })

    await waitFor(() => {
      expect(kbListRequests).toBe(1)
      expect(documentListRequests).toBe(1)
      expect(agents.result.current.data?.agents).toEqual([7])
    })

    const createKb = renderHook(() => useCreateKbMutation(), { wrapper })
    const updateKb = renderHook(() => useUpdateKbMutation('support'), { wrapper })
    const deleteKb = renderHook(() => useDeleteKbMutation('support'), { wrapper })
    const deleteDocument = renderHook(() => useDeleteDocumentMutation('support', 'doc-1'), { wrapper })

    let previousKbRequests = kbListRequests
    await createKb.result.current.mutateAsync({
      description: 'Operations runbook',
      kb_id: 'ops',
      tenant_id: 'default',
    })
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbRequests)
    })

    previousKbRequests = kbListRequests
    await updateKb.result.current.mutateAsync({ description: 'Support runbook' })
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbRequests)
    })

    const previousDeleteDocumentRequests = documentListRequests
    previousKbRequests = kbListRequests
    await deleteDocument.result.current.mutateAsync({ tenant_id: 'default' })
    await waitFor(() => {
      expect(documentListRequests).toBeGreaterThan(previousDeleteDocumentRequests)
      expect(kbListRequests).toBeGreaterThan(previousKbRequests)
    })

    previousKbRequests = kbListRequests
    await deleteKb.result.current.mutateAsync({ tenant_id: 'default' })
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbRequests)
    })
  })

  it('loads document chunks with the expected kb/document path', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/kb/support/documents/doc-1/chunks`, ({ request }) => {
        expect(new URL(request.url).pathname).toBe('/admin/kb/support/documents/doc-1/chunks')
        return HttpResponse.json<DocumentChunkRecord[]>([
          {
            chunk_id: 'chunk-1',
            content: 'Section body',
            document_id: 'doc-1',
            filename: 'support.md',
            kb_id: 'support',
            position: 0,
            score: null,
            section: 'Getting Started',
            section_path: 'Getting Started',
            source: 'support.md',
            source_url: null,
          },
        ])
      })
    )

    const wrapper = createWrapper()
    const result = renderHook(() => useDocumentChunksQuery('support', 'doc-1'), { wrapper })

    await waitFor(() => {
      expect(result.result.current.data).toEqual([
        {
          chunk_id: 'chunk-1',
          content: 'Section body',
          document_id: 'doc-1',
          filename: 'support.md',
          kb_id: 'support',
          position: 0,
          score: null,
          section: 'Getting Started',
          section_path: 'Getting Started',
          source: 'support.md',
          source_url: null,
        },
      ])
    })
  })

  it('binds and unbinds agents while refreshing kb and binding queries', async () => {
    let kbListRequests = 0
    let kbAgentRequests = 0
    const bindings = new Set<number>([7])

    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, () => {
        kbListRequests += 1
        return HttpResponse.json<KnowledgeBaseRecord[]>([
          {
            archived: false,
            bound_agents: [...bindings],
            chunk_count: 4,
            description: 'Support handbook',
            doc_count: 1,
            kb_id: 'support',
            last_import: null,
            tenant_id: 'default',
          },
        ])
      }),
      http.get(`${API_BASE_URL}/admin/kb/support/agents`, () => {
        kbAgentRequests += 1
        return HttpResponse.json({ agents: [...bindings], kb_id: 'support' })
      }),
      http.post(`${API_BASE_URL}/admin/kb/support/agents`, async ({ request }) => {
        const body = (await request.json()) as { agent_id: number; tenant_id?: string }
        expect(body).toEqual({ agent_id: 9, tenant_id: 'default' })
        bindings.add(body.agent_id)
        return HttpResponse.json({ agent_id: body.agent_id, bound: true, kb_id: 'support' })
      }),
      http.delete(`${API_BASE_URL}/admin/kb/support/agents/7`, () => {
        bindings.delete(7)
        return HttpResponse.json({ agent_id: 7, bound: false, kb_id: 'support' })
      })
    )

    const wrapper = createWrapper()
    renderHook(() => useKbsQuery(), { wrapper })
    renderHook(() => useKbAgentsQuery('support'), { wrapper })

    await waitFor(() => {
      expect(kbListRequests).toBe(1)
      expect(kbAgentRequests).toBe(1)
    })

    const bindAgent = renderHook(() => useBindAgentMutation('support'), { wrapper })
    const unbindAgent = renderHook(() => useUnbindAgentMutation('support'), { wrapper })

    let previousKbListRequests = kbListRequests
    let previousAgentRequests = kbAgentRequests
    await bindAgent.result.current.mutateAsync({ agent_id: 9, tenant_id: 'default' })
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbListRequests)
      expect(kbAgentRequests).toBeGreaterThan(previousAgentRequests)
    })

    previousKbListRequests = kbListRequests
    previousAgentRequests = kbAgentRequests
    await unbindAgent.result.current.mutateAsync({ agent_id: 7, tenant_id: 'default' })
    await waitFor(() => {
      expect(kbListRequests).toBeGreaterThan(previousKbListRequests)
      expect(kbAgentRequests).toBeGreaterThan(previousAgentRequests)
    })
  })

  it('searches a knowledge base with kb_id, query, and optional top_k', async () => {
    server.use(
      http.post(`${API_BASE_URL}/admin/kb/search`, async ({ request }) => {
        expect(await request.json()).toEqual({
          kb_ids: ['support'],
          query: 'ERR42',
          tenant_id: 'default',
          top_k: 3,
        })
        return HttpResponse.json({
          kb_ids: ['support'],
          mode: 'hybrid',
          query: 'ERR42',
          results: [
            {
              chunk_id: 'chunk-1',
              content: 'Restart the billing service when ERR42 appears.',
              document_id: 'doc-1',
              filename: 'support-guide.md',
              kb_id: 'support',
              position: 0,
              score: 0.91,
              section: 'Reset Guide',
              section_path: 'Reset Guide',
              source: 'support-guide.md',
              source_url: null,
            },
          ],
        })
      })
    )

    const wrapper = createWrapper()
    const searchKb = renderHook(() => useSearchKbMutation(), { wrapper })

    await expect(
      searchKb.result.current.mutateAsync({
        kb_id: 'support',
        query: 'ERR42',
        tenant_id: 'default',
        top_k: 3,
      })
    ).resolves.toEqual({
      kb_ids: ['support'],
      mode: 'hybrid',
      query: 'ERR42',
      results: [
        {
          chunk_id: 'chunk-1',
          content: 'Restart the billing service when ERR42 appears.',
          document_id: 'doc-1',
          filename: 'support-guide.md',
          kb_id: 'support',
          position: 0,
          score: 0.91,
          section: 'Reset Guide',
          section_path: 'Reset Guide',
          source: 'support-guide.md',
          source_url: null,
        },
      ],
    })
  })

  it('uploads documents as multipart and preserves 413/404 errors', async () => {
    server.use(
      http.post(`${API_BASE_URL}/admin/kb/support/documents`, async ({ request }) => {
        expect(request.headers.get('content-type')).toMatch(/^multipart\/form-data; boundary=/)
        const body = await request.text()
        expect(body).toContain('name="file"; filename="blob"')
        expect(body).toContain('Content-Type: text/markdown')
        return HttpResponse.json({ job_id: 'job-1' })
      }),
      http.post(`${API_BASE_URL}/admin/kb/too-large/documents`, () =>
        HttpResponse.json({ detail: 'upload exceeds max_upload_bytes' }, { status: 413 })
      ),
      http.post(`${API_BASE_URL}/admin/kb/missing/documents`, () =>
        HttpResponse.json({ detail: 'kb not found' }, { status: 404 })
      )
    )

    const wrapper = createWrapper()
    const uploadSupport = renderHook(() => useUploadDocumentMutation('support'), { wrapper })
    const uploadTooLarge = renderHook(() => useUploadDocumentMutation('too-large'), { wrapper })
    const uploadMissing = renderHook(() => useUploadDocumentMutation('missing'), { wrapper })

    await expect(
      uploadSupport.result.current.mutateAsync({
        file: new File(['hello world'], 'guide.md', { type: 'text/markdown' }),
      })
    ).resolves.toEqual({ job_id: 'job-1' })

    await expect(
      uploadTooLarge.result.current.mutateAsync({
        file: new File(['hello world'], 'guide.md', { type: 'text/markdown' }),
      })
    ).rejects.toMatchObject({
      status: 413,
      body: { detail: 'upload exceeds max_upload_bytes' },
    } satisfies Partial<ApiError>)

    await expect(
      uploadMissing.result.current.mutateAsync({
        file: new File(['hello world'], 'guide.md', { type: 'text/markdown' }),
      })
    ).rejects.toMatchObject({
      status: 404,
      body: { detail: 'kb not found' },
    } satisfies Partial<ApiError>)
  })
})

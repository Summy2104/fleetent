import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { KnowledgeBasePage } from '@/features/kb/page'
import { I18nProvider } from '@/i18n'
import { toast } from '@/lib/toast'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

vi.mock('@/lib/toast', () => ({
  toast: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
  },
}))

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

function renderPage(): void {
  render(
    <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
      <AppQueryProvider>
        <I18nProvider>
          <KnowledgeBasePage />
        </I18nProvider>
      </AppQueryProvider>
    </AuthProvider>
  )
}

async function selectOption(
  user: ReturnType<typeof userEvent.setup>,
  trigger: HTMLElement,
  optionText: string | RegExp
): Promise<void> {
  await user.click(trigger)
  await user.click(await screen.findByRole('option', { name: optionText }))
}

describe('knowledge base page', () => {
  beforeEach(() => {
    vi.mocked(toast.success).mockReset()
    vi.mocked(toast.error).mockReset()
    vi.mocked(toast.info).mockReset()
  })

  it('supports kb create/edit/delete plus document list and delete without retired ingest controls', async () => {
    const user = userEvent.setup({ delay: null })

    let knowledgeBases: KnowledgeBaseRecord[] = [
      {
        archived: false,
        bound_agents: [7],
        chunk_count: 2,
        description: 'Support handbook',
        doc_count: 1,
        kb_id: 'support',
        last_import: null,
        tenant_id: 'default',
      },
    ]
    const documents: Record<string, DocumentRecord[]> = {
      support: [
        {
          chunks: 2,
          created_at: '2026-06-21T09:00:00Z',
          document_id: 'doc-1',
          filename: 'support.md',
          source: 'support.md',
          source_url: null,
        },
      ],
      ops: [],
    }
    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, () => HttpResponse.json(knowledgeBases)),
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
        documents[body.kb_id] = []
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
        delete documents.support
        return HttpResponse.json({ archived: true, kb_id: 'support' })
      }),
      http.get(`${API_BASE_URL}/admin/kb/:kbId/documents`, ({ params }) =>
        HttpResponse.json(documents[String(params.kbId)] ?? [])
      ),
      http.delete(`${API_BASE_URL}/admin/kb/support/documents/doc-1`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true')
        documents.support = documents.support.filter((document) => document.document_id !== 'doc-1')
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, doc_count: documents.support.length } : kb
        )
        return HttpResponse.json({ deleted: true, document_id: 'doc-1', kb_id: 'support' })
      }),
      http.get(`${API_BASE_URL}/admin/kb/:kbId/agents`, ({ params }) =>
        HttpResponse.json({
          agents: params.kbId === 'support' ? [7] : [],
          kb_id: params.kbId,
        })
      )
    )

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Knowledge Base' })).toBeInTheDocument()
    expect(await screen.findByText('support')).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Connectors' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add connector' })).not.toBeInTheDocument()
    // Bound-agent ids render in the table row.
    expect(screen.getByRole('button', { name: 'Actions for support' })).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()

    // Create a knowledge base via the Add dialog.
    await user.click(screen.getByRole('button', { name: 'Add knowledge base' }))
    const createDialog = await screen.findByRole('dialog')
    await user.type(within(createDialog).getByLabelText(/Knowledge base ID/), 'ops')
    await user.type(within(createDialog).getByLabelText('Description'), 'Operations runbook')
    await user.click(within(createDialog).getByRole('button', { name: 'Create' }))
    expect(await screen.findByRole('button', { name: 'Actions for ops' })).toBeInTheDocument()

    // Edit the support kb description.
    await user.click(screen.getByRole('button', { name: 'Actions for support' }))
    await user.click(await screen.findByText('Edit'))
    const editDialog = await screen.findByRole('dialog')
    expect(within(editDialog).getByDisplayValue('support')).toBeDisabled()
    await user.clear(within(editDialog).getByLabelText('Description'))
    await user.type(within(editDialog).getByLabelText('Description'), 'Support runbook')
    await user.click(within(editDialog).getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Support runbook')).toBeInTheDocument()

    // Open Documents section, see the listed document, then delete the original.
    await user.click(screen.getByRole('button', { name: 'Actions for support' }))
    await user.click(await screen.findByText('Documents'))
    const docsSection = await screen.findByRole('heading', { name: 'Documents · support' })
    const docs = within(docsSection.closest('section') as HTMLElement)
    expect(await docs.findByText('support.md')).toBeInTheDocument()
    expect(docs.queryByLabelText('Source')).not.toBeInTheDocument()
    expect(docs.queryByLabelText('Content')).not.toBeInTheDocument()
    expect(docs.queryByRole('button', { name: 'Ingest document' })).not.toBeInTheDocument()

    await user.click(docs.getByRole('button', { name: 'Delete support.md' }))
    await waitFor(() => {
      expect(docs.queryByText('support.md')).not.toBeInTheDocument()
    })

    // Retired sync action is no longer present in the actions menu.
    await user.click(screen.getByRole('button', { name: 'Actions for support' }))
    expect(screen.queryByText('Sync')).not.toBeInTheDocument()
    await user.keyboard('{Escape}')

    // Delete the support kb via the confirm dialog.
    await user.click(screen.getByRole('button', { name: 'Actions for support' }))
    await user.click(await screen.findByText('Delete'))
    const confirm = await screen.findByRole('alertdialog')
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }))
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Actions for support' })).not.toBeInTheDocument()
    })
  })

  it('opens the documents section and previews chunks for a document', async () => {
    const user = userEvent.setup({ delay: null })

    const knowledgeBases: KnowledgeBaseRecord[] = [
      {
        archived: false,
        bound_agents: [7],
        chunk_count: 2,
        description: 'Support handbook',
        doc_count: 1,
        kb_id: 'support',
        last_import: null,
        tenant_id: 'default',
      },
    ]
    const documents: Record<string, DocumentRecord[]> = {
      support: [
        {
          chunks: 2,
          created_at: '2026-06-21T09:00:00Z',
          document_id: 'doc-1',
          filename: 'support.md',
          source: 'support.md',
          source_url: null,
        },
      ],
    }

    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, () => HttpResponse.json(knowledgeBases)),
      http.get(`${API_BASE_URL}/admin/kb/:kbId/documents`, ({ params }) =>
        HttpResponse.json(documents[String(params.kbId)] ?? [])
      ),
      http.get(`${API_BASE_URL}/admin/kb/:kbId/agents`, ({ params }) =>
        HttpResponse.json({
          agents: params.kbId === 'support' ? [7] : [],
          kb_id: params.kbId,
        })
      ),
      http.get(`${API_BASE_URL}/admin/kb/support/documents/doc-1/chunks`, ({ request }) => {
        expect(new URL(request.url).pathname).toBe('/admin/kb/support/documents/doc-1/chunks')
        return HttpResponse.json([
          {
            chunk_id: 'chunk-1',
            content: 'Install the agent package before bootstrapping.',
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

    renderPage()

    expect(await screen.findByText('support')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Actions for support' }))
    await user.click(await screen.findByText('Documents'))

    expect(await screen.findByRole('heading', { name: 'Documents · support' })).toBeInTheDocument()
    expect(await screen.findByText('support.md')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Preview chunks for support.md' }))
    expect(await screen.findByText('Install the agent package before bootstrapping.')).toBeInTheDocument()
    expect(screen.getByText('Getting Started')).toBeInTheDocument()
  })

  it('binds and unbinds agents from the agents section', async () => {
    const user = userEvent.setup({ delay: null })
    let boundAgents = [7]

    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, () =>
        HttpResponse.json<KnowledgeBaseRecord[]>([
          {
            archived: false,
            bound_agents: boundAgents,
            chunk_count: 2,
            description: 'Support handbook',
            doc_count: 1,
            kb_id: 'support',
            last_import: null,
            tenant_id: 'default',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/kb/support/documents`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/kb/support/agents`, () =>
        HttpResponse.json({
          agents: boundAgents,
          kb_id: 'support',
        })
      ),
      http.get(`${API_BASE_URL}/admin/agents`, ({ request }) => {
        expect(new URL(request.url).searchParams.get('include_archived')).toBe('true')
        return HttpResponse.json([
          { agent_id: 7, agent_name: 'support-agent', status: 'active', system_prompt: 'help', allowed_tools: [] },
          { agent_id: 9, agent_name: 'ops-agent', status: 'active', system_prompt: 'ops', allowed_tools: [] },
        ])
      }),
      http.post(`${API_BASE_URL}/admin/kb/support/agents`, async ({ request }) => {
        const body = (await request.json()) as { agent_id: number; tenant_id?: string }
        expect(body).toEqual({ agent_id: 9, tenant_id: 'default' })
        boundAgents = [7, 9]
        return HttpResponse.json({ agent_id: 9, bound: true, kb_id: 'support' })
      }),
      http.delete(`${API_BASE_URL}/admin/kb/support/agents/7`, () => {
        boundAgents = [9]
        return HttpResponse.json({ agent_id: 7, bound: false, kb_id: 'support' })
      })
    )

    renderPage()

    await user.click(await screen.findByText('support'))
    await user.click(screen.getByRole('tab', { name: 'Agents' }))

    await selectOption(user, screen.getByRole('combobox', { name: 'Agent' }), 'ops-agent')
    await user.click(screen.getByRole('button', { name: 'Bind agent' }))

    expect(await screen.findByText('9')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Unbind agent 7' }))
    await waitFor(() => {
      expect(screen.queryByText('7')).not.toBeInTheDocument()
    })
  })

  it('runs retrieval playground searches and shows results, empty state, and request errors', async () => {
    const user = userEvent.setup({ delay: null })

    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, () =>
        HttpResponse.json<KnowledgeBaseRecord[]>([
          {
            archived: false,
            bound_agents: [7],
            chunk_count: 2,
            description: 'Support handbook',
            doc_count: 1,
            kb_id: 'support',
            last_import: null,
            tenant_id: 'default',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/kb/support/documents`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/kb/support/agents`, () =>
        HttpResponse.json({
          agents: [7],
          kb_id: 'support',
        })
      ),
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/admin/kb/search`, async ({ request }) => {
        const body = (await request.json()) as { kb_ids: string[]; query: string; top_k?: number; tenant_id: string }
        expect(body.kb_ids).toEqual(['support'])
        if (body.query === 'ERR42') {
          return HttpResponse.json({
            kb_ids: ['support'],
            mode: 'hybrid',
            query: body.query,
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
        }
        if (body.query === 'missing') {
          return HttpResponse.json({
            kb_ids: ['support'],
            mode: 'hybrid',
            query: body.query,
            results: [],
          })
        }
        return HttpResponse.json({ detail: 'search backend unavailable' }, { status: 502 })
      })
    )

    renderPage()

    await user.click(await screen.findByText('support'))
    await user.click(screen.getByRole('tab', { name: 'Playground' }))

    await user.type(screen.getByLabelText('Query'), 'ERR42')
    await user.clear(screen.getByLabelText('Top K'))
    await user.type(screen.getByLabelText('Top K'), '3')
    await user.click(screen.getByRole('button', { name: 'Run search' }))

    expect(await screen.findByText('Restart the billing service when ERR42 appears.')).toBeInTheDocument()
    expect(screen.getByText('support-guide.md')).toBeInTheDocument()
    expect(screen.getByText('0.91')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Query'))
    await user.type(screen.getByLabelText('Query'), 'missing')
    await user.click(screen.getByRole('button', { name: 'Run search' }))
    expect(await screen.findByText('No retrieval results.')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Query'))
    await user.type(screen.getByLabelText('Query'), 'explode')
    await user.click(screen.getByRole('button', { name: 'Run search' }))
    expect(await screen.findByText('search backend unavailable')).toBeInTheDocument()
  })

  it('uploads a document, exposes refresh, and reports 413/404 without false success toasts', async () => {
    const user = userEvent.setup({ delay: null })
    let uploadMode: 'success' | 'too-large' | 'missing' = 'success'

    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, () =>
        HttpResponse.json<KnowledgeBaseRecord[]>([
          {
            archived: false,
            bound_agents: [7],
            chunk_count: 2,
            description: 'Support handbook',
            doc_count: 1,
            kb_id: 'support',
            last_import: null,
            tenant_id: 'default',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/kb/support/documents`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/kb/support/agents`, () =>
        HttpResponse.json({
          agents: [7],
          kb_id: 'support',
        })
      ),
      http.get(`${API_BASE_URL}/admin/agents`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/admin/kb/support/documents`, () => {
        if (uploadMode === 'too-large') {
          return HttpResponse.json({ detail: 'upload exceeds max_upload_bytes' }, { status: 413 })
        }
        if (uploadMode === 'missing') {
          return HttpResponse.json({ detail: 'kb not found' }, { status: 404 })
        }
        return HttpResponse.json({ job_id: 'job-1' })
      })
    )

    renderPage()

    await user.click(await screen.findByText('support'))
    expect(await screen.findByRole('heading', { name: 'Documents · support' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()

    const input = screen.getByLabelText('Upload document', { selector: 'input' })

    const successFile = new File(['hello'], 'guide.md', { type: 'text/markdown' })
    fireEvent.change(input, { target: { files: [successFile] } })
    expect((input as HTMLInputElement).files?.[0]?.name).toBe('guide.md')
    await user.click(screen.getByRole('button', { name: 'Upload document' }))
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('已入队（job job-1）')
    })
    expect(toast.error).not.toHaveBeenCalled()
    const queuedSuccessCalls = () =>
      vi.mocked(toast.success).mock.calls.filter(([message]) => message === '已入队（job job-1）').length

    uploadMode = 'too-large'
    fireEvent.change(input, { target: { files: [successFile] } })
    await user.click(screen.getByRole('button', { name: 'Upload document' }))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('upload exceeds max_upload_bytes')
    })
    expect(queuedSuccessCalls()).toBe(1)

    uploadMode = 'missing'
    fireEvent.change(input, { target: { files: [successFile] } })
    await user.click(screen.getByRole('button', { name: 'Upload document' }))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('kb not found')
    })
    expect(queuedSuccessCalls()).toBe(1)
  })
})

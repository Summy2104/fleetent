import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { KnowledgeBasePage } from '@/features/kb/page'
import { I18nProvider } from '@/i18n'
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

describe('knowledge base page', () => {
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

    // Open Documents dialog: ingest a new doc, see it listed, then delete the original.
    await user.click(screen.getByRole('button', { name: 'Actions for support' }))
    await user.click(await screen.findByText('Documents'))
    const docsDialog = await screen.findByRole('dialog')
    const docs = within(docsDialog)
    expect(await docs.findByText('support.md')).toBeInTheDocument()
    expect(docs.queryByLabelText('Source')).not.toBeInTheDocument()
    expect(docs.queryByLabelText('Content')).not.toBeInTheDocument()
    expect(docs.queryByRole('button', { name: 'Ingest document' })).not.toBeInTheDocument()

    await user.click(docs.getByRole('button', { name: 'Delete support.md' }))
    await waitFor(() => {
      expect(docs.queryByText('support.md')).not.toBeInTheDocument()
    })
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
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
})

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { KnowledgeBasePage } from '@/features/kb/page';
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

function renderPage(): void {
  render(
    <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
      <AppQueryProvider>
        <KnowledgeBasePage />
      </AppQueryProvider>
    </AuthProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('knowledge base page', () => {
  it('supports kb create/edit/delete plus document ingest, list, delete, and sync feedback', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

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
    ];
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
    };
    let lastSyncBody: { path: string; tenant_id?: string } | null = null;

    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, () => HttpResponse.json(knowledgeBases)),
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
        documents[body.kb_id] = [];
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
        delete documents.support;
        return HttpResponse.json({ archived: true, kb_id: 'support' });
      }),
      http.get(`${API_BASE_URL}/admin/kb/:kbId/documents`, ({ params }) =>
        HttpResponse.json(documents[String(params.kbId)] ?? [])
      ),
      http.post(`${API_BASE_URL}/admin/kb/support/documents`, async ({ request }) => {
        const body = (await request.json()) as {
          content: string;
          document_format: string;
          source: string;
          tenant_id?: string;
        };
        expect(body.document_format).toBe('markdown');
        documents.support = [
          ...documents.support,
          {
            chunks: 1,
            created_at: '2026-06-21T10:00:00Z',
            document_id: 'doc-2',
            filename: body.source,
            source: body.source,
            source_url: null,
          },
        ];
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, doc_count: documents.support.length } : kb
        );
        return HttpResponse.json({
          chunks: 1,
          document_id: 'doc-2',
          filename: body.source,
          source: body.source,
          source_url: null,
          wired: true,
        });
      }),
      http.delete(`${API_BASE_URL}/admin/kb/support/documents/doc-1`, ({ request }) => {
        expect(request.headers.get('x-confirm')).toBe('true');
        documents.support = documents.support.filter((document) => document.document_id !== 'doc-1');
        knowledgeBases = knowledgeBases.map((kb) =>
          kb.kb_id === 'support' ? { ...kb, doc_count: documents.support.length } : kb
        );
        return HttpResponse.json({ deleted: true, document_id: 'doc-1', kb_id: 'support' });
      }),
      http.post(`${API_BASE_URL}/admin/kb/support/sync`, async ({ request }) => {
        lastSyncBody = (await request.json()) as { path: string; tenant_id?: string };
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
      http.get(`${API_BASE_URL}/admin/kb/:kbId/agents`, ({ params }) =>
        HttpResponse.json({
          agents: params.kbId === 'support' ? [7] : [],
          kb_id: params.kbId,
        })
      ),
      http.get(`${API_BASE_URL}/admin/kb/connectors`, () => HttpResponse.json([]))
    );

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Knowledge Base' })).toBeInTheDocument();
    expect(await screen.findByText('support')).toBeInTheDocument();
    expect(await screen.findByText('support.md')).toBeInTheDocument();
    expect(screen.getByText('Bound agents: 7')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Knowledge base ID'), 'ops');
    await user.type(screen.getByLabelText('Description'), 'Operations runbook');
    await user.click(screen.getByRole('button', { name: 'Create knowledge base' }));
    expect(await screen.findByRole('button', { name: 'ops' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit support' }));
    expect(screen.getByDisplayValue('support')).toBeDisabled();
    await user.clear(screen.getByLabelText('Description'));
    await user.type(screen.getByLabelText('Description'), 'Support runbook');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText('Support runbook')).toBeInTheDocument();

    await user.clear(screen.getByLabelText('Document source'));
    await user.type(screen.getByLabelText('Document source'), 'new-guide.md');
    await user.clear(screen.getByLabelText('Document content'));
    await user.type(screen.getByLabelText('Document content'), '# Guide{enter}{enter}Reset billing.');
    await user.click(screen.getByRole('button', { name: 'Ingest document' }));
    expect(await screen.findByText('Imported new-guide.md with 1 chunks.')).toBeInTheDocument();
    expect(await screen.findByText('new-guide.md')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete support.md' }));
    await waitFor(() => {
      expect(screen.queryByText('support.md')).not.toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText('Sync path'));
    await user.type(screen.getByLabelText('Sync path'), '/data/support');
    await user.click(screen.getByRole('button', { name: 'Sync documents' }));
    await waitFor(() => {
      expect(lastSyncBody).toEqual({ path: '/data/support', tenant_id: 'default' });
    });
    expect(await screen.findByText('Sync queued: scanned 1, ingested 1, failed 0.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete support' }));
    await waitFor(() => {
      expect(screen.queryByText('support')).not.toBeInTheDocument();
    });
  });

  it('supports connector registration, status, check, sync, edit, and delete within the selected kb', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    let connectors: ConnectorRecord[] = [
      {
        config: { folder_id: 'FOLDER123' },
        connector_id: 'pilot-drive',
        custom: {},
        custom_yaml: '',
        description: 'Support handbook',
        enabled: true,
        kb_id: 'support',
        kind: 'google_drive',
        tenant_id: 'default',
      },
    ];
    let lastSyncBody: { dry_run: boolean } | null = null;

    server.use(
      http.get(`${API_BASE_URL}/admin/kb`, () =>
        HttpResponse.json([
          {
            archived: false,
            bound_agents: [],
            chunk_count: 0,
            description: 'Support handbook',
            doc_count: 0,
            kb_id: 'support',
            last_import: null,
            tenant_id: 'default',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/kb/support/documents`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/admin/kb/support/agents`, () =>
        HttpResponse.json({ agents: [], kb_id: 'support' })
      ),
      http.get(`${API_BASE_URL}/admin/kb/connectors`, () => HttpResponse.json(connectors)),
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
      http.get(`${API_BASE_URL}/admin/kb/connectors/:connectorId/status`, ({ params }) =>
        HttpResponse.json({
          connector_id: params.connectorId,
          error: null,
          status: 'idle',
          summary: { scanned: 3 },
        })
      ),
      http.post(`${API_BASE_URL}/admin/kb/connectors/pilot-drive/sync`, async ({ request }) => {
        lastSyncBody = (await request.json()) as { dry_run: boolean };
        return HttpResponse.json({
          connector_id: 'pilot-drive',
          error: null,
          status: 'dry_run_ok',
          summary: { planned: 2 },
        });
      })
    );

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Knowledge Base' })).toBeInTheDocument();
    expect(await screen.findByText('pilot-drive')).toBeInTheDocument();
    expect(await screen.findByText('Status: idle')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Connector ID'), 'pilot-drive-2');
    await user.selectOptions(screen.getByLabelText('Connector kind'), 'google_drive');
    await user.clear(screen.getByLabelText('Connector description'));
    await user.type(screen.getByLabelText('Connector description'), 'Second drive');
    await user.clear(screen.getByLabelText('Connector config (JSON)'));
    await user.paste('{"folder_id":"FOLDER999"}');
    await user.click(screen.getByRole('button', { name: 'Create connector' }));
    expect(await screen.findByText('pilot-drive-2')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Check pilot-drive' }));
    expect(await screen.findByText('Check result: ok - reachable')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Sync pilot-drive' }));
    await waitFor(() => {
      expect(lastSyncBody).toEqual({ dry_run: true });
    });
    expect(await screen.findByText('Sync result: dry_run_ok ({"planned":2})')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit connector pilot-drive' }));
    expect(screen.getByDisplayValue('pilot-drive')).toBeDisabled();
    await user.clear(screen.getByLabelText('Connector description'));
    await user.type(screen.getByLabelText('Connector description'), 'Updated support drive');
    await user.click(screen.getByRole('button', { name: 'Save connector' }));
    expect(await screen.findByText('Updated support drive')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete connector pilot-drive' }));
    await waitFor(() => {
      expect(screen.queryByText('pilot-drive')).not.toBeInTheDocument();
    });
  });
});

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { I18nProvider } from '@/i18n';
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
        <I18nProvider>
          <KnowledgeBasePage />
        </I18nProvider>
      </AppQueryProvider>
    </AuthProvider>
  );
}

describe('knowledge base page', () => {
  it('supports kb create/edit/delete plus document ingest, list, delete, and sync', async () => {
    const user = userEvent.setup();

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
    // Bound-agent ids render in the table row.
    expect(screen.getByRole('button', { name: 'Actions for support' })).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();

    // Create a knowledge base via the Add dialog.
    await user.click(screen.getByRole('button', { name: 'Add knowledge base' }));
    const createDialog = await screen.findByRole('dialog');
    await user.type(within(createDialog).getByLabelText(/Knowledge base ID/), 'ops');
    await user.type(within(createDialog).getByLabelText('Description'), 'Operations runbook');
    await user.click(within(createDialog).getByRole('button', { name: 'Create' }));
    expect(await screen.findByRole('button', { name: 'Actions for ops' })).toBeInTheDocument();

    // Edit the support kb description.
    await user.click(screen.getByRole('button', { name: 'Actions for support' }));
    await user.click(await screen.findByText('Edit'));
    const editDialog = await screen.findByRole('dialog');
    expect(within(editDialog).getByDisplayValue('support')).toBeDisabled();
    await user.clear(within(editDialog).getByLabelText('Description'));
    await user.type(within(editDialog).getByLabelText('Description'), 'Support runbook');
    await user.click(within(editDialog).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Support runbook')).toBeInTheDocument();

    // Open Documents dialog: ingest a new doc, see it listed, then delete the original.
    await user.click(screen.getByRole('button', { name: 'Actions for support' }));
    await user.click(await screen.findByText('Documents'));
    const docsDialog = await screen.findByRole('dialog');
    const docs = within(docsDialog);
    expect(await docs.findByText('support.md')).toBeInTheDocument();

    await user.clear(docs.getByLabelText('Source'));
    await user.type(docs.getByLabelText('Source'), 'new-guide.md');
    await user.type(docs.getByLabelText('Content'), '# Guide{enter}{enter}Reset billing.');
    await user.click(docs.getByRole('button', { name: 'Ingest document' }));
    expect(await docs.findByText('new-guide.md')).toBeInTheDocument();

    await user.click(docs.getByRole('button', { name: 'Delete support.md' }));
    await waitFor(() => {
      expect(docs.queryByText('support.md')).not.toBeInTheDocument();
    });
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    // Sync dialog posts the directory path.
    await user.click(screen.getByRole('button', { name: 'Actions for support' }));
    await user.click(await screen.findByText('Sync'));
    const syncDialog = await screen.findByRole('dialog');
    await user.clear(within(syncDialog).getByLabelText('Directory path'));
    await user.type(within(syncDialog).getByLabelText('Directory path'), '/data/support');
    await user.click(within(syncDialog).getByRole('button', { name: 'Sync' }));
    await waitFor(() => {
      expect(lastSyncBody).toEqual({ path: '/data/support', tenant_id: 'default' });
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    // Delete the support kb via the confirm dialog.
    await user.click(screen.getByRole('button', { name: 'Actions for support' }));
    await user.click(await screen.findByText('Delete'));
    const confirm = await screen.findByRole('alertdialog');
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Actions for support' })).not.toBeInTheDocument();
    });
  });

  it('supports connector registration, status, check, sync, edit, and delete', async () => {
    const user = userEvent.setup();

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
    let lastPatchBody: Partial<ConnectorRecord> | null = null;

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
        lastPatchBody = body;
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

    // Switch to the Connectors tab.
    await user.click(screen.getByRole('tab', { name: 'Connectors' }));
    expect(await screen.findByText('pilot-drive')).toBeInTheDocument();
    // Connector status renders inline next to the enabled badge.
    expect(await screen.findByText('idle')).toBeInTheDocument();

    // Register a second connector via the Add dialog (kind via Radix Select).
    await user.click(screen.getByRole('button', { name: 'Add connector' }));
    const createDialog = await screen.findByRole('dialog');
    await user.type(within(createDialog).getByLabelText(/Connector ID/), 'pilot-drive-2');
    await user.clear(within(createDialog).getByLabelText('Description'));
    await user.type(within(createDialog).getByLabelText('Description'), 'Second drive');
    const configField = within(createDialog).getByLabelText('Config (JSON)');
    await user.clear(configField);
    await user.click(configField);
    await user.paste('{"folder_id":"FOLDER999"}');
    await user.click(within(createDialog).getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('pilot-drive-2')).toBeInTheDocument();

    // Check the connector (status text flips to the check result).
    await user.click(screen.getByRole('button', { name: 'Actions for pilot-drive' }));
    await user.click(await screen.findByText('Check'));
    expect(await screen.findByText('ok')).toBeInTheDocument();

    // Dry-run sync posts { dry_run: true }.
    await user.click(screen.getByRole('button', { name: 'Actions for pilot-drive' }));
    await user.click(await screen.findByText('Sync (dry-run)'));
    await waitFor(() => {
      expect(lastSyncBody).toEqual({ dry_run: true });
    });

    // Edit the connector description.
    await user.click(screen.getByRole('button', { name: 'Actions for pilot-drive' }));
    await user.click(await screen.findByText('Edit'));
    const editDialog = await screen.findByRole('dialog');
    expect(within(editDialog).getByDisplayValue('pilot-drive')).toBeDisabled();
    await user.clear(within(editDialog).getByLabelText('Description'));
    await user.type(within(editDialog).getByLabelText('Description'), 'Updated support drive');
    await user.click(within(editDialog).getByRole('button', { name: 'Save' }));
    // The connector row does not render the description, so assert the patched
    // payload + dialog dismissal (mutation success closes the dialog).
    await waitFor(() => {
      expect(lastPatchBody?.description).toBe('Updated support drive');
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    // Delete the connector via the confirm dialog.
    await user.click(screen.getByRole('button', { name: 'Actions for pilot-drive' }));
    await user.click(await screen.findByText('Delete'));
    const confirm = await screen.findByRole('alertdialog');
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));
    await waitFor(() => {
      expect(screen.queryByText('pilot-drive')).not.toBeInTheDocument();
    });
  });
});

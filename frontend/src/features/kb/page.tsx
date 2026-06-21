import { useEffect, useMemo, useState } from 'react';

import {
  type CreateConnectorInput,
  type KbConnector,
  useConnectorCheckMutation,
  useConnectorStatusQuery,
  useConnectorSyncMutation,
  useCreateConnectorMutation,
  useCreateKbMutation,
  useDeleteConnectorMutation,
  useDeleteDocumentMutation,
  useDeleteKbMutation,
  useDocumentsQuery,
  useIngestDocumentMutation,
  useKbsQuery,
  useKbAgentsQuery,
  useKbConnectorsQuery,
  useSyncDocumentsMutation,
  useUpdateConnectorMutation,
  useUpdateKbMutation,
} from '@/features/kb/api';

type KbFormState = {
  description: string;
  kbId: string;
};

type DocumentFormState = {
  content: string;
  documentFormat: string;
  source: string;
  syncPath: string;
};

type ConnectorFormState = {
  configJson: string;
  connectorId: string;
  customYaml: string;
  description: string;
  enabled: boolean;
  kind: string;
};

const EMPTY_KB_FORM: KbFormState = {
  description: '',
  kbId: '',
};

const EMPTY_DOCUMENT_FORM: DocumentFormState = {
  content: '',
  documentFormat: 'markdown',
  source: 'support.md',
  syncPath: '/data/support',
};

const EMPTY_CONNECTOR_FORM: ConnectorFormState = {
  configJson: '{}',
  connectorId: '',
  customYaml: '',
  description: '',
  enabled: true,
  kind: 'google_drive',
};

function formatBoundAgents(agents: number[]): string {
  return agents.length ? agents.join(', ') : 'none';
}

function ConnectorCard({
  connector,
  onEdit,
}: {
  connector: KbConnector;
  onEdit: (connector: KbConnector) => void;
}): JSX.Element {
  const status = useConnectorStatusQuery(connector.connector_id);
  const checkConnector = useConnectorCheckMutation(connector.connector_id);
  const syncConnector = useConnectorSyncMutation(connector.connector_id);
  const deleteConnector = useDeleteConnectorMutation(connector.connector_id);

  const handleDelete = async (): Promise<void> => {
    if (!window.confirm(`Delete connector ${connector.connector_id}?`)) {
      return;
    }
    await deleteConnector.mutateAsync();
  };

  return (
    <article className="rounded-2xl border bg-white/80 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-lg font-semibold">{connector.connector_id}</p>
          <p className="text-sm text-muted-foreground">{connector.kind}</p>
          <p className="text-sm text-muted-foreground">{connector.description}</p>
          <p className="text-sm text-muted-foreground">
            {connector.enabled ? 'Enabled' : 'Disabled'}
          </p>
          <p className="text-sm">Status: {status.data?.status ?? 'loading'}</p>
          {checkConnector.data ? (
            <p className="text-sm">
              {`Check result: ${checkConnector.data.status} - ${checkConnector.data.message}`}
            </p>
          ) : null}
          {syncConnector.data ? (
            <p className="text-sm">
              {`Sync result: ${syncConnector.data.status} (${JSON.stringify(syncConnector.data.summary ?? {})})`}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => onEdit(connector)}
            type="button"
          >
            {`Edit connector ${connector.connector_id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void checkConnector.mutateAsync()}
            type="button"
          >
            {`Check ${connector.connector_id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void syncConnector.mutateAsync({ dry_run: true })}
            type="button"
          >
            {`Sync ${connector.connector_id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void handleDelete()}
            type="button"
          >
            {`Delete connector ${connector.connector_id}`}
          </button>
        </div>
      </div>
    </article>
  );
}

export function KnowledgeBasePage(): JSX.Element {
  const kbs = useKbsQuery();
  const connectors = useKbConnectorsQuery();
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);
  const [kbMode, setKbMode] = useState<'create' | 'edit'>('create');
  const [connectorMode, setConnectorMode] = useState<'create' | 'edit'>('create');
  const [kbForm, setKbForm] = useState<KbFormState>(EMPTY_KB_FORM);
  const [documentForm, setDocumentForm] = useState<DocumentFormState>(EMPTY_DOCUMENT_FORM);
  const [connectorForm, setConnectorForm] = useState<ConnectorFormState>(EMPTY_CONNECTOR_FORM);
  const [documentFeedback, setDocumentFeedback] = useState<string | null>(null);
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!kbs.data?.length) {
      setSelectedKbId(null);
      return;
    }
    if (!selectedKbId || !kbs.data.some((kb) => kb.kb_id === selectedKbId)) {
      setSelectedKbId(kbs.data[0].kb_id);
    }
  }, [kbs.data, selectedKbId]);

  const selectedKb = useMemo(
    () => kbs.data?.find((kb) => kb.kb_id === selectedKbId) ?? null,
    [kbs.data, selectedKbId]
  );
  const documents = useDocumentsQuery(selectedKbId);
  const agents = useKbAgentsQuery(selectedKbId);
  const visibleConnectors = useMemo(
    () => connectors.data?.filter((connector) => connector.kb_id === selectedKbId) ?? [],
    [connectors.data, selectedKbId]
  );

  const createKb = useCreateKbMutation();
  const updateKb = useUpdateKbMutation(selectedKbId ?? '');
  const deleteKb = useDeleteKbMutation(selectedKbId ?? '');
  const ingestDocument = useIngestDocumentMutation(selectedKbId ?? '');
  const syncDocuments = useSyncDocumentsMutation(selectedKbId ?? '');
  const createConnector = useCreateConnectorMutation();
  const updateConnector = useUpdateConnectorMutation(connectorForm.connectorId);
  const deleteDocument = useDeleteDocumentMutation(selectedKbId ?? '');

  useEffect(() => {
    if (kbMode === 'edit' && selectedKb) {
      setKbForm({
        description: selectedKb.description,
        kbId: selectedKb.kb_id,
      });
      setDocumentForm((current) => ({
        ...current,
        source: `${selectedKb.kb_id}.md`,
        syncPath: `/data/${selectedKb.kb_id}`,
      }));
    }
  }, [kbMode, selectedKb]);

  const resetKbForm = (): void => {
    setKbMode('create');
    setKbForm(EMPTY_KB_FORM);
  };

  const resetConnectorForm = (): void => {
    setConnectorMode('create');
    setConnectorForm(EMPTY_CONNECTOR_FORM);
  };

  const submitKbForm = async (): Promise<void> => {
    if (kbMode === 'create') {
      await createKb.mutateAsync({
        description: kbForm.description,
        kb_id: kbForm.kbId,
        tenant_id: 'default',
      });
      setSelectedKbId(kbForm.kbId);
      resetKbForm();
      return;
    }

    if (!selectedKbId) {
      return;
    }

    await updateKb.mutateAsync({ description: kbForm.description });
  };

  const handleDeleteKb = async (): Promise<void> => {
    if (!selectedKbId) {
      return;
    }
    if (!window.confirm(`Delete ${selectedKbId}?`)) {
      return;
    }
    await deleteKb.mutateAsync({ tenant_id: 'default' });
  };

  const handleDeleteDocument = async (documentId: string): Promise<void> => {
    if (!selectedKbId) {
      return;
    }
    if (!window.confirm(`Delete ${documentId}?`)) {
      return;
    }
    await deleteDocument.mutateAsync({ document_id: documentId, tenant_id: 'default' });
  };

  const submitDocument = async (): Promise<void> => {
    if (!selectedKbId) {
      return;
    }
    const result = await ingestDocument.mutateAsync({
      content: documentForm.content,
      document_format: documentForm.documentFormat,
      source: documentForm.source,
      tenant_id: 'default',
    });
    setDocumentFeedback(`Imported ${result.filename} with ${result.chunks} chunks.`);
  };

  const submitSync = async (): Promise<void> => {
    if (!selectedKbId) {
      return;
    }
    const result = await syncDocuments.mutateAsync({
      path: documentForm.syncPath,
      tenant_id: 'default',
    });
    setSyncFeedback(
      `Sync queued: scanned ${result.scanned}, ingested ${result.ingested}, failed ${result.failed}.`
    );
  };

  const startEditConnector = (connector: KbConnector): void => {
    setConnectorMode('edit');
    setConnectorForm({
      configJson: JSON.stringify(connector.config ?? {}, null, 0),
      connectorId: connector.connector_id,
      customYaml: connector.custom_yaml ?? '',
      description: connector.description,
      enabled: connector.enabled,
      kind: connector.kind,
    });
  };

  const submitConnector = async (): Promise<void> => {
    const config = JSON.parse(connectorForm.configJson || '{}') as Record<string, unknown>;
    if (connectorMode === 'create') {
      const input: CreateConnectorInput = {
        config,
        connector_id: connectorForm.connectorId,
        custom_yaml: connectorForm.customYaml,
        description: connectorForm.description,
        enabled: connectorForm.enabled,
        kb_id: selectedKbId ?? 'global',
        kind: connectorForm.kind,
        tenant_id: 'default',
      };
      await createConnector.mutateAsync(input);
      resetConnectorForm();
      return;
    }

    await updateConnector.mutateAsync({
      config,
      custom_yaml: connectorForm.customYaml,
      description: connectorForm.description,
      enabled: connectorForm.enabled,
      kb_id: selectedKbId ?? 'global',
      tenant_id: 'default',
    });
  };

  return (
    <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
            Native SPA
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Knowledge Base</h1>
          <p className="text-sm text-muted-foreground">
            Manage KB lifecycle natively: create libraries, ingest documents, run syncs, and
            operate source connectors without dropping back to legacy.
          </p>
        </header>

        <section className="rounded-2xl border bg-white/75 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Create or edit knowledge base</h2>
            {kbMode === 'edit' ? (
              <button
                className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                onClick={resetKbForm}
                type="button"
              >
                New draft
              </button>
            ) : null}
          </div>
          <div className="grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              Knowledge base ID
              <input
                className="rounded-md border bg-white px-3 py-2"
                disabled={kbMode === 'edit'}
                onChange={(event) => setKbForm((current) => ({ ...current, kbId: event.target.value }))}
                value={kbForm.kbId}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Description
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setKbForm((current) => ({ ...current, description: event.target.value }))
                }
                value={kbForm.description}
              />
            </label>
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={() => void submitKbForm()}
              type="button"
            >
              {kbMode === 'create' ? 'Create knowledge base' : 'Save changes'}
            </button>
          </div>
        </section>

        <section className="grid gap-4">
          {kbs.data?.map((kb) => (
            <article className="rounded-2xl border bg-white/80 p-5" key={kb.kb_id}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <button
                    className="text-left text-xl font-semibold"
                    onClick={() => setSelectedKbId(kb.kb_id)}
                    type="button"
                  >
                    {kb.kb_id}
                  </button>
                  <p className="mt-2 text-sm text-muted-foreground">{kb.description}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {`Documents ${kb.doc_count} / Chunks ${kb.chunk_count}`}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                    onClick={() => {
                      setSelectedKbId(kb.kb_id);
                      setKbMode('edit');
                    }}
                    type="button"
                  >
                    {`Edit ${kb.kb_id}`}
                  </button>
                  <button
                    className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                    onClick={() => {
                      setSelectedKbId(kb.kb_id);
                      void handleDeleteKb();
                    }}
                    type="button"
                  >
                    {`Delete ${kb.kb_id}`}
                  </button>
                </div>
              </div>
            </article>
          ))}
        </section>
      </div>

      <aside className="space-y-6">
        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Selected knowledge base</h2>
          <p className="mt-2 text-sm text-muted-foreground">{selectedKb?.kb_id ?? 'No KB selected'}</p>
          <p className="mt-2 text-sm">{`Bound agents: ${formatBoundAgents(agents.data?.agents ?? [])}`}</p>
        </section>

        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Documents</h2>
          <div className="mt-4 grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              Document source
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setDocumentForm((current) => ({ ...current, source: event.target.value }))
                }
                value={documentForm.source}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Document format
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setDocumentForm((current) => ({
                    ...current,
                    documentFormat: event.target.value,
                  }))
                }
                value={documentForm.documentFormat}
              >
                <option value="markdown">markdown</option>
                <option value="text">text</option>
              </select>
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Document content
              <textarea
                className="min-h-28 rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setDocumentForm((current) => ({ ...current, content: event.target.value }))
                }
                value={documentForm.content}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Sync path
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setDocumentForm((current) => ({ ...current, syncPath: event.target.value }))
                }
                value={documentForm.syncPath}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
                onClick={() => void submitDocument()}
                type="button"
              >
                Ingest document
              </button>
              <button
                className="rounded-md bg-secondary px-4 py-2 text-sm font-medium"
                onClick={() => void submitSync()}
                type="button"
              >
                Sync documents
              </button>
            </div>
            {documentFeedback ? <p className="text-sm">{documentFeedback}</p> : null}
            {syncFeedback ? <p className="text-sm">{syncFeedback}</p> : null}
          </div>

          <div className="mt-4 space-y-3">
            {documents.data?.map((document) => (
              <div
                className="flex items-center justify-between gap-4 rounded-xl border bg-white px-4 py-3"
                key={document.document_id}
              >
                <div>
                  <p className="font-medium">{document.filename}</p>
                  <p className="text-sm text-muted-foreground">{`${document.chunks} chunks`}</p>
                </div>
                <button
                  className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                  onClick={() => void handleDeleteDocument(document.document_id)}
                  type="button"
                >
                  {`Delete ${document.filename}`}
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border bg-white/75 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Connectors</h2>
            {connectorMode === 'edit' ? (
              <button
                className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                onClick={resetConnectorForm}
                type="button"
              >
                New connector
              </button>
            ) : null}
          </div>
          <div className="grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              Connector ID
              <input
                className="rounded-md border bg-white px-3 py-2"
                disabled={connectorMode === 'edit'}
                onChange={(event) =>
                  setConnectorForm((current) => ({ ...current, connectorId: event.target.value }))
                }
                value={connectorForm.connectorId}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Connector kind
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setConnectorForm((current) => ({ ...current, kind: event.target.value }))
                }
                value={connectorForm.kind}
              >
                <option value="google_drive">google_drive</option>
                <option value="confluence">confluence</option>
              </select>
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Connector description
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setConnectorForm((current) => ({ ...current, description: event.target.value }))
                }
                value={connectorForm.description}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Connector config (JSON)
              <textarea
                className="min-h-24 rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setConnectorForm((current) => ({ ...current, configJson: event.target.value }))
                }
                value={connectorForm.configJson}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Connector custom YAML
              <textarea
                className="min-h-20 rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setConnectorForm((current) => ({ ...current, customYaml: event.target.value }))
                }
                value={connectorForm.customYaml}
              />
            </label>
            <label className="flex items-center gap-3 text-sm font-medium">
              <input
                checked={connectorForm.enabled}
                onChange={(event) =>
                  setConnectorForm((current) => ({ ...current, enabled: event.target.checked }))
                }
                type="checkbox"
              />
              Enabled
            </label>
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={() => void submitConnector()}
              type="button"
            >
              {connectorMode === 'create' ? 'Create connector' : 'Save connector'}
            </button>
          </div>

          <div className="mt-4 space-y-3">
            {visibleConnectors.map((connector) => (
              <ConnectorCard connector={connector} key={connector.connector_id} onEdit={startEditConnector} />
            ))}
          </div>
        </section>
      </aside>
    </section>
  );
}

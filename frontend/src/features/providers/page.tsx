import { useEffect, useState } from 'react';

import {
  useConnectivityTestMutation,
  useCreateProviderMutation,
  useDeleteProviderMutation,
  useProvidersQuery,
  useUpdatePricingMutation,
  useUpdateProviderMutation,
  type ProviderListItem,
} from '@/features/providers/api';

type ProviderFormState = {
  apiKey: string;
  baseUrl: string;
  description: string;
  id: string;
  model: string;
  protocol: string;
  provider: string;
};

function emptyForm(): ProviderFormState {
  return {
    apiKey: '',
    baseUrl: '',
    description: '',
    id: '',
    model: '',
    protocol: '',
    provider: '',
  };
}

function priceInputValue(value: number | string | null): string {
  return typeof value === 'number' ? String(value) : '';
}

function ProviderCard({
  provider,
  isSelected,
  onEdit,
  onSelect,
}: {
  isSelected: boolean;
  onEdit: () => void;
  onSelect: () => void;
  provider: ProviderListItem;
}): JSX.Element {
  const connectivityTest = useConnectivityTestMutation(provider.id);
  const deleteProvider = useDeleteProviderMutation(provider.id);
  const updatePricing = useUpdatePricingMutation(provider.id);
  const [inputPrice, setInputPrice] = useState(priceInputValue(provider.input_price_per_1k));
  const [outputPrice, setOutputPrice] = useState(priceInputValue(provider.output_price_per_1k));

  useEffect(() => {
    setInputPrice(priceInputValue(provider.input_price_per_1k));
    setOutputPrice(priceInputValue(provider.output_price_per_1k));
  }, [provider.input_price_per_1k, provider.output_price_per_1k]);

  const connectivityMessage = connectivityTest.data
    ? connectivityTest.data.reachable
      ? `Reachable in ${connectivityTest.data.latency_ms ?? '?'}ms using ${connectivityTest.data.model ?? provider.model}`
      : connectivityTest.data.error ?? 'Connectivity test failed'
    : null;

  const handleDelete = async (): Promise<void> => {
    if (!window.confirm(`Delete provider ${provider.id}?`)) {
      return;
    }
    await deleteProvider.mutateAsync();
  };

  return (
    <article className="rounded-2xl border bg-white/80 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <button
            className="text-left text-xl font-semibold"
            onClick={onSelect}
            type="button"
          >
            {provider.id}
          </button>
          <p className="mt-2 text-sm text-muted-foreground">{provider.base_url}</p>
          <p className="mt-1 text-sm text-muted-foreground">{provider.model}</p>
          <p className="mt-1 text-sm text-muted-foreground">{provider.api_key ?? 'No key configured'}</p>
          {provider.description ? (
            <p className="mt-2 text-sm text-foreground">{provider.description}</p>
          ) : null}
          {connectivityMessage ? <p className="mt-2 text-sm text-foreground">{connectivityMessage}</p> : null}
          <p className="mt-2 text-sm font-medium">
            {`Input ${provider.input_price_per_1k ?? '未配置'} / Output ${provider.output_price_per_1k ?? '未配置'}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="rounded-md bg-secondary px-3 py-2 text-sm font-medium" onClick={onEdit} type="button">
            {`Edit ${provider.id}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void connectivityTest.mutateAsync()}
            type="button"
          >
            {`Test ${provider.id} connectivity`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => void handleDelete()}
            type="button"
          >
            {`Delete ${provider.id}`}
          </button>
        </div>
      </div>

      {isSelected ? (
        <div className="mt-4 grid gap-3 border-t pt-4 md:grid-cols-[1fr_1fr_auto]">
          <label className="grid gap-2 text-sm font-medium">
            Input price / 1K tokens
            <input
              className="rounded-md border bg-white px-3 py-2"
              onChange={(event) => setInputPrice(event.target.value)}
              value={inputPrice}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium">
            Output price / 1K tokens
            <input
              className="rounded-md border bg-white px-3 py-2"
              onChange={(event) => setOutputPrice(event.target.value)}
              value={outputPrice}
            />
          </label>
          <div className="flex items-end">
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={() =>
                void updatePricing.mutateAsync({
                  input_price_per_1k: inputPrice === '' ? null : Number(inputPrice),
                  output_price_per_1k: outputPrice === '' ? null : Number(outputPrice),
                })
              }
              type="button"
            >
              {`Save ${provider.id} pricing`}
            </button>
          </div>
        </div>
      ) : null}
    </article>
  );
}

export function ProvidersPage(): JSX.Element {
  const providers = useProvidersQuery();
  const createProvider = useCreateProviderMutation();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<'create' | 'edit'>('create');
  const [form, setForm] = useState<ProviderFormState>(emptyForm);

  useEffect(() => {
    if (!selectedId && providers.data && providers.data.length > 0) {
      setSelectedId(providers.data[0].id);
    }
  }, [providers.data, selectedId]);

  const resetForm = (): void => {
    setMode('create');
    setForm(emptyForm());
  };

  const selectedProvider = providers.data?.find((provider) => provider.id === selectedId) ?? null;
  const updateProvider = useUpdateProviderMutation(selectedId ?? '');

  useEffect(() => {
    if (selectedId && providers.data && !selectedProvider) {
      setSelectedId(providers.data[0]?.id ?? null);
      resetForm();
    }
  }, [providers.data, selectedId, selectedProvider]);

  const startEdit = (provider: ProviderListItem): void => {
    setSelectedId(provider.id);
    setMode('edit');
    setForm({
      apiKey: '',
      baseUrl: provider.base_url,
      description: provider.description ?? '',
      id: provider.id,
      model: provider.model,
      protocol: provider.protocol ?? '',
      provider: provider.provider ?? '',
    });
  };

  const onSubmit = async (): Promise<void> => {
    if (mode === 'create') {
      await createProvider.mutateAsync({
        api_key: form.apiKey || undefined,
        base_url: form.baseUrl,
        description: form.description || undefined,
        id: form.id,
        model: form.model,
        protocol: form.protocol || undefined,
        provider: form.provider || undefined,
      });
      setSelectedId(form.id);
      resetForm();
      return;
    }

    if (!selectedId) {
      return;
    }

    await updateProvider.mutateAsync({
      api_key: form.apiKey || undefined,
      base_url: form.baseUrl || undefined,
      description: form.description || undefined,
      model: form.model || undefined,
      protocol: form.protocol || undefined,
      provider: form.provider || undefined,
    });
    setForm((current) => ({ ...current, apiKey: '' }));
  };

  return (
    <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
            Native SPA
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Providers</h1>
          <p className="text-sm text-muted-foreground">
            Manage model providers natively, including secret rotation, connectivity checks, and
            pricing updates.
          </p>
        </header>

        <section className="rounded-2xl border bg-white/75 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Create or edit provider</h2>
            {mode === 'edit' ? (
              <button
                className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                onClick={resetForm}
                type="button"
              >
                New draft
              </button>
            ) : null}
          </div>
          <div className="grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              Provider ID
              <input
                className="rounded-md border bg-white px-3 py-2"
                disabled={mode === 'edit'}
                onChange={(event) => setForm((current) => ({ ...current, id: event.target.value }))}
                value={form.id}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Base URL
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))}
                value={form.baseUrl}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Model
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                value={form.model}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              API Key
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))}
                type="password"
                value={form.apiKey}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Description
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) =>
                  setForm((current) => ({ ...current, description: event.target.value }))
                }
                value={form.description}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Vendor
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value }))}
                value={form.provider}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Protocol
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setForm((current) => ({ ...current, protocol: event.target.value }))}
                value={form.protocol}
              />
            </label>
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={() => void onSubmit()}
              type="button"
            >
              {mode === 'create' ? 'Create provider' : 'Save changes'}
            </button>
          </div>
        </section>
      </div>

      <section className="grid gap-4">
        {providers.data?.map((provider) => (
          <ProviderCard
            isSelected={provider.id === selectedId}
            key={provider.id}
            onEdit={() => startEdit(provider)}
            onSelect={() => setSelectedId(provider.id)}
            provider={provider}
          />
        ))}
        {!providers.data?.length ? (
          <p className="rounded-2xl border bg-white/80 p-5 text-sm text-muted-foreground">
            No providers configured yet.
          </p>
        ) : null}
        {selectedProvider ? (
          <p className="text-sm text-muted-foreground">{`Selected provider: ${selectedProvider.id}`}</p>
        ) : null}
      </section>
    </section>
  );
}

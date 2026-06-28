import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import {
  useConnectivityTestMutation,
  useCreateModelMutation,
  useCreateProviderMutation,
  useDeleteModelMutation,
  useDeleteProviderMutation,
  useModelsQuery,
  useProvidersQuery,
  useUpdateModelMutation,
  useUpdateProviderMutation,
} from '@/features/providers/api';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

type ProviderRecord = {
  api_key: string | null;
  api_key_env: string | null;
  api_key_set: boolean;
  base_url: string | null;
  description: string | null;
  id: string;
  model_count: number;
  provider: string | null;
  vendor?: string | null;
};

type ModelRecord = {
  base_url: string | null;
  description: string | null;
  endpoint: string | null;
  id: string;
  input_price_per_1k: number | null;
  max_tokens: number | null;
  model_name: string;
  output_price_per_1k: number | null;
  params: Record<string, unknown> | null;
  protocol: string;
  provider_id: string;
};

function renderWithProviders(ui: ReactNode): void {
  render(
    <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
      <AppQueryProvider>{ui}</AppQueryProvider>
    </AuthProvider>
  );
}

function ProvidersProbe(): JSX.Element {
  const providers = useProvidersQuery();
  const models = useModelsQuery();
  const createProvider = useCreateProviderMutation();
  const updateProvider = useUpdateProviderMutation('alpha');
  const deleteProvider = useDeleteProviderMutation('alpha');
  const createModel = useCreateModelMutation();
  const updateModel = useUpdateModelMutation('alpha-chat');
  const deleteModel = useDeleteModelMutation('alpha-chat');
  const connectivityTest = useConnectivityTestMutation('alpha-chat');

  return (
    <section>
      <button
        type="button"
        onClick={() =>
          createProvider.mutate({
            api_key: 'sk-new-secret',
            base_url: 'https://beta.provider',
            id: 'beta',
            provider: 'anthropic',
          })
        }
      >
        create-provider
      </button>
      <button
        type="button"
        onClick={() =>
          updateProvider.mutate({
            base_url: 'https://alpha.edited',
            description: 'Edited provider',
          })
        }
      >
        update-provider
      </button>
      <button type="button" onClick={() => deleteProvider.mutate()}>
        delete-provider
      </button>
      <button
        type="button"
        onClick={() =>
          createModel.mutate({
            base_url: 'https://beta.provider/v1',
            id: 'beta-chat',
            model_name: 'claude-3-7-sonnet',
            protocol: 'openai_chat',
            provider_id: 'beta',
          })
        }
      >
        create-model
      </button>
      <button
        type="button"
        onClick={() =>
          updateModel.mutate({
            base_url: 'https://alpha.chat.edited',
            model_name: 'gpt-5-mini',
          })
        }
      >
        update-model
      </button>
      <button type="button" onClick={() => deleteModel.mutate()}>
        delete-model
      </button>
      <button type="button" onClick={() => connectivityTest.mutate()}>
        connectivity
      </button>
      <ul>
        {providers.data?.map((provider) => (
          <li key={provider.id}>
            provider:{provider.id}:{provider.base_url}
          </li>
        ))}
        {models.data?.map((model) => (
          <li key={model.id}>
            model:{model.id}:{model.model_name}
          </li>
        ))}
      </ul>
      <p>{connectivityTest.data ? `${connectivityTest.data.reachable}:${connectivityTest.data.latency_ms}` : 'idle'}</p>
    </section>
  );
}

describe('providers api', () => {
  it('loads and refreshes provider and model lists after CRUD mutations', async () => {
    const user = userEvent.setup({ delay: null });
    let providers: ProviderRecord[] = [
      {
        api_key: '****',
        api_key_env: 'FLEETENT_MODEL_ALPHA_API_KEY',
        api_key_set: true,
        base_url: 'https://alpha.initial',
        description: 'Initial provider',
        id: 'alpha',
        model_count: 1,
        provider: 'openai',
      },
    ];
    let models: ModelRecord[] = [
      {
        base_url: 'https://alpha.initial',
        description: 'Primary chat model',
        endpoint: null,
        id: 'alpha-chat',
        input_price_per_1k: null,
        max_tokens: 4096,
        model_name: 'gpt-5',
        output_price_per_1k: null,
        params: null,
        protocol: 'openai_chat',
        provider_id: 'alpha',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/providers`, ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Session session-token');
        return HttpResponse.json(providers);
      }),
      http.get(`${API_BASE_URL}/admin/models`, () => HttpResponse.json(models)),
      http.post(`${API_BASE_URL}/admin/providers`, async ({ request }) => {
        const body = (await request.json()) as {
          api_key: string;
          base_url: string;
          id: string;
          provider: string;
        };
        providers = [
          ...providers,
          {
            api_key: '****',
            api_key_env: 'FLEETENT_MODEL_BETA_API_KEY',
            api_key_set: true,
            base_url: body.base_url,
            description: null,
            id: body.id,
            model_count: 0,
            provider: body.provider,
          },
        ];
        return HttpResponse.json(providers[1], { status: 201 });
      }),
      http.put(`${API_BASE_URL}/admin/providers/alpha`, async ({ request }) => {
        const body = (await request.json()) as { base_url?: string; description?: string };
        providers = providers.map((provider) =>
          provider.id === 'alpha'
            ? { ...provider, base_url: body.base_url ?? provider.base_url, description: body.description ?? provider.description }
            : provider
        );
        return HttpResponse.json(providers[0]);
      }),
      http.delete(`${API_BASE_URL}/admin/providers/alpha`, () => {
        providers = providers.filter((provider) => provider.id !== 'alpha');
        return HttpResponse.json({ deleted: true, id: 'alpha' });
      }),
      http.post(`${API_BASE_URL}/admin/models`, async ({ request }) => {
        const body = (await request.json()) as ModelRecord;
        models = [
          ...models,
          {
            base_url: body.base_url,
            description: null,
            endpoint: null,
            id: body.id,
            input_price_per_1k: null,
            max_tokens: null,
            model_name: body.model_name,
            output_price_per_1k: null,
            params: null,
            protocol: body.protocol,
            provider_id: body.provider_id,
          },
        ];
        providers = providers.map((provider) =>
          provider.id === body.provider_id ? { ...provider, model_count: provider.model_count + 1 } : provider
        );
        return HttpResponse.json(models[models.length - 1], { status: 201 });
      }),
      http.put(`${API_BASE_URL}/admin/models/alpha-chat`, async ({ request }) => {
        const body = (await request.json()) as { base_url?: string; model_name?: string };
        models = models.map((model) =>
          model.id === 'alpha-chat'
            ? { ...model, base_url: body.base_url ?? model.base_url, model_name: body.model_name ?? model.model_name }
            : model
        );
        return HttpResponse.json(models[0]);
      }),
      http.delete(`${API_BASE_URL}/admin/models/alpha-chat`, () => {
        models = models.filter((model) => model.id !== 'alpha-chat');
        providers = providers.map((provider) =>
          provider.id === 'alpha' ? { ...provider, model_count: provider.model_count - 1 } : provider
        );
        return HttpResponse.json({ deleted: true, id: 'alpha-chat' });
      })
    );

    renderWithProviders(<ProvidersProbe />);
    expect(await screen.findByText('provider:alpha:https://alpha.initial')).toBeInTheDocument();
    expect(await screen.findByText('model:alpha-chat:gpt-5')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'create-provider' }));
    expect(await screen.findByText('provider:beta:https://beta.provider')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'update-provider' }));
    await waitFor(() => {
      expect(screen.getByText('provider:alpha:https://alpha.edited')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'create-model' }));
    expect(await screen.findByText('model:beta-chat:claude-3-7-sonnet')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'update-model' }));
    await waitFor(() => {
      expect(screen.getByText('model:alpha-chat:gpt-5-mini')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'delete-model' }));
    await waitFor(() => {
      expect(screen.queryByText('model:alpha-chat:gpt-5-mini')).not.toBeInTheDocument();
    });
  });

  it('posts connectivity tests through the model admin endpoint', async () => {
    const user = userEvent.setup({ delay: null });

    server.use(
      http.get(`${API_BASE_URL}/admin/providers`, () =>
        HttpResponse.json([
          {
            api_key: '****',
            api_key_env: 'FLEETENT_MODEL_ALPHA_API_KEY',
            api_key_set: true,
            base_url: 'https://alpha.initial',
            description: 'Initial provider',
            id: 'alpha',
            model_count: 1,
            provider: 'openai',
          },
        ])
      ),
      http.get(`${API_BASE_URL}/admin/models`, () =>
        HttpResponse.json([
          {
            base_url: 'https://alpha.initial',
            description: 'Primary chat model',
            endpoint: null,
            id: 'alpha-chat',
            input_price_per_1k: null,
            max_tokens: 4096,
            model_name: 'gpt-5',
            output_price_per_1k: null,
            params: null,
            protocol: 'openai_chat',
            provider_id: 'alpha',
          },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/models/alpha-chat/connectivity-test`, () =>
        HttpResponse.json({ latency_ms: 42, model: 'gpt-5', reachable: true })
      )
    );

    renderWithProviders(<ProvidersProbe />);
    expect(await screen.findByText('provider:alpha:https://alpha.initial')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'connectivity' }));
    await waitFor(() => {
      expect(screen.getByText('true:42')).toBeInTheDocument();
    });
  });
});

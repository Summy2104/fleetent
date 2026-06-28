import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { I18nProvider } from '@/i18n';
import { ProvidersPage } from '@/features/providers/page';
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

function renderPage(): void {
  render(
    <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
      <AppQueryProvider>
        <I18nProvider>
          <ProvidersPage />
        </I18nProvider>
      </AppQueryProvider>
    </AuthProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('providers page', () => {
  it('renders providers with nested models and supports CRUD plus model connectivity tests', async () => {
    const user = userEvent.setup({ delay: null });

    let providers: ProviderRecord[] = [
      {
        api_key: 'alph…9999',
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
        input_price_per_1k: 1.5,
        max_tokens: 4096,
        model_name: 'gpt-5',
        output_price_per_1k: 3,
        params: null,
        protocol: 'openai_chat',
        provider_id: 'alpha',
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/admin/me`, () =>
        HttpResponse.json({ email: 'admin@fleetent.test', id: 'admin-1', role: 'admin' })
      ),
      http.get(`${API_BASE_URL}/admin/providers`, () => HttpResponse.json(providers)),
      http.get(`${API_BASE_URL}/admin/models`, () => HttpResponse.json(models)),
      http.post(`${API_BASE_URL}/admin/providers`, async ({ request }) => {
        const body = (await request.json()) as { base_url?: string; id: string; provider?: string; api_key?: string };
        providers = [
          ...providers,
          {
            api_key: 'beta…0001',
            api_key_env: 'FLEETENT_MODEL_BETA_API_KEY',
            api_key_set: true,
            base_url: body.base_url ?? null,
            description: null,
            id: body.id,
            model_count: 0,
            provider: body.provider ?? null,
          },
        ];
        return HttpResponse.json(providers[providers.length - 1], { status: 201 });
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
        models = models.filter((model) => model.provider_id !== 'alpha');
        return HttpResponse.json({ deleted: true, id: 'alpha' });
      }),
      http.post(`${API_BASE_URL}/admin/models`, async ({ request }) => {
        const body = (await request.json()) as {
          base_url?: string;
          endpoint?: string;
          id: string;
          model_name: string;
          protocol: string;
          provider_id: string;
        };
        models = [
          ...models,
          {
            base_url: body.base_url ?? null,
            description: null,
            endpoint: body.endpoint ?? null,
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
      }),
      http.post(`${API_BASE_URL}/admin/models/alpha-chat/connectivity-test`, () =>
        HttpResponse.json({ latency_ms: 42, model: 'gpt-5', reachable: true })
      )
    );

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Providers' })).toBeInTheDocument();
    expect(await screen.findByText('alpha')).toBeInTheDocument();
    expect(await screen.findByText('gpt-5')).toBeInTheDocument();
    expect(screen.getByText('alph…9999')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'New provider' }));
    await user.type(screen.getByLabelText('Provider ID'), 'beta');
    await user.type(screen.getByLabelText('Base URL'), 'https://beta.provider');
    await user.type(screen.getByLabelText('API Key'), 'sk-beta-secret');
    await user.click(screen.getByRole('button', { name: 'Create provider' }));
    expect(await screen.findByText('beta')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Actions for alpha' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Edit alpha' }));
    await user.clear(screen.getByLabelText('Base URL'));
    await user.type(screen.getByLabelText('Base URL'), 'https://alpha.edited');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => {
      expect(screen.getByText('https://alpha.edited')).toBeInTheDocument();
    });

    const alphaCard = screen.getByText('alpha').closest('div.rounded-lg');
    expect(alphaCard).not.toBeNull();
    const card = within(alphaCard as HTMLElement);
    await user.click(card.getByRole('button', { name: 'New model' }));
    await user.type(screen.getByLabelText('Model ID'), 'beta-chat');
    await user.type(screen.getByLabelText('Model name'), 'claude-3-7-sonnet');
    await user.click(screen.getByRole('button', { name: 'Create model' }));
    expect(await screen.findByText('claude-3-7-sonnet')).toBeInTheDocument();

    await user.click(card.getByRole('button', { name: 'Test alpha-chat connectivity' }));
    expect(await screen.findByText('Reachable in 42ms using gpt-5')).toBeInTheDocument();
  });
});

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { ProvidersPage } from '@/features/providers/page';
import { server } from '@/test/msw/server';

const API_BASE_URL = 'http://fleetent.test';

type ProviderRecord = {
  api_key: string | null;
  api_key_env: string | null;
  api_key_set: boolean;
  base_url: string;
  description: string | null;
  id: string;
  input_price_per_1k: number | string | null;
  model: string;
  output_price_per_1k: number | string | null;
  protocol: string | null;
  provider: string | null;
};

function renderPage(): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken="session-token"
    >
      <AppQueryProvider>
        <ProvidersPage />
      </AppQueryProvider>
    </AuthProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('providers page', () => {
  it('renders masked providers and supports create, edit, delete, connectivity tests, and pricing updates', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    let providers: ProviderRecord[] = [
      {
        api_key: 'alph…9999',
        api_key_env: 'FLEETENT_MODEL_ALPHA_API_KEY',
        api_key_set: true,
        base_url: 'https://alpha.initial',
        description: 'Initial provider',
        id: 'alpha',
        input_price_per_1k: '未配置',
        model: 'gpt-5.5',
        output_price_per_1k: '未配置',
        protocol: 'openai_chat',
        provider: 'openai',
      },
    ];
    let lastPricingBody: { input_price_per_1k: number | null; output_price_per_1k: number | null } | null =
      null;

    server.use(
      http.get(`${API_BASE_URL}/admin/providers`, () => HttpResponse.json(providers)),
      http.post(`${API_BASE_URL}/admin/providers`, async ({ request }) => {
        const body = (await request.json()) as {
          api_key?: string;
          base_url: string;
          description?: string;
          id: string;
          model: string;
          protocol?: string;
          provider?: string;
        };
        providers = [
          ...providers,
          {
            api_key: 'beta…0001',
            api_key_env: 'FLEETENT_MODEL_BETA_API_KEY',
            api_key_set: true,
            base_url: body.base_url,
            description: body.description ?? null,
            id: body.id,
            input_price_per_1k: '未配置',
            model: body.model,
            output_price_per_1k: '未配置',
            protocol: body.protocol ?? null,
            provider: body.provider ?? null,
          },
        ];
        return HttpResponse.json(providers[1], { status: 201 });
      }),
      http.put(`${API_BASE_URL}/admin/providers/alpha`, async ({ request }) => {
        const body = (await request.json()) as {
          api_key?: string;
          base_url?: string;
          description?: string;
          model?: string;
        };
        providers = providers.map((provider) =>
          provider.id === 'alpha'
            ? {
                ...provider,
                base_url: body.base_url ?? provider.base_url,
                description: body.description ?? provider.description,
                model: body.model ?? provider.model,
              }
            : provider
        );
        return HttpResponse.json(providers[0]);
      }),
      http.delete(`${API_BASE_URL}/admin/providers/alpha`, () => {
        providers = providers.filter((provider) => provider.id !== 'alpha');
        return HttpResponse.json({ deleted: true, id: 'alpha' });
      }),
      http.post(`${API_BASE_URL}/admin/providers/alpha/connectivity-test`, () =>
        HttpResponse.json({ latency_ms: 42, model: 'gpt-5.5', reachable: true })
      ),
      http.put(`${API_BASE_URL}/admin/providers/alpha/pricing`, async ({ request }) => {
        lastPricingBody = (await request.json()) as {
          input_price_per_1k: number | null;
          output_price_per_1k: number | null;
        };
        providers = providers.map((provider) =>
          provider.id === 'alpha'
            ? {
                ...provider,
                input_price_per_1k: lastPricingBody?.input_price_per_1k ?? provider.input_price_per_1k,
                output_price_per_1k: lastPricingBody?.output_price_per_1k ?? provider.output_price_per_1k,
              }
            : provider
        );
        return HttpResponse.json({
          id: 'alpha',
          input_price_per_1k: lastPricingBody?.input_price_per_1k ?? null,
          output_price_per_1k: lastPricingBody?.output_price_per_1k ?? null,
        });
      })
    );

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Providers' })).toBeInTheDocument();
    expect(await screen.findByText('alpha')).toBeInTheDocument();
    expect(screen.getByText('alph…9999')).toBeInTheDocument();
    expect(screen.queryByText('sk-secret-plaintext')).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Provider ID'), 'beta');
    await user.type(screen.getByLabelText('Base URL'), 'https://beta.new');
    await user.type(screen.getByLabelText('Model'), 'claude-3-7-sonnet');
    await user.type(screen.getByLabelText('API Key'), 'sk-beta-secret');
    await user.click(screen.getByRole('button', { name: 'Create provider' }));

    expect(await screen.findByText('beta')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('sk-beta-secret')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit alpha' }));
    expect(screen.getByDisplayValue('alpha')).toBeDisabled();
    await user.clear(screen.getByLabelText('Base URL'));
    await user.type(screen.getByLabelText('Base URL'), 'https://alpha.edited');
    await user.clear(screen.getByLabelText('Model'));
    await user.type(screen.getByLabelText('Model'), 'gpt-5.5-mini');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(screen.getByText('https://alpha.edited')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Test alpha connectivity' }));
    expect(await screen.findByText('Reachable in 42ms using gpt-5.5')).toBeInTheDocument();

    await user.clear(screen.getByLabelText('Input price / 1K tokens'));
    await user.type(screen.getByLabelText('Input price / 1K tokens'), '1.5');
    await user.clear(screen.getByLabelText('Output price / 1K tokens'));
    await user.type(screen.getByLabelText('Output price / 1K tokens'), '3');
    await user.click(screen.getByRole('button', { name: 'Save alpha pricing' }));

    await waitFor(() => {
      expect(lastPricingBody).toEqual({ input_price_per_1k: 1.5, output_price_per_1k: 3 });
    });
    expect(await screen.findByText('Input 1.5 / Output 3')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete alpha' }));
    await waitFor(() => {
      expect(screen.queryByText('alpha')).not.toBeInTheDocument();
    });
  });
});

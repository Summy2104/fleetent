import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import {
  useConnectivityTestMutation,
  useCreateProviderMutation,
  useDeleteProviderMutation,
  useProvidersQuery,
  useUpdatePricingMutation,
  useUpdateProviderMutation,
} from '@/features/providers/api';
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

function renderWithProviders(ui: ReactNode): void {
  render(
    <AuthProvider
      baseUrl={API_BASE_URL}
      initialToken="session-token"
    >
      <AppQueryProvider>{ui}</AppQueryProvider>
    </AuthProvider>
  );
}

function ProvidersProbe(): JSX.Element {
  const query = useProvidersQuery();
  const createProvider = useCreateProviderMutation();
  const updateProvider = useUpdateProviderMutation('alpha');
  const deleteProvider = useDeleteProviderMutation('alpha');
  const connectivityTest = useConnectivityTestMutation('alpha');
  const updatePricing = useUpdatePricingMutation('alpha');

  return (
    <section>
      <button
        onClick={() =>
          createProvider.mutate({
            api_key: 'sk-new-secret',
            base_url: 'https://alpha.new',
            id: 'beta',
            model: 'claude-3-7-sonnet',
          })
        }
        type="button"
      >
        create
      </button>
      <button
        onClick={() =>
          updateProvider.mutate({
            api_key: 'sk-rotated-secret',
            base_url: 'https://alpha.edited',
            description: 'Edited provider',
          })
        }
        type="button"
      >
        update
      </button>
      <button
        onClick={() => deleteProvider.mutate()}
        type="button"
      >
        delete
      </button>
      <button
        onClick={() => connectivityTest.mutate()}
        type="button"
      >
        connectivity
      </button>
      <button
        onClick={() =>
          updatePricing.mutate({
            input_price_per_1k: 1.5,
            output_price_per_1k: 3,
          })
        }
        type="button"
      >
        pricing
      </button>
      <ul>
        {query.data?.map((provider) => (
          <li key={provider.id}>
            {provider.id}:{provider.base_url}
          </li>
        ))}
      </ul>
      <p>{connectivityTest.data ? `${connectivityTest.data.reachable}:${connectivityTest.data.latency_ms}` : 'idle'}</p>
      <p>
        {updatePricing.data
          ? `${updatePricing.data.input_price_per_1k}/${updatePricing.data.output_price_per_1k}`
          : 'no-pricing'}
      </p>
    </section>
  );
}

describe('providers api', () => {
  it('loads providers and refreshes the list after create, update, and delete mutations', async () => {
    const user = userEvent.setup({ delay: null });
    let providers: ProviderRecord[] = [
      {
        api_key: '****',
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

    server.use(
      http.get(`${API_BASE_URL}/admin/providers`, ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Session session-token');
        return HttpResponse.json(providers);
      }),
      http.post(`${API_BASE_URL}/admin/providers`, async ({ request }) => {
        const body = (await request.json()) as {
          api_key: string;
          base_url: string;
          id: string;
          model: string;
        };
        expect(body.api_key).toBe('sk-new-secret');
        providers = [
          ...providers,
          {
            api_key: '****',
            api_key_env: 'FLEETENT_MODEL_BETA_API_KEY',
            api_key_set: true,
            base_url: body.base_url,
            description: null,
            id: body.id,
            input_price_per_1k: '未配置',
            model: body.model,
            output_price_per_1k: '未配置',
            protocol: null,
            provider: null,
          },
        ];
        return HttpResponse.json(providers[1], { status: 201 });
      }),
      http.put(`${API_BASE_URL}/admin/providers/alpha`, async ({ request }) => {
        const body = (await request.json()) as {
          api_key?: string;
          base_url?: string;
          description?: string;
        };
        expect(body.api_key).toBe('sk-rotated-secret');
        providers = providers.map((provider) =>
          provider.id === 'alpha'
            ? {
                ...provider,
                base_url: body.base_url ?? provider.base_url,
                description: body.description ?? provider.description,
              }
            : provider
        );
        return HttpResponse.json(providers[0]);
      }),
      http.delete(`${API_BASE_URL}/admin/providers/alpha`, ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Session session-token');
        providers = providers.filter((provider) => provider.id !== 'alpha');
        return HttpResponse.json({ deleted: true, id: 'alpha' });
      })
    );

    renderWithProviders(<ProvidersProbe />);
    expect(await screen.findByText('alpha:https://alpha.initial')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'create' }));
    expect(await screen.findByText('beta:https://alpha.new')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'update' }));
    await waitFor(() => {
      expect(screen.getByText('alpha:https://alpha.edited')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'delete' }));
    await waitFor(() => {
      expect(screen.queryByText('alpha:https://alpha.edited')).not.toBeInTheDocument();
    });
  });

  it('posts connectivity tests and pricing updates through the provider admin endpoints', async () => {
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
            input_price_per_1k: '未配置',
            model: 'gpt-5.5',
            output_price_per_1k: '未配置',
            protocol: 'openai_chat',
            provider: 'openai',
          },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/providers/alpha/connectivity-test`, () =>
        HttpResponse.json({ latency_ms: 42, model: 'gpt-5.5', reachable: true })
      ),
      http.put(`${API_BASE_URL}/admin/providers/alpha/pricing`, async ({ request }) => {
        const body = (await request.json()) as {
          input_price_per_1k: number;
          output_price_per_1k: number;
        };
        expect(body).toEqual({ input_price_per_1k: 1.5, output_price_per_1k: 3 });
        return HttpResponse.json(body);
      })
    );

    renderWithProviders(<ProvidersProbe />);
    expect(await screen.findByText('alpha:https://alpha.initial')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'connectivity' }));
    await waitFor(() => {
      expect(screen.getByText('true:42')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'pricing' }));
    await waitFor(() => {
      expect(screen.getByText('1.5/3')).toBeInTheDocument();
    });
  });
});

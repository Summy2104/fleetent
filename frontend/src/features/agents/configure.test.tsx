import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ModelsTab } from '@/features/agents/configure'
import { API_BASE_URL, renderAgents } from '@/features/agents/test/render'
import { server } from '@/test/msw/server'

const AGENT = 'alpha'

const MODELS = [
  {
    id: 'chat-x',
    provider_id: 'anthropic',
    protocol: 'openai_chat',
    model_name: 'claude-sonnet-4-5',
    base_url: 'https://api.anthropic.com/v1/',
    endpoint: null,
    max_tokens: 4096,
    input_price_per_1k: null,
    output_price_per_1k: null,
    params: null,
  },
  {
    id: 'chat-y',
    provider_id: 'acme',
    protocol: 'openai_chat',
    model_name: 'qwen3-32b',
    base_url: 'https://vllm.acme.internal/v1/',
    endpoint: null,
    max_tokens: 2048,
    input_price_per_1k: null,
    output_price_per_1k: null,
    params: null,
  },
  {
    id: 'rerank-x',
    provider_id: 'acme',
    protocol: 'http_rerank',
    model_name: 'bge-reranker-large',
    base_url: null,
    endpoint: 'https://rerank.acme.internal/rerank',
    max_tokens: null,
    input_price_per_1k: null,
    output_price_per_1k: null,
    params: null,
  },
  {
    id: 'embed-x',
    provider_id: 'acme',
    protocol: 'http_embedding',
    model_name: 'bge-m3',
    base_url: null,
    endpoint: 'https://embed.acme.internal/embed',
    max_tokens: null,
    input_price_per_1k: null,
    output_price_per_1k: null,
    params: null,
  },
  {
    id: 'image-x',
    provider_id: 'acme',
    protocol: 'openai_image_generation',
    model_name: 'flux-schnell',
    base_url: null,
    endpoint: 'https://image.acme.internal/v1/images/generations',
    max_tokens: null,
    input_price_per_1k: null,
    output_price_per_1k: null,
    params: null,
  },
]

type ModelOverrides = Record<string, unknown>

function mockOverview(modelOverrides: ModelOverrides = {}): { patch?: { model_overrides?: ModelOverrides } } {
  const captured: { patch?: { model_overrides?: ModelOverrides } } = {}
  server.use(
    http.get(`${API_BASE_URL}/admin/agents/${AGENT}`, () =>
      HttpResponse.json({
        agent: AGENT,
        allowed_tools: [],
        model_overrides: modelOverrides,
        status: 'enabled',
        system_prompt: 'hi',
        memory_namespace: 'default',
      })
    ),
    http.get(`${API_BASE_URL}/admin/models`, () => HttpResponse.json(MODELS)),
    http.get(`${API_BASE_URL}/admin/providers`, () => HttpResponse.json([])),
    http.get(`${API_BASE_URL}/admin/agents/${AGENT}/secrets`, () =>
      HttpResponse.json({ agent: AGENT, secrets: [] })
    ),
    http.patch(`${API_BASE_URL}/admin/agents/${AGENT}`, async ({ request }) => {
      captured.patch = (await request.json()) as { model_overrides?: ModelOverrides }
      return HttpResponse.json({ ok: true })
    })
  )
  return captured
}

afterEach(() => vi.restoreAllMocks())

describe('ModelsTab model routes', () => {
  it('renders a selector for every standard model route', async () => {
    mockOverview()
    renderAgents(<ModelsTab agentName={AGENT} canWrite />)

    // Routes already exposed before this change.
    expect(await screen.findByText('Model provider')).toBeInTheDocument()
    expect(screen.getByText('Embedding model')).toBeInTheDocument()
    expect(screen.getByText('Memory extraction model')).toBeInTheDocument()
    expect(screen.getByText('Image generation model')).toBeInTheDocument()

    // Newly exposed routes.
    expect(screen.getByText('Vision model')).toBeInTheDocument()
    expect(screen.getByText('Knowledge extraction model')).toBeInTheDocument()
    expect(screen.getByText('Rerank model')).toBeInTheDocument()
    expect(screen.getByText('Audio transcription model')).toBeInTheDocument()
    expect(screen.getByText('Audio generation model')).toBeInTheDocument()
  })

  it('renders the model tiers section with primary/fast/backup slots', async () => {
    mockOverview()
    renderAgents(<ModelsTab agentName={AGENT} canWrite />)

    expect(await screen.findByText('Model tiers')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'primary' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'fast' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'backup' })).toBeInTheDocument()
  })

  it('shows an empty-state hint for reserved audio routes with no matching model', async () => {
    mockOverview()
    renderAgents(<ModelsTab agentName={AGENT} canWrite />)

    // No registered model has an audio protocol, so the audio selectors must explain the gap.
    const hints = await screen.findAllByText(/no model supports this route yet/i)
    expect(hints).toHaveLength(2)
  })
})

type OverridesShape = { targets?: Record<string, unknown>; routes?: Record<string, unknown> }

describe('ModelsTab tiers and fallback chains', () => {
  it('assigns tiers and references them as a fallback chain on a chat route', async () => {
    const user = userEvent.setup()
    const captured = mockOverview()
    renderAgents(<ModelsTab agentName={AGENT} canWrite />)

    // Assign models to the primary and backup tiers.
    await selectOption(user, await screen.findByRole('combobox', { name: 'primary' }), /chat-x/)
    await selectOption(user, screen.getByRole('combobox', { name: 'backup' }), /chat-y/)

    // The default (chat) route now offers those tiers; pick primary, then chain backup as fallback.
    await selectOption(user, screen.getByRole('combobox', { name: 'Model provider' }), /^primary/)
    await user.click(screen.getByRole('button', { name: 'Add fallback to Model provider' }))
    const fallback = screen.getByRole('group', { name: 'Model provider · fallback 1' })
    await selectOption(user, within(fallback).getByRole('combobox'), /^backup/)

    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(captured.patch).toBeTruthy())
    const mo = captured.patch?.model_overrides as OverridesShape
    expect(mo.targets).toEqual({ primary: { model_id: 'chat-x' }, backup: { model_id: 'chat-y' } })
    expect(mo.routes?.default).toEqual([{ target: 'primary' }, { target: 'backup' }])
  })

  it('writes a per-tier temperature override into the targets block', async () => {
    const user = userEvent.setup()
    const captured = mockOverview()
    renderAgents(<ModelsTab agentName={AGENT} canWrite />)

    const primary = await screen.findByRole('group', { name: 'primary' })
    await selectOption(user, within(primary).getByRole('combobox'), /chat-x/)
    await user.click(within(primary).getByRole('button', { name: /override params/i }))
    await user.type(within(primary).getByLabelText('Temperature'), '0.5')

    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(captured.patch).toBeTruthy())
    const mo = captured.patch?.model_overrides as OverridesShape
    expect(mo.targets?.primary).toEqual({ model_id: 'chat-x', params: { temperature: 0.5 } })
  })

  it('saves a specialized route as a one-entry model chain', async () => {
    const user = userEvent.setup()
    const captured = mockOverview()
    renderAgents(<ModelsTab agentName={AGENT} canWrite />)

    await selectOption(user, await screen.findByRole('combobox', { name: 'Embedding model' }), /embed-x/)
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(captured.patch).toBeTruthy())
    const mo = captured.patch?.model_overrides as OverridesShape
    expect(mo.routes?.embedding).toEqual([{ model_id: 'embed-x' }])
  })

  it('reorders a chat route chain so fallback priority changes', async () => {
    const user = userEvent.setup()
    const captured = mockOverview({
      targets: { primary: { model_id: 'chat-x' }, backup: { model_id: 'chat-y' } },
      routes: { default: [{ target: 'primary' }, { target: 'backup' }] },
    })
    renderAgents(<ModelsTab agentName={AGENT} canWrite />)

    const fallback = await screen.findByRole('group', { name: 'Model provider · fallback 1' })
    await user.click(within(fallback).getByRole('button', { name: /move up/i }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(captured.patch).toBeTruthy())
    const mo = captured.patch?.model_overrides as OverridesShape
    expect(mo.routes?.default).toEqual([{ target: 'backup' }, { target: 'primary' }])
  })
})

async function selectOption(
  user: ReturnType<typeof userEvent.setup>,
  trigger: HTMLElement,
  optionText: string | RegExp
): Promise<void> {
  await user.click(trigger)
  await user.click(await screen.findByRole('option', { name: optionText }))
}

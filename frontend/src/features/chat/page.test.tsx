import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { ChatPage } from '@/features/chat/page'
import { I18nProvider } from '@/i18n'
import { server } from '@/test/msw/server'

const API_BASE_URL = 'http://fleetent.test'

function renderChatPage(): void {
  render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <AppQueryProvider>
          <ChatPage />
        </AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  )
}

describe('chat page', () => {
  it('streams assistant replies into the transcript and surfaces stream errors in the conversation', async () => {
    const user = userEvent.setup({ delay: null })
    const encoder = new TextEncoder()
    const tail: { release: (() => void) | null } = { release: null }

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([{ agent_name: 'alpha', provenance: 'adhoc', status: 'enabled' }])
      ),
      http.post(`${API_BASE_URL}/admin/agents/alpha/chat`, async ({ request }) => {
        const body = (await request.json()) as { message: string }
        if (body.message === 'hello') {
          const stream = new ReadableStream<Uint8Array>({
            async start(controller) {
              controller.enqueue(encoder.encode('data: {"type":"text_delta","content":"hel"}\n\n'))
              await new Promise<void>((resolve) => {
                tail.release = resolve
              })
              controller.enqueue(encoder.encode('data: {"type":"text_delta","content":"lo"}\n\n'))
              controller.enqueue(encoder.encode('data: {"type":"done","content":""}\n\n'))
              controller.close()
            },
          })
          return new Response(stream, {
            headers: {
              'content-type': 'text/event-stream',
            },
            status: 200,
          })
        }

        return new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(encoder.encode('data: {"type":"text_delta","content":"partial"}\n\n'))
              controller.enqueue(encoder.encode('data: {"type":"error","content":"tool exploded"}\n\n'))
              controller.close()
            },
          }),
          {
            headers: {
              'content-type': 'text/event-stream',
            },
            status: 200,
          }
        )
      })
    )

    renderChatPage()

    expect(await screen.findByRole('heading', { name: 'Chat Console' })).toBeInTheDocument()
    // First agent is auto-selected; the Radix Select trigger reflects the chosen name.
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Agent' })).toHaveTextContent('alpha')
    })
    expect(screen.getByText('No messages yet.')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Message'), 'hello')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(screen.getByText('hel')).toBeInTheDocument()
    })
    // While streaming, the Send button is disabled and a Stop control appears.
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled()

    tail.release?.()

    await waitFor(() => {
      expect(screen.getByText('hello')).toBeInTheDocument()
    })

    await user.clear(screen.getByLabelText('Message'))
    await user.type(screen.getByLabelText('Message'), 'fail')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(screen.getByText('tool exploded')).toBeInTheDocument()
    })

    const transcript = within(screen.getByTestId('chat-transcript'))
    expect(transcript.getByText('partial')).toBeInTheDocument()
    expect(transcript.getByText('tool exploded')).toBeInTheDocument()
  })

  it('surfaces ingress error detail for unknown and unavailable agents', async () => {
    const user = userEvent.setup({ delay: null })

    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, () =>
        HttpResponse.json([
          { agent_name: 'ghost', provenance: 'adhoc', status: 'disabled' },
          { agent_name: 'orphan', provenance: 'adhoc', status: 'enabled' },
        ])
      ),
      http.post(`${API_BASE_URL}/admin/agents/ghost/chat`, () =>
        HttpResponse.json({ detail: 'agent ghost not found' }, { status: 404 })
      ),
      http.post(`${API_BASE_URL}/admin/agents/orphan/chat`, () =>
        HttpResponse.json({ detail: "node 'local-node' service key unavailable" }, { status: 503 })
      )
    )

    renderChatPage()
    await screen.findByRole('heading', { name: 'Chat Console' })
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Agent' })).toHaveTextContent('ghost')
    })

    await user.type(screen.getByLabelText('Message'), 'hello')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Agent "ghost": agent ghost not found')).toBeInTheDocument()

    // Switch the target agent via the Radix Select.
    await user.click(screen.getByRole('combobox', { name: 'Agent' }))
    await user.click(await screen.findByRole('option', { name: 'orphan' }))
    await user.clear(screen.getByLabelText('Message'))
    await user.type(screen.getByLabelText('Message'), 'again')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(`Agent "orphan": node 'local-node' service key unavailable`)).toBeInTheDocument()
    expect(screen.getByLabelText('Message')).toBeEnabled()
  })

  it('renders loading and empty states without enabling sends prematurely', async () => {
    server.use(
      http.get(`${API_BASE_URL}/admin/agents`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 10))
        return HttpResponse.json([])
      })
    )

    renderChatPage()

    expect(screen.getByText('Loading agents…')).toBeInTheDocument()
    expect(await screen.findByText('No agents available.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })
})

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AgentRowActions } from '@/features/agents/row-actions/agent-row-actions'
import { API_BASE_URL, renderAgents } from '@/features/agents/test/render'
import { server } from '@/test/msw/server'

const AGENT = { agent_name: 'alpha', is_default: false, status: 'enabled', system_prompt: 'p' }

afterEach(() => vi.restoreAllMocks())

describe('AgentRowActions', () => {
  it('exposes only configure for viewers', async () => {
    const user = userEvent.setup()
    renderAgents(<AgentRowActions agent={AGENT} canWrite={false} onConfigure={() => {}} />)
    await user.click(screen.getByRole('button', { name: 'Actions for alpha' }))
    expect(await screen.findByRole('menuitem', { name: 'Configure' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('invokes onConfigure from the menu', async () => {
    const user = userEvent.setup()
    const onConfigure = vi.fn()
    renderAgents(<AgentRowActions agent={AGENT} canWrite onConfigure={onConfigure} />)
    await user.click(screen.getByRole('button', { name: 'Actions for alpha' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Configure' }))
    expect(onConfigure).toHaveBeenCalledWith(AGENT)
  })

  it('confirms before disabling and only fires the mutation after confirm', async () => {
    const user = userEvent.setup()
    let hits = 0
    server.use(
      http.post(`${API_BASE_URL}/admin/agents/alpha/disable`, () => {
        hits += 1
        return HttpResponse.json({})
      })
    )
    renderAgents(<AgentRowActions agent={AGENT} canWrite onConfigure={() => {}} />)

    await user.click(screen.getByRole('button', { name: 'Actions for alpha' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Disable' }))

    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Disable alpha?')
    expect(hits).toBe(0)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(hits).toBe(0)

    await user.click(screen.getByRole('button', { name: 'Actions for alpha' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Disable' }))
    await screen.findByRole('alertdialog')
    await user.click(screen.getByRole('button', { name: 'Disable' }))
    await vi.waitFor(() => expect(hits).toBe(1))
  })

  it('confirms before enabling a disabled agent', async () => {
    const user = userEvent.setup()
    let hits = 0
    server.use(
      http.post(`${API_BASE_URL}/admin/agents/alpha/enable`, () => {
        hits += 1
        return HttpResponse.json({})
      })
    )
    renderAgents(<AgentRowActions agent={{ ...AGENT, status: 'disabled' }} canWrite onConfigure={() => {}} />)

    await user.click(screen.getByRole('button', { name: 'Actions for alpha' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Enable' }))
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('Enable alpha?')
    await user.click(screen.getByRole('button', { name: 'Enable' }))
    await vi.waitFor(() => expect(hits).toBe(1))
  })

  it('confirms before archiving with the confirm header', async () => {
    const user = userEvent.setup()
    let confirmHeader: string | null = 'unset'
    server.use(
      http.post(`${API_BASE_URL}/admin/agents/alpha/archive`, ({ request }) => {
        confirmHeader = request.headers.get('X-Confirm')
        return HttpResponse.json({})
      })
    )
    renderAgents(<AgentRowActions agent={AGENT} canWrite onConfigure={() => {}} />)

    await user.click(screen.getByRole('button', { name: 'Actions for alpha' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Archive' }))
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('Archive alpha?')
    await user.click(screen.getByRole('button', { name: 'Archive' }))
    await vi.waitFor(() => expect(confirmHeader).toBe('true'))
  })

  it('confirms before setting an agent as default', async () => {
    const user = userEvent.setup()
    let hits = 0
    server.use(
      http.put(`${API_BASE_URL}/admin/agents/alpha/default`, () => {
        hits += 1
        return HttpResponse.json({})
      })
    )
    renderAgents(<AgentRowActions agent={AGENT} canWrite onConfigure={() => {}} />)

    await user.click(screen.getByRole('button', { name: 'Actions for alpha' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Set as default' }))
    await screen.findByRole('alertdialog')
    await user.click(screen.getByRole('button', { name: 'Set as default' }))
    await vi.waitFor(() => expect(hits).toBe(1))
  })
})

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AgentRowActions } from '@/features/agents/row-actions/agent-row-actions'
import { renderAgents } from '@/features/agents/test/render'

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
})

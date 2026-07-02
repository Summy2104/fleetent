import type * as React from 'react'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SkillListItem } from '@/features/skills/api'
import { SkillRowActions } from '@/features/skills/row-actions/skill-row-actions'
import { API_BASE_URL, renderSkills } from '@/features/skills/test/render'
import { server } from '@/test/msw/server'

const SKILL: SkillListItem = {
  audit_verdict: 'pass',
  description: 'helper',
  drifted_agents: [],
  enabling_agents: [],
  global_enabled: true,
  name: 'ops-guide',
  source: 'adhoc',
  status: 'active',
}

const noop = (): void => {}

function renderActions(overrides: Partial<React.ComponentProps<typeof SkillRowActions>> = {}) {
  return renderSkills(
    <SkillRowActions
      backflowCount={0}
      canWrite
      onBackflow={noop}
      onBindings={noop}
      onProposals={noop}
      onVersions={noop}
      onViewContent={noop}
      proposalCount={0}
      skill={SKILL}
      {...overrides}
    />
  )
}

afterEach(() => vi.restoreAllMocks())

describe('SkillRowActions', () => {
  it('treats disable as a destructive action requiring confirmation', async () => {
    const user = userEvent.setup()
    let hits = 0
    server.use(
      http.post(`${API_BASE_URL}/admin/skills/ops-guide/disable`, () => {
        hits += 1
        return HttpResponse.json({})
      })
    )
    renderActions({ skill: { ...SKILL, global_enabled: true } })

    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }))
    const disableItem = await screen.findByRole('menuitem', { name: 'Disable' })
    expect(disableItem).toHaveAttribute('data-variant', 'destructive')

    await user.click(disableItem)
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Disable ops-guide?')
    expect(hits).toBe(0)

    await user.click(within(dialog).getByRole('button', { name: 'Disable' }))
    await vi.waitFor(() => expect(hits).toBe(1))
  })

  it('enables directly without a confirmation dialog', async () => {
    const user = userEvent.setup()
    let hits = 0
    server.use(
      http.post(`${API_BASE_URL}/admin/skills/ops-guide/enable`, () => {
        hits += 1
        return HttpResponse.json({})
      })
    )
    renderActions({ skill: { ...SKILL, global_enabled: false } })

    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Enable' }))
    await vi.waitFor(() => expect(hits).toBe(1))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('disables the proposals and backflow items when there is nothing to show', async () => {
    const user = userEvent.setup()
    renderActions({ proposalCount: 0, backflowCount: 0 })

    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }))
    expect(await screen.findByRole('menuitem', { name: /Proposals/ })).toHaveAttribute('data-disabled')
    expect(screen.getByRole('menuitem', { name: /Backflow/ })).toHaveAttribute('data-disabled')
  })

  it('enables the proposals and backflow items when counts are present', async () => {
    const user = userEvent.setup()
    renderActions({ proposalCount: 2, backflowCount: 3 })

    await user.click(screen.getByRole('button', { name: 'Actions for ops-guide' }))
    expect(await screen.findByRole('menuitem', { name: /Proposals \(2\)/ })).not.toHaveAttribute('data-disabled')
    expect(screen.getByRole('menuitem', { name: /Backflow \(3\)/ })).not.toHaveAttribute('data-disabled')
  })
})

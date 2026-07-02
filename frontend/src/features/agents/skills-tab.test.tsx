import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SkillsTab } from '@/features/agents/skills-tab'
import { API_BASE_URL, renderAgents } from '@/features/agents/test/render'
import { server } from '@/test/msw/server'

const AGENT = 'alpha'

const SKILLS = [
  { skill_name: 'getting-started', enabled: true },
  { skill_name: 'summarizer', enabled: false },
]

function mockSkills(): void {
  server.use(http.get(`${API_BASE_URL}/admin/agents/${AGENT}/skills`, () => HttpResponse.json(SKILLS)))
}

afterEach(() => vi.restoreAllMocks())

describe('SkillsTab', () => {
  it('renders skill rows with their toggle state', async () => {
    mockSkills()
    renderAgents(<SkillsTab agentName={AGENT} canWrite />)
    expect(await screen.findByText('getting-started')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: /getting-started/i })).toBeChecked()
    expect(screen.getByRole('switch', { name: /summarizer/i })).not.toBeChecked()
  })

  it('enables a skill when its toggle is switched on', async () => {
    mockSkills()
    let payload: { skill: string; enabled: unknown } | null = null
    server.use(
      http.put(`${API_BASE_URL}/admin/agents/${AGENT}/skills/:skill`, async ({ params, request }) => {
        const body = (await request.json()) as { enabled: boolean }
        payload = { skill: params.skill as string, enabled: body.enabled }
        return HttpResponse.json({ agent: AGENT, enabled: body.enabled, skill_name: params.skill })
      })
    )
    const user = userEvent.setup()
    renderAgents(<SkillsTab agentName={AGENT} canWrite />)
    await user.click(await screen.findByRole('switch', { name: /summarizer/i }))
    await waitFor(() => expect(payload).toEqual({ skill: 'summarizer', enabled: true }))
  })

  it('disables all toggles for viewers', async () => {
    mockSkills()
    renderAgents(<SkillsTab agentName={AGENT} canWrite={false} />)
    expect(await screen.findByRole('switch', { name: /getting-started/i })).toHaveAttribute('aria-disabled', 'true')
  })
})

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderUsers } from '@/features/users/test/render'
import { ImRowActions } from './im-row-actions'

const IM_USER = {
  allowed: true,
  id: 7,
  platform: 'slack',
  platform_user_id: 'U123',
  status: 'active',
  user_email: null,
  user_id: 'u1',
  user_name: 'Ann',
}

afterEach(() => vi.restoreAllMocks())

describe('ImRowActions', () => {
  it('renders nothing for viewers', () => {
    const { container } = renderUsers(<ImRowActions canWrite={false} imUser={IM_USER} users={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('opens the block dialog from the menu', async () => {
    const user = userEvent.setup()
    renderUsers(<ImRowActions canWrite imUser={IM_USER} users={[]} />)
    await user.click(screen.getByRole('button', { name: /slack/ }))
    await user.click(await screen.findByText('Block identity'))
    expect(await screen.findByLabelText(/reason/i)).toBeInTheDocument()
  })
})

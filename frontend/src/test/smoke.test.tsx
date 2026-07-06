import { render } from '@testing-library/react'

import { App } from '@/app/App'

describe('App shell', () => {
  it('renders the login shell by default', () => {
    window.history.replaceState({}, '', '/admin/ui/')
    const view = render(<App />)

    expect(view.getByRole('heading', { name: 'Admin Login' })).toBeInTheDocument()
  })
})

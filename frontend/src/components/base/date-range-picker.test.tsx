import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { DateRangePicker } from '@/components/base/date-range-picker'

// DateRangePicker is preserved for reuse but not wired into any table; these
// tests keep the component covered. Bounds coverage lives in date-picker.test.tsx.
describe('DateRangePicker', () => {
  it('shows the placeholder when no range is selected', () => {
    render(<DateRangePicker onChange={vi.fn()} placeholder="Pick a range" triggerAriaLabel="Filter date" />)
    expect(screen.getByRole('button', { name: 'Filter date' })).toHaveTextContent('Pick a range')
  })

  it('renders the selected range with times and clears it', async () => {
    const user = userEvent.setup({ delay: null })
    const onChange = vi.fn()
    render(
      <DateRangePicker
        onChange={onChange}
        triggerAriaLabel="Filter date"
        value={{ from: '2026-06-27', to: '2026-06-28', fromTime: '09:30' }}
      />
    )

    expect(screen.getByRole('button', { name: 'Filter date' })).toHaveTextContent('2026-06-27 09:30 → 2026-06-28')

    await user.click(screen.getByRole('button', { name: 'Clear date range' }))
    expect(onChange).toHaveBeenCalledWith(undefined)
  })
})

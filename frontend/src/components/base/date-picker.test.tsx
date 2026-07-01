import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { DatePicker, dateRangeBounds } from '@/components/base/date-picker'

describe('dateRangeBounds', () => {
  it('returns undefined bounds for an empty value', () => {
    expect(dateRangeBounds(undefined)).toEqual({})
    expect(dateRangeBounds({})).toEqual({})
  })

  it('expands from/to to inclusive day bounds', () => {
    expect(dateRangeBounds({ from: '2026-06-27', to: '2026-06-28' })).toEqual({
      since: '2026-06-27T00:00:00',
      until: '2026-06-28T23:59:59.999',
    })
  })

  it('handles independently-selected ends', () => {
    expect(dateRangeBounds({ from: '2026-06-27' })).toEqual({ since: '2026-06-27T00:00:00' })
    expect(dateRangeBounds({ to: '2026-06-28' })).toEqual({ until: '2026-06-28T23:59:59.999' })
  })

  it('applies optional per-end times', () => {
    expect(dateRangeBounds({ from: '2026-06-27', fromTime: '09:30' })).toEqual({ since: '2026-06-27T09:30:00' })
    expect(dateRangeBounds({ to: '2026-06-28', toTime: '17:45' })).toEqual({ until: '2026-06-28T17:45:59.999' })
  })

  it('ignores a time with no matching date', () => {
    expect(dateRangeBounds({ fromTime: '09:30', toTime: '17:45' })).toEqual({})
  })
})

describe('DatePicker', () => {
  it('shows the placeholder when no date is selected', () => {
    render(<DatePicker onChange={vi.fn()} placeholder="Pick start" triggerAriaLabel="Filter start" />)
    expect(screen.getByRole('button', { name: 'Filter start' })).toHaveTextContent('Pick start')
  })

  it('renders the selected date/time and clears it', async () => {
    const user = userEvent.setup({ delay: null })
    const onChange = vi.fn()
    render(
      <DatePicker onChange={onChange} triggerAriaLabel="Filter start" value={{ date: '2026-06-27', time: '09:30' }} />
    )

    expect(screen.getByRole('button', { name: 'Filter start' })).toHaveTextContent('2026-06-27 09:30')

    await user.click(screen.getByRole('button', { name: 'Clear date' }))
    expect(onChange).toHaveBeenCalledWith(undefined)
  })
})

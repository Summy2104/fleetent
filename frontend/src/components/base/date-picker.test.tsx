/// <reference types="node" />
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, describe, expect, it, vi } from 'vitest'

import { DatePicker, dateRangeBounds } from '@/components/base/date-picker'

// Pin the runner to a non-UTC zone (团队在 UTC+8) so the local→UTC normalization is
// observable and the expected bounds are deterministic regardless of the host machine.
// The wall-clock ends the user picks are local; the emitted bounds must be UTC (`...Z`)
// so they compare correctly against the UTC-stored `created_at`.
const ORIGINAL_TZ = process.env.TZ
process.env.TZ = 'Asia/Shanghai'

afterAll(() => {
  process.env.TZ = ORIGINAL_TZ
})

describe('dateRangeBounds', () => {
  it('returns undefined bounds for an empty value', () => {
    expect(dateRangeBounds(undefined)).toEqual({})
    expect(dateRangeBounds({})).toEqual({})
  })

  it('expands from/to to inclusive day bounds, normalized to UTC', () => {
    // Local 2026-06-27 00:00 .. 2026-06-28 23:59:59.999 at UTC+8 → shifted back 8h.
    expect(dateRangeBounds({ from: '2026-06-27', to: '2026-06-28' })).toEqual({
      since: '2026-06-26T16:00:00.000Z',
      until: '2026-06-28T15:59:59.999Z',
    })
  })

  it('handles independently-selected ends', () => {
    expect(dateRangeBounds({ from: '2026-06-27' })).toEqual({ since: '2026-06-26T16:00:00.000Z' })
    expect(dateRangeBounds({ to: '2026-06-28' })).toEqual({ until: '2026-06-28T15:59:59.999Z' })
  })

  it('applies optional per-end times as local wall-clock, emitted in UTC', () => {
    // Local 09:30 at UTC+8 → 01:30 UTC; local 17:45 (minute-inclusive) → 09:45:59.999 UTC.
    expect(dateRangeBounds({ from: '2026-06-27', fromTime: '09:30' })).toEqual({ since: '2026-06-27T01:30:00.000Z' })
    expect(dateRangeBounds({ to: '2026-06-28', toTime: '17:45' })).toEqual({ until: '2026-06-28T09:45:59.999Z' })
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

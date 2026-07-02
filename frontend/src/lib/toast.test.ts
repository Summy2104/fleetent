import { beforeEach, describe, expect, it, vi } from 'vitest'

import { pushToast, toast } from '@/lib/toast'

const success = vi.fn()
const error = vi.fn()
const info = vi.fn()

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => success(...args),
    error: (...args: unknown[]) => error(...args),
    info: (...args: unknown[]) => info(...args),
  },
}))

beforeEach(() => {
  success.mockClear()
  error.mockClear()
  info.mockClear()
})

describe('pushToast', () => {
  it('defaults the variant to info when none is given', () => {
    pushToast({ title: 'Saved' })

    expect(info).toHaveBeenCalledWith('Saved', { description: undefined, duration: undefined })
    expect(success).not.toHaveBeenCalled()
    expect(error).not.toHaveBeenCalled()
  })

  it('dispatches to the matching sonner variant with description and duration', () => {
    pushToast({ title: 'Done', description: 'All good', variant: 'success', duration: 4000 })

    expect(success).toHaveBeenCalledWith('Done', { description: 'All good', duration: 4000 })
  })

  it('routes error variants to the error channel', () => {
    pushToast({ title: 'Nope', variant: 'error' })

    expect(error).toHaveBeenCalledWith('Nope', { description: undefined, duration: undefined })
  })
})

describe('toast helpers', () => {
  it('forwards description when provided', () => {
    toast.success('Hi', 'there')

    expect(success).toHaveBeenCalledWith('Hi', { description: 'there' })
  })

  it('omits description when not provided', () => {
    toast.info('Just a note')

    expect(info).toHaveBeenCalledWith('Just a note', { description: undefined })
  })
})

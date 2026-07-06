import { describe, expect, it } from 'vitest'

import { labelWithId } from '@/lib/labels'

describe('labelWithId', () => {
  it('renders "Name (id)" when a name is known', () => {
    expect(labelWithId('Alice', 'user-a')).toBe('Alice (user-a)')
  })

  it('falls back to the bare id when the name is missing or blank', () => {
    expect(labelWithId(null, 'user-a')).toBe('user-a')
    expect(labelWithId(undefined, 'user-a')).toBe('user-a')
    expect(labelWithId('   ', 'user-a')).toBe('user-a')
  })

  it('trims surrounding whitespace from the name', () => {
    expect(labelWithId('  Alice  ', 'user-a')).toBe('Alice (user-a)')
  })
})

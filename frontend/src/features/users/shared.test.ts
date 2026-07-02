import { describe, expect, it } from 'vitest'

import { initials, metadataValueToString, parseScopes, statusVariant } from '@/features/users/shared'

describe('parseScopes', () => {
  it('splits on commas, trims, and drops empties', () => {
    expect(parseScopes(' read, , write ,')).toEqual(['read', 'write'])
  })

  it('returns an empty list for a blank string', () => {
    expect(parseScopes('   ')).toEqual([])
  })
})

describe('initials', () => {
  it('uses the first letter of the first two words, uppercased', () => {
    expect(initials('alice bob')).toBe('AB')
  })

  it('treats hyphens and underscores as word separators', () => {
    expect(initials('ada_lovelace')).toBe('AL')
  })

  it('falls back to the first two characters for a single word', () => {
    expect(initials('bob')).toBe('BO')
  })
})

describe('statusVariant', () => {
  it('maps blocked/active to destructive/success and everything else to secondary', () => {
    expect(statusVariant('blocked')).toBe('destructive')
    expect(statusVariant('active')).toBe('success')
    expect(statusVariant('pending')).toBe('secondary')
  })
})

describe('metadataValueToString', () => {
  it('renders primitives and stringifies objects; null/undefined become empty', () => {
    expect(metadataValueToString(null)).toBe('')
    expect(metadataValueToString(undefined)).toBe('')
    expect(metadataValueToString('hi')).toBe('hi')
    expect(metadataValueToString(42)).toBe('42')
    expect(metadataValueToString(true)).toBe('true')
    expect(metadataValueToString({ a: 1 })).toBe('{"a":1}')
  })
})

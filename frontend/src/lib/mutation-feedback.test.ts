import { describe, expect, it } from 'vitest'

import { extractPayloadError } from '@/lib/mutation-feedback'

describe('extractPayloadError', () => {
  it('returns the error string when a 2xx payload carries one', () => {
    expect(extractPayloadError({ reachable: false, error: 'API error: Connection error.' })).toBe(
      'API error: Connection error.'
    )
  })

  it('returns null for a clean success payload', () => {
    expect(extractPayloadError({ reachable: true, latency_ms: 42 })).toBeNull()
    expect(extractPayloadError({ success: true, server_id: 'x', connected: true })).toBeNull()
  })

  it('ignores a blank or whitespace-only error field', () => {
    expect(extractPayloadError({ error: '' })).toBeNull()
    expect(extractPayloadError({ error: '   ' })).toBeNull()
  })

  it('ignores non-string error fields', () => {
    expect(extractPayloadError({ error: null })).toBeNull()
    expect(extractPayloadError({ error: { message: 'nope' } })).toBeNull()
  })

  it('returns null for non-object payloads', () => {
    expect(extractPayloadError(null)).toBeNull()
    expect(extractPayloadError(undefined)).toBeNull()
    expect(extractPayloadError('done')).toBeNull()
    expect(extractPayloadError(42)).toBeNull()
  })
})

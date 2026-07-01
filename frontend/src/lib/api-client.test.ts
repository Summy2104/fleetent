import { describe, expect, it } from 'vitest'

import { ApiError, describeApiError, parseResponse } from '@/lib/api-client'

describe('ApiError', () => {
  it('carries the status and body and has a descriptive message', () => {
    const err = new ApiError(404, { detail: 'nope' })
    expect(err.status).toBe(404)
    expect(err.body).toEqual({ detail: 'nope' })
    expect(err.name).toBe('ApiError')
    expect(err.message).toBe('request failed: 404')
    expect(err).toBeInstanceOf(Error)
  })
})

describe('parseResponse', () => {
  it('returns the parsed JSON for a 200', async () => {
    const res = new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
    await expect(parseResponse(res)).resolves.toEqual({ ok: true })
  })

  it('returns undefined for a 204 without touching the body', async () => {
    await expect(parseResponse(new Response(null, { status: 204 }))).resolves.toBeUndefined()
  })

  it('throws an ApiError with the parsed body for a non-2xx JSON response', async () => {
    const res = new Response(JSON.stringify({ detail: 'bad' }), {
      status: 400,
      headers: { 'content-type': 'application/json' },
    })
    await expect(parseResponse(res)).rejects.toMatchObject({ status: 400, body: { detail: 'bad' } })
  })

  it('throws an ApiError with a null body when the error response is not JSON', async () => {
    const res = new Response('boom', { status: 500 })
    await expect(parseResponse(res)).rejects.toMatchObject({ status: 500, body: null })
  })
})

describe('describeApiError', () => {
  it('uses a string detail verbatim', () => {
    expect(describeApiError(new ApiError(409, { detail: 'already exists' }))).toBe('already exists')
  })

  it('joins blocker lists onto an object detail error', () => {
    const err = new ApiError(409, { detail: { error: 'in use', agents: ['a1', 'a2'] } })
    expect(describeApiError(err)).toBe('in use: a1, a2')
  })

  it('returns just the error when the blocker list is empty', () => {
    const err = new ApiError(409, { detail: { error: 'in use', users: [] } })
    expect(describeApiError(err)).toBe('in use')
  })

  it('falls back to the status when there is no usable detail', () => {
    expect(describeApiError(new ApiError(500, null))).toBe('Request failed (500)')
    expect(describeApiError(new ApiError(500, { detail: { note: 'x' } }))).toBe('Request failed (500)')
  })

  it('reads the message off a plain Error and labels anything else unknown', () => {
    expect(describeApiError(new Error('kaboom'))).toBe('kaboom')
    expect(describeApiError('a string')).toBe('Unknown error')
  })
})

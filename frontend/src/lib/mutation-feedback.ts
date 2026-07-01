/**
 * Global mutation feedback helpers.
 *
 * A 2xx HTTP response does not always mean the operation logically succeeded:
 * connectivity / "test" endpoints (MCP server test, model connectivity test…)
 * return HTTP 200 with a populated `error` field to describe an internal
 * failure. The generic success toast must treat those as errors instead of
 * cheerfully reporting "Done".
 */

/**
 * Extract a human-readable error message from a successful mutation's payload,
 * or `null` when the payload represents a genuine success.
 *
 * Keyed on a non-empty `error` string — the shared contract across the test
 * endpoints — to avoid false positives from legitimate boolean fields such as
 * `enabled: false` or `deleted: true` on normal responses.
 */
export function extractPayloadError(data: unknown): string | null {
  if (!data || typeof data !== 'object') {
    return null
  }
  const error = (data as { error?: unknown }).error
  if (typeof error === 'string' && error.trim() !== '') {
    return error
  }
  return null
}

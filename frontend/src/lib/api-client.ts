import { useMemo } from 'react'

import { useAuthSession } from '@/app/auth'

export type AdminApiClient = {
  get: <T>(path: string) => Promise<T>
  post: <T>(path: string, body?: unknown, headers?: HeadersInit) => Promise<T>
  put: <T>(path: string, body: unknown) => Promise<T>
  patch: <T>(path: string, body: unknown) => Promise<T>
  delete: <T>(path: string, headers?: HeadersInit) => Promise<T>
}

/** Error carrying the HTTP status and parsed response body for richer feedback. */
export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, body: unknown) {
    super(`request failed: ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

// Exported for unit tests: turns a fetch Response into data, mapping non-2xx to
// ApiError (parsing the JSON body when present) and 204 to undefined.
export async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      /* non-JSON or empty body */
    }
    throw new ApiError(response.status, body)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

/** Build a human-readable message from an error (ApiError-aware). */
export function describeApiError(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | null)?.detail
    if (typeof detail === 'string') {
      return detail
    }
    if (detail && typeof detail === 'object') {
      const obj = detail as { error?: string; agents?: unknown; users?: unknown; channels?: unknown }
      const blockers = [obj.agents, obj.users, obj.channels].find((value) => Array.isArray(value)) as
        | unknown[]
        | undefined
      if (obj.error) {
        return blockers && blockers.length > 0 ? `${obj.error}: ${blockers.join(', ')}` : obj.error
      }
    }
    return `Request failed (${error.status})`
  }
  return error instanceof Error ? error.message : 'Unknown error'
}

export function useAdminApi(): AdminApiClient {
  const auth = useAuthSession()

  return useMemo(() => {
    const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
      const headers = new Headers(init?.headers)
      if (!headers.has('content-type') && init?.body) {
        headers.set('content-type', 'application/json')
      }
      if (auth.token) {
        headers.set('authorization', `Session ${auth.token}`)
      }

      const response = await fetch(`${auth.baseUrl}${path}`, {
        ...init,
        headers,
      })

      if (response.status === 401) {
        auth.clearToken()
      }

      return parseResponse<T>(response)
    }

    return {
      get: <T>(path: string) => request<T>(path),
      post: <T>(path: string, body?: unknown, extraHeaders?: HeadersInit) =>
        request<T>(path, {
          body: body === undefined ? undefined : JSON.stringify(body),
          headers: extraHeaders,
          method: 'POST',
        }),
      put: <T>(path: string, body: unknown) =>
        request<T>(path, {
          body: JSON.stringify(body),
          method: 'PUT',
        }),
      patch: <T>(path: string, body: unknown) =>
        request<T>(path, {
          body: JSON.stringify(body),
          method: 'PATCH',
        }),
      delete: <T>(path: string, extraHeaders?: HeadersInit) =>
        request<T>(path, {
          headers: extraHeaders,
          method: 'DELETE',
        }),
    }
  }, [auth])
}

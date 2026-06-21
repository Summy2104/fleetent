import { useMemo } from 'react';

import { useAuthSession } from '@/app/auth';

export type AdminApiClient = {
  get: <T>(path: string) => Promise<T>;
  post: <T>(path: string, body?: unknown, headers?: HeadersInit) => Promise<T>;
  patch: <T>(path: string, body: unknown) => Promise<T>;
  delete: <T>(path: string, headers?: HeadersInit) => Promise<T>;
};

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function useAdminApi(): AdminApiClient {
  const auth = useAuthSession();

  return useMemo(() => {
    const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
      const headers = new Headers(init?.headers);
      if (!headers.has('content-type') && init?.body) {
        headers.set('content-type', 'application/json');
      }
      if (auth.token) {
        headers.set('authorization', `Session ${auth.token}`);
      }

      const response = await fetch(`${auth.baseUrl}${path}`, {
        ...init,
        headers,
      });

      if (response.status === 401) {
        auth.clearToken();
      }

      return parseResponse<T>(response);
    };

    return {
      get: <T>(path: string) => request<T>(path),
      post: <T>(path: string, body?: unknown, extraHeaders?: HeadersInit) =>
        request<T>(path, {
          body: body === undefined ? undefined : JSON.stringify(body),
          headers: extraHeaders,
          method: 'POST',
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
    };
  }, [auth]);
}

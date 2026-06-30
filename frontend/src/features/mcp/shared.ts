import { useQuery } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export const TRANSPORTS = ['stdio', 'http', 'websocket'] as const
export const GLOBAL_SCOPE = 'global'

export type AdminMe = { email: string; id: string; role: string }

export function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

export function statusVariant(status: string): 'success' | 'secondary' | 'warning' {
  if (status === 'connected' || status === 'configured') return 'success'
  if (status === 'disabled') return 'secondary'
  return 'warning'
}

export type EnvPair = { key: string; value: string }

export const toPairs = (map?: Record<string, string>): EnvPair[] =>
  Object.entries(map ?? {}).map(([key, value]) => ({ key, value }))

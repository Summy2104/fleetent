import { useQuery } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export const ROLES = ['viewer', 'admin', 'built_in_admin']
export const IM_PLATFORMS = ['slack', 'telegram', 'whatsapp']

export type AdminMe = { email: string; id: string; role: string }

export function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

export function parseScopes(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function initials(name: string): string {
  const parts = name.replace(/[-_]/g, ' ').split(' ').filter(Boolean)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
}

export function statusVariant(status: string): 'success' | 'destructive' | 'secondary' {
  if (status === 'blocked') return 'destructive'
  if (status === 'active') return 'success'
  return 'secondary'
}

export function metadataValueToString(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value) ?? ''
}

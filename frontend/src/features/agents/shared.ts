import { useQuery } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export const AGENT_STATUSES = ['enabled', 'disabled', 'archived']

export type AdminMe = { email: string; id: string; role: string }

export function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

export function initials(name: string): string {
  const parts = name.replace(/[-_]/g, ' ').split(' ').filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

export function statusVariant(status: string): 'success' | 'warning' | 'secondary' {
  if (status === 'archived') return 'warning'
  if (status === 'disabled') return 'secondary'
  return 'success'
}

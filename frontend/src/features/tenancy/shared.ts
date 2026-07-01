import { useQuery } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'
import { cn } from '@/lib/utils'

export type AdminMe = {
  email: string
  id: string
  role: string
}

export type TenancyUser = {
  email: string | null
  id: string
  must_reset: boolean
  name: string
  role: string
  status: string
  tenant_id?: string | null
}

export const SELECT_CLASS = cn(
  'flex h-9 w-full appearance-none rounded-md border border-input bg-background/60 px-3 py-1 text-sm shadow-sm transition-colors',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50'
)

export function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

export function useTenancyUsersQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['users'], queryFn: () => api.get<TenancyUser[]>('/admin/users') })
}

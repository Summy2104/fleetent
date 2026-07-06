import { useQuery } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export type AdminMe = { email: string; id: string; role: string }
export type TeamUser = { email: string | null; id: string; name: string }

export function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

export function useTeamUsersQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['users'], queryFn: () => api.get<TeamUser[]>('/admin/users') })
}

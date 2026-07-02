import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export const SKILL_STATUSES = ['active', 'archived', 'quarantined', 'disabled']

/** Latch `active` on for `ms` then clear — used to flash a transient "done" state on a
 * button after a mutation resolves (React Query's `isSuccess` stays true indefinitely). */
export function useTransientFlag(active: boolean, ms = 2500): boolean {
  const [on, setOn] = useState(false)
  useEffect(() => {
    if (!active) return
    setOn(true)
    const id = setTimeout(() => setOn(false), ms)
    return () => clearTimeout(id)
  }, [active, ms])
  return on
}

export type AdminMe = { email: string; id: string; role: string }

export function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

export function auditVariant(verdict: string): 'success' | 'warning' | 'destructive' | 'secondary' {
  if (verdict === 'approved' || verdict === 'passed') return 'success'
  if (verdict === 'rejected') return 'destructive'
  if (verdict === 'pending') return 'warning'
  return 'secondary'
}

export function statusVariant(status: string): 'success' | 'warning' | 'secondary' {
  if (status === 'archived' || status === 'quarantined') return 'warning'
  if (status === 'disabled') return 'secondary'
  return 'success'
}

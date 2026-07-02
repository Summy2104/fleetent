import { useQuery } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export type AuditLogRow = {
  action: string
  actor_user_id: string | null
  batch_id: string | null
  created_at: string
  detail: Record<string, unknown> | null
  id: number
  target_id: string | null
  target_type: string | null
}

export type AuditLogFilters = {
  action?: string
  actor?: string
  targetId?: string
  since?: string
  until?: string
}

function buildQuery(filters: AuditLogFilters): string {
  const params = new URLSearchParams()
  if (filters.actor) params.set('actor', filters.actor)
  if (filters.action) params.set('action', filters.action)
  if (filters.targetId) params.set('target_id', filters.targetId)
  if (filters.since) params.set('since', filters.since)
  if (filters.until) params.set('until', filters.until)
  const query = params.toString()
  return query ? `?${query}` : ''
}

export function useAuditLogsQuery(filters: AuditLogFilters, enabled = true) {
  const api = useAdminApi()

  return useQuery({
    enabled,
    queryKey: ['audit-logs', filters],
    queryFn: () => api.get<AuditLogRow[]>(`/admin/audit${buildQuery(filters)}`),
  })
}

function csvCell(value: unknown): string {
  const raw = typeof value === 'string' ? value : value == null ? '' : (JSON.stringify(value) ?? '')
  return /[",\n]/.test(raw) ? `"${raw.replace(/"/g, '""')}"` : raw
}

export function auditRowsToCsv(rows: AuditLogRow[]): string {
  const headers = ['created_at', 'actor_user_id', 'action', 'target_type', 'target_id', 'detail', 'batch_id']
  const lines = rows.map((row) =>
    [row.created_at, row.actor_user_id, row.action, row.target_type, row.target_id, row.detail, row.batch_id]
      .map(csvCell)
      .join(',')
  )
  return `${headers.join(',')}\n${lines.join('\n')}\n`
}

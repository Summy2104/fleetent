import { useMemo, useState } from 'react'
import type { ColumnFiltersState } from '@tanstack/react-table'
import { Download, Search } from 'lucide-react'

import { DataTable } from '@/components/base/data-table'
import { type DateRangeValue, dateRangeBounds } from '@/components/base/date-picker'
import { Button } from '@/components/ui/button'
import { type AuditLogFilters, type AuditLogRow, auditRowsToCsv, useAuditLogsQuery } from '@/features/audit/api'
import { buildAuditColumns } from '@/features/audit/columns/audit-columns'
import { useUsersQuery } from '@/features/users/api'
import { useT } from '@/i18n'

/**
 * Map the DataTable column-filter state onto the backend audit query. Text
 * columns become exact-ish filters; the `created_at` date-range expands to
 * inclusive `since`/`until` bounds.
 */
export function auditFiltersFromColumns(columnFilters: ColumnFiltersState): AuditLogFilters {
  const filters: AuditLogFilters = {}
  for (const { id, value } of columnFilters) {
    if (id === 'created_at') {
      const { since, until } = dateRangeBounds(value as DateRangeValue | undefined)
      if (since) filters.since = since
      if (until) filters.until = until
      continue
    }
    const text = typeof value === 'string' ? value.trim() : ''
    if (!text) continue
    if (id === 'actor_user_id') filters.actor = text
    else if (id === 'action') filters.action = text
    else if (id === 'resource') filters.targetId = text
  }
  return filters
}

function downloadCsv(rows: AuditLogRow[]): void {
  const blob = new Blob([auditRowsToCsv(rows)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'audit-logs.csv'
  anchor.click()
  URL.revokeObjectURL(url)
}

export function AuditPage(): JSX.Element {
  const t = useT()
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [filters, setFilters] = useState<AuditLogFilters>({})
  const [searched, setSearched] = useState(false)
  const auditLogs = useAuditLogsQuery(filters, searched)
  const users = useUsersQuery()
  const columns = useMemo(() => buildAuditColumns({ t, users: users.data ?? [] }), [t, users.data])
  const rows = auditLogs.data ?? []

  // Commit the current column filters to the backend query on demand — audit
  // logs can be large, so we never auto-fetch on filter change.
  const search = (): void => {
    setFilters(auditFiltersFromColumns(columnFilters))
    setSearched(true)
  }

  // The toolbar right-aligns external actions and pins Reset last, so Search
  // renders at the far right, just left of Reset.
  const searchAction = (
    <Button className="h-8" onClick={search} size="sm">
      <Search className="size-4" /> {t('audit.search')}
    </Button>
  )

  const exportAction = (
    <Button disabled={rows.length === 0} onClick={() => downloadCsv(rows)} variant="secondary">
      <Download className="size-4" /> {t('audit.exportCsv')}
    </Button>
  )

  return (
    <DataTable
      actions={exportAction}
      columnFilters={columnFilters}
      columns={columns}
      data={rows}
      emptyState={
        <div className="py-12 text-center text-muted-foreground text-sm">
          {searched ? t('audit.empty') : t('audit.searchPrompt')}
        </div>
      }
      enableColumnVisibility
      getRowId={(row) => String(row.id)}
      isLoading={searched && auditLogs.isPending}
      manualFiltering
      onColumnFiltersChange={setColumnFilters}
      title={t('audit.title')}
      toolbar={searchAction}
    />
  )
}

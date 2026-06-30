import { useMemo, useState } from 'react'
import { Download, Search } from 'lucide-react'

import { DataTable } from '@/components/base/data-table'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { type AuditLogFilters, type AuditLogRow, auditRowsToCsv, useAuditLogsQuery } from '@/features/audit/api'
import { buildAuditColumns } from '@/features/audit/columns/audit-columns'
import { useT } from '@/i18n'

type FormState = {
  action: string
  actor: string
  endTime: string
  startTime: string
  target: string
}

const EMPTY_FORM: FormState = {
  action: '',
  actor: '',
  endTime: '',
  startTime: '',
  target: '',
}

function withinTimeRange(row: AuditLogRow, form: FormState): boolean {
  if (form.startTime && row.created_at < form.startTime) return false
  if (form.endTime && row.created_at > form.endTime) return false
  return true
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
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [filters, setFilters] = useState<AuditLogFilters>({})
  const [searched, setSearched] = useState(false)
  const auditLogs = useAuditLogsQuery(filters, searched)
  const columns = useMemo(() => buildAuditColumns({ t }), [t])

  const visibleRows = useMemo(
    () => (auditLogs.data ?? []).filter((row) => withinTimeRange(row, form)),
    [auditLogs.data, form]
  )

  const search = (): void => {
    setFilters({
      action: form.action.trim() || undefined,
      actor: form.actor.trim() || undefined,
      targetId: form.target.trim() || undefined,
    })
    setSearched(true)
  }

  const exportAction = (
    <Button disabled={visibleRows.length === 0} onClick={() => downloadCsv(visibleRows)} variant="secondary">
      <Download className="size-4" /> {t('audit.exportCsv')}
    </Button>
  )

  return (
    <div className="space-y-3">
      <Card className="space-y-3 px-4 py-3">
        <div className="grid gap-3 md:grid-cols-5">
          <div className="grid gap-2">
            <Label htmlFor="audit-actor">{t('audit.actor')}</Label>
            <Input
              id="audit-actor"
              onChange={(event) => setForm((current) => ({ ...current, actor: event.target.value }))}
              value={form.actor}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="audit-action">{t('audit.action')}</Label>
            <Input
              id="audit-action"
              onChange={(event) => setForm((current) => ({ ...current, action: event.target.value }))}
              value={form.action}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="audit-target">{t('audit.target')}</Label>
            <Input
              id="audit-target"
              onChange={(event) => setForm((current) => ({ ...current, target: event.target.value }))}
              value={form.target}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="audit-start">{t('audit.startTime')}</Label>
            <Input
              id="audit-start"
              onChange={(event) => setForm((current) => ({ ...current, startTime: event.target.value }))}
              value={form.startTime}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="audit-end">{t('audit.endTime')}</Label>
            <Input
              id="audit-end"
              onChange={(event) => setForm((current) => ({ ...current, endTime: event.target.value }))}
              value={form.endTime}
            />
          </div>
        </div>
        <Button onClick={search}>
          <Search className="size-4" /> {t('audit.search')}
        </Button>
      </Card>

      <DataTable
        actions={exportAction}
        columns={columns}
        data={visibleRows}
        emptyState={
          <div className="py-12 text-center text-muted-foreground text-sm">
            {searched ? t('audit.empty') : t('audit.searchPrompt')}
          </div>
        }
        enableColumnVisibility
        getRowId={(row) => String(row.id)}
        isLoading={searched && auditLogs.isPending}
        title={t('audit.title')}
      />
    </div>
  )
}

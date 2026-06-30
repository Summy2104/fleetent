import { useMemo, useState } from 'react'
import { Download, Search } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { type AuditLogFilters, type AuditLogRow, auditRowsToCsv, useAuditLogsQuery } from '@/features/audit/api'
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-xl tracking-tight">{t('audit.title')}</h2>
          <Badge variant="secondary">{visibleRows.length}</Badge>
        </div>
        <Button disabled={visibleRows.length === 0} onClick={() => downloadCsv(visibleRows)} variant="secondary">
          <Download className="size-4" /> {t('audit.exportCsv')}
        </Button>
      </div>

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

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase">
                {t('audit.when')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase">
                {t('audit.actor')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase">
                {t('audit.action')}
              </th>
              <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground text-xs uppercase">
                {t('audit.resource')}
              </th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr className="border-border border-b last:border-0" key={row.id}>
                <td className="px-4 py-3 font-mono text-sm">{row.created_at}</td>
                <td className="px-4 py-3 text-sm">{row.actor_user_id ?? '-'}</td>
                <td className="px-4 py-3 text-sm">{row.action}</td>
                <td className="px-4 py-3 text-sm">
                  {row.target_type ?? '-'}:{row.target_id ?? '-'}
                </td>
              </tr>
            ))}
            {searched && !auditLogs.isPending && visibleRows.length === 0 ? (
              <tr>
                <td className="px-4 py-12 text-center text-muted-foreground text-sm" colSpan={4}>
                  {t('audit.empty')}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  )
}

import { useMemo, useState } from 'react';
import { Download, Search } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useT } from '@/i18n';
import { auditRowsToCsv, type AuditLogFilters, type AuditLogRow, useAuditLogsQuery } from '@/features/audit/api';

type FormState = {
  action: string;
  actor: string;
  endTime: string;
  startTime: string;
  target: string;
};

const EMPTY_FORM: FormState = {
  action: '',
  actor: '',
  endTime: '',
  startTime: '',
  target: '',
};

function withinTimeRange(row: AuditLogRow, form: FormState): boolean {
  if (form.startTime && row.created_at < form.startTime) return false;
  if (form.endTime && row.created_at > form.endTime) return false;
  return true;
}

function downloadCsv(rows: AuditLogRow[]): void {
  const blob = new Blob([auditRowsToCsv(rows)], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'audit-logs.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

export function AuditPage(): JSX.Element {
  const t = useT();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [filters, setFilters] = useState<AuditLogFilters>({});
  const [searched, setSearched] = useState(false);
  const auditLogs = useAuditLogsQuery(filters, searched);

  const visibleRows = useMemo(
    () => (auditLogs.data ?? []).filter((row) => withinTimeRange(row, form)),
    [auditLogs.data, form]
  );

  const search = (): void => {
    setFilters({
      action: form.action.trim() || undefined,
      actor: form.actor.trim() || undefined,
      targetId: form.target.trim() || undefined,
    });
    setSearched(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">{t('audit.title')}</h2>
          <Badge variant="secondary">{visibleRows.length}</Badge>
        </div>
        <Button
          variant="secondary"
          disabled={visibleRows.length === 0}
          onClick={() => downloadCsv(visibleRows)}
        >
          <Download className="size-4" /> {t('audit.exportCsv')}
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-5">
        <div className="grid gap-2">
          <Label htmlFor="audit-actor">{t('audit.actor')}</Label>
          <Input
            id="audit-actor"
            value={form.actor}
            onChange={(event) => setForm((current) => ({ ...current, actor: event.target.value }))}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="audit-action">{t('audit.action')}</Label>
          <Input
            id="audit-action"
            value={form.action}
            onChange={(event) => setForm((current) => ({ ...current, action: event.target.value }))}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="audit-target">{t('audit.target')}</Label>
          <Input
            id="audit-target"
            value={form.target}
            onChange={(event) => setForm((current) => ({ ...current, target: event.target.value }))}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="audit-start">{t('audit.startTime')}</Label>
          <Input
            id="audit-start"
            value={form.startTime}
            onChange={(event) => setForm((current) => ({ ...current, startTime: event.target.value }))}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="audit-end">{t('audit.endTime')}</Label>
          <Input
            id="audit-end"
            value={form.endTime}
            onChange={(event) => setForm((current) => ({ ...current, endTime: event.target.value }))}
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
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-muted-foreground">
                {t('audit.when')}
              </th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-muted-foreground">
                {t('audit.actor')}
              </th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-muted-foreground">
                {t('audit.action')}
              </th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-muted-foreground">
                {t('audit.resource')}
              </th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={row.id} className="border-b border-border last:border-0">
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
                <td colSpan={4} className="px-4 py-12 text-center text-sm text-muted-foreground">
                  {t('audit.empty')}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

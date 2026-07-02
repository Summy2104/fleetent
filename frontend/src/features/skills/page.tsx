import type { ReactNode } from 'react'
import { GitBranch, Lock, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  type SkillGitStatus,
  useReloadSkillsMutation,
  useSkillGitStatusQuery,
  useTriggerSkillGitSyncMutation,
} from '@/features/skills/api'
import { useAdminMeQuery, useTransientFlag } from '@/features/skills/shared'
import { SkillsTable } from '@/features/skills/skills-table'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'

// ─────────────────────────── GitOps read-only banner + sync status ───────────────────────────

function GitopsBanner(): JSX.Element {
  const t = useT()
  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-300/60 bg-amber-50 px-4 py-3 text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-200">
      <Lock className="mt-0.5 size-4 shrink-0" />
      <div className="space-y-0.5">
        <p className="font-semibold text-sm">{t('skills.gitopsBannerTitle')}</p>
        <p className="text-sm">{t('skills.gitopsBannerBody')}</p>
      </div>
    </div>
  )
}

/** Render a server ISO timestamp (UTC) in the viewer's local time; fall back to the raw
 * string if it doesn't parse, so a bad value is still shown rather than silently dropped. */
function formatLocalTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function SyncField({ label, mono, children }: { label: string; mono?: boolean; children: ReactNode }): JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-muted-foreground text-xs uppercase tracking-wide">{label}</dt>
      <dd className={cn('truncate text-foreground', mono && 'font-mono text-xs')}>{children}</dd>
    </div>
  )
}

function GitSyncStatusCard({ status, canWrite }: { status: SkillGitStatus; canWrite: boolean }): JSX.Element {
  const t = useT()
  const sync = useTriggerSkillGitSyncMutation()
  const synced = useTransientFlag(sync.isSuccess)
  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <GitBranch className="size-4 text-muted-foreground" />
          <h3 className="font-semibold text-foreground text-sm">{t('skills.gitSyncTitle')}</h3>
        </div>
        {canWrite ? (
          <Button disabled={sync.isPending} onClick={() => void sync.mutateAsync()} size="sm" variant="outline">
            <RefreshCw className={cn('size-4', sync.isPending && 'animate-spin')} />
            {sync.isPending ? t('skills.gitSyncing') : synced ? t('skills.gitSynced') : t('skills.gitSyncNow')}
          </Button>
        ) : null}
      </div>
      <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
        {status.provider ? <SyncField label={t('skills.gitSyncProvider')}>{status.provider}</SyncField> : null}
        {status.remote_url ? (
          <SyncField label={t('skills.gitSyncRemote')} mono>
            {status.remote_url}
          </SyncField>
        ) : null}
        {status.branch ? <SyncField label={t('skills.gitSyncBranch')}>{status.branch}</SyncField> : null}
        <SyncField label={t('skills.gitSyncLastCommit')} mono>
          {status.last_synced_commit ? status.last_synced_commit.slice(0, 10) : t('skills.gitSyncNever')}
        </SyncField>
        {status.last_sync_at ? (
          <SyncField label={t('skills.gitSyncLastAt')}>{formatLocalTime(status.last_sync_at)}</SyncField>
        ) : null}
      </dl>
      {status.last_sync_error ? (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-destructive text-sm">
          {t('skills.gitSyncError')}: {status.last_sync_error}
        </p>
      ) : null}
    </div>
  )
}

export function SkillsPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const reload = useReloadSkillsMutation()
  const gitStatus = useSkillGitStatusQuery()
  const gitopsEnabled = gitStatus.data?.enabled ?? false

  const canWrite = me.data?.role !== 'viewer'

  // In gitops mode the git sync status card owns refresh ("Sync now" reloads the index as
  // part of the sync), so the standalone "Reload index" action is redundant — hide it.
  const actions =
    canWrite && !gitopsEnabled ? (
      <Button onClick={() => void reload.mutateAsync()} variant="outline">
        <RefreshCw className="size-4" /> {t('skills.reloadIndex')}
      </Button>
    ) : undefined

  return (
    <div className="space-y-6">
      {gitopsEnabled ? <GitopsBanner /> : null}
      {gitopsEnabled && gitStatus.data ? <GitSyncStatusCard canWrite={canWrite} status={gitStatus.data} /> : null}
      <SkillsTable actions={actions} canWrite={canWrite} gitopsEnabled={gitopsEnabled} title={t('skills.title')} />
    </div>
  )
}

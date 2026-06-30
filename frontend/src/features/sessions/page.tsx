import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Ban, Eraser, LogIn, LogOut, MessageSquarePlus, MoreVertical, RotateCcw, Search } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import { SimpleSelect } from '@/components/base/simple-select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  type SessionListItem,
  type SessionsFilter,
  useBulkSessionMutation,
  useClearSessionMutation,
  useForceEndSessionMutation,
  useInjectSessionMutation,
  useReleaseSessionMutation,
  useResetSessionMutation,
  useSessionDetailQuery,
  useSessionsQuery,
  useTakeoverSessionMutation,
} from '@/features/sessions/api'
import { useT } from '@/i18n'
import { useAdminApi } from '@/lib/api-client'
import { cn } from '@/lib/utils'

type AdminMe = {
  id: string
  email: string
  role: string
  must_reset?: boolean
}

function useAdminMeQuery() {
  const api = useAdminApi()

  return useQuery({
    queryKey: ['admin-me'],
    queryFn: () => api.get<AdminMe>('/admin/me'),
  })
}

function statusVariant(status: string): 'success' | 'warning' | 'secondary' | 'outline' {
  if (status === 'active') return 'success'
  if (status === 'idle') return 'warning'
  if (status === 'ended') return 'secondary'
  return 'outline'
}

// ─────────────────────────── Session actions ───────────────────────────

function SessionActions({ canWrite, session }: { canWrite: boolean; session: SessionListItem }): JSX.Element | null {
  const t = useT()
  const takeover = useTakeoverSessionMutation(session.session_id)
  const release = useReleaseSessionMutation(session.session_id)
  const inject = useInjectSessionMutation(session.session_id)
  const reset = useResetSessionMutation(session.session_id)
  const clear = useClearSessionMutation(session.session_id)
  const forceEnd = useForceEndSessionMutation(session.session_id)

  const [confirmReset, setConfirmReset] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const [confirmForceEnd, setConfirmForceEnd] = useState(false)
  const [resetKeepTurns, setResetKeepTurns] = useState('2')

  if (!canWrite) {
    return null
  }

  const runInject = async (): Promise<void> => {
    const content = window.prompt(t('sessions.injectPrompt'))
    if (!content) {
      return
    }
    await inject.mutateAsync({ content, role: 'human_agent' })
  }

  const runReset = async (): Promise<void> => {
    const keepTurns = Number.parseInt(resetKeepTurns, 10)
    if (Number.isNaN(keepTurns)) {
      return
    }
    await reset.mutateAsync({ keepTurns })
    setConfirmReset(false)
  }

  const runClear = async (): Promise<void> => {
    await clear.mutateAsync()
    setConfirmClear(false)
  }

  const runForceEnd = async (): Promise<void> => {
    await forceEnd.mutateAsync()
    setConfirmForceEnd(false)
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button aria-label={t('sessions.actionsFor', { id: session.session_id })} size="icon" variant="ghost">
              <MoreVertical className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => void takeover.mutateAsync()}>
            <LogIn /> {t('sessions.takeOver')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void release.mutateAsync()}>
            <LogOut /> {t('sessions.release')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void runInject()}>
            <MessageSquarePlus /> {t('sessions.inject')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setConfirmReset(true)}>
            <RotateCcw /> {t('sessions.reset')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setConfirmClear(true)} variant="destructive">
            <Eraser /> {t('sessions.clearTranscript')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setConfirmForceEnd(true)} variant="destructive">
            <Ban /> {t('sessions.forceEnd')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog onOpenChange={setConfirmReset} open={confirmReset}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('sessions.resetTitle', { id: session.session_id })}</AlertDialogTitle>
            <AlertDialogDescription>{t('sessions.resetDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="grid gap-2">
            <Label htmlFor={`keep-turns-${session.session_id}`}>{t('sessions.keepTurns')}</Label>
            <Input
              id={`keep-turns-${session.session_id}`}
              min={0}
              onChange={(event) => setResetKeepTurns(event.target.value)}
              type="number"
              value={resetKeepTurns}
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('sessions.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runReset()}>{t('sessions.reset')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog onOpenChange={setConfirmClear} open={confirmClear}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('sessions.clearTitle', { id: session.session_id })}</AlertDialogTitle>
            <AlertDialogDescription>{t('sessions.clearDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('sessions.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runClear()}>{t('sessions.clear')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog onOpenChange={setConfirmForceEnd} open={confirmForceEnd}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('sessions.forceEndTitle', { id: session.session_id })}</AlertDialogTitle>
            <AlertDialogDescription>{t('sessions.forceEndDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('sessions.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runForceEnd()}>{t('sessions.forceEnd')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

// ─────────────────────────── Session row ───────────────────────────

function SessionRow({
  session,
  isAdmin,
  selected,
  picked,
  onClick,
  onTogglePicked,
}: {
  session: SessionListItem
  isAdmin: boolean
  selected: boolean
  picked: boolean
  onClick: () => void
  onTogglePicked: () => void
}): JSX.Element {
  const t = useT()
  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-lg border px-4 py-3 transition-colors',
        selected ? 'border-primary/40 bg-primary/[0.04]' : 'border-border bg-card hover:bg-accent/40'
      )}
    >
      {isAdmin ? (
        <input
          aria-label={t('sessions.selectSession', { id: session.session_id })}
          checked={picked}
          className="size-4 shrink-0 accent-primary"
          onChange={onTogglePicked}
          type="checkbox"
        />
      ) : null}

      <button className="flex min-w-0 flex-1 flex-col gap-1 text-left" onClick={onClick} type="button">
        <span className="flex items-center gap-2">
          <span className="truncate font-medium font-mono text-foreground text-sm">{session.session_id}</span>
          <Badge variant={statusVariant(session.status)}>{session.status}</Badge>
        </span>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-muted-foreground text-xs">
          <span>{session.origin}</span>
          <span>·</span>
          <span>{session.agent_name ?? '—'}</span>
          {session.user_id ? (
            <>
              <span>·</span>
              <span>{session.user_id}</span>
            </>
          ) : null}
        </span>
      </button>

      <SessionActions canWrite={isAdmin} session={session} />
    </div>
  )
}

// ─────────────────────────── Detail panel ───────────────────────────

function SessionDetailPanel({ sessionId }: { sessionId: string | null }): JSX.Element {
  const t = useT()
  const detail = useSessionDetailQuery(sessionId)
  const meta = detail.data?.meta

  return (
    <Card className="lg:sticky lg:top-24">
      <CardHeader>
        <CardTitle>{t('sessions.detailTitle')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {meta ? (
          <>
            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground text-xs">{t('sessions.sessionId')}</dt>
                <dd className="break-all font-mono text-foreground">{meta.session_id}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">{t('sessions.statusLabel')}</dt>
                <dd>
                  <Badge variant={statusVariant(meta.status)}>{meta.status}</Badge>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">{t('sessions.origin')}</dt>
                <dd className="text-foreground">{meta.origin}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">{t('sessions.agent')}</dt>
                <dd className="text-foreground">{meta.agent_name ?? '—'}</dd>
              </div>
            </dl>

            <Separator />

            <div className="space-y-3">
              <h3 className="font-semibold text-foreground text-sm">{t('sessions.transcript')}</h3>
              {detail.data?.transcript.length ? (
                detail.data.transcript.map((entry, index) => (
                  <article
                    className="rounded-lg border border-border bg-secondary/30 p-4"
                    key={`${entry.role}-${index}`}
                  >
                    <p className="font-semibold text-[10px] text-muted-foreground uppercase tracking-[0.2em]">
                      {entry.role}
                    </p>
                    <p className="mt-2 whitespace-pre-wrap break-words text-foreground text-sm">{entry.content}</p>
                  </article>
                ))
              ) : (
                <p className="text-muted-foreground text-sm">{t('sessions.noTranscriptEntries')}</p>
              )}
            </div>
          </>
        ) : (
          <p className="text-muted-foreground text-sm">{t('sessions.selectSessionToInspect')}</p>
        )}
      </CardContent>
    </Card>
  )
}

// ─────────────────────────── Page ───────────────────────────

export function SessionsPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const [filters, setFilters] = useState<SessionsFilter>({})
  const [draftStatus, setDraftStatus] = useState('')
  const [draftUserId, setDraftUserId] = useState('')
  const [draftAgentName, setDraftAgentName] = useState('')
  const [search, setSearch] = useState('')
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [pickedSessionIds, setPickedSessionIds] = useState<string[]>([])
  const [confirmBulk, setConfirmBulk] = useState(false)

  const sessions = useSessionsQuery(filters)
  const bulk = useBulkSessionMutation()

  const isAdmin = me.data?.role !== 'viewer'
  const visibleSessions = (sessions.data ?? []).filter((session) => {
    const query = search.trim().toLowerCase()
    if (!query) {
      return true
    }
    return [session.session_id, session.agent_name, session.origin, session.user_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query))
  })

  useEffect(() => {
    if (!sessions.data?.length) {
      setSelectedSessionId(null)
      setPickedSessionIds([])
      return
    }

    const selectedStillExists = sessions.data.some((session) => session.session_id === selectedSessionId)
    if (!selectedStillExists) {
      setSelectedSessionId(sessions.data[0].session_id)
    }

    setPickedSessionIds((current) =>
      current.filter((sessionId) => sessions.data?.some((session) => session.session_id === sessionId))
    )
  }, [selectedSessionId, sessions.data])

  const togglePicked = (sessionId: string): void => {
    setPickedSessionIds((current) =>
      current.includes(sessionId) ? current.filter((item) => item !== sessionId) : [...current, sessionId]
    )
  }

  const applyFilters = (): void => {
    setFilters({
      agentName: draftAgentName || undefined,
      status: draftStatus || undefined,
      userId: draftUserId || undefined,
    })
  }

  const runBulkClear = async (): Promise<void> => {
    if (!pickedSessionIds.length) {
      return
    }
    await bulk.mutateAsync({ action: 'clear', sessionIds: pickedSessionIds })
    setConfirmBulk(false)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-xl tracking-tight">{t('sessions.title')}</h2>
          <Badge variant="secondary">{sessions.data?.length ?? 0}</Badge>
          {!isAdmin ? <Badge variant="outline">{t('sessions.readOnly')}</Badge> : null}
        </div>
        {isAdmin && pickedSessionIds.length ? (
          <Button onClick={() => setConfirmBulk(true)} variant="destructive">
            <Eraser className="size-4" /> {t('sessions.bulkClear', { count: pickedSessionIds.length })}
          </Button>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Search className="size-4 text-primary" /> {t('sessions.filters')}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t('sessions.searchPlaceholder')}
                value={search}
              />
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div className="grid gap-2">
                  <Label className="text-muted-foreground text-xs">{t('sessions.statusLabel')}</Label>
                  <SimpleSelect
                    onValueChange={(value) => setDraftStatus(!value || value === 'all' ? '' : value)}
                    options={[
                      { value: 'all', label: t('sessions.allStatuses') },
                      { value: 'active', label: 'active' },
                      { value: 'idle', label: 'idle' },
                      { value: 'ended', label: 'ended' },
                    ]}
                    value={draftStatus || 'all'}
                  />
                </div>
                <div className="grid gap-2">
                  <Label className="text-muted-foreground text-xs">{t('sessions.userId')}</Label>
                  <Input onChange={(event) => setDraftUserId(event.target.value)} value={draftUserId} />
                </div>
                <div className="grid gap-2">
                  <Label className="text-muted-foreground text-xs">{t('sessions.agentName')}</Label>
                  <Input onChange={(event) => setDraftAgentName(event.target.value)} value={draftAgentName} />
                </div>
              </div>
              <Button onClick={applyFilters} variant="outline">
                {t('sessions.applyFilters')}
              </Button>
            </CardContent>
          </Card>

          <div className="space-y-2">
            {visibleSessions.map((session) => (
              <SessionRow
                isAdmin={isAdmin}
                key={session.session_id}
                onClick={() => setSelectedSessionId(session.session_id)}
                onTogglePicked={() => togglePicked(session.session_id)}
                picked={pickedSessionIds.includes(session.session_id)}
                selected={selectedSessionId === session.session_id}
                session={session}
              />
            ))}
            {visibleSessions.length === 0 ? (
              <div className="rounded-lg border border-border border-dashed py-12 text-center text-muted-foreground text-sm">
                {t('sessions.noSessions')}
              </div>
            ) : null}
          </div>
        </div>

        <SessionDetailPanel sessionId={selectedSessionId} />
      </div>

      <AlertDialog onOpenChange={setConfirmBulk} open={confirmBulk}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('sessions.bulkClearTitle', { count: pickedSessionIds.length })}</AlertDialogTitle>
            <AlertDialogDescription>{t('sessions.bulkClearDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('sessions.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runBulkClear()}>{t('sessions.bulkClearAction')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

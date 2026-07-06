import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Badge } from '@/components/base/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { useUpdateUserMutation } from '@/features/users/api'
import { useT } from '@/i18n'
import { useAdminApi } from '@/lib/api-client'

type AdminMe = { email: string | null; id: string; role: string; must_reset?: boolean }

function useMe() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

// POST /admin/change-password — sets a new password and clears must_reset.
export function useChangePasswordMutation() {
  const api = useAdminApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (newPassword: string) => api.post('/admin/change-password', { new_password: newPassword }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-me'] })
    },
  })
}

// Shared new-password + confirm fields with client-side validation. Reused by the
// profile page and the first-login (must_reset) gate.
export function ChangePasswordFields({
  submitLabel,
  onDone,
}: {
  submitLabel: string
  onDone?: () => void
}): JSX.Element {
  const t = useT()
  const change = useChangePasswordMutation()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async (): Promise<void> => {
    if (!password) {
      setError(t('profile.errEnterPassword'))
      return
    }
    if (password !== confirm) {
      setError(t('profile.errPasswordMismatch'))
      return
    }
    setError(null)
    await change.mutateAsync(password)
    setPassword('')
    setConfirm('')
    onDone?.()
  }

  return (
    <form
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
    >
      <div className="grid gap-2">
        <Label htmlFor="cp-new">{t('profile.newPassword')}</Label>
        <Input
          autoComplete="new-password"
          id="cp-new"
          onChange={(event) => setPassword(event.target.value)}
          type="password"
          value={password}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cp-confirm">{t('profile.confirmNewPassword')}</Label>
        <Input
          autoComplete="new-password"
          id="cp-confirm"
          onChange={(event) => setConfirm(event.target.value)}
          type="password"
          value={confirm}
        />
      </div>
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      <Button className="justify-self-start" disabled={!password || !confirm || change.isPending} type="submit">
        {submitLabel}
      </Button>
    </form>
  )
}

function initials(value: string): string {
  return value.slice(0, 2).toUpperCase()
}

// ─────────────────────────── User center ───────────────────────────

export function ProfilePage(): JSX.Element {
  const t = useT()
  const me = useMe()
  const updateUser = useUpdateUserMutation(me.data?.id ?? '')

  const canEditProfile = me.data?.role !== 'viewer'
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')

  useEffect(() => {
    if (me.data) {
      setName('')
      setEmail(me.data.email ?? '')
    }
  }, [me.data])

  const displayName = me.data?.email ?? me.data?.role ?? 'admin'

  return (
    <div className="max-w-2xl space-y-8">
      <div className="flex items-center gap-4">
        <span className="grid size-12 place-items-center rounded-full bg-secondary font-semibold text-foreground text-sm">
          {initials(displayName)}
        </span>
        <div>
          <h2 className="font-semibold text-xl tracking-tight">{t('profile.account')}</h2>
          <p className="text-muted-foreground text-sm">{t('profile.subtitle')}</p>
        </div>
      </div>

      <Separator />

      <section className="space-y-4">
        <h3 className="font-semibold text-base text-foreground">{t('profile.profile')}</h3>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="outline">role: {me.data?.role ?? '—'}</Badge>
          <span className="font-mono text-muted-foreground text-xs">id: {me.data?.id ?? '—'}</span>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="profile-email">{t('profile.email')}</Label>
          <Input
            disabled={!canEditProfile}
            id="profile-email"
            onChange={(event) => setEmail(event.target.value)}
            value={email}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="profile-name">{t('profile.username')}</Label>
          <Input
            disabled={!canEditProfile}
            id="profile-name"
            onChange={(event) => setName(event.target.value)}
            placeholder={me.data?.role ?? ''}
            value={name}
          />
        </div>
        {canEditProfile ? (
          <Button
            className="justify-self-start"
            disabled={updateUser.isPending}
            onClick={() =>
              void updateUser.mutateAsync({
                email,
                ...(name.trim() ? { name: name.trim() } : {}),
              })
            }
          >
            {t('profile.save')}
          </Button>
        ) : (
          <p className="text-muted-foreground text-sm">{t('profile.viewerCantEdit')}</p>
        )}
      </section>

      <Separator />

      <section className="space-y-4">
        <h3 className="font-semibold text-base text-foreground">{t('profile.changePassword')}</h3>
        <ChangePasswordFields submitLabel={t('profile.savePassword')} />
      </section>
    </div>
  )
}

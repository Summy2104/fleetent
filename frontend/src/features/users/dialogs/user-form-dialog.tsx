import { useEffect, useState } from 'react'

import { SimpleSelect } from '@/components/base/simple-select'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type { UserListItem } from '@/features/users/api'
import { canSubmitUser, initialUserForm, type UserFormState } from '@/features/users/dialogs/user-form-dialog-logic'
import { ROLES } from '@/features/users/shared'
import { useT } from '@/i18n'

export type { UserFormState }

export function UserFormDialog({
  mode,
  open,
  onOpenChange,
  user,
  busy,
  onSubmit,
}: {
  mode: 'create' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  user: UserListItem | null
  busy: boolean
  onSubmit: (state: UserFormState) => Promise<void>
}): JSX.Element {
  const t = useT()
  const [state, setState] = useState<UserFormState>(() => initialUserForm(mode, user))

  useEffect(() => {
    if (!open) return
    setState(initialUserForm(mode, user))
  }, [open, mode, user])

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {mode === 'create'
              ? t('users.createUser')
              : t('users.editUser', { name: user?.name ?? t('users.userFallback') })}
          </DialogTitle>
          <DialogDescription>
            {mode === 'create' ? t('users.createUserDescription') : t('users.editUserDescription')}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="user-name">{t('users.userName')}</Label>
            <Input
              id="user-name"
              onChange={(event) => setState((current) => ({ ...current, name: event.target.value }))}
              value={state.name}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="user-email">{t('users.email')}</Label>
            <Input
              id="user-email"
              onChange={(event) => setState((current) => ({ ...current, email: event.target.value }))}
              value={state.email}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="user-role">{t('users.role')}</Label>
            <SimpleSelect
              onValueChange={(value) => setState((current) => ({ ...current, role: value ?? '' }))}
              options={ROLES.map((role) => ({ value: role, label: role }))}
              triggerAriaLabel={t('users.role')}
              triggerId="user-role"
              value={state.role}
            />
          </div>
          <div className="flex items-center justify-between gap-3 font-medium text-sm">
            <Label htmlFor="user-must-reset">{t('users.mustResetPassword')}</Label>
            <Switch
              checked={state.mustReset}
              id="user-must-reset"
              onCheckedChange={(checked) => setState((current) => ({ ...current, mustReset: checked }))}
            />
          </div>
          {mode === 'create' ? (
            <div className="grid gap-2">
              <Label htmlFor="user-password">{t('users.password')}</Label>
              <Input
                id="user-password"
                onChange={(event) => setState((current) => ({ ...current, password: event.target.value }))}
                type="password"
                value={state.password}
              />
            </div>
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="user-reset-password">{t('users.resetPassword')}</Label>
              <Input
                id="user-reset-password"
                onChange={(event) => setState((current) => ({ ...current, resetPassword: event.target.value }))}
                type="password"
                value={state.resetPassword}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button disabled={busy || !canSubmitUser(mode, state)} onClick={() => void onSubmit(state)}>
            {mode === 'create' ? t('users.createUser') : t('users.saveChanges')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

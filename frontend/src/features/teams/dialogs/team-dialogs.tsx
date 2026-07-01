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
import type { TeamUser } from '@/features/teams/shared'
import {
  type TeamListItem,
  useCreateTeamMutation,
  useSetApproverMutation,
  useTenantsQuery,
} from '@/features/tenancy/api'
import { useT } from '@/i18n'

const APPROVER_NONE = '__none__'

export function CreateTeamDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const create = useCreateTeamMutation()
  const tenants = useTenantsQuery()
  const [name, setName] = useState('')
  const [tenantId, setTenantId] = useState<string | null>('')

  useEffect(() => {
    if (open && !tenantId && tenants.data?.length) {
      setTenantId(tenants.data[0].id)
    }
  }, [open, tenantId, tenants.data])

  const submit = async (): Promise<void> => {
    await create.mutateAsync({ name: name.trim(), tenant_id: tenantId ?? '' })
    setName('')
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('teams.createTeam')}</DialogTitle>
          <DialogDescription>{t('teams.createTeamDesc')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="team-name">{t('teams.name')}</Label>
            <Input id="team-name" onChange={(event) => setName(event.target.value)} value={name} />
          </div>
          <div className="grid gap-1.5">
            <Label>{t('teams.tenant')}</Label>
            <SimpleSelect
              onValueChange={setTenantId}
              options={(tenants.data ?? []).map((tenant) => ({ value: tenant.id, label: tenant.name }))}
              placeholder={t('teams.selectTenant')}
              value={tenantId || undefined}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('teams.cancel')}
          </Button>
          <Button disabled={!name.trim() || !tenantId || create.isPending} onClick={() => void submit()}>
            {t('teams.createTeam')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function SetApproverDialog({
  team,
  users,
  onOpenChange,
}: {
  team: TeamListItem | null
  users: TeamUser[]
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const setApprover = useSetApproverMutation(team?.id ?? '')
  const [value, setValue] = useState<string | null>(APPROVER_NONE)

  // Reset the picker to the team's current approver whenever the dialog opens for a team.
  useEffect(() => {
    setValue(team?.approver_user_id ?? APPROVER_NONE)
  }, [team])

  const submit = async (): Promise<void> => {
    await setApprover.mutateAsync({
      approver_user_id: value === APPROVER_NONE ? null : value,
      entity_type: 'team',
    })
    onOpenChange(false)
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(team)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('teams.approverTitle', { name: team?.name ?? '' })}</DialogTitle>
          <DialogDescription>{t('teams.approverDesc')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label>{t('teams.approver')}</Label>
          <SimpleSelect
            onValueChange={setValue}
            options={[
              { value: APPROVER_NONE, label: t('teams.none') },
              ...users.map((user) => ({
                value: user.id,
                label: user.email ? t('teams.userWithEmail', { name: user.name, email: user.email }) : user.name,
              })),
            ]}
            value={value}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('teams.cancel')}
          </Button>
          <Button disabled={setApprover.isPending} onClick={() => void submit()}>
            {t('teams.saveApprover')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

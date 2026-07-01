import { useState } from 'react'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { CreateTeamDialog } from '@/features/teams/dialogs/team-dialogs'
import { useAdminMeQuery } from '@/features/teams/shared'
import { TeamsTable } from '@/features/teams/teams-table'
import { useT } from '@/i18n'

export function TeamsPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const [creating, setCreating] = useState(false)

  const canWrite = me.data?.role !== 'viewer'

  const actions = canWrite ? (
    <Button onClick={() => setCreating(true)}>
      <Plus className="size-4" /> {t('teams.createTeam')}
    </Button>
  ) : undefined

  return (
    <div className="space-y-6">
      <TeamsTable actions={actions} canWrite={canWrite} title={t('teams.title')} />

      {canWrite ? <CreateTeamDialog onOpenChange={setCreating} open={creating} /> : null}
    </div>
  )
}

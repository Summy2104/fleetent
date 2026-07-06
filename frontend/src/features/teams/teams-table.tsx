import type * as React from 'react'
import { useMemo, useState } from 'react'

import { DataTable } from '@/components/base/data-table'
import { buildTeamColumns } from '@/features/teams/columns/team-columns'
import { SetApproverDialog } from '@/features/teams/dialogs/team-dialogs'
import { useTeamUsersQuery } from '@/features/teams/shared'
import { type TeamListItem, useTeamsQuery, useTenantsQuery } from '@/features/tenancy/api'
import { useT } from '@/i18n'
import { labelWithId } from '@/lib/labels'

export function TeamsTable({
  canWrite,
  actions,
  title,
}: {
  canWrite: boolean
  actions?: React.ReactNode
  title?: React.ReactNode
}): JSX.Element {
  const t = useT()
  const teams = useTeamsQuery()
  const users = useTeamUsersQuery()
  const tenants = useTenantsQuery()
  const [approverTeam, setApproverTeam] = useState<TeamListItem | null>(null)

  const userList = users.data ?? []
  const tenantList = tenants.data ?? []

  const columns = useMemo(() => {
    const userName = (id: string | null): string => {
      if (!id) return t('teams.unassigned')
      return userList.find((user) => user.id === id)?.name ?? id
    }
    // Cell resolvers show "name (id)"; the approver filter still keys off `userName`.
    const approverLabel = (id: string | null): string =>
      id ? labelWithId(userList.find((user) => user.id === id)?.name, id) : t('teams.unassigned')
    const tenantLabel = (id: string): string => labelWithId(tenantList.find((tenant) => tenant.id === id)?.name, id)
    const tenantOptions = tenantList.map((tenant) => ({ label: tenant.name, value: tenant.id }))
    // Approver filter matches the resolved name the accessor renders, so options mirror `userName`.
    const approverOptions = [
      { label: t('teams.unassigned'), value: t('teams.unassigned') },
      ...userList.map((user) => ({ label: user.name, value: user.name })),
    ]
    return buildTeamColumns({
      approverLabel,
      approverOptions,
      canWrite,
      onSetApprover: setApproverTeam,
      t,
      tenantLabel,
      tenantOptions,
      userName,
    })
  }, [canWrite, t, userList, tenantList])

  return (
    <>
      <DataTable
        actions={actions}
        columns={columns}
        data={teams.data ?? []}
        emptyState={<div className="py-12 text-center text-muted-foreground text-sm">{t('teams.noTeams')}</div>}
        enableColumnVisibility
        enableGlobalFilter
        getRowId={(row) => row.id}
        isLoading={teams.isPending}
        title={title}
      />

      <SetApproverDialog onOpenChange={(open) => !open && setApproverTeam(null)} team={approverTeam} users={userList} />
    </>
  )
}

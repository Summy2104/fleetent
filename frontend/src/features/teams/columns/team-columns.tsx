import type { ColumnDef } from '@tanstack/react-table'

import type { ColumnFilterOption } from '@/components/base/data-table/types'
import { TeamRowActions } from '@/features/teams/row-actions/team-row-actions'
import type { TeamListItem } from '@/features/tenancy/api'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

export function buildTeamColumns({
  t,
  canWrite,
  userName,
  approverLabel,
  tenantLabel,
  tenantOptions,
  approverOptions,
  onSetApprover,
}: {
  t: Translate
  canWrite: boolean
  // Name-only resolver; drives the approver filter's accessor/options so the
  // select values stay in sync. The cells below render the richer "name (id)".
  userName: (id: string | null) => string
  approverLabel: (id: string | null) => string
  tenantLabel: (id: string) => string
  tenantOptions: ColumnFilterOption[]
  approverOptions: ColumnFilterOption[]
  onSetApprover: (team: TeamListItem) => void
}): ColumnDef<TeamListItem, unknown>[] {
  const columns: ColumnDef<TeamListItem, unknown>[] = [
    {
      accessorKey: 'name',
      header: t('teams.colTeam'),
      meta: { title: t('teams.colTeam') },
      cell: ({ row }) => {
        const team = row.original
        return (
          <div className="min-w-0">
            <div className="font-semibold text-foreground text-sm">{team.name}</div>
            <div className="font-mono text-muted-foreground text-xs">{team.id}</div>
          </div>
        )
      },
    },
    {
      accessorKey: 'tenant_id',
      header: t('teams.colTenant'),
      meta: { title: t('teams.colTenant'), filter: { type: 'select', options: tenantOptions } },
      cell: ({ row }) => (
        <span className="font-mono text-muted-foreground text-sm">{tenantLabel(row.original.tenant_id)}</span>
      ),
    },
    {
      id: 'approver',
      accessorFn: (team) => userName(team.approver_user_id),
      header: t('teams.colApprover'),
      meta: { title: t('teams.colApprover'), filter: { type: 'select', options: approverOptions } },
      cell: ({ row }) => (
        <span className="text-foreground text-sm">{approverLabel(row.original.approver_user_id)}</span>
      ),
    },
  ]

  if (canWrite) {
    columns.push({
      id: 'actions',
      header: '',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => <TeamRowActions onSetApprover={onSetApprover} team={row.original} />,
    })
  }

  return columns
}

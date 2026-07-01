import type { ColumnDef } from '@tanstack/react-table'

import { Badge } from '@/components/base/badge'
import type { SkillListItem } from '@/features/skills/api'
import { SkillRowActions } from '@/features/skills/row-actions/skill-row-actions'
import { auditVariant, SKILL_STATUSES, statusVariant } from '@/features/skills/shared'
import type { useT } from '@/i18n'

type Translate = ReturnType<typeof useT>

export function buildSkillColumns({
  t,
  canWrite,
  proposalCountFor,
  backflowCountFor,
  onViewContent,
  onVersions,
  onBindings,
  onProposals,
  onBackflow,
}: {
  t: Translate
  canWrite: boolean
  proposalCountFor: (name: string) => number
  backflowCountFor: (name: string) => number
  onViewContent: (name: string) => void
  onVersions: (name: string) => void
  onBindings: (name: string) => void
  onProposals: (name: string) => void
  onBackflow: (name: string) => void
}): ColumnDef<SkillListItem, unknown>[] {
  return [
    {
      accessorKey: 'name',
      header: t('skills.colSkill'),
      meta: { title: t('skills.colSkill') },
      cell: ({ row }) => {
        const skill = row.original
        return (
          <div className="min-w-0 max-w-[320px]">
            <span className="block truncate font-semibold text-foreground text-sm">{skill.name}</span>
            {skill.description ? (
              <span className="mt-0.5 line-clamp-1 block text-muted-foreground text-sm">{skill.description}</span>
            ) : null}
          </div>
        )
      },
    },
    {
      accessorKey: 'status',
      header: t('skills.colStatus'),
      filterFn: 'equals',
      meta: {
        title: t('skills.colStatus'),
        filter: { type: 'select', options: SKILL_STATUSES.map((status) => ({ label: status, value: status })) },
      },
      cell: ({ row }) => <Badge variant={statusVariant(row.original.status)}>{row.original.status}</Badge>,
    },
    {
      accessorKey: 'global_enabled',
      header: t('skills.colEnabled'),
      filterFn: 'equalsString',
      meta: {
        title: t('skills.colEnabled'),
        filter: {
          type: 'select',
          options: [
            { label: t('skills.enabled'), value: 'true' },
            { label: t('skills.disabled'), value: 'false' },
          ],
        },
      },
      cell: ({ row }) => (
        <Badge variant={row.original.global_enabled ? 'success' : 'secondary'}>
          {row.original.global_enabled ? t('skills.enabled') : t('skills.disabled')}
        </Badge>
      ),
    },
    {
      accessorKey: 'audit_verdict',
      header: t('skills.colAudit'),
      cell: ({ row }) =>
        row.original.audit_verdict ? (
          <Badge variant={auditVariant(row.original.audit_verdict)}>{row.original.audit_verdict}</Badge>
        ) : (
          <span className="text-muted-foreground text-sm">-</span>
        ),
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      enableHiding: false,
      cell: ({ row }) => (
        <SkillRowActions
          backflowCount={backflowCountFor(row.original.name)}
          canWrite={canWrite}
          onBackflow={() => onBackflow(row.original.name)}
          onBindings={() => onBindings(row.original.name)}
          onProposals={() => onProposals(row.original.name)}
          onVersions={() => onVersions(row.original.name)}
          onViewContent={() => onViewContent(row.original.name)}
          proposalCount={proposalCountFor(row.original.name)}
          skill={row.original}
        />
      ),
    },
  ]
}

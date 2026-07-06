import { useCallback, useMemo } from 'react'

import { DataTable } from '@/components/base/data-table'
import { useAgentSkillsQuery, useSetAgentSkillMutation } from '@/features/agents/api'
import { buildSkillColumns } from '@/features/agents/columns/capability-columns'
import { useT } from '@/i18n'

// Skills are injected into the system prompt (read-on-demand catalog), not exposed as tools; the
// toggle flips each binding's `enabled` flag. Its own tab, distinct from MCP servers.
export function SkillsTab({ agentName, canWrite }: { agentName: string; canWrite: boolean }): JSX.Element {
  const t = useT()

  const skills = useAgentSkillsQuery(agentName)
  const setSkill = useSetAgentSkillMutation(agentName).mutateAsync
  const onToggle = useCallback(
    (skillName: string, enabled: boolean) => {
      void setSkill({ skill_name: skillName, enabled })
    },
    [setSkill]
  )
  const columns = useMemo(() => buildSkillColumns({ t, canWrite, onToggle }), [t, canWrite, onToggle])

  return (
    <DataTable
      columns={columns}
      data={skills.data ?? []}
      emptyState={
        <div className="py-10 text-center text-muted-foreground text-sm">{t('agents.noSkillsAvailable')}</div>
      }
      enableGlobalFilter
      getRowId={(row) => row.skill_name}
      isLoading={skills.isPending}
      title={t('agents.skillsTitle')}
    />
  )
}

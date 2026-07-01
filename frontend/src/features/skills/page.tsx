import { RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useReloadSkillsMutation } from '@/features/skills/api'
import { useAdminMeQuery } from '@/features/skills/shared'
import { SkillsTable } from '@/features/skills/skills-table'
import { useT } from '@/i18n'

export function SkillsPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const reload = useReloadSkillsMutation()

  const canWrite = me.data?.role !== 'viewer'

  const actions = canWrite ? (
    <Button onClick={() => void reload.mutateAsync()} variant="outline">
      <RefreshCw className="size-4" /> {t('skills.reloadIndex')}
    </Button>
  ) : undefined

  return (
    <div className="space-y-6">
      <SkillsTable actions={actions} canWrite={canWrite} title={t('skills.title')} />
    </div>
  )
}

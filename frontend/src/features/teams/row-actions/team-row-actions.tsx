import { MoreVertical } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import type { TeamListItem } from '@/features/tenancy/api'
import { useT } from '@/i18n'

export function TeamRowActions({
  team,
  onSetApprover,
}: {
  team: TeamListItem
  onSetApprover: (team: TeamListItem) => void
}): JSX.Element {
  const t = useT()
  return (
    <div className="flex justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button aria-label={t('teams.actionsFor', { name: team.name })} size="icon" variant="ghost">
              <MoreVertical className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setTimeout(() => onSetApprover(team), 0)}>
            {t('teams.setApprover')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

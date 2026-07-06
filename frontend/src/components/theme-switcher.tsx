import { Moon, Sun } from 'lucide-react'

import { useTheme } from '@/app/theme'
import { Button } from '@/components/ui/button'
import { useT } from '@/i18n'

export function ThemeSwitcher(): JSX.Element {
  const { theme, toggleTheme } = useTheme()
  const t = useT()
  const isDark = theme === 'dark'
  const label = isDark ? t('theme.switchToLight') : t('theme.switchToDark')

  return (
    <Button aria-label={label} onClick={toggleTheme} size="icon" title={label} variant="ghost">
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}

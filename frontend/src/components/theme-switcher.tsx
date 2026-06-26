import { Moon, Sun } from 'lucide-react';

import { useTheme } from '@/app/theme';
import { useT } from '@/i18n';
import { Button } from '@/components/ui/button';

export function ThemeSwitcher(): JSX.Element {
  const { theme, toggleTheme } = useTheme();
  const t = useT();
  const isDark = theme === 'dark';
  const label = isDark ? t('theme.switchToLight') : t('theme.switchToDark');

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={label}
      title={label}
      onClick={toggleTheme}
    >
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}

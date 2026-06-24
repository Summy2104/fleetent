import { Moon, Sun } from 'lucide-react';

import { useTheme } from '@/app/theme';
import { Button } from '@/components/ui/button';

export function ThemeSwitcher(): JSX.Element {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={isDark ? 'Switch to light' : 'Switch to dark'}
      title={isDark ? 'Switch to light' : 'Switch to dark'}
      onClick={toggleTheme}
    >
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}

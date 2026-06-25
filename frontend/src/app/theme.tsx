import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

/**
 * Theme system — Dark (default) and Light.
 *
 * Every color in the app resolves through CSS custom properties declared in
 * `index.css` (`--background`, `--primary`, …). A theme is therefore just a set
 * of overrides for those variables. The dark default lives in `:root` (no flash
 * on first paint); switching applies the preset's overrides via
 * `style.setProperty` on the document root and persists the choice. Adding more
 * presets (or a custom accent picker) later is just more entries here.
 */

const STORAGE_KEY = 'fleetent.admin.theme';

type Tokens = Record<string, string>;

export type ThemeId = 'dark' | 'light';

export type ThemeDef = {
  id: ThemeId;
  label: string;
  scheme: 'dark' | 'light';
  /** CSS variable overrides applied on top of the `:root` base. */
  tokens: Tokens;
};

const LIGHT_TOKENS: Tokens = {
  '--background': '210 20% 98%',
  '--foreground': '222 47% 11%',
  '--card': '0 0% 100%',
  '--card-foreground': '222 47% 11%',
  '--popover': '0 0% 100%',
  '--popover-foreground': '222 47% 11%',
  '--primary': '158 64% 38%',
  '--primary-foreground': '0 0% 100%',
  '--secondary': '210 40% 96%',
  '--secondary-foreground': '222 47% 11%',
  '--muted': '210 40% 96%',
  '--muted-foreground': '215 16% 45%',
  '--accent': '210 40% 93%',
  '--accent-foreground': '222 47% 11%',
  '--destructive': '0 72% 51%',
  '--destructive-foreground': '0 0% 100%',
  '--border': '214 32% 88%',
  '--input': '214 32% 88%',
  '--ring': '158 64% 38%',
  '--sidebar': '210 24% 96%',
  '--sidebar-foreground': '215 16% 40%',
  '--sidebar-accent': '210 40% 90%',
  '--sidebar-border': '214 32% 88%',
  '--success': '158 64% 38%',
  '--warning': '38 92% 42%',
};

export const THEMES: Record<ThemeId, ThemeDef> = {
  dark: { id: 'dark', label: 'Dark', scheme: 'dark', tokens: {} },
  light: { id: 'light', label: 'Light', scheme: 'light', tokens: LIGHT_TOKENS },
};

export const THEME_LIST: ThemeDef[] = Object.values(THEMES);

const DEFAULT_THEME: ThemeId = 'dark';

// Union of every variable any theme can touch, so switching cleanly resets
// variables a previous theme set but the next one does not.
const ALL_KEYS = Array.from(new Set(THEME_LIST.flatMap((theme) => Object.keys(theme.tokens))));

function applyTheme(id: ThemeId): void {
  const theme = THEMES[id] ?? THEMES[DEFAULT_THEME];
  const root = document.documentElement;
  for (const key of ALL_KEYS) {
    const value = theme.tokens[key];
    if (value) {
      root.style.setProperty(key, value);
    } else {
      root.style.removeProperty(key);
    }
  }
  root.style.colorScheme = theme.scheme;
  root.dataset.theme = id;
}

function readStoredTheme(): ThemeId {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY) as ThemeId | null;
    return stored && stored in THEMES ? stored : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

type ThemeContextValue = {
  theme: ThemeId;
  setTheme: (id: ThemeId) => void;
  toggleTheme: () => void;
  themes: ThemeDef[];
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [theme, setThemeState] = useState<ThemeId>(() => readStoredTheme());

  useEffect(() => {
    applyTheme(theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* ignore persistence failures (private mode, etc.) */
    }
  }, [theme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme: setThemeState,
      toggleTheme: () => setThemeState((current) => (current === 'dark' ? 'light' : 'dark')),
      themes: THEME_LIST,
    }),
    [theme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}

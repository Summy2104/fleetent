import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from 'react'

/**
 * Theme system — Dark (default) and Light.
 *
 * Colors resolve through CSS custom properties declared in `index.css`: `:root`
 * holds the light palette and the `.dark` class overrides it with the dark
 * palette. Switching a theme is therefore just toggling that class (plus the
 * native `color-scheme`) and persisting the choice. The dark-first default is
 * applied before first paint by a small head script in `index.html`, so there
 * is no flash; this provider keeps React in sync after hydration.
 */

const STORAGE_KEY = 'fleetent.admin.theme'

export type ThemeId = 'dark' | 'light'

export type ThemeDef = {
  id: ThemeId
  label: string
  scheme: 'dark' | 'light'
}

export const THEMES: Record<ThemeId, ThemeDef> = {
  dark: { id: 'dark', label: 'Dark', scheme: 'dark' },
  light: { id: 'light', label: 'Light', scheme: 'light' },
}

export const THEME_LIST: ThemeDef[] = Object.values(THEMES)

const DEFAULT_THEME: ThemeId = 'dark'

function applyTheme(id: ThemeId): void {
  const theme = THEMES[id] ?? THEMES[DEFAULT_THEME]
  const root = document.documentElement
  root.classList.toggle('dark', theme.scheme === 'dark')
  root.style.colorScheme = theme.scheme
  root.dataset.theme = id
}

function readStoredTheme(): ThemeId {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY) as ThemeId | null
    return stored && stored in THEMES ? stored : DEFAULT_THEME
  } catch {
    return DEFAULT_THEME
  }
}

type ThemeContextValue = {
  theme: ThemeId
  setTheme: (id: ThemeId) => void
  toggleTheme: () => void
  themes: ThemeDef[]
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [theme, setThemeState] = useState<ThemeId>(() => readStoredTheme())

  useEffect(() => {
    applyTheme(theme)
    try {
      window.localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      /* ignore persistence failures (private mode, etc.) */
    }
  }, [theme])

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme: setThemeState,
      toggleTheme: () => setThemeState((current) => (current === 'dark' ? 'light' : 'dark')),
      themes: THEME_LIST,
    }),
    [theme]
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

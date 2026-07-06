/* eslint-disable react-refresh/only-export-components */

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const TOKEN_STORAGE_KEY = 'fleetent.admin.token'
// Persisted alongside the token so a forced password reset survives a page reload:
// the backend rejects every admin call except /me and /change-password while it is set.
const MUST_RESET_STORAGE_KEY = 'fleetent.admin.must_reset'
const memoryStorage = new Map<string, string>()

function readStored(key: string): string | null {
  try {
    return window.localStorage?.getItem(key) ?? memoryStorage.get(key) ?? null
  } catch {
    return memoryStorage.get(key) ?? null
  }
}

function writeStored(key: string, value: string): void {
  memoryStorage.set(key, value)
  try {
    window.localStorage?.setItem(key, value)
  } catch {
    return
  }
}

function clearStored(key: string): void {
  memoryStorage.delete(key)
  try {
    window.localStorage?.removeItem(key)
  } catch {
    return
  }
}

type AuthContextValue = {
  baseUrl: string
  token: string | null
  mustReset: boolean
  setToken: (token: string) => void
  setSession: (token: string, mustReset: boolean) => void
  clearMustReset: () => void
  clearToken: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({
  baseUrl,
  initialToken = null,
  initialMustReset = false,
  onSessionExpired,
  children,
}: {
  baseUrl: string
  initialToken?: string | null
  initialMustReset?: boolean
  onSessionExpired?: () => void
  children: ReactNode
}): JSX.Element {
  const [token, setTokenState] = useState<string | null>(() => {
    return initialToken ?? readStored(TOKEN_STORAGE_KEY)
  })
  const [mustReset, setMustResetState] = useState<boolean>(() => {
    return initialMustReset || readStored(MUST_RESET_STORAGE_KEY) === '1'
  })

  useEffect(() => {
    if (initialToken) {
      writeStored(TOKEN_STORAGE_KEY, initialToken)
    }
  }, [initialToken])

  const persistMustReset = useCallback((next: boolean): void => {
    if (next) {
      writeStored(MUST_RESET_STORAGE_KEY, '1')
    } else {
      clearStored(MUST_RESET_STORAGE_KEY)
    }
    setMustResetState(next)
  }, [])

  // OIDC callback path: token only, no pending reset (provisioned users are verified).
  const setToken = useCallback(
    (nextToken: string): void => {
      writeStored(TOKEN_STORAGE_KEY, nextToken)
      setTokenState(nextToken)
      persistMustReset(false)
    },
    [persistMustReset]
  )

  const setSession = useCallback(
    (nextToken: string, nextMustReset: boolean): void => {
      writeStored(TOKEN_STORAGE_KEY, nextToken)
      setTokenState(nextToken)
      persistMustReset(nextMustReset)
    },
    [persistMustReset]
  )

  const clearMustReset = useCallback((): void => {
    persistMustReset(false)
  }, [persistMustReset])

  const clearToken = useCallback((): void => {
    clearStored(TOKEN_STORAGE_KEY)
    clearStored(MUST_RESET_STORAGE_KEY)
    setTokenState(null)
    setMustResetState(false)
    onSessionExpired?.()
  }, [onSessionExpired])

  const value = useMemo<AuthContextValue>(
    () => ({
      baseUrl,
      token,
      mustReset,
      setToken,
      setSession,
      clearMustReset,
      clearToken,
    }),
    [baseUrl, clearMustReset, clearToken, mustReset, setSession, setToken, token]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuthSession(): AuthContextValue {
  const value = useContext(AuthContext)
  if (value === null) {
    throw new Error('useAuthSession must be used within AuthProvider')
  }
  return value
}

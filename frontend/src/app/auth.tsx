/* eslint-disable react-refresh/only-export-components */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

const TOKEN_STORAGE_KEY = 'fleetent.admin.token';
const memoryStorage = new Map<string, string>();

function readToken(): string | null {
  try {
    return window.localStorage?.getItem(TOKEN_STORAGE_KEY) ?? memoryStorage.get(TOKEN_STORAGE_KEY) ?? null;
  } catch {
    return memoryStorage.get(TOKEN_STORAGE_KEY) ?? null;
  }
}

function writeToken(token: string): void {
  memoryStorage.set(TOKEN_STORAGE_KEY, token);
  try {
    window.localStorage?.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    return;
  }
}

function clearStoredToken(): void {
  memoryStorage.delete(TOKEN_STORAGE_KEY);
  try {
    window.localStorage?.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    return;
  }
}

type AuthContextValue = {
  baseUrl: string;
  token: string | null;
  setToken: (token: string) => void;
  clearToken: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  baseUrl,
  initialToken = null,
  onSessionExpired,
  children,
}: {
  baseUrl: string;
  initialToken?: string | null;
  onSessionExpired?: () => void;
  children: ReactNode;
}): JSX.Element {
  const [token, setTokenState] = useState<string | null>(() => {
    return initialToken ?? readToken();
  });

  useEffect(() => {
    if (initialToken) {
      writeToken(initialToken);
    }
  }, [initialToken]);

  const setToken = useCallback((nextToken: string): void => {
    writeToken(nextToken);
    setTokenState(nextToken);
  }, []);

  const clearToken = useCallback((): void => {
    clearStoredToken();
    setTokenState(null);
    onSessionExpired?.();
  }, [onSessionExpired]);

  const value = useMemo<AuthContextValue>(
    () => ({
      baseUrl,
      token,
      setToken,
      clearToken,
    }),
    [baseUrl, clearToken, setToken, token]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuthSession(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error('useAuthSession must be used within AuthProvider');
  }
  return value;
}

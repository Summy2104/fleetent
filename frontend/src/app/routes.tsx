import { useEffect, useState } from 'react';
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { LogOut, Menu, X } from 'lucide-react';

import { useAuthSession } from '@/app/auth';
import { NAV_GROUPS, NAV_TITLE_KEYS } from '@/app/nav';
import { useT } from '@/i18n';
import { useAdminApi } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LanguageSwitcher } from '@/components/language-switcher';
import { ThemeSwitcher } from '@/components/theme-switcher';
import { ChangePasswordFields, ProfilePage } from '@/features/profile/page';
import { AgentsPage } from '@/features/agents/page';
import { AgentConfigurePage } from '@/features/agents/configure';
import { SkillsPage } from '@/features/skills/page';
import { KnowledgeBasePage } from '@/features/kb/page';
import { McpPage } from '@/features/mcp/page';
import { ProvidersPage } from '@/features/providers/page';
import { NodesPage } from '@/features/nodes/page';
import { UsersPage } from '@/features/users/page';
import { ChatPage } from '@/features/chat/page';
import { StatsPage } from '@/features/stats/page';
import { AuditPage } from '@/features/audit/page';
import { TenancyPage } from '@/features/tenancy/page';
import { TeamsPage } from '@/features/teams/page';

type AdminMe = { email: string; id: string; role: string; must_reset?: boolean };
type OidcConfig = { enabled: boolean; label: string };

function useMe() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

function useOidcConfigQuery(baseUrl: string) {
  return useQuery({
    queryKey: ['admin-oidc-config', baseUrl],
    queryFn: async (): Promise<OidcConfig> => {
      const response = await fetch(`${baseUrl}/admin/oidc/config`);
      if (!response.ok) {
        throw new Error('failed to load oidc config');
      }
      return (await response.json()) as OidcConfig;
    },
  });
}

// Full-screen gate shown when the logged-in user still has must_reset set.
function ChangePasswordGate(): JSX.Element {
  const auth = useAuthSession();
  const t = useT();
  return (
    <main className="grid min-h-screen place-items-center px-6 py-16">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card/80 p-8 shadow-soft backdrop-blur">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-lg bg-primary/15 text-primary">
            <span className="size-3 rounded-full bg-primary" />
          </span>
          <span className="text-sm font-semibold tracking-[0.3em] text-muted-foreground">FLEETENT</span>
        </div>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">{t('gate.title')}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t('gate.subtitle')}</p>
        <div className="mt-7">
          <ChangePasswordFields submitLabel={t('gate.submit')} onDone={() => auth.clearMustReset()} />
        </div>
      </div>
    </main>
  );
}

function LoginPage(): JSX.Element {
  const auth = useAuthSession();
  const t = useT();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const oidcConfig = useOidcConfigQuery(auth.baseUrl);
  const showOidcLogin = oidcConfig.data?.enabled === true;
  const oidcLoginLabel = oidcConfig.data?.label || t('login.signInWithSso');

  const callbackToken = searchParams.get('token');

  useEffect(() => {
    if (!callbackToken) {
      return;
    }
    auth.setToken(callbackToken);
    navigate('/agents', { replace: true });
  }, [auth, callbackToken, navigate]);

  if (callbackToken) {
    return <main className="min-h-screen" />;
  }

  const onSubmit = async (): Promise<void> => {
    if (!email.trim() || !password) {
      setError(t('login.missingFields'));
      return;
    }
    setError(null);
    const response = await fetch(`${auth.baseUrl}/admin/login`, {
      body: JSON.stringify({ email, password }),
      headers: { 'content-type': 'application/json' },
      method: 'POST',
    });
    if (!response.ok) {
      setError(t('login.failed'));
      return;
    }
    const body = (await response.json()) as { token: string; must_reset?: boolean };
    auth.setSession(body.token, Boolean(body.must_reset));
    navigate('/agents', { replace: true });
  };

  return (
    <main className="grid min-h-screen place-items-center px-6 py-16">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card/80 p-8 shadow-soft backdrop-blur">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-lg bg-primary/15 text-primary">
            <span className="size-3 rounded-full bg-primary" />
          </span>
          <span className="text-sm font-semibold tracking-[0.3em] text-muted-foreground">FLEETENT</span>
        </div>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">{t('login.title')}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t('login.subtitle')}</p>
        <div className="mt-7 grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="email">{t('common.email')}</Label>
            <Input
              id="email"
              placeholder={t('login.emailPlaceholder')}
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="password">{t('common.password')}</Label>
            <Input
              id="password"
              type="password"
              placeholder={t('login.passwordPlaceholder')}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <Button disabled={!email.trim() || !password} onClick={() => void onSubmit()}>
            {t('common.signIn')}
          </Button>
          {showOidcLogin ? (
            <Button
              variant="outline"
              onClick={() => {
                window.location.href = `${auth.baseUrl}/admin/oidc/login`;
              }}
            >
              {oidcLoginLabel}
            </Button>
          ) : null}
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
      </div>
    </main>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }): JSX.Element {
  const auth = useAuthSession();
  const api = useAdminApi();
  const me = useMe();
  const t = useT();

  const signOut = async (): Promise<void> => {
    try {
      // Tear down the server-side session so the token can't be replayed until
      // its idle timeout; the call carries the current token via the api client.
      await api.post('/admin/logout');
    } catch (error) {
      // Best-effort: always drop the local session even if the network call
      // fails (offline, or the token was already invalidated server-side).
      console.warn('logout request failed', error);
    } finally {
      auth.clearToken();
    }
  };

  return (
    <aside className="flex h-full w-64 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="flex h-16 items-center justify-between gap-2.5 px-6">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-primary/15 text-primary">
            <span className="size-3 rounded-full bg-primary" />
          </span>
          <span className="text-base font-semibold tracking-wide text-foreground">{t('shell.brand')}</span>
        </div>
        {onNavigate ? (
          <Button variant="ghost" size="icon" className="md:hidden" aria-label={t('shell.closeMenu')} onClick={onNavigate}>
            <X className="size-4" />
          </Button>
        ) : null}
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-2">
        {NAV_GROUPS.map((group, groupIndex) => (
          <div key={group.labelKey ?? `group-${groupIndex}`} className="space-y-1">
            {group.labelKey ? (
              <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {t(group.labelKey)}
              </p>
            ) : null}
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-sidebar-accent text-foreground'
                        : 'text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-foreground'
                    )
                  }
                >
                  <Icon className="size-4 shrink-0" />
                  {t(item.labelKey)}
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <div className="flex items-center gap-2 rounded-md">
          <NavLink
            to="/profile"
            onClick={onNavigate}
            className="flex min-w-0 flex-1 flex-col rounded-md px-2 py-2 transition-colors hover:bg-sidebar-accent/60"
          >
            <span className="truncate text-sm font-medium text-foreground">{me.data?.role ?? 'admin'}</span>
            <span className="truncate text-xs text-muted-foreground">{me.data?.email ?? '—'}</span>
          </NavLink>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('common.signOut')}
            title={t('common.signOut')}
            onClick={() => void signOut()}
          >
            <LogOut className="size-4" />
          </Button>
        </div>
      </div>
    </aside>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }): JSX.Element {
  const location = useLocation();
  const t = useT();
  const titleKey = NAV_TITLE_KEYS[location.pathname];
  const title = titleKey ? t(titleKey) : t('common.admin');

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-border bg-background/80 px-4 backdrop-blur md:px-8">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" className="md:hidden" aria-label={t('shell.openMenu')} onClick={onMenu}>
          <Menu className="size-4" />
        </Button>
        <h1 className="text-base font-semibold text-foreground">{title}</h1>
      </div>
      <div className="flex items-center gap-1">
        <LanguageSwitcher />
        <ThemeSwitcher />
      </div>
    </header>
  );
}

function AppLayout(): JSX.Element {
  const [mobileOpen, setMobileOpen] = useState(false);
  const t = useT();

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <div className="sticky top-0 hidden h-screen md:block">
        <Sidebar />
      </div>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label={t('shell.closeMenuOverlay')}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm animate-overlay-in"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 h-full w-64 shadow-soft">
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <Topbar onMenu={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-y-auto px-4 py-6 md:px-8 md:py-8">
          <Routes>
            <Route element={<AgentsPage />} path="/agents" />
            <Route element={<AgentConfigurePage />} path="/agents/:name/configure" />
            <Route element={<SkillsPage />} path="/skills" />
            <Route element={<ProvidersPage />} path="/providers" />
            <Route element={<KnowledgeBasePage />} path="/kb" />
            <Route element={<McpPage />} path="/mcp" />
            <Route element={<NodesPage />} path="/nodes" />
            <Route element={<UsersPage />} path="/users" />
            <Route element={<StatsPage />} path="/stats" />
            <Route element={<AuditPage />} path="/audit" />
            <Route element={<TenancyPage />} path="/tenancy" />
            <Route element={<TeamsPage />} path="/teams" />
            <Route element={<ChatPage />} path="/chat" />
            <Route element={<ProfilePage />} path="/profile" />
            <Route element={<Navigate replace to="/agents" />} path="*" />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function RequireAuth(): JSX.Element {
  const auth = useAuthSession();
  const me = useMe();

  // The server (`/admin/me`) is the source of truth for must_reset. Once it resolves
  // and reports no pending reset, drop any stale locally-persisted flag — otherwise a
  // leftover `mustReset` in localStorage (e.g. a password changed via the profile page,
  // or cleared on another tab) keeps re-opening the gate on every reload.
  useEffect(() => {
    if (me.data && !me.data.must_reset && auth.mustReset) {
      auth.clearMustReset();
    }
  }, [me.data, auth]);

  if (!auth.token) {
    return <Navigate replace to="/login" />;
  }
  // Prefer the server's answer; fall back to the login-time hint only until /me loads
  // (avoids a flash of the console before the gate on a genuine first login).
  const mustReset = me.data ? Boolean(me.data.must_reset) : auth.mustReset;
  if (mustReset) {
    return <ChangePasswordGate />;
  }
  return <AppLayout />;
}

export function AdminRoutes(): JSX.Element {
  return (
    <Routes>
      <Route element={<LoginPage />} path="/login" />
      <Route element={<RequireAuth />} path="/*" />
    </Routes>
  );
}

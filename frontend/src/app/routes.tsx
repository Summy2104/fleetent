import { useEffect, useState } from 'react';
import { Navigate, NavLink, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom';

import { useAuthSession } from '@/app/auth';
import { useAdminApi } from '@/lib/api-client';
import { AgentsPage } from '@/features/agents/page';
import { SkillsPage } from '@/features/skills/page';
import { KnowledgeBasePage } from '@/features/kb/page';
import { ConnectorsPage } from '@/features/connectors/page';
import { SessionsPage } from '@/features/sessions/page';
import { ProvidersPage } from '@/features/providers/page';
import { NodesPage } from '@/features/nodes/page';
import { UsersPage } from '@/features/users/page';
import { ImIdentitiesPage } from '@/features/im-identities/page';
import { ChatPage } from '@/features/chat/page';
import { StatsPage } from '@/features/stats/page';
import { TenancyPage } from '@/features/tenancy/page';

function LoginPage(): JSX.Element {
  const auth = useAuthSession();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('admin@example.com');
  const [password, setPassword] = useState('adminpw');
  const [error, setError] = useState<string | null>(null);

  const callbackToken = searchParams.get('token');

  useEffect(() => {
    if (!callbackToken) {
      return;
    }
    auth.setToken(callbackToken);
    navigate('/agents', { replace: true });
  }, [auth, callbackToken, navigate]);

  if (callbackToken) {
    return <main className="min-h-screen px-6 py-16" />;
  }

  const onSubmit = async (): Promise<void> => {
    setError(null);
    const response = await fetch(`${auth.baseUrl}/admin/login`, {
      body: JSON.stringify({ email, password }),
      headers: {
        'content-type': 'application/json',
      },
      method: 'POST',
    });
    if (!response.ok) {
      setError('Login failed');
      return;
    }
    const body = (await response.json()) as { token: string; must_reset?: boolean };
    auth.setSession(body.token, Boolean(body.must_reset));
    navigate('/agents', { replace: true });
  };

  return (
    <main className="min-h-screen px-6 py-16">
      <div className="mx-auto max-w-xl rounded-3xl border bg-card/90 p-10 shadow-soft backdrop-blur">
        <p className="text-sm font-medium uppercase tracking-[0.3em] text-muted-foreground">
          fleetent control plane
        </p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight">Admin Login</h1>
        <p className="mt-4 text-base text-muted-foreground">
          Session auth, query wiring, and agents migration now run through the same admin API
          contract as the legacy console.
        </p>
        <div className="mt-8 grid gap-4">
          <label className="grid gap-2 text-sm font-medium">
            Email
            <input
              className="rounded-md border bg-white px-3 py-2"
              onChange={(event) => setEmail(event.target.value)}
              value={email}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium">
            Password
            <input
              className="rounded-md border bg-white px-3 py-2"
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </label>
          <button
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            onClick={() => void onSubmit()}
            type="button"
          >
            Sign in
          </button>
          <a
            className="rounded-md border border-primary/30 px-4 py-2 text-center text-sm font-medium text-primary"
            href={`${auth.baseUrl}/admin/oidc/login`}
          >
            Sign in with SSO
          </a>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
        </div>
      </div>
    </main>
  );
}

function ChangePasswordPage(): JSX.Element {
  const auth = useAuthSession();
  const api = useAdminApi();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (): Promise<void> => {
    setError(null);
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    setBusy(true);
    try {
      await api.post('/admin/change-password', { new_password: password });
    } catch {
      setBusy(false);
      setError('Could not update password');
      return;
    }
    auth.clearMustReset();
    navigate('/agents', { replace: true });
  };

  return (
    <main className="min-h-screen px-6 py-16">
      <div className="mx-auto max-w-xl rounded-3xl border bg-card/90 p-10 shadow-soft backdrop-blur">
        <p className="text-sm font-medium uppercase tracking-[0.3em] text-muted-foreground">
          fleetent control plane
        </p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight">Change password</h1>
        <p className="mt-4 text-base text-muted-foreground">
          Your account must set a new password before you can manage the platform.
        </p>
        <div className="mt-8 grid gap-4">
          <label className="grid gap-2 text-sm font-medium">
            New password
            <input
              className="rounded-md border bg-white px-3 py-2"
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </label>
          <button
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            disabled={busy}
            onClick={() => void onSubmit()}
            type="button"
          >
            Update password
          </button>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
        </div>
      </div>
    </main>
  );
}

function AppLayout(): JSX.Element {
  return (
    <main className="min-h-screen px-6 py-12">
      <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[240px_1fr]">
        <aside className="rounded-3xl border bg-card/90 p-6 shadow-soft backdrop-blur">
          <p className="text-sm font-medium uppercase tracking-[0.3em] text-muted-foreground">
            fleetent
          </p>
          <nav className="mt-8 space-y-2">
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/agents"
            >
              Agents
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/skills"
            >
              Skills
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/sessions"
            >
              Sessions
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/providers"
            >
              Providers
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/kb"
            >
              Knowledge Base
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/connectors"
            >
              Connectors
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/nodes"
            >
              Nodes
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/users"
            >
              Users
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/im-identities"
            >
              用户-IM 关系
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/stats"
            >
              Statistics
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/tenancy"
            >
              Tenancy
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                [
                  'block rounded-xl px-4 py-3 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary/80 text-foreground',
                ].join(' ')
              }
              to="/chat"
            >
              Chat
            </NavLink>
          </nav>
        </aside>
        <div className="rounded-3xl border bg-card/85 p-8 shadow-soft backdrop-blur">
          <Routes>
            <Route
              element={<AgentsPage />}
              path="/agents"
            />
            <Route
              element={<SkillsPage />}
              path="/skills"
            />
            <Route
              element={<SessionsPage />}
              path="/sessions"
            />
            <Route
              element={<ProvidersPage />}
              path="/providers"
            />
            <Route
              element={<KnowledgeBasePage />}
              path="/kb"
            />
            <Route
              element={<ConnectorsPage />}
              path="/connectors"
            />
            <Route
              element={<NodesPage />}
              path="/nodes"
            />
            <Route
              element={<UsersPage />}
              path="/users"
            />
            <Route
              element={<ImIdentitiesPage />}
              path="/im-identities"
            />
            <Route
              element={<StatsPage />}
              path="/stats"
            />
            <Route
              element={<TenancyPage />}
              path="/tenancy"
            />
            <Route
              element={<ChatPage />}
              path="/chat"
            />
            <Route
              element={
                <Navigate
                  replace
                  to="/agents"
                />
              }
              path="*"
            />
          </Routes>
        </div>
      </div>
    </main>
  );
}

function RequireAuth(): JSX.Element {
  const auth = useAuthSession();
  if (!auth.token) {
    return (
      <Navigate
        replace
        to="/login"
      />
    );
  }
  // The backend rejects every admin endpoint except /me and /change-password until the
  // pending reset is cleared, so block the rest of the console behind the reset form.
  if (auth.mustReset) {
    return <ChangePasswordPage />;
  }
  return <AppLayout />;
}

export function AdminRoutes(): JSX.Element {
  return (
    <Routes>
      <Route
        element={<LoginPage />}
        path="/login"
      />
      <Route
        element={<RequireAuth />}
        path="/*"
      />
    </Routes>
  );
}

import { useState } from 'react';
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom';

import { useAuthSession } from '@/app/auth';
import { AgentsPage } from '@/features/agents/page';
import { SkillsPage } from '@/features/skills/page';
import { KnowledgeBasePage } from '@/features/kb/page';
import { ConnectorsPage } from '@/features/connectors/page';
import { SessionsPage } from '@/features/sessions/page';
import { ProvidersPage } from '@/features/providers/page';
import { NodesPage } from '@/features/nodes/page';
import { UsersPage } from '@/features/users/page';
import { ChatPage } from '@/features/chat/page';

// Domains not yet migrated to the SPA: deep-link into the legacy console by tab anchor.
// (nodes / tenancy have no legacy tab and stay UI-less until natively migrated.)
const legacyLinks: Array<{ href: string; label: string }> = [
  { href: '/admin/ui-legacy#skills', label: 'Skills' },
  { href: '/admin/ui-legacy#kb', label: 'Knowledge Base' },
  { href: '/admin/ui-legacy#stats', label: 'Statistics' },
];

function LoginPage(): JSX.Element {
  const auth = useAuthSession();
  const navigate = useNavigate();
  const [email, setEmail] = useState('admin@example.com');
  const [password, setPassword] = useState('adminpw');
  const [error, setError] = useState<string | null>(null);

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
    const body = (await response.json()) as { token: string };
    auth.setToken(body.token);
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
              to="/chat"
            >
              Chat
            </NavLink>
            {legacyLinks.map((item) => (
              <a
                className="block rounded-xl bg-secondary/50 px-4 py-3 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
                href={item.href}
                key={item.label}
              >
                {item.label}
              </a>
            ))}
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

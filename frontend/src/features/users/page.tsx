import { useEffect, useState } from 'react';

import {
  useBindImUserMutation,
  useBlockImUserMutation,
  useBlockUserMutation,
  useCreateKeyMutation,
  useCreateUserMutation,
  useDeleteUserMutation,
  useImUsersQuery,
  useResetPasswordMutation,
  useRestoreImUserMutation,
  useRevokeKeyMutation,
  useRotateKeyMutation,
  useSetRoleMutation,
  useUnblockUserMutation,
  useUpdateUserMutation,
  useUserKeysQuery,
  useUsersQuery,
} from '@/features/users/api';

function parseScopes(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

type EditorState = {
  email: string;
  name: string;
  password: string;
  resetPassword: string;
  role: string;
};

const EMPTY_EDITOR: EditorState = {
  email: '',
  name: '',
  password: '',
  resetPassword: '',
  role: 'viewer',
};

export function UsersPage(): JSX.Element {
  const users = useUsersQuery();
  const imUsers = useImUsersQuery();
  const [mode, setMode] = useState<'create' | 'edit'>('create');
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState>(EMPTY_EDITOR);
  const [mustReset, setMustReset] = useState(false);
  const [blockReason, setBlockReason] = useState('');
  const [keyNote, setKeyNote] = useState('');
  const [keyScope, setKeyScope] = useState('*');
  const [secret, setSecret] = useState<string | null>(null);
  const [imBindings, setImBindings] = useState<Record<number, string>>({});
  const [imReasons, setImReasons] = useState<Record<number, string>>({});

  useEffect(() => {
    if (!users.data?.length) {
      setSelectedUserId(null);
      return;
    }
    if (!selectedUserId || !users.data.some((item) => item.id === selectedUserId)) {
      setSelectedUserId(users.data[0].id);
    }
  }, [selectedUserId, users.data]);

  const selectedUser = users.data?.find((item) => item.id === selectedUserId) ?? null;
  const userKeys = useUserKeysQuery(selectedUserId);
  const createUser = useCreateUserMutation();
  const updateUser = useUpdateUserMutation(selectedUserId ?? '');
  const setRole = useSetRoleMutation(selectedUserId ?? '');
  const resetPassword = useResetPasswordMutation(selectedUserId ?? '');
  const createKey = useCreateKeyMutation(selectedUserId ?? '');
  const rotateKey = useRotateKeyMutation(selectedUserId ?? '');
  const revokeKey = useRevokeKeyMutation(selectedUserId ?? '');

  useEffect(() => {
    if (mode === 'edit' && selectedUser) {
      setEditor({
        email: selectedUser.email ?? '',
        name: selectedUser.name,
        password: '',
        resetPassword: '',
        role: selectedUser.role,
      });
      setMustReset(selectedUser.must_reset);
    }
  }, [mode, selectedUser]);

  const resetEditor = (): void => {
    setMode('create');
    setEditor(EMPTY_EDITOR);
    setMustReset(false);
    setBlockReason('');
    setKeyNote('');
    setKeyScope('*');
  };

  const onSubmit = async (): Promise<void> => {
    if (mode === 'create') {
      await createUser.mutateAsync({
        email: editor.email,
        must_reset: mustReset,
        name: editor.name,
        password: editor.password,
        role: editor.role,
      });
      resetEditor();
      return;
    }

    if (!selectedUser) {
      return;
    }

    if (selectedUser.name !== editor.name || (selectedUser.email ?? '') !== editor.email) {
      await updateUser.mutateAsync({
        email: editor.email,
        name: editor.name,
      });
    }
    if (selectedUser.role !== editor.role) {
      await setRole.mutateAsync({ role: editor.role });
    }
    if (editor.resetPassword.trim()) {
      await resetPassword.mutateAsync({ new_password: editor.resetPassword });
      setEditor((current) => ({ ...current, resetPassword: '' }));
    }
  };

  const onIssueKey = async (): Promise<void> => {
    const result = await createKey.mutateAsync({
      note: keyNote || undefined,
      scope: parseScopes(keyScope),
    });
    setSecret(result.plaintext);
  };

  const onRotateKey = async (): Promise<void> => {
    const result = await rotateKey.mutateAsync();
    setSecret(result.api_key_plaintext_once);
  };

  return (
    <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
            Native SPA
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-muted-foreground">
            User administration, API key lifecycle, and IM identity controls now run natively in
            the React admin surface.
          </p>
        </header>

        <section className="rounded-2xl border bg-white/75 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              {mode === 'create' ? 'Create user' : `Edit ${selectedUser?.name ?? 'user'}`}
            </h2>
            {mode === 'edit' ? (
              <button
                className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                onClick={resetEditor}
                type="button"
              >
                New draft
              </button>
            ) : null}
          </div>
          <div className="grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              User name
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setEditor((current) => ({ ...current, name: event.target.value }))}
                value={editor.name}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Email
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setEditor((current) => ({ ...current, email: event.target.value }))}
                value={editor.email}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Role
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setEditor((current) => ({ ...current, role: event.target.value }))}
                value={editor.role}
              >
                <option value="viewer">viewer</option>
                <option value="admin">admin</option>
                <option value="built_in_admin">built_in_admin</option>
              </select>
            </label>
            <label className="flex items-center gap-3 text-sm font-medium">
              <input
                checked={mustReset}
                onChange={(event) => setMustReset(event.target.checked)}
                type="checkbox"
              />
              Must reset password on first login
            </label>
            {mode === 'create' ? (
              <label className="grid gap-2 text-sm font-medium">
                Password
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) =>
                    setEditor((current) => ({ ...current, password: event.target.value }))
                  }
                  value={editor.password}
                />
              </label>
            ) : (
              <label className="grid gap-2 text-sm font-medium">
                Reset password
                <input
                  className="rounded-md border bg-white px-3 py-2"
                  onChange={(event) =>
                    setEditor((current) => ({ ...current, resetPassword: event.target.value }))
                  }
                  value={editor.resetPassword}
                />
              </label>
            )}
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={() => void onSubmit()}
              type="button"
            >
              {mode === 'create' ? 'Create user' : 'Save changes'}
            </button>
          </div>
        </section>

        <section className="grid gap-4">
          {users.data?.map((user) => (
            <UserCard
              blockReason={blockReason}
              key={user.id}
              onEdit={() => {
                setSelectedUserId(user.id);
                setMode('edit');
                setSecret(null);
              }}
              user={user}
            />
          ))}
        </section>
      </div>

      <aside className="space-y-6">
        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">Selected user controls</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {selectedUser ? selectedUser.name : 'No user selected'}
          </p>

          <div className="mt-4 grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              Block reason
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setBlockReason(event.target.value)}
                value={blockReason}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Key note
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setKeyNote(event.target.value)}
                value={keyNote}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Key scope
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setKeyScope(event.target.value)}
                value={keyScope}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
                disabled={!selectedUser}
                onClick={() => void onIssueKey()}
                type="button"
              >
                {selectedUser ? `Issue key for ${selectedUser.name}` : 'Issue key'}
              </button>
              <button
                className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                disabled={!selectedUser}
                onClick={() => void onRotateKey()}
                type="button"
              >
                {selectedUser ? `Rotate key for ${selectedUser.name}` : 'Rotate key'}
              </button>
            </div>
          </div>

          {secret ? (
            <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-4">
              <p className="text-sm font-medium">Copy this key now. It will not be shown again.</p>
              <p className="mt-2 font-mono text-sm">{secret}</p>
              <button
                className="mt-3 rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                onClick={() => setSecret(null)}
                type="button"
              >
                Dismiss new secret
              </button>
            </div>
          ) : null}

          <div className="mt-4 space-y-3">
            {(userKeys.data ?? []).map((key) => (
              <div
                className="rounded-xl border bg-white px-4 py-3"
                key={key.id}
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-mono text-sm">{key.masked}</p>
                    <p className="text-xs text-muted-foreground">{key.prefix}</p>
                  </div>
                  <button
                    className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
                    onClick={() => {
                      if (window.confirm(`Revoke key ${key.masked}?`)) {
                        void revokeKey.mutateAsync(key.id);
                      }
                    }}
                    type="button"
                  >
                    {`Revoke key ${key.id}`}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">IM identities</h2>
          <div className="mt-4 space-y-4">
            {imUsers.data?.map((imUser) => (
              <article
                className="rounded-xl border bg-white p-4"
                data-testid={`im-user-${imUser.id}`}
                key={imUser.id}
              >
                <div className="space-y-2">
                  <p className="font-medium">{imUser.platform_user_id}</p>
                  <div className="flex flex-wrap gap-2 text-sm">
                    <span>{imUser.user_id}</span>
                    <span>{imUser.status}</span>
                    <span>{imUser.allowed ? 'allowed' : 'not allowed'}</span>
                  </div>
                </div>
                <div className="mt-4 grid gap-3">
                  <label className="grid gap-2 text-sm font-medium">
                    Bind to user
                    <select
                      className="rounded-md border bg-white px-3 py-2"
                      onChange={(event) =>
                        setImBindings((current) => ({
                          ...current,
                          [imUser.id]: event.target.value,
                        }))
                      }
                      value={imBindings[imUser.id] ?? imUser.user_id}
                    >
                      {users.data?.map((user) => (
                        <option
                          key={user.id}
                          value={user.id}
                        >
                          {user.id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="grid gap-2 text-sm font-medium">
                    IM reason
                    <input
                      className="rounded-md border bg-white px-3 py-2"
                      onChange={(event) =>
                        setImReasons((current) => ({
                          ...current,
                          [imUser.id]: event.target.value,
                        }))
                      }
                      value={imReasons[imUser.id] ?? ''}
                    />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <ImBindButton
                      imUserId={imUser.id}
                      userId={imBindings[imUser.id] ?? imUser.user_id}
                    />
                    <ImStatusButton
                      imUserId={imUser.id}
                      isAllowed={imUser.allowed}
                      reason={imReasons[imUser.id] ?? ''}
                    />
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      </aside>
    </section>
  );
}

function UserCard({
  blockReason,
  onEdit,
  user,
}: {
  blockReason: string;
  onEdit: () => void;
  user: {
    email: string | null;
    id: string;
    name: string;
    role: string;
    status: string;
  };
}): JSX.Element {
  const blockUser = useBlockUserMutation(user.id);
  const unblockUser = useUnblockUserMutation(user.id);
  const deleteUser = useDeleteUserMutation(user.id);

  return (
    <article
      className="rounded-2xl border bg-white/80 p-5"
      data-testid={`user-card-${user.id}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{user.name}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{user.email ?? 'no email'}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            <span>{user.role}</span>
            <span>{user.status}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={onEdit}
            type="button"
          >
            {`Edit ${user.name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() =>
              void (user.status === 'blocked'
                ? unblockUser.mutateAsync()
                : blockUser.mutateAsync({ reason: blockReason }))
            }
            type="button"
          >
            {user.status === 'blocked' ? `Unblock ${user.name}` : `Block ${user.name}`}
          </button>
          <button
            className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
            onClick={() => {
              if (window.confirm(`Delete ${user.name}?`)) {
                void deleteUser.mutateAsync();
              }
            }}
            type="button"
          >
            {`Delete ${user.name}`}
          </button>
        </div>
      </div>
    </article>
  );
}

function ImBindButton({ imUserId, userId }: { imUserId: number; userId: string }): JSX.Element {
  const bindImUser = useBindImUserMutation(imUserId);

  return (
    <button
      className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
      onClick={() => void bindImUser.mutateAsync({ user_id: userId })}
      type="button"
    >
      Bind identity
    </button>
  );
}

function ImStatusButton({
  imUserId,
  isAllowed,
  reason,
}: {
  imUserId: number;
  isAllowed: boolean;
  reason: string;
}): JSX.Element {
  const blockImUser = useBlockImUserMutation(imUserId);
  const restoreImUser = useRestoreImUserMutation(imUserId);

  return (
    <button
      className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
      onClick={() =>
        void (isAllowed
          ? blockImUser.mutateAsync({ reason })
          : restoreImUser.mutateAsync({ reason }))
      }
      type="button"
    >
      {isAllowed ? 'Block identity' : 'Restore identity'}
    </button>
  );
}

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAdminApi } from '@/lib/api-client';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { useUpdateUserMutation } from '@/features/users/api';

type AdminMe = { email: string | null; id: string; role: string; must_reset?: boolean };

function useMe() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

// POST /admin/change-password — sets a new password and clears must_reset.
export function useChangePasswordMutation() {
  const api = useAdminApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (newPassword: string) => api.post('/admin/change-password', { new_password: newPassword }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-me'] });
    },
  });
}

// Shared new-password + confirm fields with client-side validation. Reused by the
// profile page and the first-login (must_reset) gate.
export function ChangePasswordFields({
  submitLabel,
  onDone,
}: {
  submitLabel: string;
  onDone?: () => void;
}): JSX.Element {
  const change = useChangePasswordMutation();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async (): Promise<void> => {
    if (!password) {
      setError('Please enter a new password.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setError(null);
    await change.mutateAsync(password);
    setPassword('');
    setConfirm('');
    onDone?.();
  };

  return (
    <div className="grid gap-4">
      <div className="grid gap-2">
        <Label htmlFor="cp-new">New password</Label>
        <Input
          id="cp-new"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cp-confirm">Confirm new password</Label>
        <Input
          id="cp-confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button
        className="justify-self-start"
        disabled={!password || !confirm || change.isPending}
        onClick={() => void submit()}
      >
        {submitLabel}
      </Button>
    </div>
  );
}

function initials(value: string): string {
  return value.slice(0, 2).toUpperCase();
}

// ─────────────────────────── User center ───────────────────────────

export function ProfilePage(): JSX.Element {
  const me = useMe();
  const updateUser = useUpdateUserMutation(me.data?.id ?? '');

  const canEditProfile = me.data?.role !== 'viewer';
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');

  useEffect(() => {
    if (me.data) {
      setName('');
      setEmail(me.data.email ?? '');
    }
  }, [me.data]);

  const displayName = me.data?.email ?? me.data?.role ?? 'admin';

  return (
    <div className="max-w-2xl space-y-8">
      <div className="flex items-center gap-4">
        <span className="grid size-12 place-items-center rounded-full bg-secondary text-sm font-semibold text-foreground">
          {initials(displayName)}
        </span>
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Account</h2>
          <p className="text-sm text-muted-foreground">Manage your profile and password.</p>
        </div>
      </div>

      <Separator />

      <section className="space-y-4">
        <h3 className="text-base font-semibold text-foreground">Profile</h3>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="outline">role: {me.data?.role ?? '—'}</Badge>
          <span className="font-mono text-xs text-muted-foreground">id: {me.data?.id ?? '—'}</span>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="profile-email">Email</Label>
          <Input
            id="profile-email"
            disabled={!canEditProfile}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="profile-name">Username (leave blank to keep)</Label>
          <Input
            id="profile-name"
            placeholder={me.data?.role ?? ''}
            disabled={!canEditProfile}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        {canEditProfile ? (
          <Button
            className="justify-self-start"
            disabled={updateUser.isPending}
            onClick={() =>
              void updateUser.mutateAsync({
                email,
                ...(name.trim() ? { name: name.trim() } : {}),
              })
            }
          >
            Save
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">Viewer role can't edit account info.</p>
        )}
      </section>

      <Separator />

      <section className="space-y-4">
        <h3 className="text-base font-semibold text-foreground">Change password</h3>
        <ChangePasswordFields submitLabel="Save password" />
      </section>
    </div>
  );
}

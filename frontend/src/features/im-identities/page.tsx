import { type ReactNode, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Inbox, Plus } from 'lucide-react';

import { useAdminApi } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import {
  type ImMapping,
  useBindableUsersQuery,
  useCreateMappingMutation,
  useDeleteMappingMutation,
  useImMappingsQuery,
} from '@/features/im-identities/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const PLATFORMS = ['slack', 'telegram', 'whatsapp'];

type AdminMe = { email: string; id: string; role: string };

function useAdminMeQuery() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

function Th({ children, className }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <th className={cn('px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground', className)}>
      {children}
    </th>
  );
}

// ─────────────────────────── Add mapping dialog ───────────────────────────

function AddMappingDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const users = useBindableUsersQuery();
  const create = useCreateMappingMutation();
  const [platform, setPlatform] = useState(PLATFORMS[0]);
  const [platformUserId, setPlatformUserId] = useState('');
  const [userId, setUserId] = useState('');

  const canSubmit = Boolean(platformUserId.trim()) && Boolean(userId);

  const submit = async (): Promise<void> => {
    await create.mutateAsync({ platform, platform_user_id: platformUserId.trim(), user_id: userId });
    setPlatform(PLATFORMS[0]);
    setPlatformUserId('');
    setUserId('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add mapping</DialogTitle>
          <DialogDescription>Bind an external IM identity to an internal user.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label>Platform</Label>
            <Select value={platform} onValueChange={setPlatform}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PLATFORMS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ext-id">External ID</Label>
            <Input
              id="ext-id"
              placeholder="e.g. U0123 / 123456"
              value={platformUserId}
              onChange={(event) => setPlatformUserId(event.target.value)}
            />
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <Label>Internal user</Label>
            <Select value={userId} onValueChange={setUserId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a user" />
              </SelectTrigger>
              <SelectContent>
                {(users.data ?? []).map((user) => (
                  <SelectItem key={user.id} value={user.id}>
                    {user.email ? `${user.name} (${user.email})` : user.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!canSubmit || create.isPending} onClick={() => void submit()}>
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Row ───────────────────────────

function MappingRow({ mapping, canWrite }: { mapping: ImMapping; canWrite: boolean }): JSX.Element {
  const deleteMapping = useDeleteMappingMutation();
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3">
        <Badge variant="outline">{mapping.platform}</Badge>
      </td>
      <td className="px-4 py-3 font-mono text-sm text-foreground">{mapping.platform_user_id}</td>
      <td className="px-4 py-3">
        <div className="text-sm text-foreground">{mapping.user_name}</div>
        <div className="text-xs text-muted-foreground">{mapping.user_email ?? mapping.user_id}</div>
      </td>
      <td className="px-4 py-3 text-right">
        {canWrite ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="secondary"
                size="sm"
                aria-label={`Actions for ${mapping.platform}:${mapping.platform_user_id}`}
              >
                Actions
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                className="text-destructive"
                onSelect={() => setTimeout(() => setConfirmDelete(true), 0)}
              >
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}

        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete mapping?</AlertDialogTitle>
              <AlertDialogDescription>
                Unbind {mapping.platform}:{mapping.platform_user_id} from {mapping.user_name}. You can
                re-add it later.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => void deleteMapping.mutateAsync(mapping.id)}>
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </td>
    </tr>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function ImIdentitiesPage(): JSX.Element {
  const me = useAdminMeQuery();
  const mappings = useImMappingsQuery();
  const [adding, setAdding] = useState(false);

  const canWrite = me.data?.role !== 'viewer';
  const list = mappings.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">IM Identities</h2>
          <Badge variant="secondary">{list.length}</Badge>
        </div>
        {canWrite ? (
          <Button onClick={() => setAdding(true)}>
            <Plus className="size-4" /> Add mapping
          </Button>
        ) : null}
      </div>

      <p className="text-sm text-muted-foreground">
        Maps each external IM identity to the internal user it is bound to.
      </p>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full">
          <thead className="bg-secondary/50">
            <tr>
              <Th>Platform</Th>
              <Th>External ID</Th>
              <Th>User</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {list.map((mapping) => (
              <MappingRow key={mapping.id} mapping={mapping} canWrite={canWrite} />
            ))}
            {mappings.data && list.length === 0 ? (
              <tr>
                <td colSpan={4}>
                  <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
                    <Inbox className="size-6 opacity-50" />
                    <span className="text-sm">No mappings yet.</span>
                  </div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <AddMappingDialog open={adding} onOpenChange={setAdding} />
    </div>
  );
}

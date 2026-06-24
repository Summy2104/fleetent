import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, Inbox, KeyRound, Plus, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  type ConnectorEditInput,
  type ConnectorGrant,
  type ConnectorRecord,
  useConnectorAuthorizeQuery,
  useConnectorCredentialsMutation,
  useConnectorGrantsQuery,
  useConnectorTestMutation,
  useConnectorsQuery,
  useCreateConnectorMutation,
  useDeleteConnectorMutation,
  useOffboardingQuery,
  useRevokeConnectorGrantMutation,
  useUpdateConnectorMutation,
} from '@/features/connectors/api';

const PROTOCOLS = ['oauth2', 'apikey'] as const;

function grantStatusVariant(status: string): 'success' | 'warning' | 'destructive' | 'secondary' {
  if (status === 'authorized') return 'success';
  if (status === 'needs_reauth') return 'warning';
  if (status === 'credential_error') return 'destructive';
  return 'secondary';
}

// ─────────────────────────── Add / Edit dialog ───────────────────────────

function ConnectorDialog({
  open,
  editing,
  onOpenChange,
}: {
  open: boolean;
  editing: ConnectorRecord | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const create = useCreateConnectorMutation();
  const update = useUpdateConnectorMutation(editing?.id ?? '');
  const isEdit = editing !== null;

  const [id, setId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [protocol, setProtocol] = useState<string>('oauth2');
  const [enabled, setEnabled] = useState(true);
  const [oauthConfig, setOauthConfig] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setId(editing?.id ?? '');
      setDisplayName(editing?.display_name ?? '');
      setProtocol(editing?.protocol ?? 'oauth2');
      setEnabled(editing?.enabled ?? true);
      setOauthConfig(editing?.oauth_config ? JSON.stringify(editing.oauth_config, null, 2) : '');
      setError(null);
    }
  }, [open, editing]);

  const submit = async (): Promise<void> => {
    let parsedConfig: Record<string, unknown> | undefined;
    if (oauthConfig.trim()) {
      try {
        parsedConfig = JSON.parse(oauthConfig) as Record<string, unknown>;
      } catch {
        setError('oauth_config is not valid JSON.');
        return;
      }
    }

    if (isEdit) {
      const input: ConnectorEditInput = { display_name: displayName, protocol: protocol as ConnectorRecord['protocol'], enabled };
      if (parsedConfig) input.oauth_config = parsedConfig;
      await update.mutateAsync(input);
    } else {
      const input: ConnectorRecord = {
        id: id.trim(),
        display_name: displayName,
        protocol: protocol as ConnectorRecord['protocol'],
        enabled,
        ...(parsedConfig ? { oauth_config: parsedConfig } : {}),
      };
      await create.mutateAsync(input);
    }
    onOpenChange(false);
  };

  const canSubmit = (isEdit || id.trim().length > 0) && displayName.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${editing?.display_name}` : 'Add connector'}</DialogTitle>
          <DialogDescription>External OAuth / API-key service the agents can call.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="conn-id">
              Connector ID <span className="text-destructive">*</span>
            </Label>
            <Input
              id="conn-id"
              placeholder="e.g. github"
              disabled={isEdit}
              value={id}
              onChange={(event) => setId(event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="conn-name">
              Display name <span className="text-destructive">*</span>
            </Label>
            <Input id="conn-name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>Protocol</Label>
            <Select value={protocol} onValueChange={setProtocol}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROTOCOLS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <label className="flex items-center justify-between text-sm">
            Enabled
            <Switch checked={enabled} aria-label="Enabled" onCheckedChange={setEnabled} />
          </label>
          <div className="grid gap-2">
            <Label htmlFor="conn-config">OAuth config (JSON, optional)</Label>
            <Textarea
              id="conn-config"
              className="min-h-28 font-mono text-xs"
              placeholder='{"authorize_url": "...", "client_id": "..."}'
              value={oauthConfig}
              onChange={(event) => setOauthConfig(event.target.value)}
            />
          </div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!canSubmit || create.isPending || update.isPending} onClick={() => void submit()}>
            {isEdit ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── API-key credential dialog ───────────────────────────

function CredentialDialog({
  connectorId,
  onOpenChange,
}: {
  connectorId: string | null;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  const setCredential = useConnectorCredentialsMutation(connectorId ?? '');
  const [apiKey, setApiKey] = useState('');

  useEffect(() => {
    if (connectorId) setApiKey('');
  }, [connectorId]);

  return (
    <Dialog open={Boolean(connectorId)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Set API key · {connectorId}</DialogTitle>
          <DialogDescription>The key is encrypted and bound to your own session user.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="conn-key">API key</Label>
          <Input
            id="conn-key"
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!apiKey || setCredential.isPending}
            onClick={async () => {
              await setCredential.mutateAsync({ api_key: apiKey });
              onOpenChange(false);
            }}
          >
            Submit
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Authorize action ───────────────────────────

function AuthorizeAction({ connectorId }: { connectorId: string }): JSX.Element {
  const [requested, setRequested] = useState(false);
  const authorize = useConnectorAuthorizeQuery(requested ? connectorId : null);

  useEffect(() => {
    if (authorize.data?.authorize_url) {
      window.open(authorize.data.authorize_url, '_blank', 'noopener');
      setRequested(false);
    }
  }, [authorize.data]);

  return (
    <DropdownMenuItem onSelect={() => setRequested(true)}>
      <ExternalLink /> Authorize
    </DropdownMenuItem>
  );
}

// ─────────────────────────── Connector row ───────────────────────────

function ConnectorRow({
  connector,
  onEdit,
  onSetCredential,
}: {
  connector: ConnectorRecord;
  onEdit: () => void;
  onSetCredential: () => void;
}): JSX.Element {
  const test = useConnectorTestMutation(connector.id);
  const remove = useDeleteConnectorMutation(connector.id);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30">
      <td className="px-4 py-3 font-mono text-sm text-foreground">{connector.id}</td>
      <td className="px-4 py-3 text-sm text-foreground">{connector.display_name}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{connector.protocol}</td>
      <td className="px-4 py-3">
        <Badge variant={connector.enabled ? 'success' : 'secondary'}>
          {connector.enabled ? 'enabled' : 'disabled'}
        </Badge>
        {test.data ? (
          <span className="ml-2 text-xs text-muted-foreground">
            {test.data.success ? (test.data.token_valid ? 'token valid' : 'reachable') : test.data.error ?? 'failed'}
          </span>
        ) : null}
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" aria-label={`Actions for ${connector.id}`}>
              Actions
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setTimeout(onEdit, 0)}>Edit</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void test.mutateAsync()}>Test connection</DropdownMenuItem>
            {connector.protocol === 'oauth2' ? <AuthorizeAction connectorId={connector.id} /> : null}
            {connector.protocol === 'apikey' ? (
              <DropdownMenuItem onSelect={() => setTimeout(onSetCredential, 0)}>
                <KeyRound /> Set API key
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={() => setTimeout(() => setConfirmDelete(true), 0)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete {connector.id}?</AlertDialogTitle>
              <AlertDialogDescription>This removes the connector configuration.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => void remove.mutateAsync()}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </td>
    </tr>
  );
}

// ─────────────────────────── Authorization matrix ───────────────────────────

function GrantRow({ grant }: { grant: ConnectorGrant }): JSX.Element {
  const revoke = useRevokeConnectorGrantMutation(grant.user_id, grant.connector_id);
  return (
    <tr className="border-b border-border last:border-0">
      <td className="px-4 py-2.5 font-mono text-sm text-foreground">{grant.user_id}</td>
      <td className="px-4 py-2.5 text-sm text-muted-foreground">{grant.connector_id}</td>
      <td className="px-4 py-2.5">
        <Badge variant={grantStatusVariant(grant.status)}>{grant.status}</Badge>
      </td>
      <td className="px-4 py-2.5 text-right">
        <Button size="sm" variant="ghost" onClick={() => void revoke.mutateAsync()}>
          Revoke
        </Button>
      </td>
    </tr>
  );
}

function AuthorizationMatrix(): JSX.Element {
  const grants = useConnectorGrantsQuery();
  const [offboardId, setOffboardId] = useState('');
  const [offboardTarget, setOffboardTarget] = useState<string | null>(null);
  const offboarding = useOffboardingQuery(offboardTarget);

  return (
    <Card className="border-none bg-transparent shadow-none">
      <CardHeader className="px-0">
        <CardTitle>Authorization matrix</CardTitle>
        <p className="text-sm text-muted-foreground">{grants.data?.consent_hint}</p>
      </CardHeader>
      <CardContent className="space-y-4 px-0">
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full">
            <thead className="bg-secondary/50">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">User</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Connector</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(grants.data?.grants ?? []).map((grant) => (
                <GrantRow key={`${grant.user_id}:${grant.connector_id}`} grant={grant} />
              ))}
              {grants.data && grants.data.grants.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
                      <Inbox className="size-6 opacity-50" />
                      <span className="text-sm">No grants</span>
                    </div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <Separator />

        <div className="space-y-2">
          <Label className="text-sm font-semibold text-foreground">Offboarding</Label>
          <div className="flex items-center gap-2">
            <Input
              className="max-w-xs"
              placeholder="user-id"
              value={offboardId}
              onChange={(event) => setOffboardId(event.target.value)}
            />
            <Button variant="secondary" onClick={() => setOffboardTarget(offboardId.trim() || null)}>
              Load offboarding summary
            </Button>
          </div>
          {offboarding.data ? (
            <p className="text-sm text-muted-foreground">
              Revoked: {offboarding.data.revoked.join(', ') || '—'} · Failed:{' '}
              {offboarding.data.failed.join(', ') || '—'}
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────── Page ───────────────────────────

export function ConnectorsPage(): JSX.Element {
  const connectors = useConnectorsQuery();
  const [query, setQuery] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ConnectorRecord | null>(null);
  const [credentialFor, setCredentialFor] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const list = connectors.data ?? [];
    if (!term) return list;
    return list.filter(
      (connector) =>
        connector.id.toLowerCase().includes(term) || connector.display_name.toLowerCase().includes(term)
    );
  }, [connectors.data, query]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Connector</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          External OAuth / API-key services and the per-user authorization matrix.
        </p>
      </div>

      <Tabs defaultValue="connectors">
        <TabsList className="flex w-full flex-wrap justify-start">
          <TabsTrigger value="connectors">Connectors</TabsTrigger>
          <TabsTrigger value="grants">Grants matrix</TabsTrigger>
        </TabsList>

        <TabsContent value="connectors" className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <Input
              className="max-w-xs"
              placeholder="Search connectors…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <Button
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              <Plus className="size-4" /> Add connector
            </Button>
          </div>

          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full">
              <thead className="bg-secondary/50">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">ID</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Name</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Protocol</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((connector) => (
                  <ConnectorRow
                    key={connector.id}
                    connector={connector}
                    onEdit={() => {
                      setEditing(connector);
                      setDialogOpen(true);
                    }}
                    onSetCredential={() => setCredentialFor(connector.id)}
                  />
                ))}
                {connectors.data && filtered.length === 0 ? (
                  <tr>
                    <td colSpan={5}>
                      <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
                        <Inbox className="size-6 opacity-50" />
                        <span className="text-sm">{query ? 'No matching connectors.' : 'No connectors'}</span>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </TabsContent>

        <TabsContent value="grants">
          <AuthorizationMatrix />
        </TabsContent>
      </Tabs>

      <ConnectorDialog open={dialogOpen} editing={editing} onOpenChange={setDialogOpen} />
      <CredentialDialog connectorId={credentialFor} onOpenChange={(open) => !open && setCredentialFor(null)} />
    </div>
  );
}
